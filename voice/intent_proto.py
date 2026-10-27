"""語音指令離線原型：wav → faster-whisper STT → Claude Haiku 意圖 → 白名單夾限後的車子指令 JSON。

用途：在筆電上先驗證整條「語音 → 文字 → 指令」管線，之後 Pi 5 的 voice_agent.py
直接 import 這裡的函式（transcribe / has_wake_word / is_stop_shortcut / parse_intent /
sanitize / apply_move_guard / handle_text），所以邏輯都拆成獨立函式，CLI 只是薄薄一層。

用法：
    PYTHONUTF8=1 python intent_proto.py a.wav b.wav
    PYTHONUTF8=1 python intent_proto.py --text "小車 蜂鳴器響三十秒" --text "小車 停"
    PYTHONUTF8=1 python intent_proto.py --no-llm a.wav
    PYTHONUTF8=1 python intent_proto.py --selftest
    PYTHONUTF8=1 python intent_proto.py --selftest-llm   # 需要 API key：實打 LLM 驗幾個固定句
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

# ── 常數 ─────────────────────────────────────────────
LLM_MODEL = "claude-haiku-5-5"
LLM_MAX_TOKENS = 200
# 規格要求 3 秒：超過就當聽不懂，「停」捷徑不受影響
LLM_TIMEOUT_SEC = 3.0

STT_INITIAL_PROMPT = (
    "以下是繁體中文的小車語音指令：小車，蜂鳴器響三十秒、蜂鳴器停止、"
    "直線前進、後退、左轉、右轉、停止。鏡頭往左看、鏡頭往右看、鏡頭低頭、鏡頭回正、"
    "雲台回正、拍一張照片、慢慢前進、快一點前進。"
)

# whisper 對「小車」常見的誤辨字；MVP 先用清單比對，之後再考慮拼音近似
WAKE_WORDS = ("小車", "小鞋", "小謝", "曉車", "小陳")

ALLOWED_ACTIONS = ("beep", "move", "stop", "gimbal", "photo", "unknown")

# 夾限值對應 SPEC.md「指令 JSON」表格
BEEP_MS_MIN, BEEP_MS_MAX = 0, 60000
LINEAR_MAX = 0.15
ANGULAR_MAX = 0.8
SECONDS_MIN, SECONDS_MAX = 0.5, 3.0
DEFAULT_LINEAR = 0.1
DEFAULT_ANGULAR = 0.5
DEFAULT_SECONDS = 2.0

# 雲台角度（度）。安全鐵律：tilt 大於 0 會抬頭扯掉相機 USB 線，只准 -45～0；
# ros_cmd_node.py 也會再夾一次（雙重保險）
PAN_MIN, PAN_MAX = -90, 90
TILT_MIN, TILT_MAX = -45, 0

# 規則護欄：LLM 回 move 但原文沒有這些字，就當聽不清楚。
# 起因：「鏡頭往左看」被 STT 辨識成「小車進頭往。」，LLM 卻猜成前進
MOVE_WORDS = ("前進", "後退", "往前", "往後", "向前", "向後", "前", "後", "退", "走",
              "左轉", "右轉", "轉彎", "轉圈", "轉", "倒車")

ENV_PATH = Path(__file__).resolve().parent / ".env"

SYSTEM_PROMPT = """你是 Yahboom 麥克納姆輪小車的指令解析器，把使用者的繁體中文語音辨識文字轉成 car_command 工具呼叫。
規則：
1. 蜂鳴器：action=beep，ms 是要響的毫秒數（例：「蜂鳴器響三十秒」→ ms=30000）。「停止蜂鳴器」「蜂鳴器停止」→ beep，ms=0。
2. 移動：action=move。前進 linear 為正、後退 linear 為負；左轉 angular 為正、右轉 angular 為負。
   只有句子清楚表達移動方向（前進、後退、左轉、右轉、轉圈等）才可以用 move。
   速度對照：linear 一般 0.1、「慢」「慢一點」0.05、「快」「快一點」0.15；
   angular 轉彎一般 0.5、快 0.8、慢 0.3。seconds 沒講用 2。只前進後退時 angular=0，只轉彎時 linear=0。
3. 停車：action=stop。
4. 雲台（鏡頭／雲台／攝影機／相機／「看」）：action=gimbal，pan、tilt 都是絕對角度（度）。
   往左看 pan=45、往右看 pan=-45、最左 pan=90、最右 pan=-90；
   低頭 tilt=-30、低頭到底 tilt=-45、抬頭或平視 tilt=0（不能再往上，tilt 絕不可大於 0）；回正 pan=0、tilt=0。
   只改一個軸時只填那一軸，另一軸不要填。
5. 拍照：「拍照」「拍一張」「照相」→ action=photo。
6. 不在上述能力內、或聽不懂：action=unknown，並在 reason 簡短說明原因。
7. 文字可能有語音辨識錯字，可依小車指令情境推測；但意思不完整、不通順、或無法確定時一律用 unknown，
   不要猜成 move——猜錯會讓車子亂跑。reason 一律簡短說明你的判斷。"""

CAR_COMMAND_TOOL = {
    "name": "car_command",
    "description": ("輸出一個要給小車執行的指令。move 只在句子清楚表達移動方向時使用；"
                    "鏡頭／雲台／相機／看 → gimbal；拍照 → photo；聽不清楚 → unknown"),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(ALLOWED_ACTIONS)},
            "ms": {"type": "integer", "description": "beep 響的毫秒數，0 表示停止"},
            "linear": {"type": "number",
                       "description": "move 線速度 m/s，前進正、後退負；一般 0.1、慢 0.05、快 0.15"},
            "angular": {"type": "number",
                        "description": "move 角速度 rad/s，左轉正、右轉負；一般 0.5、慢 0.3、快 0.8"},
            "seconds": {"type": "number", "description": "move 持續秒數"},
            "pan": {"type": "integer",
                    "description": "gimbal 水平絕對角度 -90～90：往左看 45、往右看 -45、最左 90、最右 -90、回正 0"},
            "tilt": {"type": "integer",
                     "description": "gimbal 垂直絕對角度 -45～0：低頭 -30、低頭到底 -45、抬頭／平視／回正 0，不可大於 0"},
            "reason": {"type": "string", "description": "判斷理由（簡短）"},
        },
        "required": ["action", "reason"],
    },
}

# 模型與 client 都很貴（載入 / 建連線），整個程序只建一次
_whisper_cache = {}
_anthropic_client = None


# ── STT ──────────────────────────────────────────────
def _get_whisper_model(model_name):
    """取得（並快取）faster-whisper 模型；import 延後到這裡，讓 --selftest 不需要裝套件。"""
    if model_name not in _whisper_cache:
        from faster_whisper import WhisperModel  # 延遲 import：只有真的做 STT 才需要
        _whisper_cache[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _whisper_cache[model_name]


def transcribe(path, model="small"):
    """把 wav 檔轉成文字。回傳 (文字, 耗時秒數)；耗時不含首次載入模型。"""
    wav_path = Path(path)
    if not wav_path.is_file():
        raise FileNotFoundError(f"找不到音檔：{wav_path}")
    whisper_model = _get_whisper_model(model)
    start = time.perf_counter()
    segments, _info = whisper_model.transcribe(
        str(wav_path), language="zh", initial_prompt=STT_INITIAL_PROMPT,
        # 實測雜音觸發溫度 fallback 反覆重試（跑了 144 秒）：固定單一溫度、不帶前文
        temperature=0.0, condition_on_previous_text=False,
    )
    # segments 是 generator，真正的辨識在迭代時才發生，所以計時要包住 join
    text = "".join(seg.text for seg in segments).strip()
    return text, time.perf_counter() - start


# ── 規則判斷 ──────────────────────────────────────────
def has_wake_word(text):
    """文字是否含喚醒詞（含常見誤辨字）。"""
    if text is None:
        return False
    return any(word in text for word in WAKE_WORDS)


def is_stop_shortcut(text):
    """含「停」且不含「蜂鳴」→ 直接停車，不經 LLM（斷網時也要能停）。"""
    if text is None:
        return False
    return "停" in text and "蜂鳴" not in text


# ── API key ──────────────────────────────────────────
def _read_env_file(env_path):
    """簡單解析 KEY=VALUE 格式的 .env；忽略空行與 # 註解，去掉值兩側引號。"""
    env_values = {}
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return env_values
    except (OSError, UnicodeDecodeError) as exc:
        print(f"警告：讀取 {env_path} 失敗：{exc}", file=sys.stderr)
        return env_values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_values[key.strip()] = value.strip().strip('"').strip("'")
    return env_values


def load_api_key():
    """先讀環境變數，再讀同目錄 .env；找不到回傳 None。絕不印出 key 內容。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key
    api_key = _read_env_file(ENV_PATH).get("ANTHROPIC_API_KEY")
    # .env.example 的佔位字串不算有效 key
    if api_key and api_key != "請填入":
        return api_key
    return None


def _get_anthropic_client():
    """建立（並快取）Anthropic client；沒 key 時丟 RuntimeError。"""
    global _anthropic_client
    if _anthropic_client is None:
        api_key = load_api_key()
        if api_key is None:
            raise RuntimeError("缺少 ANTHROPIC_API_KEY（環境變數或 voice/.env）")
        import anthropic  # 延遲 import：--no-llm / --selftest 不需要裝 SDK
        _anthropic_client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SEC)
    return _anthropic_client


# ── LLM 意圖解析 ───────────────────────────────────────
def parse_intent(text):
    """呼叫 Claude Haiku，強制用 car_command tool 回傳指令 dict。

    任何錯誤（網路 / 逾時 / API / 回應格式）都轉成 {"action": "unknown", "reason": "llm_error: ..."}，
    不往外丟例外——語音迴圈不能因為一次 LLM 失敗就整個掛掉。
    """
    try:
        import anthropic
    except ImportError as exc:
        return {"action": "unknown", "reason": f"llm_error: 未安裝 anthropic 套件（{exc}）"}
    try:
        client = _get_anthropic_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[CAR_COMMAND_TOOL],
            tool_choice={"type": "tool", "name": "car_command"},
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.APIError as exc:  # 含 APIConnectionError / APITimeoutError / APIStatusError
        return {"action": "unknown", "reason": f"llm_error: {type(exc).__name__}: {exc}"}
    except RuntimeError as exc:
        return {"action": "unknown", "reason": f"llm_error: {exc}"}

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "car_command":
            if isinstance(block.input, dict):
                return dict(block.input)
    return {"action": "unknown", "reason": "llm_error: 回應中沒有 car_command tool_use"}


# ── 安全檢查 ──────────────────────────────────────────
def _clamp(value, low, high):
    return max(low, min(high, value))


def _to_finite_float(value, default):
    """轉 float；None、非數字、NaN/Inf 一律用預設值，避免 LLM 亂回值傳到馬達。"""
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _sanitize_move(cmd):
    linear = _to_finite_float(cmd.get("linear"), 0.0)
    angular = _to_finite_float(cmd.get("angular"), 0.0)
    seconds = _to_finite_float(cmd.get("seconds"), DEFAULT_SECONDS)
    return {
        "action": "move",
        "linear": _clamp(linear, -LINEAR_MAX, LINEAR_MAX),
        "angular": _clamp(angular, -ANGULAR_MAX, ANGULAR_MAX),
        "seconds": _clamp(seconds, SECONDS_MIN, SECONDS_MAX),
    }


def _sanitize_gimbal(cmd):
    """缺的軸保持缺（交給 voice_agent 用目前角度補）；有值才夾限，無效值視同缺。"""
    result = {"action": "gimbal"}
    for key, low, high in (("pan", PAN_MIN, PAN_MAX), ("tilt", TILT_MIN, TILT_MAX)):
        angle = _to_finite_float(cmd.get(key), None)
        if angle is not None:
            result[key] = int(_clamp(round(angle), low, high))
    return result


def sanitize(cmd):
    """白名單＋夾限，回傳只含該 action 所需欄位的乾淨 dict。"""
    if not isinstance(cmd, dict):
        return {"action": "unknown", "reason": "非 dict 指令"}
    action = cmd.get("action")
    if action not in ALLOWED_ACTIONS:
        return {"action": "unknown", "reason": f"非白名單動作：{action}"}
    if action == "beep":
        ms = _to_finite_float(cmd.get("ms"), 0.0)
        return {"action": "beep", "ms": int(_clamp(round(ms), BEEP_MS_MIN, BEEP_MS_MAX))}
    if action == "move":
        return _sanitize_move(cmd)
    if action == "gimbal":
        return _sanitize_gimbal(cmd)
    if action in ("stop", "photo"):
        return {"action": action}
    reason = cmd.get("reason")
    return {"action": "unknown", "reason": str(reason) if reason is not None else ""}


def apply_move_guard(text, cmd):
    """LLM 回 move 但原文沒有任何移動字 → 改成 unknown；聽不清楚寧可不動，也不能猜成移動。"""
    if cmd.get("action") != "move":
        return cmd
    if text is not None and any(word in text for word in MOVE_WORDS):
        return cmd
    return {"action": "unknown", "reason": "guard: 沒有移動字"}


# ── 組合流程 ──────────────────────────────────────────
def handle_text(text, use_llm=True):
    """文字 → 最終指令 dict：喚醒詞 → 停車捷徑 → LLM → sanitize → 移動護欄。"""
    if not has_wake_word(text):
        return {"action": "ignore"}
    if is_stop_shortcut(text):
        return {"action": "stop", "via": "shortcut"}
    if not use_llm:
        return {"action": "unknown", "reason": "no_llm", "via": "rule"}
    start = time.perf_counter()
    raw_cmd = parse_intent(text)
    llm_sec = time.perf_counter() - start
    result = apply_move_guard(text, sanitize(raw_cmd))
    result["via"] = "llm"
    result["llm_sec"] = round(llm_sec, 3)
    return result


# ── CLI ──────────────────────────────────────────────
def _print_row(text, result, elapsed_desc):
    print(f"{text} | {json.dumps(result, ensure_ascii=False)} | {elapsed_desc}")


def _process_wav(wav_path, model_name, use_llm):
    try:
        text, stt_sec = transcribe(wav_path, model_name)
    except FileNotFoundError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return False
    except ImportError as exc:
        print(f"錯誤：未安裝 faster-whisper（python -m pip install faster-whisper）：{exc}", file=sys.stderr)
        return False
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"錯誤：辨識 {wav_path} 失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    result = handle_text(text, use_llm=use_llm)
    llm_desc = f" llm={result['llm_sec']:.2f}s" if "llm_sec" in result else ""
    _print_row(f"[{Path(wav_path).name}] {text}", result, f"stt={stt_sec:.2f}s{llm_desc}")
    return True


def _process_text(text, use_llm):
    start = time.perf_counter()
    result = handle_text(text, use_llm=use_llm)
    _print_row(text, result, f"total={time.perf_counter() - start:.2f}s")


def run_selftest():
    """不需網路：只測規則與 sanitize。"""
    assert has_wake_word("小車 蜂鳴器響三十秒")
    assert has_wake_word("曉車前進")
    assert not has_wake_word("蜂鳴器響三十秒")
    assert not has_wake_word(None)

    assert is_stop_shortcut("小車 停")
    assert is_stop_shortcut("小車停止轉動")
    assert not is_stop_shortcut("小車 蜂鳴器停止")
    assert not is_stop_shortcut("小車 前進")

    assert sanitize({"action": "beep", "ms": 999999}) == {"action": "beep", "ms": 60000}
    assert sanitize({"action": "beep", "ms": -5}) == {"action": "beep", "ms": 0}
    assert sanitize({"action": "beep", "ms": 30000, "linear": 1}) == {"action": "beep", "ms": 30000}

    moved = sanitize({"action": "move", "linear": 5, "angular": -9, "seconds": 0.1, "reason": "x"})
    assert moved == {"action": "move", "linear": 0.15, "angular": -0.8, "seconds": 0.5}, moved
    moved = sanitize({"action": "move", "linear": "abc", "seconds": float("nan")})
    assert moved == {"action": "move", "linear": 0.0, "angular": 0.0, "seconds": 2.0}, moved
    assert sanitize({"action": "move", "seconds": 99})["seconds"] == 3.0

    assert sanitize({"action": "fly"})["action"] == "unknown"
    assert sanitize("not a dict")["action"] == "unknown"
    assert sanitize({"action": "stop", "ms": 3}) == {"action": "stop"}

    assert handle_text("今天天氣好") == {"action": "ignore"}
    assert handle_text("小車 停") == {"action": "stop", "via": "shortcut"}
    _selftest_gimbal_photo()
    _selftest_move_guard()
    print("PASS")


def _selftest_gimbal_photo():
    gimbal = sanitize({"action": "gimbal", "pan": 200, "tilt": 30})
    assert gimbal == {"action": "gimbal", "pan": 90, "tilt": 0}, gimbal
    gimbal = sanitize({"action": "gimbal", "pan": -45.4, "tilt": -99})
    assert gimbal == {"action": "gimbal", "pan": -45, "tilt": -45}, gimbal
    # 只給一軸：另一軸保持缺，交給 voice_agent 補目前值
    assert sanitize({"action": "gimbal", "pan": 45}) == {"action": "gimbal", "pan": 45}
    assert sanitize({"action": "gimbal", "tilt": "abc"}) == {"action": "gimbal"}
    assert sanitize({"action": "photo", "pan": 3}) == {"action": "photo"}


def _selftest_move_guard():
    move = {"action": "move", "linear": 0.1, "angular": 0.0, "seconds": 2.0}
    # 實測誤判句：「鏡頭往左看」被辨識成「小車進頭往。」
    assert apply_move_guard("小車進頭往。", move) == {"action": "unknown", "reason": "guard: 沒有移動字"}
    assert apply_move_guard("小車進頭往", move)["action"] == "unknown"
    assert apply_move_guard("小車鏡頭往左看", move)["action"] == "unknown"
    assert apply_move_guard("小車往前走", move) == move
    assert apply_move_guard("小車左轉", move) == move
    assert apply_move_guard(None, move)["action"] == "unknown"
    gimbal = {"action": "gimbal", "pan": 45}
    assert apply_move_guard("小車鏡頭往左看", gimbal) == gimbal


# 需要 LLM 的固定案例：(文字, 預期 action)
LLM_SELFTEST_CASES = (
    ("小車進頭往", "unknown"),
    ("小車鏡頭往左看", "gimbal"),
    ("小車拍一張照片", "photo"),
    ("小車往前走", "move"),
)


def run_llm_selftest():
    """實打 LLM 驗固定句；回傳是否全部通過。"""
    all_ok = True
    for text, expected in LLM_SELFTEST_CASES:
        result = handle_text(text)
        is_ok = result.get("action") == expected
        all_ok = all_ok and is_ok
        mark = "OK " if is_ok else "NG "
        print(f"{mark}{text} → 預期 {expected} | {json.dumps(result, ensure_ascii=False)}")
    print("PASS" if all_ok else "FAIL")
    return all_ok


def build_arg_parser():
    parser = argparse.ArgumentParser(description="語音 → 文字 → 小車指令 JSON 離線原型")
    parser.add_argument("wavs", nargs="*", help="要辨識的 wav 檔")
    parser.add_argument("--text", action="append", default=[], help="跳過 STT 直接測文字（可多次）")
    parser.add_argument("--model", default="small", help="faster-whisper 模型名（預設 small）")
    parser.add_argument("--no-llm", action="store_true", help="只跑 STT 與規則，不呼叫 LLM")
    parser.add_argument("--selftest", action="store_true", help="不需網路的規則自我測試")
    parser.add_argument("--selftest-llm", action="store_true", help="實打 LLM 驗固定句（需要 API key）")
    return parser


def main():
    args = build_arg_parser().parse_args()
    if args.selftest:
        run_selftest()
        return
    if not args.wavs and not args.text and not args.selftest_llm:
        print("錯誤：請給 wav 檔或 --text（或用 --selftest）", file=sys.stderr)
        sys.exit(2)
    use_llm = not args.no_llm or args.selftest_llm
    if use_llm and load_api_key() is None:
        print("錯誤：缺少 ANTHROPIC_API_KEY。請設環境變數，或在 "
              f"{ENV_PATH} 寫入 ANTHROPIC_API_KEY=...（可參考 .env.example）；"
              "或加 --no-llm 只測 STT 與規則。", file=sys.stderr)
        sys.exit(1)
    if args.selftest_llm:
        sys.exit(0 if run_llm_selftest() else 1)

    all_ok = True
    for wav_path in args.wavs:
        all_ok = _process_wav(wav_path, args.model, use_llm) and all_ok
    for text in args.text:
        _process_text(text, use_llm)
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已中斷", file=sys.stderr)
        sys.exit(130)
