"""依 /odom 回饋沿路線行駛（示範 SLAM 建圖用）"""
import math
import sys
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry

ROUTE = [(1.0, 0.9), (2.6, 0.9), (2.6, 2.3), "spin", (2.6, 0.9), (3.5, 0.2), "spin",
         (2.6, 0.9), (1.0, 0.9), (0.6, -0.3), (0.6, -2.3), "spin", (0.0, -0.3),
         (-1.5, -0.2), (-3.2, -0.2), "spin", (-1.4, 0.0), (-1.4, 2.2), (-3.2, 2.2), "spin", (0.0, 0.0)]


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class RouteDriver(Node):
    def __init__(self):
        super().__init__("route_driver")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.pose = None
        self.create_subscription(Odometry, "/odom", self.on_odom, 10)

    def on_odom(self, msg):
        q = msg.pose.pose.orientation
        yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.pose = (msg.pose.pose.position.x, msg.pose.pose.position.y, yaw)

    def send(self, v, w):
        t = Twist()
        t.linear.x, t.angular.z = float(v), float(w)
        self.pub.publish(t)

    def tick(self):
        rclpy.spin_once(self, timeout_sec=0.05)

    def go(self, gx, gy, timeout=120.0):
        start = time.time()
        turning = True
        while time.time() - start < timeout:
            self.tick()
            x, y, yaw = self.pose
            dist = math.hypot(gx - x, gy - y)
            if dist < 0.08:
                break
            err = wrap(math.atan2(gy - y, gx - x) - yaw)
            if turning and abs(err) < 0.08:
                turning = False
            if not turning and abs(err) > 0.6:
                turning = True
            if turning:
                self.send(0.0, max(-0.7, min(0.7, 1.8 * err)))
            else:
                self.send(min(0.22, 0.8 * dist), max(-0.8, min(0.8, 2.0 * err)))
        self.send(0, 0)
        print(f"  到達 ({gx:+.1f}, {gy:+.1f})", flush=True)

    def spin(self):
        total, last = 0.0, self.pose[2]
        while total < 2 * math.pi - 0.05:
            self.tick()
            yaw = self.pose[2]
            total += abs(wrap(yaw - last))
            last = yaw
            self.send(0.0, 0.6)
        self.send(0, 0)
        print("  原地轉一圈，讓光達看清四周", flush=True)


def main():
    rclpy.init()
    node = RouteDriver()
    try:
        while node.pose is None:
            node.tick()
        for step in ROUTE:
            if step == "spin":
                node.spin()
            else:
                node.go(*step)
        print("路線完成", flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"錯誤：{e}", file=sys.stderr)
    finally:
        node.send(0, 0)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
