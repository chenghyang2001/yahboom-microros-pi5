"""monitor.py — Yahboom MicroROS-Pi5 即時車況儀表板（在車上 ROS 2 Humble 容器內執行）

這支不在筆電上跑，而是由 ycar.py 透過 stdin 送進車上容器執行：
  PYTHONUTF8=1 python ycar.py rospy monitor.py --timeout 7200

只訂閱、不發布任何話題，所以不會讓車動或叫。
每 0.5 秒清畫面重印一次，寬度 ≤ 60 欄，適合放在半個螢幕的終端機。
Ctrl+C（或 SIGTERM / SIGINT）乾淨結束。
"""
import math
import signal
import sys
import time
import unicodedata
from collections import deque

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import Int32, UInt16
except ImportError as exc:
    print(f"錯誤：載入 ROS 2 套件失敗（要在已 source humble 的容器內執行）：{exc}", file=sys.stderr)
    sys.exit(1)

REFRESH_SEC = 0.5
CMD_STALE_SEC = 1.0  # 超過 1 秒沒收到 /cmd_vel 就視為沒有指令
MOVING_V = 0.01
MOVING_W = 0.02
LIDAR_HALF_DEG = 10.0
MAX_WIDTH = 60
CLEAR = "\033[H\033[2J"
# 光達四個方向（ROS 慣例：0 前、+90 左、-90 右、180 後）
LIDAR_DIRS = (("前", 0.0), ("左", 90.0), ("右", -90.0), ("後", 180.0))


def display_width(text):
    """中文字在終端機佔 2 欄，用來確保每行不超過 60 欄"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def fit_width(text, limit=MAX_WIDTH):
    """超過寬度就截斷，避免半螢幕終端機自動換行把版面打亂"""
    out, width = [], 0
    for ch in text:
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > limit:
            break
        out.append(ch)
        width += w
    return "".join(out)


def is_valid_range(r, scan):
    """光達無效值（inf/nan/0 或超出量程）要略過"""
    if not math.isfinite(r) or r <= 0.0:
        return False
    if scan.range_min > 0.0 and r < scan.range_min:
        return False
    if scan.range_max > 0.0 and r > scan.range_max:
        return False
    return True


def sector_min(scan, center_deg, half_deg=LIDAR_HALF_DEG):
    """取 center_deg ±half_deg 內的最小有效距離；依 angle_min/angle_increment 換算索引"""
    count = len(scan.ranges)
    inc = scan.angle_increment
    if count == 0 or inc == 0.0:
        return None
    if inc < 0:  # 少數驅動逆時針排列，統一成正方向處理
        inc = -inc
    full_circle = count * inc >= 2 * math.pi - 2 * inc
    offset = (math.radians(center_deg) - scan.angle_min) % (2 * math.pi)
    center_idx = int(round(offset / inc))
    half_steps = max(1, int(round(math.radians(half_deg) / inc)))
    best = None
    for k in range(center_idx - half_steps, center_idx + half_steps + 1):
        if full_circle:
            k %= count  # 360° 光達在 ±180° 接縫處要繞回去
        elif not 0 <= k < count:
            continue
        r = scan.ranges[k]
        if is_valid_range(r, scan) and (best is None or r < best):
            best = r
    return best


class CarMonitor(Node):
    """訂閱車況話題並定時重繪儀表板"""

    def __init__(self):
        super().__init__("ycar_monitor")
        self.battery_raw = None
        self.cmd_vel = None
        self.cmd_time = 0.0
        self.odom = None
        self.servo_s1 = None
        self.servo_s2 = None
        self.scan = None
        self.scan_stamps = deque(maxlen=200)
        # /scan、/odom_raw 是高頻感測資料，用 sensor_data QoS（best effort）才收得到
        self.create_subscription(Odometry, "/odom_raw", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan", self.on_scan, qos_profile_sensor_data)
        self.create_subscription(UInt16, "/battery", self.on_battery, 10)
        self.create_subscription(Twist, "/cmd_vel", self.on_cmd_vel, 10)
        self.create_subscription(Int32, "/servo_s1", self.on_servo_s1, 10)
        self.create_subscription(Int32, "/servo_s2", self.on_servo_s2, 10)
        self.create_timer(REFRESH_SEC, self.render)

    def on_odom(self, msg):
        self.odom = msg

    def on_scan(self, msg):
        self.scan = msg
        self.scan_stamps.append(time.monotonic())

    def on_battery(self, msg):
        self.battery_raw = msg.data

    def on_cmd_vel(self, msg):
        self.cmd_vel = msg
        self.cmd_time = time.monotonic()

    def on_servo_s1(self, msg):
        self.servo_s1 = msg.data

    def on_servo_s2(self, msg):
        self.servo_s2 = msg.data

    def scan_hz(self):
        """用最近 2 秒內收到的筆數估頻率，比 header 時間戳可靠（車上時鐘可能不準）"""
        now = time.monotonic()
        recent = [t for t in self.scan_stamps if now - t <= 2.0]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0

    def line_battery(self):
        if self.battery_raw is None:
            return " 電池      —（尚未收到 /battery）"
        # Yahboom 驅動板回報的是 0.1 V 為單位的整數（79 → 7.9 V）
        return f" 電池      {self.battery_raw / 10:.1f} V（原始值 {self.battery_raw}）"

    def line_cmd(self):
        if self.cmd_vel is None or time.monotonic() - self.cmd_time > CMD_STALE_SEC:
            return " 指令速度  —（無指令）"
        return (f" 指令速度  前進 {self.cmd_vel.linear.x:+.2f} m/s"
                f"  轉向 {self.cmd_vel.angular.z:+.2f} rad/s")

    def lines_odom(self):
        if self.odom is None:
            return [" 輪子回報  —（尚未收到 /odom_raw）", " 輪子狀態  —"]
        v = self.odom.twist.twist.linear.x
        w = self.odom.twist.twist.angular.z
        moving = abs(v) > MOVING_V or abs(w) > MOVING_W
        return [f" 輪子回報  前進 {v:+.2f} m/s  轉向 {w:+.2f} rad/s",
                " 輪子狀態  " + ("● 轉動中" if moving else "○ 靜止")]

    def line_servo(self):
        s1 = "—" if self.servo_s1 is None else f"{self.servo_s1:+3d}°"
        s2 = "—" if self.servo_s2 is None else f"{self.servo_s2:+3d}°"
        return f" 雲台      左右 s1 = {s1}   上下 s2 = {s2}"

    def lines_lidar(self):
        if self.scan is None:
            return [" 光達      —（尚未收到 /scan）"]
        parts = []
        for label, deg in LIDAR_DIRS:
            r = sector_min(self.scan, deg)
            parts.append(f"{label} {r:.2f} m" if r is not None else f"{label}  —  ")
        # 一行放四方向會超過 60 欄，拆成兩行
        return [f" 光達      {parts[0]}  {parts[1]}  {parts[2]}",
                f"           {parts[3]}  頻率 {self.scan_hz():.0f} Hz"]

    def render(self):
        lines = [" Yahboom MicroROS-Pi5 車況（每 0.5 秒更新）",
                 " " + "─" * 28,
                 self.line_battery(),
                 self.line_cmd(),
                 *self.lines_odom(),
                 self.line_servo(),
                 *self.lines_lidar(),
                 " " + "─" * 28,
                 f" {time.strftime('%H:%M:%S')}  Ctrl+C 結束"]
        sys.stdout.write(CLEAR + "\n".join(fit_width(line) for line in lines) + "\n")
        sys.stdout.flush()


def handle_stop_signal(signum, frame):
    """SIGTERM（timeout 結束時送的）也轉成 KeyboardInterrupt，走同一條收尾路徑"""
    raise KeyboardInterrupt


def self_test():
    """不需 ROS 資料的小檢查：所有預設行寬 ≤ 60、光達扇區計算正確"""
    class FakeScan:
        angle_min = -math.pi
        angle_increment = math.radians(1.0)
        range_min = 0.05
        range_max = 12.0
        ranges = [float("inf")] * 360
    scan = FakeScan()
    scan.ranges[180] = 0.85       # 0°（前）
    scan.ranges[185] = 0.0        # 無效值要略過
    scan.ranges[270] = 1.20       # +90°（左）
    scan.ranges[90] = 0.60        # -90°（右）
    scan.ranges[359] = 2.10       # 179°（後，接縫附近）
    assert abs(sector_min(scan, 0.0) - 0.85) < 1e-9
    assert abs(sector_min(scan, 90.0) - 1.20) < 1e-9
    assert abs(sector_min(scan, -90.0) - 0.60) < 1e-9
    assert abs(sector_min(scan, 180.0) - 2.10) < 1e-9
    sample = " 光達      前 0.85 m  左 1.20 m  右 0.60 m"
    assert display_width(sample) <= MAX_WIDTH, display_width(sample)


def main():
    signal.signal(signal.SIGTERM, handle_stop_signal)
    self_test()
    rclpy.init()
    node = CarMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # rclpy 在 shutdown 時偶爾丟 ExternalShutdownException
        print(f"\n錯誤：監看中斷：{type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print("\n[monitor] 已結束監看")


if __name__ == "__main__":
    main()
