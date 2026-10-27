"""容器內的 ROS 2 指令節點：從 stdin 一行讀一個 JSON 指令，轉成 /beep、/cmd_vel、/servo_s1、/servo_s2 發布。

由 Pi 主機的 voice_agent.py 透過下列方式啟動（stdin/stdout 當作簡單的 IPC 管道）：
    docker exec -i <容器> bash -c 'source /opt/ros/humble/setup.bash; \
        export ROS_DOMAIN_ID=20; exec python3 -u /tmp/ros_cmd_node.py'

指令格式（每行一個 JSON）：
    {"action":"beep","ms":30000}
    {"action":"move","linear":0.1,"angular":0.0,"seconds":2}
    {"action":"stop"}                     # 只停車與蜂鳴器，不動雲台
    {"action":"gimbal","pan":45,"tilt":-30}   # 絕對角度（度）

回報：每處理一筆印 `ACK <json>`，錯誤印 `ERR <訊息>`；主機端逐行讀取。
只依賴 rclpy 與標準庫，方便直接 docker cp 進容器執行。
"""
import json
import math
import queue
import sys
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Int32, UInt16

# 夾限值與 intent_proto.py／SPEC.md 一致；節點端再夾一次，避免主機端被繞過時車子暴衝
BEEP_MS_MIN, BEEP_MS_MAX = 0, 60000
LINEAR_MAX = 0.15
ANGULAR_MAX = 0.8
SECONDS_MIN, SECONDS_MAX = 0.5, 3.0
# 雲台安全鐵律：/servo_s2 大於 0 會抬頭扯掉相機 USB 線，只准 -45（低頭到底）～0（平視）
PAN_MIN, PAN_MAX = -90, 90
TILT_MIN, TILT_MAX = -45, 0

# 底盤韌體約 0.5 秒沒收到 cmd_vel 就可能停下，0.1 秒重發確保移動連續
REPUBLISH_SEC = 0.1
STOP_REPEAT = 3

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


class RosCmdNode(Node):
    """持有發布器與進行中的 move 狀態；所有發布都在主 thread 執行。"""

    def __init__(self):
        super().__init__("voice_cmd_node")
        self.beep_pub = self.create_publisher(UInt16, "/beep", 10)
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.pan_pub = self.create_publisher(Int32, "/servo_s1", 10)
        self.tilt_pub = self.create_publisher(Int32, "/servo_s2", 10)
        self.move_twist = None
        self.move_deadline = 0.0
        self.next_publish = 0.0

    def publish_twist(self, linear, angular):
        twist = Twist()
        twist.linear.x = float(linear)
        twist.angular.z = float(angular)
        self.cmd_vel_pub.publish(twist)

    def publish_beep(self, ms):
        msg = UInt16()
        msg.data = int(ms)
        self.beep_pub.publish(msg)

    def publish_angle(self, publisher, angle):
        msg = Int32()
        msg.data = int(angle)
        publisher.publish(msg)

    def send_zero(self):
        """連發數次零速度：UDP/DDS 偶爾掉封包，單發不保險。"""
        for _ in range(STOP_REPEAT):
            self.publish_twist(0.0, 0.0)
            time.sleep(0.02)

    def cancel_move(self):
        was_moving = self.move_twist is not None
        self.move_twist = None
        return was_moving

    def handle_command(self, cmd):
        """依 action 分派；新指令一律先取消舊 move。回傳要 ACK 的 dict。"""
        action = cmd.get("action")
        if action not in ("beep", "move", "stop", "gimbal"):
            raise ValueError(f"不支援的 action：{action!r}")
        if self.cancel_move() and action != "stop":
            self.send_zero()
        if action == "stop":
            return self._do_stop()
        if action == "beep":
            return self._do_beep(cmd)
        if action == "gimbal":
            return self._do_gimbal(cmd)
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

    def _do_move(self, cmd):
        linear = _clamp(_finite_float(cmd.get("linear")), -LINEAR_MAX, LINEAR_MAX)
        angular = _clamp(_finite_float(cmd.get("angular")), -ANGULAR_MAX, ANGULAR_MAX)
        seconds = _clamp(_finite_float(cmd.get("seconds"), SECONDS_MIN), SECONDS_MIN, SECONDS_MAX)
        now = time.monotonic()
        self.move_twist = (linear, angular)
        self.move_deadline = now + seconds
        self.next_publish = now
        return {"action": "move", "linear": linear, "angular": angular, "seconds": seconds}

    def tick_move(self):
        """主迴圈每輪呼叫：時間到送零速度，否則每 0.1 秒重發 Twist。"""
        if self.move_twist is None:
            return
        now = time.monotonic()
        if now >= self.move_deadline:
            self.move_twist = None
            self.send_zero()
            emit("ACK", {"action": "move_done"})
            return
        if now >= self.next_publish:
            self.publish_twist(*self.move_twist)
            self.next_publish = now + REPUBLISH_SEC


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
    """主 thread 迴圈：spin_once 處理 ROS 事件，穿插處理指令與 move 重發。"""
    while rclpy.ok():
        if not drain_queue(node, cmd_queue):
            emit("ACK", {"action": "eof"})
            return
        node.tick_move()
        rclpy.spin_once(node, timeout_sec=0.02)


def main():
    rclpy.init()
    node = RosCmdNode()
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
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
