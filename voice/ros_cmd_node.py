"""容器內的 ROS 2 指令節點：從 stdin 一行讀一個 JSON 指令，轉成 /beep、/cmd_vel、/servo_s1、/servo_s2 發布。

由 Pi 主機的 voice_agent.py 透過下列方式啟動（stdin/stdout 當作簡單的 IPC 管道）：
    docker exec -i <容器> bash -c 'source /opt/ros/humble/setup.bash; \
        export ROS_DOMAIN_ID=20; exec python3 -u /tmp/ros_cmd_node.py'

指令格式（每行一個 JSON）：
    {"action":"beep","ms":30000}
    {"action":"move","linear":0.1,"angular":0.0,"seconds":2}
    {"action":"drive","linear":0.1,"angular":0.0}   # 持續移動，直到 stop／新指令／30 秒／雷達防撞
    {"action":"stop"}                     # 只停車與蜂鳴器，不動雲台
    {"action":"gimbal","pan":45,"tilt":-30}   # 絕對角度（度）

回報：每處理一筆印 `ACK <json>`，錯誤印 `ERR <訊息>`；主機端逐行讀取。
自動停車時另外回報：
    ACK {"action":"move_done"}
    ACK {"action":"drive_done","reason":"timeout|obstacle|cancel"}
    ACK {"action":"obstacle_stop","dist":0.25}  或  {"action":"obstacle_stop","reason":"no_scan"}

自我測試（不需要 ROS）：python3 ros_cmd_node.py --selftest
只依賴 rclpy 與標準庫，方便直接 docker cp 進容器執行。
"""
import json
import math
import queue
import sys
import threading
import time
import types

# ── 雷達防撞設定（實車驗證後最可能要改的值，放最上面）──────────
# 車頭方向對應的雷達角度（度）。實測 /scan 為 -180°～180°、每 1° 一點；
# 若實測發現車頭其實在雷達的 180°，把這裡改成 180.0 即可（後退扇形會自動跟著轉）
FRONT_ANGLE_DEG = 0.0
SECTOR_HALF_DEG = 25.0      # 扇形半角：車寬約 ±25° 內的東西才會撞到
OBSTACLE_STOP_M = 0.30      # 扇形內最近距離小於這個值就停車
SCAN_STALE_SEC = 1.0        # 超過這麼久沒收到新 scan，視同雷達失效 → 停車（安全預設）

# 夾限值與 intent_proto.py／SPEC.md 一致；節點端再夾一次，避免主機端被繞過時車子暴衝
BEEP_MS_MIN, BEEP_MS_MAX = 0, 60000
LINEAR_MAX = 0.15
ANGULAR_MAX = 0.8
SECONDS_MIN, SECONDS_MAX = 0.5, 3.0
DRIVE_MAX_SEC = 30.0        # drive 的保底上限：就算一直沒聽到「停」也會自己停
# 雲台安全鐵律：/servo_s2 大於 0 會抬頭扯掉相機 USB 線，只准 -45（低頭到底）～0（平視）
PAN_MIN, PAN_MAX = -90, 90
TILT_MIN, TILT_MAX = -45, 0

# 底盤韌體約 0.5 秒沒收到 cmd_vel 就可能停下，0.1 秒重發確保移動連續
REPUBLISH_SEC = 0.1
STOP_REPEAT = 3

SUPPORTED_ACTIONS = ("beep", "move", "drive", "stop", "gimbal")

_EOF = object()  # stdin 結束的哨兵


def _clamp(value, low, high):
    return max(low, min(high, value))


def _finite_float(value, default=0.0):
    """轉成有限浮點數；NaN／inf／非數字一律回 default，避免送出怪值給底盤。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def emit(prefix, payload):
    """印一行回報給主機端；payload 為 dict 時轉 JSON。"""
    text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
    print(f"{prefix} {text}", flush=True)


# ── 雷達防撞純函式（不依賴 ROS，--selftest 直接測）──────────
def angle_diff_deg(a_deg, b_deg):
    """a - b 環繞到 [-180, 180)：讓 179° 與 -180° 被視為只差 1°。"""
    return (a_deg - b_deg + 180.0) % 360.0 - 180.0


def sector_min_distance(ranges, angle_min, angle_inc, center_deg, half_deg, range_min):
    """扇形（center_deg ± half_deg）內的最小有效距離；沒有任何有效點回 None。

    只採用有限且大於 range_min 的距離：0、inf、NaN 是雷達「沒測到」，不是障礙物。
    angle_min／angle_inc 為弧度（LaserScan 原始單位）。
    """
    nearest = None
    for index, distance in enumerate(ranges):
        if not math.isfinite(distance) or distance <= range_min:
            continue
        point_deg = math.degrees(angle_min + index * angle_inc)
        if abs(angle_diff_deg(point_deg, center_deg)) > half_deg:
            continue
        nearest = distance if nearest is None else min(nearest, distance)
    return nearest


def sector_center_deg(linear, front_deg=FRONT_ANGLE_DEG):
    """依行進方向決定要看的扇形中心；純轉向（linear == 0）不會撞到前後，回 None。"""
    if linear > 0:
        return front_deg
    if linear < 0:
        return front_deg + 180.0
    return None


def check_obstacle(linear, scan, scan_age, front_deg=FRONT_ANGLE_DEG):
    """回傳要 ACK 的 obstacle_stop dict；可以繼續走時回 None。

    scan：(ranges, angle_min, angle_inc, range_min) 或 None（從沒收到過）。
    scan_age：距離上次收到 scan 的秒數。
    """
    center = sector_center_deg(linear, front_deg)
    if center is None:
        return None
    if scan is None or scan_age > SCAN_STALE_SEC:
        return {"action": "obstacle_stop", "reason": "no_scan"}
    ranges, angle_min, angle_inc, range_min = scan
    nearest = sector_min_distance(ranges, angle_min, angle_inc, center, SECTOR_HALF_DEG, range_min)
    if nearest is not None and nearest < OBSTACLE_STOP_M:
        return {"action": "obstacle_stop", "dist": round(nearest, 2)}
    return None


# ── stdin ────────────────────────────────────────────
def stdin_reader(cmd_queue):
    """背景 thread：逐行讀 stdin，解析 JSON 丟進佇列；解析失敗只回 ERR 不中斷。"""
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError as exc:
                emit("ERR", f"JSON 解析失敗：{exc}；原文：{line[:120]}")
                continue
            if not isinstance(cmd, dict):
                emit("ERR", f"指令必須是 JSON 物件：{line[:120]}")
                continue
            cmd_queue.put(cmd)
    except (OSError, ValueError) as exc:
        emit("ERR", f"讀取 stdin 失敗：{exc}")
    finally:
        cmd_queue.put(_EOF)


def load_ros():
    """延遲 import ROS 套件：--selftest 在沒有 ROS 的筆電上也能跑。"""
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import Int32, UInt16
    return types.SimpleNamespace(rclpy=rclpy, Twist=Twist, Int32=Int32, UInt16=UInt16,
                                 LaserScan=LaserScan, qos_sensor=qos_profile_sensor_data)


# ── 節點 ─────────────────────────────────────────────
class RosCmdNode:
    """持有 ROS 節點、發布器與進行中的移動狀態；所有發布都在主 thread 執行。

    用組合而非繼承 rclpy Node，ROS 類別才能延遲到 main() 才 import。
    """

    def __init__(self, ros):
        self.ros = ros
        self.node = ros.rclpy.create_node("voice_cmd_node")
        self.beep_pub = self.node.create_publisher(ros.UInt16, "/beep", 10)
        self.cmd_vel_pub = self.node.create_publisher(ros.Twist, "/cmd_vel", 10)
        self.pan_pub = self.node.create_publisher(ros.Int32, "/servo_s1", 10)
        self.tilt_pub = self.node.create_publisher(ros.Int32, "/servo_s2", 10)
        # 雷達用 best-effort QoS 發布，訂閱端也要 sensor_data profile 才收得到
        self.node.create_subscription(ros.LaserScan, "/scan", self.on_scan, ros.qos_sensor)
        self.scan = None
        self.scan_time = 0.0
        # motion：None 或 {"kind": "move"/"drive", "linear", "angular", "deadline"}
        self.motion = None
        self.next_publish = 0.0

    def on_scan(self, msg):
        self.scan = (list(msg.ranges), msg.angle_min, msg.angle_increment, msg.range_min)
        self.scan_time = time.monotonic()

    def obstacle_now(self, linear):
        return check_obstacle(linear, self.scan, time.monotonic() - self.scan_time)

    def publish_twist(self, linear, angular):
        twist = self.ros.Twist()
        twist.linear.x = float(linear)
        twist.angular.z = float(angular)
        self.cmd_vel_pub.publish(twist)

    def publish_beep(self, ms):
        msg = self.ros.UInt16()
        msg.data = int(ms)
        self.beep_pub.publish(msg)

    def publish_angle(self, publisher, angle):
        msg = self.ros.Int32()
        msg.data = int(angle)
        publisher.publish(msg)

    def send_zero(self):
        """連發數次零速度：UDP/DDS 偶爾掉封包，單發不保險。"""
        for _ in range(STOP_REPEAT):
            self.publish_twist(0.0, 0.0)
            time.sleep(0.02)

    def cancel_motion(self):
        """取消進行中的移動；drive 被取消要回報 drive_done（cancel）。回傳是否原本在動。"""
        if self.motion is None:
            return False
        if self.motion["kind"] == "drive":
            emit("ACK", {"action": "drive_done", "reason": "cancel"})
        self.motion = None
        return True

    def handle_command(self, cmd):
        """依 action 分派；新指令一律先取消舊移動。回傳要 ACK 的 dict。"""
        action = cmd.get("action")
        if action not in SUPPORTED_ACTIONS:
            raise ValueError(f"不支援的 action：{action!r}")
        if self.cancel_motion() and action != "stop":
            self.send_zero()
        if action == "stop":
            return self._do_stop()
        if action == "beep":
            return self._do_beep(cmd)
        if action == "gimbal":
            return self._do_gimbal(cmd)
        if action == "drive":
            return self._do_drive(cmd)
        return self._do_move(cmd)

    def _do_stop(self):
        # 刻意不動雲台：停車是安全動作，鏡頭角度維持使用者最後的設定
        self.send_zero()
        self.publish_beep(0)  # 嘗試中斷正在響的蜂鳴器
        return {"action": "stop"}

    def _do_gimbal(self, cmd):
        pan = int(round(_clamp(_finite_float(cmd.get("pan")), PAN_MIN, PAN_MAX)))
        tilt = int(round(_clamp(_finite_float(cmd.get("tilt")), TILT_MIN, TILT_MAX)))
        self.publish_angle(self.pan_pub, pan)
        self.publish_angle(self.tilt_pub, tilt)
        return {"action": "gimbal", "pan": pan, "tilt": tilt}

    def _do_beep(self, cmd):
        ms = int(_clamp(_finite_float(cmd.get("ms"), 0.0), BEEP_MS_MIN, BEEP_MS_MAX))
        self.publish_beep(ms)
        return {"action": "beep", "ms": ms}

    @staticmethod
    def _speeds(cmd):
        linear = _clamp(_finite_float(cmd.get("linear")), -LINEAR_MAX, LINEAR_MAX)
        angular = _clamp(_finite_float(cmd.get("angular")), -ANGULAR_MAX, ANGULAR_MAX)
        return linear, angular

    def _start_motion(self, kind, linear, angular, seconds):
        """開始移動前先看雷達：起步時前方就太近或雷達沒資料，直接不動並回報 obstacle_stop。"""
        blocked = self.obstacle_now(linear)
        if blocked is not None:
            return blocked
        now = time.monotonic()
        self.motion = {"kind": kind, "linear": linear, "angular": angular,
                       "deadline": now + seconds}
        self.next_publish = now
        return None

    def _do_move(self, cmd):
        linear, angular = self._speeds(cmd)
        seconds = _clamp(_finite_float(cmd.get("seconds"), SECONDS_MIN), SECONDS_MIN, SECONDS_MAX)
        blocked = self._start_motion("move", linear, angular, seconds)
        if blocked is not None:
            return blocked
        return {"action": "move", "linear": linear, "angular": angular, "seconds": seconds}

    def _do_drive(self, cmd):
        linear, angular = self._speeds(cmd)
        if linear == 0.0 and angular == 0.0:
            return self._do_stop()  # 零速度的 drive 等同停車，不必佔用 30 秒
        blocked = self._start_motion("drive", linear, angular, DRIVE_MAX_SEC)
        if blocked is not None:
            return blocked
        return {"action": "drive", "linear": linear, "angular": angular, "max_sec": DRIVE_MAX_SEC}

    def _end_motion(self, acks):
        self.motion = None
        self.send_zero()
        for ack in acks:
            emit("ACK", ack)

    def _finish_acks(self, kind, blocked):
        """依結束原因組 ACK：防撞先報 obstacle_stop，drive 另補 drive_done。"""
        if blocked is not None:
            extra = [{"action": "drive_done", "reason": "obstacle"}] if kind == "drive" else []
            return [blocked] + extra
        if kind == "drive":
            return [{"action": "drive_done", "reason": "timeout"}]
        return [{"action": "move_done"}]

    def tick_motion(self):
        """主迴圈每輪呼叫：先查防撞、再看時限，都沒事就每 0.1 秒重發 Twist。"""
        if self.motion is None:
            return
        now = time.monotonic()
        blocked = self.obstacle_now(self.motion["linear"])
        if blocked is not None or now >= self.motion["deadline"]:
            self._end_motion(self._finish_acks(self.motion["kind"], blocked))
            return
        if now >= self.next_publish:
            self.publish_twist(self.motion["linear"], self.motion["angular"])
            self.next_publish = now + REPUBLISH_SEC

    def destroy(self):
        self.node.destroy_node()


def drain_queue(node, cmd_queue):
    """處理佇列中所有指令；回傳 False 代表 stdin 已 EOF、該結束了。"""
    while True:
        try:
            cmd = cmd_queue.get_nowait()
        except queue.Empty:
            return True
        if cmd is _EOF:
            return False
        try:
            emit("ACK", node.handle_command(cmd))
        except (ValueError, TypeError) as exc:
            emit("ERR", f"指令處理失敗：{exc}")


def run_loop(node, cmd_queue):
    """主 thread 迴圈：spin_once 處理 ROS 事件（含 /scan），穿插處理指令與移動重發。"""
    rclpy = node.ros.rclpy
    while rclpy.ok():
        if not drain_queue(node, cmd_queue):
            emit("ACK", {"action": "eof"})
            return
        node.tick_motion()
        rclpy.spin_once(node.node, timeout_sec=0.02)


# ── 自我測試（不需 ROS）───────────────────────────────
def _synthetic_scan(overrides, base=1.0):
    """合成 360 點 scan：index i 對應 -180+i 度；overrides 為 {角度: 距離}。"""
    ranges = [base] * 360
    for deg, distance in overrides.items():
        ranges[int(round(deg)) + 180] = distance
    return ranges, -math.pi, math.radians(1.0), 0.12


def run_selftest():
    # 前方 0.2 m → 前進要觸發
    scan = _synthetic_scan({0: 0.2})
    assert check_obstacle(0.1, scan, 0.0, front_deg=0.0) == {"action": "obstacle_stop", "dist": 0.2}
    # 前方 1.0 m、後方 0.1 m：前進不觸發、後退要觸發、純轉向不檢查
    scan = _synthetic_scan({-180: 0.15, 179: 0.15})
    assert check_obstacle(0.1, scan, 0.0, front_deg=0.0) is None
    assert check_obstacle(-0.1, scan, 0.0, front_deg=0.0) == {"action": "obstacle_stop", "dist": 0.15}
    assert check_obstacle(0.0, scan, 0.0, front_deg=0.0) is None
    # 中心 180° 的環繞：-170°（差 10°）要算進扇形，0° 的近點不能算
    scan = _synthetic_scan({-170: 0.2, 0: 0.05})
    assert sector_min_distance(*scan[:3], 180.0, 25.0, scan[3]) == 0.2
    assert abs(angle_diff_deg(-175.0, 180.0) - 5.0) < 1e-9
    # 無效值（inf／NaN／小於 range_min）要忽略，不能誤判成障礙物
    scan = _synthetic_scan({0: float("inf"), 1: float("nan"), -1: 0.05})
    assert check_obstacle(0.1, scan, 0.0, front_deg=0.0) is None
    # 雷達沒資料或過期 → 安全預設停車
    assert check_obstacle(0.1, None, 0.0) == {"action": "obstacle_stop", "reason": "no_scan"}
    assert check_obstacle(0.1, _synthetic_scan({}), SCAN_STALE_SEC + 0.1)["reason"] == "no_scan"
    print("PASS")


def main():
    if "--selftest" in sys.argv[1:]:
        run_selftest()
        return
    try:
        ros = load_ros()
    except ImportError as exc:
        emit("ERR", f"無法載入 ROS 2 套件（請先 source /opt/ros/humble/setup.bash）：{exc}")
        sys.exit(1)
    ros.rclpy.init()
    node = RosCmdNode(ros)
    cmd_queue = queue.Queue()
    reader = threading.Thread(target=stdin_reader, args=(cmd_queue,), daemon=True)
    reader.start()
    emit("ACK", {"action": "ready"})
    try:
        run_loop(node, cmd_queue)
    except KeyboardInterrupt:
        emit("ERR", "收到中斷訊號")
    except Exception as exc:  # 看門狗：任何未預期例外都要先停車再結束
        emit("ERR", f"節點例外：{exc!r}")
    finally:
        # 看門狗：不論 EOF 或例外，結束前一定送零速度
        try:
            node.send_zero()
        except Exception as exc:
            emit("ERR", f"結束時送零速度失敗：{exc!r}")
        node.destroy()
        if ros.rclpy.ok():
            ros.rclpy.shutdown()


if __name__ == "__main__":
    main()
