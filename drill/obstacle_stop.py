"""前方有障礙就停車、沒有就前進的第一個控制節點。

訂閱 /scan（sensor_msgs/LaserScan），發布 /cmd_vel（geometry_msgs/Twist）。
"""
import math

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan


class ObstacleStop(Node):
    def __init__(self):
        super().__init__('obstacle_stop')

        # 參數：執行中可用 ros2 param set 修改，每次計時器觸發都重新讀取
        self.declare_parameter('stop_distance', 0.3)     # 公尺，比這近就停
        self.declare_parameter('resume_margin', 0.05)    # 公尺，要退到 stop_distance + 這個值才再走
        self.declare_parameter('forward_speed', 0.1)     # 公尺/秒，前進速度
        self.declare_parameter('front_angle_deg', 15.0)  # 度，只看正前方左右各幾度
        self.declare_parameter('angle_offset_deg', 0.0)  # 度，光達裝歪或零度不在正前方時用來修正
        self.declare_parameter('scan_timeout', 0.5)      # 秒，超過這麼久沒收到 /scan 就停車

        # 光達資料常用「盡力傳送」QoS，用 sensor_data 設定才收得到兩種發布者
        self.sub_scan = self.create_subscription(
            LaserScan, '/scan', self.scan_callback, qos_profile_sensor_data)
        self.pub_vel = self.create_publisher(Twist, '/cmd_vel', 10)

        self.front_min = math.inf        # 前方扇形內最近距離
        self.last_scan_time = None       # 最後一次收到 /scan 的時間
        self.blocked = False             # 目前是否判定「被擋住」
        self.timer = self.create_timer(0.1, self.control_loop)  # 10 Hz 送速度
        self.get_logger().info('obstacle_stop 已啟動，等待 /scan ...')

    def scan_callback(self, msg):
        """從一整圈資料中，找出正前方扇形內的最近距離。"""
        front_angle = math.radians(self.get_parameter('front_angle_deg').value)
        offset = math.radians(self.get_parameter('angle_offset_deg').value)
        nearest = math.inf
        for i, distance in enumerate(msg.ranges):
            # 無效值：inf、nan、0，或超出光達量測範圍，一律跳過
            if not math.isfinite(distance) or distance <= 0.0:
                continue
            if distance < msg.range_min or distance > msg.range_max:
                continue
            angle = msg.angle_min + msg.angle_increment * i - offset
            # 角度壓到 -pi ~ +pi，0 代表正前方、正值在左邊
            angle = math.atan2(math.sin(angle), math.cos(angle))
            if abs(angle) <= front_angle and distance < nearest:
                nearest = distance
        self.front_min = nearest
        self.last_scan_time = self.get_clock().now()

    def control_loop(self):
        """每 0.1 秒決定一次要停還是要走。"""
        stop_distance = self.get_parameter('stop_distance').value
        resume_margin = self.get_parameter('resume_margin').value
        forward_speed = self.get_parameter('forward_speed').value
        scan_timeout = self.get_parameter('scan_timeout').value

        cmd = Twist()
        if self.last_scan_time is None:
            self.pub_vel.publish(cmd)  # 還沒收到光達：原地不動
            return
        age = (self.get_clock().now() - self.last_scan_time).nanoseconds / 1e9
        if age > scan_timeout:
            self.get_logger().warn('超過 %.1f 秒沒收到 /scan，先停車' % age,
                                   throttle_duration_sec=2.0)
            self.pub_vel.publish(cmd)
            return

        # 遲滯：停下來之後，要離開到更遠一點才重新出發，避免在邊界抖動
        if self.blocked:
            if self.front_min > stop_distance + resume_margin:
                self.blocked = False
                self.get_logger().info('前方淨空 %.2f m，繼續前進' % self.front_min)
        elif self.front_min < stop_distance:
            self.blocked = True
            self.get_logger().info('前方 %.2f m 有障礙，停車' % self.front_min)

        if not self.blocked:
            cmd.linear.x = float(forward_speed)
        self.pub_vel.publish(cmd)

    def stop_robot(self):
        """結束前送一個零速度，讓車停下來。"""
        self.pub_vel.publish(Twist())


def init_ros(args):
    """關掉 rclpy 自帶的 Ctrl+C 處理，按 Ctrl+C 時才來得及送出停車指令。"""
    try:
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    except ImportError:
        rclpy.init(args=args)


def main(args=None):
    init_ros(args)
    node = ObstacleStop()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if rclpy.ok():
            node.stop_robot()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
