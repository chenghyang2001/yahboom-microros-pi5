"""ycar.py — 教練用的 Yahboom MicroROS-Pi5 車子指令工具（Windows 本機執行）

連線路徑：筆電 127.0.0.1:8022 → USB → Android 手機轉接 → 車上 Pi 5 SSH。
密碼只從環境變數 YCAR_PASS 讀取，不寫在檔案裡。

用法（Git Bash，先 export YCAR_PASS=...）：
  PYTHONUTF8=1 python ycar.py host "uptime"
  PYTHONUTF8=1 python ycar.py ros "ros2 topic list"
  PYTHONUTF8=1 python ycar.py rospy monitor.py --timeout 7200
  PYTHONUTF8=1 python ycar.py gui "rviz2"
  PYTHONUTF8=1 python ycar.py kill "ros2 topic echo"
  PYTHONUTF8=1 python ycar.py stopcar
  PYTHONUTF8=1 python ycar.py status

環境變數：YCAR_PASS（必填）、YCAR_HOST（預設 127.0.0.1）、YCAR_PORT（預設 8022）、YCAR_USER（預設 pi）
"""
import argparse
import codecs
import os
import shlex
import socket
import sys
import time
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("錯誤：缺少 paramiko，請先執行 python -m pip install paramiko", file=sys.stderr)
    sys.exit(1)

ROS_IMAGE = "yahboomtechnology/ros-humble:4.1.2"
# 容器內預設 shell 不會自動載入 ROS；工作區 setup 不一定存在，所以用 if 判斷避免報錯
ROS_ENV = (
    "source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=20; "
    "if [ -f /root/yahboomcar_ws/install/setup.bash ]; then "
    "source /root/yahboomcar_ws/install/setup.bash; fi"
)
CONNECT_TIMEOUT = 8
EXIT_TIMEOUT = 124  # 跟 GNU timeout 一致，方便辨識「逾時」

# stopcar 用 rclpy 發送：ros2 topic pub --once 常在 discovery 完成前就送出而遺失
STOPCAR_PY = r'''
import time
import rclpy
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32, UInt16

rclpy.init()
node = rclpy.create_node("ycar_stopcar")
pub_vel = node.create_publisher(Twist, "/cmd_vel", 10)
pub_s1 = node.create_publisher(Int32, "/servo_s1", 10)
pub_s2 = node.create_publisher(Int32, "/servo_s2", 10)
pub_beep = node.create_publisher(UInt16, "/beep", 10)
# 等訂閱端配對（最多 2 秒），不然第一筆零速度可能沒人收到
deadline = time.time() + 2.0
while time.time() < deadline and pub_vel.get_subscription_count() == 0:
    rclpy.spin_once(node, timeout_sec=0.1)
print(f"/cmd_vel 訂閱者數量：{pub_vel.get_subscription_count()}")
for i in range(3):
    pub_vel.publish(Twist())
    print(f"已送出零速度 /cmd_vel 第 {i + 1} 次")
    time.sleep(0.15)
pub_s1.publish(Int32(data=0))
pub_s2.publish(Int32(data=0))
pub_beep.publish(UInt16(data=0))
print("已送出 /servo_s1=0、/servo_s2=0、/beep=0")
time.sleep(0.3)
node.destroy_node()
rclpy.shutdown()
'''


class YcarError(Exception):
    """可預期的錯誤（連線、找不到容器等），只印訊息不印 traceback"""


def setup_console():
    """讓 Windows 終端機輸出 UTF-8 並啟用 ANSI（monitor.py 的清畫面要用）"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    if os.name == "nt":
        os.system("")  # 舊版 conhost 需要這招才會開啟 VT 序列處理


def load_config():
    """讀環境變數；密碼缺少時直接退出，不用預設值掩蓋"""
    password = os.environ.get("YCAR_PASS")
    if not password:
        raise YcarError("缺少環境變數 YCAR_PASS（車上 Pi 的 SSH 密碼），請先 export YCAR_PASS=...")
    host = os.environ.get("YCAR_HOST") or "127.0.0.1"
    port_text = os.environ.get("YCAR_PORT") or "8022"
    try:
        port = int(port_text)
    except ValueError:
        raise YcarError(f"YCAR_PORT 不是數字：{port_text!r}") from None
    user = os.environ.get("YCAR_USER") or "pi"
    return host, port, user, password


def connect():
    """建立 SSH 連線，各種失敗都轉成清楚的繁中訊息"""
    host, port, user, password = load_config()
    client = paramiko.SSHClient()
    # 轉接埠是本機 127.0.0.1，host key 會隨手機/車子變，學習情境下自動接受
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    hint = "請確認 USB 轉接仍在執行（手機 App 開著、USB 線沒鬆）"
    try:
        client.connect(host, port=port, username=user, password=password,
                       timeout=CONNECT_TIMEOUT, banner_timeout=CONNECT_TIMEOUT,
                       auth_timeout=CONNECT_TIMEOUT, look_for_keys=False, allow_agent=False)
    except paramiko.AuthenticationException:
        raise YcarError(f"登入 {user}@{host}:{port} 失敗：密碼錯誤（檢查 YCAR_PASS）") from None
    except (socket.timeout, TimeoutError):
        raise YcarError(f"連線 {host}:{port} 逾時：{hint}") from None
    except (ConnectionRefusedError, ConnectionResetError, OSError, paramiko.SSHException) as exc:
        raise YcarError(f"連不上 {host}:{port}：{hint}（{exc}）") from None
    return client


def stream_command(client, command, timeout, stdin_data=None):
    """執行遠端指令，stdout/stderr 收到就印（不等結束），回傳遠端 exit code"""
    transport = client.get_transport()
    if transport is None or not transport.is_active():
        raise YcarError("SSH 連線已中斷")
    channel = transport.open_session()
    channel.settimeout(1.0)
    channel.exec_command(command)
    if stdin_data is not None:
        channel.sendall(stdin_data)
        channel.shutdown_write()  # 送 EOF，遠端 python3 - 才會開始執行
    out_dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    err_dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    deadline = time.monotonic() + timeout
    try:
        while True:
            got_data = _pump(channel, out_dec, err_dec)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if time.monotonic() > deadline:
                print(f"\n[ycar] 本機等待逾時 {timeout:.0f} 秒，中斷連線", file=sys.stderr)
                return EXIT_TIMEOUT
            if not got_data:
                time.sleep(0.03)
        return channel.recv_exit_status()
    finally:
        channel.close()


def _pump(channel, out_dec, err_dec):
    """把目前緩衝區的輸出搬到本機終端，回傳這輪有沒有資料"""
    got_data = False
    while channel.recv_ready():
        sys.stdout.write(out_dec.decode(channel.recv(65536)))
        got_data = True
    while channel.recv_stderr_ready():
        sys.stderr.write(err_dec.decode(channel.recv_stderr(65536)))
        got_data = True
    if got_data:
        sys.stdout.flush()
        sys.stderr.flush()
    return got_data


def capture_command(client, command, timeout=15):
    """執行短指令並回傳 (exit_code, stdout, stderr)，用於查容器 ID 這類內部步驟"""
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdin.close()
        out_text = stdout.read().decode("utf-8", errors="replace")
        err_text = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out_text, err_text
    except (socket.timeout, TimeoutError):
        raise YcarError(f"遠端指令逾時（{timeout} 秒）：{command}") from None


def find_container(client):
    """找執行中的 ros-humble 容器；容器 ID 每次開機會變，所以每次現查"""
    code, out_text, err_text = capture_command(
        client, f"docker ps --filter ancestor={ROS_IMAGE} --format '{{{{.ID}}}}'")
    if "permission denied" in err_text.lower():
        raise YcarError("pi 帳號沒有 docker 權限（需加入 docker 群組）：" + err_text.strip())
    if code == 0 and out_text.strip():
        return out_text.split()[0]
    # 映像 tag 可能改過，退而用名稱或映像含 ros-humble 的第一個
    code, out_text, err_text = capture_command(
        client, "docker ps --format '{{.ID}} {{.Image}} {{.Names}}'")
    if code != 0:
        raise YcarError(f"docker ps 失敗：{err_text.strip() or out_text.strip()}")
    for line in out_text.splitlines():
        if "ros-humble" in line:
            return line.split()[0]
    raise YcarError("找不到執行中的 ros-humble 容器：請確認車上的 ROS 容器已啟動（docker ps）")


def ros_exec(container_id, inner_script, timeout, interactive=False, marker=None):
    """組出 docker exec 指令；timeout 放在容器內，本機斷線後遠端程序也會自己結束"""
    flags = "-i " if interactive else ""
    wrapped = f"{ROS_ENV}; {inner_script}"
    parts = [f"docker exec {flags}{container_id}",
             f"timeout -k 3 {int(timeout)} bash -c {shlex.quote(wrapped)}"]
    if marker:
        parts.append(shlex.quote(marker))  # 成為 bash 的 $0，Ctrl+C 時用來 pkill
    return " ".join(parts)


def run_in_container(client, container_id, inner_script, timeout, stdin_data=None, signal_name="TERM"):
    """在容器內串流執行；本機 Ctrl+C 時順手把容器內的程序收掉"""
    marker = f"ycar_job_{os.getpid()}_{int(time.time())}"
    command = ros_exec(container_id, inner_script, timeout,
                       interactive=stdin_data is not None, marker=marker)
    try:
        return stream_command(client, command, timeout + 10, stdin_data=stdin_data)
    except KeyboardInterrupt:
        print("\n[ycar] 收到 Ctrl+C，停止容器內程序…", file=sys.stderr)
        # pkill 直接由 docker exec 啟動（沒有 bash 包裝），不會比對到自己
        capture_command(client, f"docker exec {container_id} pkill -{signal_name} -f -- {shlex.quote(marker)}")
        return 130


def cmd_host(client, args):
    command = f"timeout -k 3 {int(args.timeout)} bash -c {shlex.quote(args.command)}"
    return stream_command(client, command, args.timeout + 10)


def cmd_ros(client, args):
    container_id = find_container(client)
    return run_in_container(client, container_id, args.command, args.timeout)


def cmd_rospy(client, args):
    script_path = Path(args.script)
    try:
        script_bytes = script_path.read_bytes()
    except OSError as exc:
        raise YcarError(f"讀不到本機 Python 檔 {script_path}：{exc}") from None
    container_id = find_container(client)
    # SIGINT 讓遠端 rclpy 走 KeyboardInterrupt 乾淨收尾
    return run_in_container(client, container_id, "python3 -u - \"$0\"", args.timeout,
                            stdin_data=script_bytes, signal_name="INT")


def cmd_gui(client, args):
    container_id = find_container(client)
    log_path = f"/tmp/gui_{time.strftime('%Y%m%d_%H%M%S')}.log"
    wrapped = f"{ROS_ENV}; {args.command} > {log_path} 2>&1"
    command = f"docker exec -d -e DISPLAY=:0 {container_id} bash -c {shlex.quote(wrapped)}"
    code, out_text, err_text = capture_command(client, command)
    if code != 0:
        raise YcarError(f"GUI 啟動失敗：{err_text.strip() or out_text.strip()}")
    print(f"已在容器 {container_id} 背景啟動，畫面在 Pi 桌面（DISPLAY=:0）")
    print(f"log：{log_path}（看 log：python ycar.py ros \"cat {log_path}\"）")
    print("若畫面沒出現，可能要在 Pi 桌面先執行 xhost +local:")
    return 0


def cmd_kill(client, args):
    container_id = find_container(client)
    # 不經 bash 包裝直接跑 pkill：pkill 本身會排除自己，也就不會誤殺下指令的 shell
    command = f"docker exec {container_id} pkill -e -f -- {shlex.quote(args.pattern)}"
    code, out_text, err_text = capture_command(client, command)
    if out_text.strip():
        print(out_text.rstrip())
    if code == 1:
        print(f"容器內沒有符合「{args.pattern}」的程序")
    elif code != 0:
        print(f"pkill 失敗（exit {code}）：{err_text.strip()}", file=sys.stderr)
    return code


def cmd_stopcar(client, args):
    container_id = find_container(client)
    return run_in_container(client, container_id, "python3 -u -", 30,
                            stdin_data=STOPCAR_PY.encode("utf-8"), signal_name="INT")


def cmd_status(client, args):
    container_id = find_container(client)
    print(f"== 容器 ID：{container_id}")
    script = (
        "echo '== ros2 node list'; timeout 10 ros2 node list; "
        "echo '== /battery（一筆）'; timeout 6 ros2 topic echo --once /battery; "
        "echo '== /scan 頻率（6 秒）'; timeout -s INT 6 ros2 topic hz /scan 2>/dev/null; true"
    )
    return run_in_container(client, container_id, script, 40)


def build_parser():
    parser = argparse.ArgumentParser(description="Yahboom MicroROS-Pi5 車子指令工具")
    sub = parser.add_subparsers(dest="action", required=True)
    for name, help_text, default_timeout in (("host", "在 Pi 主機上執行", 60),
                                             ("ros", "在 ROS 容器內執行", 60)):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("command")
        p.add_argument("--timeout", type=float, default=default_timeout)
    p = sub.add_parser("rospy", help="把本機 .py 送進容器用 python3 執行")
    p.add_argument("script")
    p.add_argument("--timeout", type=float, default=120)
    p = sub.add_parser("gui", help="在容器內背景執行 GUI 程式（顯示在 Pi 桌面）")
    p.add_argument("command")
    p = sub.add_parser("kill", help="在容器內 pkill -f")
    p.add_argument("pattern")
    sub.add_parser("stopcar", help="送零速度並把雲台、蜂鳴器歸零")
    sub.add_parser("status", help="容器 ID、節點、電池、光達頻率")
    return parser


HANDLERS = {"host": cmd_host, "ros": cmd_ros, "rospy": cmd_rospy, "gui": cmd_gui,
            "kill": cmd_kill, "stopcar": cmd_stopcar, "status": cmd_status}


def main():
    setup_console()
    args = build_parser().parse_args()
    if getattr(args, "timeout", 1) <= 0:
        print("錯誤：--timeout 必須大於 0", file=sys.stderr)
        sys.exit(2)
    client = None
    try:
        client = connect()
        exit_code = HANDLERS[args.action](client, args)
    except YcarError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        print("\n[ycar] 已中斷", file=sys.stderr)
        exit_code = 130
    except (paramiko.SSHException, OSError) as exc:
        print(f"錯誤：SSH 通訊中斷：{exc}（請確認 USB 轉接仍在執行）", file=sys.stderr)
        exit_code = 1
    finally:
        if client is not None:
            client.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
