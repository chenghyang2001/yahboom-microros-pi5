#!/usr/bin/env python3
"""雲台守門員節點（M3 視覺演練用）。

為什麼需要這個節點：
    Yahboom 官方視覺程式（colorTracker / face_fllow / follow_line / HandCtrl）的雲台邏輯
    以 0 當正中、範圍 -90～90，直接送到 /servo_s1、/servo_s2。但這台車：
      - S2（上下）送 -10 就扯斷過相機線，絕對不能用指令動 → 一律攔下、不轉發。
      - S1（左右）實體正前方是 -30，官方的 0 會讓鏡頭歪掉；也只准在正前方 ±10 度內動。
    所以演練時讓官方程式用
        --ros-args -r servo_s1:=servo_s1_raw -r servo_s2:=servo_s2_raw
    改名，由本節點把 S1 換算、限幅、限速後才發布到 /servo_s1；S2 只記 log 不轉發。

使用範例（小車 ROS 2 Humble Docker 容器內）：
    python3 servo_guard.py
    ros2 run yahboomcar_astra colorTracker --ros-args -r servo_s1:=servo_s1_raw -r servo_s2:=servo_s2_raw -r /cmd_vel:=/cmd_vel_raw
本機自我測試（不需要 rclpy，Windows 也可跑）：
    PYTHONUTF8=1 python servo_guard.py --selftest
"""
import math
import signal
import sys

DEFAULT_CENTER = -30
DEFAULT_RANGE = 10
# 官方 PID 一下可能要求 90 度，一筆就甩過去會扯到線，每筆最多走幾度
DEFAULT_MAX_STEP = 3
# 官方程式每秒送幾十筆，每筆都印會洗版
LOG_INTERVAL_SEC = 1.0
# 剛建立的 publisher 還沒跟底盤節點配對，立刻 publish 會掉包，延遲一下再送回正
STARTUP_CENTER_DELAY_SEC = 0.5


def to_int(value):
    """轉成 int；NaN、inf、帶小數、非數字一律回 None，讓呼叫端忽略這筆。"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def clamp(value, limit):
    """夾在 ±limit；limit 取絕對值，負數參數不會讓範圍反轉。"""
    safe_limit = abs(limit)
    return max(-safe_limit, min(safe_limit, value))


def map_s1(raw, center, range_deg):
    """官方以 0 為正中的角度 → 實體角度，且只准在 center ±range_deg 內。"""
    return center + clamp(raw, range_deg)


def step_limit(target, last, max_step):
    """每筆最多比上一筆變化 max_step 度；還沒送過（last 為 None）就直接到位。"""
    if last is None:
        return target
    return last + clamp(target - last, max_step)


def run_selftest():
    """只測純函式，不 import rclpy。"""
    # map_s1：正常值在範圍內、負向在範圍內
    assert map_s1(5, -30, 10) == -25 and map_s1(0, -30, 10) == -30 and map_s1(-7, -30, 10) == -37
    # 超出範圍被夾（正向、負向）
    assert map_s1(90, -30, 10) == -20 and map_s1(-90, -30, 10) == -40
    # range 為 0：永遠停在正前方；range 負數視同正數
    assert map_s1(45, -30, 0) == -30 and map_s1(45, -30, -10) == -20
    # step_limit：小變化直接到、正向與負向都被限制、last 為 None 直接回 target
    assert step_limit(-29, -30, 3) == -29 and step_limit(-20, None, 3) == -20
    assert step_limit(-20, -30, 3) == -27 and step_limit(-40, -30, 3) == -33
    assert to_int(5) == 5 and to_int(5.0) == 5
    assert to_int(float("nan")) is None and to_int(float("inf")) is None
    assert to_int(3.5) is None and to_int("10") is None and to_int(True) is None
    print("selftest OK")


def main():
    """啟動 ROS 2 節點。rclpy 只在這裡 import，讓 --selftest 在無 ROS 的機器也能跑。"""
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import Int32
    except ImportError as exc:
        print(f"錯誤：找不到 rclpy / std_msgs（請在小車 ROS 2 容器內執行）：{exc}", file=sys.stderr)
        sys.exit(1)

    class ServoGuard(Node):
        """S1：換算＋限幅＋限速後轉發；S2：攔下不轉發（刻意不建 /servo_s2 publisher）。"""

        def __init__(self):
            super().__init__("servo_guard")
            self.declare_parameter("center", DEFAULT_CENTER)
            self.declare_parameter("range", DEFAULT_RANGE)
            self.declare_parameter("max_step", DEFAULT_MAX_STEP)
            self.s1_publisher = self.create_publisher(Int32, "/servo_s1", 10)
            self.create_subscription(Int32, "/servo_s1_raw", self.on_s1_raw, 10)
            self.create_subscription(Int32, "/servo_s2_raw", self.on_s2_raw, 10)
            self.last_out = None
            self.last_log_time = {"s1": None, "s2": None}
            self.startup_timer = self.create_timer(STARTUP_CENTER_DELAY_SEC, self.on_startup)
            center, range_deg, max_step = self.read_params()
            self.get_logger().info(
                f"雲台守門員啟動：/servo_s1_raw → /servo_s1（center={center}, range=±{range_deg}, "
                f"max_step={max_step}），/servo_s2_raw 一律攔下"
            )

        def read_param(self, name, default):
            # ros2 param set 可能被設成 double 或字串，轉不成整數就退回預設值
            value = to_int(self.get_parameter(name).value)
            return default if value is None else value

        def read_params(self):
            # 每次重讀，演練中 ros2 param set 能立刻生效
            return (
                self.read_param("center", DEFAULT_CENTER),
                self.read_param("range", DEFAULT_RANGE),
                self.read_param("max_step", DEFAULT_MAX_STEP),
            )

        def should_log(self, key):
            now = self.get_clock().now().nanoseconds / 1e9
            last = self.last_log_time[key]
            if last is not None and now - last < LOG_INTERVAL_SEC:
                return False
            self.last_log_time[key] = now
            return True

        def publish_s1(self, angle):
            self.s1_publisher.publish(Int32(data=int(angle)))
            self.last_out = angle

        def publish_center(self):
            center = self.read_params()[0]
            self.publish_s1(center)
            return center

        def on_startup(self):
            self.startup_timer.cancel()  # 只送一次
            self.get_logger().info(f"啟動回正：S1 = {self.publish_center()}（鏡頭朝正前方）")

        def on_s1_raw(self, msg):
            raw = to_int(msg.data)
            if raw is None:
                self.get_logger().warn(f"S1 收到異常值 {msg.data!r}，已忽略")
                return
            center, range_deg, max_step = self.read_params()
            out = step_limit(map_s1(raw, center, range_deg), self.last_out, max_step)
            if out != self.last_out:
                self.publish_s1(out)
            if self.should_log("s1"):
                note = "（已限幅）" if out != center + raw else ""
                self.get_logger().info(f"S1 要求 {raw} → 送出 {out}{note}")

        def on_s2_raw(self, msg):
            raw = to_int(msg.data)
            if raw is None:
                self.get_logger().warn(f"S2 收到異常值 {msg.data!r}，已忽略")
                return
            if self.should_log("s2"):
                self.get_logger().info(f"S2 要求 {raw} → 已攔下（S2 禁止用指令動）")

    # rclpy 預設的訊號處理會在 Ctrl+C／SIGTERM 時先關掉 context，之後 publish 會失敗、
    # 回正送不出去。所以關掉內建處理，SIGTERM 自己轉成 KeyboardInterrupt。
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
        node = ServoGuard()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass  # Ctrl+C 是正常結束，不印 traceback
    except Exception as exc:  # 非預期錯誤也要先回正再離開
        print(f"錯誤：servo_guard 異常結束：{exc}", file=sys.stderr)
    finally:
        if node is not None:
            try:
                # 結束前讓鏡頭回正前方，下一個程式接手時才不會歪著
                center = node.publish_center()
                node.get_logger().info(f"雲台守門員結束，S1 已回正 {center}")
                node.destroy_node()
            except Exception as exc:
                print(f"警告：結束時回正失敗：{exc}", file=sys.stderr)
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        run_selftest()
    else:
        main()
