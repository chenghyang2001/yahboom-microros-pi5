#!/usr/bin/env python3
"""cmd_vel 限速節點（M4 光達演練用）。

為什麼需要這個節點：
    Yahboom 官方光達程式（laser_Avoidance / laser_Tracker / laser_Warning / patrol）
    內部用 PID 算速度，輸出沒有上限，追蹤或避障時常常一下衝到 0.9 m/s 以上，
    在室內演練很容易撞到東西。所以演練時讓官方程式用
        --ros-args -r cmd_vel:=cmd_vel_raw -r /cmd_vel:=/cmd_vel_raw
    改名把速度送到 /cmd_vel_raw，再由本節點限幅後才發布到 /cmd_vel 給底盤。

演練安全上限：linear 0.15 m/s、angular 0.8 rad/s（可用 ROS 參數調整）。

執行環境：小車 ROS 2 Humble Docker 容器（Python 3.10、rclpy、geometry_msgs）。
    ros2 run 以外也可直接：python3 cmd_vel_limiter.py
    參數範例：python3 cmd_vel_limiter.py --ros-args -p max_linear:=0.1

本機自我測試（不需要 rclpy，Windows 也可跑）：
    PYTHONUTF8=1 python cmd_vel_limiter.py --selftest
"""
import math
import signal
import sys

# 看門狗逾時：上游程式當掉或被 Ctrl+C 時，最後一筆速度會一直留在底盤上，
# 0.5 秒沒新訊息就補一筆零速度讓車停下
WATCHDOG_TIMEOUT_SEC = 0.5
WATCHDOG_PERIOD_SEC = 0.1
# 限速 log 節流：PID 每秒送幾十筆，每筆都印會洗版
CLAMP_LOG_INTERVAL_SEC = 1.0
DEFAULT_MAX_LINEAR = 0.15
DEFAULT_MAX_ANGULAR = 0.8


def _sanitize(value):
    """NaN / inf 一律當 0，避免把無效值送進底盤造成暴衝。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _clamp(value, limit):
    """把 value 夾在 ±limit；limit 為負或無效時視為 0（寧可不動也不要失控）。"""
    safe_limit = abs(_sanitize(limit))
    return max(-safe_limit, min(safe_limit, _sanitize(value)))


def clamp_twist_values(lx, ly, az, max_lin, max_ang):
    """限幅純函式（不依賴 rclpy，方便本機測試）。

    linear.x、linear.y 各自夾在 ±max_lin；angular.z 夾在 ±max_ang。
    麥克納姆輪會用到 linear.y 橫移，所以兩軸分開限制。

    回傳 (lx, ly, az) 限幅後的 tuple。
    """
    return (
        _clamp(lx, max_lin),
        _clamp(ly, max_lin),
        _clamp(az, max_ang),
    )


def run_selftest():
    """只測純函式，不 import rclpy。"""
    # 1. 正常值在範圍內：不變
    assert clamp_twist_values(0.1, -0.05, 0.5, 0.15, 0.8) == (0.1, -0.05, 0.5)
    # 2. 超上限：被夾到上限
    assert clamp_twist_values(0.92, 0.3, 1.3, 0.15, 0.8) == (0.15, 0.15, 0.8)
    # 3. 負向超限：被夾到負上限
    assert clamp_twist_values(-0.92, -0.3, -1.3, 0.15, 0.8) == (-0.15, -0.15, -0.8)
    # 4. NaN / inf：一律變 0
    assert clamp_twist_values(float("nan"), float("inf"), float("-inf"), 0.15, 0.8) == (0.0, 0.0, 0.0)
    # 5. 邊界值剛好等於上限：不變
    assert clamp_twist_values(0.15, -0.15, 0.8, 0.15, 0.8) == (0.15, -0.15, 0.8)
    # 6. 上限參數本身是 NaN：視為 0，車子不動
    assert clamp_twist_values(0.1, 0.1, 0.5, float("nan"), float("nan")) == (0.0, 0.0, 0.0)
    print("selftest OK")


def main():
    """啟動 ROS 2 節點。rclpy 只在這裡 import，讓 --selftest 在無 ROS 的機器也能跑。"""
    try:
        import rclpy
        from rclpy.node import Node
        from geometry_msgs.msg import Twist
    except ImportError as exc:
        print(f"錯誤：找不到 rclpy / geometry_msgs（請在小車 ROS 2 容器內執行）：{exc}", file=sys.stderr)
        sys.exit(1)

    class CmdVelLimiter(Node):
        """訂閱 /cmd_vel_raw，限幅後發布到 /cmd_vel。"""

        def __init__(self):
            super().__init__("cmd_vel_limiter")
            self.declare_parameter("max_linear", DEFAULT_MAX_LINEAR)
            self.declare_parameter("max_angular", DEFAULT_MAX_ANGULAR)
            self.publisher = self.create_publisher(Twist, "/cmd_vel", 10)
            self.subscription = self.create_subscription(Twist, "/cmd_vel_raw", self.on_raw_cmd, 10)
            self.last_raw_time = None
            # 看門狗只送一次零速度，避免一直洗 /cmd_vel 蓋掉手動遙控
            self.is_watchdog_stopped = True
            self.last_clamp_log_time = None
            self.timer = self.create_timer(WATCHDOG_PERIOD_SEC, self.on_watchdog)
            max_lin, max_ang = self.read_limits()
            self.get_logger().info(
                f"限速節點啟動：/cmd_vel_raw → /cmd_vel，max_linear={max_lin:.2f}, "
                f"max_angular={max_ang:.2f}，看門狗 {WATCHDOG_TIMEOUT_SEC} 秒"
            )

        def now_sec(self):
            return self.get_clock().now().nanoseconds / 1e9

        def read_limits(self):
            # 每次重讀，演練中用 ros2 param set 調整能立刻生效
            max_lin = self.get_parameter("max_linear").get_parameter_value().double_value
            max_ang = self.get_parameter("max_angular").get_parameter_value().double_value
            return max_lin, max_ang

        def on_raw_cmd(self, raw_msg):
            max_lin, max_ang = self.read_limits()
            raw_lx = _sanitize(raw_msg.linear.x)
            raw_ly = _sanitize(raw_msg.linear.y)
            raw_az = _sanitize(raw_msg.angular.z)
            lx, ly, az = clamp_twist_values(raw_lx, raw_ly, raw_az, max_lin, max_ang)

            out_msg = Twist()  # 其他分量預設 0
            out_msg.linear.x = lx
            out_msg.linear.y = ly
            out_msg.angular.z = az
            self.publisher.publish(out_msg)

            self.last_raw_time = self.now_sec()
            self.is_watchdog_stopped = False
            if (raw_lx, raw_ly, raw_az) != (lx, ly, az):
                self.log_clamp(raw_lx, raw_ly, raw_az, lx, ly, az)

        def log_clamp(self, raw_lx, raw_ly, raw_az, lx, ly, az):
            now = self.now_sec()
            if self.last_clamp_log_time is not None and now - self.last_clamp_log_time < CLAMP_LOG_INTERVAL_SEC:
                return
            self.last_clamp_log_time = now
            raw_lin = math.hypot(raw_lx, raw_ly)
            out_lin = math.hypot(lx, ly)
            self.get_logger().info(
                f"限速：linear {raw_lin:.2f}→{out_lin:.2f}, angular {abs(raw_az):.2f}→{abs(az):.2f}"
            )

        def on_watchdog(self):
            if self.is_watchdog_stopped or self.last_raw_time is None:
                return
            if self.now_sec() - self.last_raw_time > WATCHDOG_TIMEOUT_SEC:
                self.publish_stop()
                self.is_watchdog_stopped = True
                self.get_logger().warn(f"看門狗：{WATCHDOG_TIMEOUT_SEC} 秒沒收到 /cmd_vel_raw，已送零速度")

        def publish_stop(self):
            self.publisher.publish(Twist())

    # rclpy 預設的訊號處理會在 Ctrl+C／SIGTERM 時先關掉 context，之後 publish 會失敗、
    # 零速度送不出去。所以關掉內建處理，SIGTERM 自己轉成 KeyboardInterrupt，
    # SIGINT 用 Python 預設行為（本來就丟 KeyboardInterrupt），context 保持可用直到 finally。
    def raise_keyboard_interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, raise_keyboard_interrupt)
    try:
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(args=sys.argv, signal_handler_options=SignalHandlerOptions.NO)
    except ImportError:
        # 舊版 rclpy 沒有 SignalHandlerOptions，退回預設
        rclpy.init(args=sys.argv)
    node = None
    try:
        node = CmdVelLimiter()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass  # Ctrl+C 是正常結束，不印 traceback
    except Exception as exc:  # 非預期錯誤也要先停車再離開
        print(f"錯誤：cmd_vel_limiter 異常結束：{exc}", file=sys.stderr)
    finally:
        if node is not None:
            try:
                # 結束前一定送零速度，避免底盤停在最後一筆速度
                node.publish_stop()
                node.get_logger().info("限速節點結束，已送零速度")
                node.destroy_node()
            except Exception as exc:
                print(f"警告：結束時送零速度失敗：{exc}", file=sys.stderr)
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        run_selftest()
    else:
        main()
