"""Pi 5 主機上的語音代理：藍牙耳機收音 → 斷句 → STT → 意圖 → 經 docker exec 送給 ROS 2 節點。

流程：
    parec（耳機 HFP 麥克風）→ RMS 斷句 → wav → intent_proto.transcribe
    → intent_proto.handle_text → JSON 一行寫入容器內 ros_cmd_node.py 的 stdin
    （photo 例外：在主機用 ffmpeg 直接拍，不送節點；dry-run 也會真的拍，因為拍照不會動車）

用法（主機上）：
    ~/voice/.venv/bin/python voice_agent.py                 # 正式收音
    ~/voice/.venv/bin/python voice_agent.py --dry-run       # 不啟動容器節點，只印 JSON
    ~/voice/.venv/bin/python voice_agent.py --dry-run --wav a.wav   # 冒煙測試
    ~/voice/.venv/bin/python voice_agent.py --camera /dev/video2    # 指定拍照用的相機
    ~/voice/.venv/bin/python voice_agent.py --allow-gimbal          # 允許雲台（預設停用）
    ~/voice/.venv/bin/python voice_agent.py --no-ready-voice        # 不播「準備好了」語音
"""
import argparse
import array
import collections
import hashlib
import json
import math
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

from intent_proto import handle_text, transcribe

# ── 常數 ─────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
NODE_SCRIPT = HERE / "ros_cmd_node.py"
NODE_REMOTE_PATH = "/tmp/ros_cmd_node.py"
NODE_SHELL = ("source /opt/ros/humble/setup.bash; export ROS_DOMAIN_ID=20; "
              f"exec python3 -u {NODE_REMOTE_PATH}")

HEADSET_MAC = "00_12_12_00_D9_C2"
BT_CARD = f"bluez_card.{HEADSET_MAC}"
BT_SOURCE = f"bluez_input.{HEADSET_MAC}.0"
PROFILE_HFP = "headset-head-unit-msbc"
PROFILE_A2DP = "a2dp-sink-sbc"

RATE = 16000
CHUNK_MS = 30
CHUNK_BYTES = RATE * CHUNK_MS // 1000 * 2  # s16le 單聲道 → 960 bytes
NOISE_SEC = 1.0
NOISE_FACTOR = 1.6
PREROLL_SEC = 0.3
SILENCE_END_SEC = 1.0
MAX_UTTER_SEC = 6.0
MIN_UTTER_SEC = 0.4
RECONNECT_SEC = 3.0
NODE_EXIT_TIMEOUT = 3.0

# 送給節點時只保留這些欄位；via / llm_sec / reason 是主機端除錯用，節點不需要
NODE_FIELDS = {"beep": ("ms",), "move": ("linear", "angular", "seconds"), "stop": (),
               "gimbal": ("pan", "tilt")}

DEFAULT_CAMERA = "/dev/video0"
PHOTO_DIR = Path(__file__).parent / "photos"
PHOTO_TIMEOUT_SEC = 10

TONES_OK = [(1200, 0.15)]
TONES_FAIL = [(400, 0.15), (400, 0.15)]
TONES_PHOTO = [(1600, 0.1), (2000, 0.1)]
TONES_READY_FALLBACK = [(1200, 0.1)] * 3  # TTS 失敗時的備援：三聲短高音

READY_TEXT = "小車已經準備好了，可以開始用語音下命令。"
TTS_VOICE = "zh-TW-HsiaoChenNeural"
TTS_CACHE_DIR = Path(__file__).parent / "tts_cache"
TTS_GEN_TIMEOUT_SEC = 20
TTS_PLAY_TIMEOUT_SEC = 30  # 語音比提示音長很多，pacat 逾時要放寬


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_cmd(cmd, desc):
    """執行外部指令並回傳 stdout；找不到指令或非 0 結束都印清楚錯誤，回傳 None。"""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              timeout=30, check=False)
    except FileNotFoundError:
        log(f"錯誤：找不到指令 {cmd[0]}（{desc}）")
        return None
    except subprocess.TimeoutExpired:
        log(f"錯誤：{desc} 逾時（{' '.join(cmd)}）")
        return None
    if done.returncode != 0:
        log(f"錯誤：{desc} 失敗（code={done.returncode}）：{done.stderr.strip()}")
        return None
    return done.stdout


# ── ROS 節點連線 ─────────────────────────────────────
class NodeLink:
    """包裝容器內 ros_cmd_node.py 的子程序；dry_run 時只印出要送的 JSON。"""

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.proc = None
        # 雲台目前角度：LLM 只講一軸時用來補另一軸；開機假設回正（0, 0）
        self.gimbal = {"pan": 0, "tilt": 0}

    def start(self):
        if self.dry_run:
            log("dry-run：不啟動 docker 節點")
            return
        container = self._find_container()
        if run_cmd(["docker", "cp", str(NODE_SCRIPT), f"{container}:{NODE_REMOTE_PATH}"],
                   "docker cp 節點腳本") is None:
            raise RuntimeError("無法把 ros_cmd_node.py 複製進容器")
        self.proc = subprocess.Popen(
            ["docker", "exec", "-i", container, "bash", "-c", NODE_SHELL],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        log(f"已在容器 {container} 啟動 ROS 指令節點")

    @staticmethod
    def _find_container():
        # 車上另有 micro-ros-agent 容器，要指定 Yahboom 的 ROS 映像檔
        output = run_cmd(["docker", "ps", "-q", "--filter", "ancestor=yahboomtechnology/ros-humble:4.1.2"], "列出容器")
        ids = output.split() if output else []
        if not ids:
            raise RuntimeError("找不到執行中的 docker 容器（請先啟動 ROS 2 容器）")
        return ids[0]

    def _pump_stdout(self):
        for line in self.proc.stdout:
            log(f"[node] {line.rstrip()}")
        log("[node] 節點輸出已結束")

    def send(self, cmd):
        line = json.dumps(cmd, ensure_ascii=False)
        if self.dry_run:
            log(f"dry-run 送出：{line}")
            return
        if self.proc is None or self.proc.poll() is not None:
            log(f"錯誤：節點未執行，無法送出 {line}")
            return
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            log(f"錯誤：寫入節點失敗：{exc}")

    def close(self):
        self.send({"action": "stop"})
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=NODE_EXIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            log("節點 3 秒內沒結束，強制 kill")
            self.proc.kill()


# ── 耳機與收音 ───────────────────────────────────────
def set_headset_profile(profile):
    ok = run_cmd(["pactl", "set-card-profile", BT_CARD, profile], f"切換耳機到 {profile}")
    if ok is not None:
        log(f"耳機已切到 {profile}")
    return ok is not None


def find_source():
    """優先用固定名稱；耳機重連後編號可能變，找不到就挑第一個 bluez_input。"""
    output = run_cmd(["pactl", "list", "short", "sources"], "列出收音來源")
    if output is None:
        return None
    names = [line.split("\t")[1] for line in output.splitlines() if "\t" in line]
    if BT_SOURCE in names:
        return BT_SOURCE
    return next((name for name in names if "bluez_input" in name), None)


def start_parec(source, chunk_queue):
    """開 parec 並用背景 thread 把固定大小的音訊塊丟進佇列；EOF 時丟 None。"""
    try:
        proc = subprocess.Popen(
            ["parec", f"--device={source}", "--format=s16le", f"--rate={RATE}",
             "--channels=1", "--raw"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        log("錯誤：找不到 parec（請安裝 pulseaudio-utils）")
        return None

    def pump():
        while True:
            chunk = proc.stdout.read(CHUNK_BYTES)
            if not chunk or len(chunk) < CHUNK_BYTES:
                chunk_queue.put(None)
                return
            chunk_queue.put(chunk)

    threading.Thread(target=pump, daemon=True).start()
    log(f"開始收音：{source}")
    return proc


def stop_proc(proc):
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def chunk_rms(chunk):
    samples = array.array("h", chunk)
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def drain(chunk_queue):
    """丟掉佇列裡累積的音訊；回傳是否遇到 EOF（None）。"""
    hit_eof = False
    while True:
        try:
            if chunk_queue.get_nowait() is None:
                hit_eof = True
        except queue.Empty:
            return hit_eof


# ── 斷句 ─────────────────────────────────────────────
class Segmenter:
    """RMS 門檻斷句：保留預錄、連續靜音結束、過長強制切、過短丟棄。"""

    def __init__(self, threshold):
        self.threshold = threshold
        self.preroll = collections.deque(maxlen=round(PREROLL_SEC * 1000 / CHUNK_MS))
        self.frames = None
        self.silent = 0

    def reset(self):
        self.preroll.clear()
        self.frames = None
        self.silent = 0

    def feed(self, chunk):
        """餵一塊音訊；斷出一句時回傳 PCM bytes，否則回 None。"""
        loud = chunk_rms(chunk) > self.threshold
        if self.frames is None:
            self.preroll.append(chunk)
            if loud:
                self.frames, self.silent = list(self.preroll), 0
            return None
        self.frames.append(chunk)
        self.silent = 0 if loud else self.silent + 1
        silence_end = self.silent * CHUNK_MS >= SILENCE_END_SEC * 1000
        too_long = len(self.frames) * CHUNK_MS >= MAX_UTTER_SEC * 1000
        if not (silence_end or too_long):
            return None
        frames, voiced = self.frames, len(self.frames) - self.silent
        self.reset()
        if voiced * CHUNK_MS < MIN_UTTER_SEC * 1000:
            log("片段太短，丟棄")
            return None
        return b"".join(frames)


def write_wav(pcm):
    fd, path = tempfile.mkstemp(prefix="voice_", suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(RATE)
        wav_file.writeframes(pcm)
    return path


# ── 提示音 ───────────────────────────────────────────
def tone_bytes(freq, seconds, volume=0.4):
    count = int(RATE * seconds)
    samples = array.array("h", (int(32767 * volume * math.sin(2 * math.pi * freq * i / RATE))
                                for i in range(count)))
    return samples.tobytes()


def play_pcm(pcm, timeout=5):
    """把 16k 單聲道 s16le PCM 用 pacat 播到預設 sink（HFP 時就是耳機）；失敗只警告。"""
    try:
        subprocess.run(["pacat", "--playback", "--format=s16le", f"--rate={RATE}",
                        "--channels=1"], input=pcm, timeout=timeout, check=True,
                       stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        log("警告：找不到 pacat，略過播放")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log(f"警告：播放音訊失敗：{exc}")


def play_tones(tones):
    """tones：[(頻率, 秒數), ...]，中間插 0.08 秒靜音；失敗只警告，不影響主流程。"""
    gap = bytes(int(RATE * 0.08) * 2)
    play_pcm(gap.join(tone_bytes(freq, sec) for freq, sec in tones))


# ── 語音通知（TTS）────────────────────────────────────
def tts_cache_path(text):
    # 用文字雜湊當檔名：改了文字自然換新檔，同一句第二次啟動就不需要網路
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return TTS_CACHE_DIR / f"{digest}.mp3"


def _stderr_text(exc):
    return (exc.stderr or b"").decode("utf-8", "replace").strip()


def ensure_tts_mp3(text):
    """取得這句話的 mp3（有快取就直接用）；失敗回傳 None（已印警告）。"""
    mp3_path = tts_cache_path(text)
    if mp3_path.is_file() and mp3_path.stat().st_size > 0:
        return mp3_path
    # 先寫暫存檔再改名：edge-tts 中途斷網時不會留下半個 mp3 被當成快取
    part_path = mp3_path.with_suffix(".part")
    edge_tts = Path(sys.executable).parent / "edge-tts"
    cmd = [str(edge_tts), "--voice", TTS_VOICE, "--text", text, "--write-media", str(part_path)]
    try:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(cmd, capture_output=True, timeout=TTS_GEN_TIMEOUT_SEC, check=True)
        part_path.replace(mp3_path)
    except FileNotFoundError:
        log(f"警告：找不到 edge-tts（{edge_tts}）")
        return None
    except subprocess.TimeoutExpired:
        log(f"警告：edge-tts 逾時 {TTS_GEN_TIMEOUT_SEC} 秒（沒網路？）")
        return None
    except subprocess.CalledProcessError as exc:
        log(f"警告：edge-tts 失敗（code={exc.returncode}）：{_stderr_text(exc)}")
        return None
    except OSError as exc:
        log(f"警告：寫入 TTS 快取失敗：{exc}")
        return None
    finally:
        part_path.unlink(missing_ok=True)
    return mp3_path


def mp3_to_pcm(mp3_path):
    """用 ffmpeg 把 mp3 解成 16k 單聲道 s16le，與提示音同格式；失敗回傳 None。"""
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(mp3_path),
           "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-"]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=TTS_GEN_TIMEOUT_SEC, check=True)
    except FileNotFoundError:
        log("警告：找不到 ffmpeg，無法播放語音")
        return None
    except subprocess.TimeoutExpired:
        log(f"警告：ffmpeg 解碼逾時（{mp3_path}）")
        return None
    except subprocess.CalledProcessError as exc:
        log(f"警告：ffmpeg 解碼失敗（code={exc.returncode}）：{_stderr_text(exc)}")
        return None
    return done.stdout or None


def announce_ready(args):
    """在耳機播「準備好了」語音；任何一步失敗就改播三聲短高音，不中斷收音。"""
    if args.no_ready_voice:
        return
    mp3_path = ensure_tts_mp3(args.ready_text)
    pcm = mp3_to_pcm(mp3_path) if mp3_path is not None else None
    if pcm is None:
        log("警告：語音通知失敗，改播備援提示音")
        play_tones(TONES_READY_FALLBACK)
        return
    log(f"播放語音通知：「{args.ready_text}」")
    play_pcm(pcm, timeout=TTS_PLAY_TIMEOUT_SEC)


# ── 拍照 ─────────────────────────────────────────────
def take_photo(camera):
    """用 ffmpeg 從 v4l2 相機抓一張 jpg；成功回傳路徑，失敗回傳 None（已印錯誤）。"""
    try:
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"錯誤：無法建立相片目錄 {PHOTO_DIR}：{exc}")
        return None
    photo_path = PHOTO_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "v4l2",
           "-video_size", "1280x720", "-i", camera, "-frames:v", "1", "-update", "1",
           str(photo_path)]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=PHOTO_TIMEOUT_SEC, check=False)
    except FileNotFoundError:
        log("錯誤：找不到 ffmpeg（請 sudo apt install ffmpeg）")
        return None
    except subprocess.TimeoutExpired:
        log(f"錯誤：拍照逾時 {PHOTO_TIMEOUT_SEC} 秒（相機 {camera}）")
        return None
    if done.returncode != 0 or not photo_path.is_file():
        log(f"錯誤：拍照失敗（code={done.returncode}，相機 {camera}）：{done.stderr.strip()}")
        return None
    return photo_path


def handle_photo(args):
    photo_path = take_photo(args.camera)
    if photo_path is None:
        play_tones(TONES_FAIL)
        return
    log(f"拍照完成：{photo_path}")
    play_tones(TONES_PHOTO)


# ── 處理一句 ─────────────────────────────────────────
def node_command(result):
    action = result.get("action")
    return {"action": action, **{k: result[k] for k in NODE_FIELDS[action] if k in result}}


def fill_gimbal(cmd, current):
    """LLM 只改一軸時，缺的那軸補成目前角度（節點端每次都要收到兩軸）。"""
    return {**cmd, **{axis: cmd.get(axis, current[axis]) for axis in ("pan", "tilt")}}


def dispatch_result(result, args, link):
    """依 action 分派：ignore 靜默、photo 主機拍、白名單送節點、其餘播失敗音。"""
    action = result.get("action")
    if action == "ignore":
        return
    if action == "photo":
        handle_photo(args)
        return
    if action not in NODE_FIELDS:
        play_tones(TONES_FAIL)
        return
    if action == "gimbal" and not args.allow_gimbal:
        # 使用者要求測試期間雲台完全不能動，必須明確加 --allow-gimbal 才放行
        log(f"雲台已停用，略過：{json.dumps(result, ensure_ascii=False)}")
        play_tones(TONES_FAIL)
        return
    cmd = node_command(result)
    if action == "gimbal":
        cmd = fill_gimbal(cmd, link.gimbal)
    link.send(cmd)
    if action == "gimbal":
        link.gimbal = {"pan": cmd["pan"], "tilt": cmd["tilt"]}
    play_tones(TONES_OK)


def process_wav(wav_path, args, link):
    start = time.perf_counter()
    try:
        text, stt_sec = transcribe(wav_path, model=args.model)
        log(f"辨識：「{text}」（STT {stt_sec:.2f}s）")
        result = handle_text(text, use_llm=not args.no_llm)
    except Exception as exc:  # STT／LLM 任何失敗都不能讓代理整個掛掉
        log(f"錯誤：處理音檔失敗：{exc!r}")
        play_tones(TONES_FAIL)
        return
    log(f"結果：{json.dumps(result, ensure_ascii=False)}（總耗時 {time.perf_counter() - start:.2f}s）")
    dispatch_result(result, args, link)


def handle_utterance(pcm, args, link):
    wav_path = write_wav(pcm)
    try:
        process_wav(wav_path, args, link)
    finally:
        Path(wav_path).unlink(missing_ok=True)


# ── 收音主迴圈 ───────────────────────────────────────
def measure_noise(chunk_queue):
    """量背景噪音 RMS；回傳 None 代表量測途中來源就斷了。"""
    levels = []
    for _ in range(round(NOISE_SEC * 1000 / CHUNK_MS)):
        chunk = chunk_queue.get()
        if chunk is None:
            return None
        levels.append(chunk_rms(chunk))
    return sum(levels) / len(levels)


def open_capture(chunk_queue):
    """找來源並開 parec；失敗時每 3 秒重試，直到成功（Ctrl+C 可中斷）。"""
    while True:
        source = find_source()
        proc = start_parec(source, chunk_queue) if source else None
        if proc is not None:
            return proc
        log(f"找不到藍牙收音來源，{RECONNECT_SEC:.0f} 秒後重試")
        time.sleep(RECONNECT_SEC)
        set_headset_profile(PROFILE_HFP)


def listen_forever(args, link, state):
    chunk_queue = queue.Queue()
    segmenter = None
    while True:
        state["parec"] = open_capture(chunk_queue)
        if segmenter is None:
            noise = measure_noise(chunk_queue)
            if noise is not None:
                segmenter = Segmenter(max(noise * NOISE_FACTOR, args.threshold))
                log(f"背景 RMS {noise:.0f}，門檻 {segmenter.threshold:.0f}，開始聆聽")
        # 首次啟動與每次斷線重連後都要通知；回傳 True 代表播放期間來源就斷了
        if segmenter is not None and not announce_and_flush(chunk_queue, segmenter, args):
            listen_until_eof(chunk_queue, segmenter, args, link)
        log("收音中斷（耳機斷線？），先送 stop 再重連")
        link.send({"action": "stop"})
        stop_proc(state["parec"])
        drain(chunk_queue)
        time.sleep(RECONNECT_SEC)
        set_headset_profile(PROFILE_HFP)


def announce_and_flush(chunk_queue, segmenter, args):
    """播準備好語音後丟掉播放期間收到的音訊（含耳機回授），回傳是否遇到 EOF。"""
    announce_ready(args)
    time.sleep(0.2)
    segmenter.reset()
    return drain(chunk_queue)


def listen_until_eof(chunk_queue, segmenter, args, link):
    while True:
        chunk = chunk_queue.get()
        if chunk is None:
            return
        pcm = segmenter.feed(chunk)
        if pcm is None:
            continue
        handle_utterance(pcm, args, link)
        # 處理期間累積的音訊含提示音，整段丟掉避免自己觸發自己
        time.sleep(0.2)
        segmenter.reset()
        if drain(chunk_queue):
            return


# ── 入口 ─────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="Yahboom 小車語音代理")
    parser.add_argument("--model", default="base", help="faster-whisper 模型（base／small）")
    parser.add_argument("--threshold", type=float, default=500, help="RMS 門檻下限")
    parser.add_argument("--no-llm", action="store_true", help="不呼叫 Claude，只走規則")
    parser.add_argument("--dry-run", action="store_true", help="不啟動 docker 節點")
    parser.add_argument("--wav", help="直接處理這個 wav 一次後結束")
    parser.add_argument("--camera", default=DEFAULT_CAMERA, help=f"拍照用的 v4l2 裝置（預設 {DEFAULT_CAMERA}）")
    parser.add_argument("--allow-gimbal", action="store_true", help="允許雲台指令（預設停用，安全考量）")
    parser.add_argument("--ready-text", default=READY_TEXT, help="準備好時要念的語音文字")
    parser.add_argument("--no-ready-voice", action="store_true", help="不播準備好語音通知")
    return parser.parse_args()


def _raise_interrupt(_signum, _frame):
    raise KeyboardInterrupt


def teardown(link, state):
    log("結束中：停車、關閉節點與收音")
    try:
        link.close()
    except Exception as exc:
        log(f"錯誤：關閉節點失敗：{exc!r}")
    stop_proc(state.get("parec"))
    if state.get("hfp"):
        set_headset_profile(PROFILE_A2DP)


def main():
    args = parse_args()
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    signal.signal(signal.SIGTERM, _raise_interrupt)
    link, state = NodeLink(args.dry_run), {}
    try:
        link.start()
        if args.wav:
            process_wav(args.wav, args, link)
            return
        state["hfp"] = set_headset_profile(PROFILE_HFP)
        time.sleep(2)  # 剛切 HFP 時來源還沒出現，等它就緒
        listen_forever(args, link, state)
    except KeyboardInterrupt:
        log("收到中斷訊號")
    except RuntimeError as exc:
        log(f"錯誤：{exc}")
        sys.exit(1)
    finally:
        teardown(link, state)


if __name__ == "__main__":
    main()
