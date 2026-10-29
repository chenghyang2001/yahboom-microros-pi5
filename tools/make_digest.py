"""把一支逐步演練錄影做成 3～5 分鐘「精華版」影片。

用法：
    PYTHONUTF8=1 python tools/make_digest.py <beats.json> --code m5 [--dry-run] [--only-tts]
    PYTHONUTF8=1 python tools/make_digest.py --selftest

每段（beat）＝ edge-tts 旁白 + 錄影畫面（前段快轉到 key、後段原速）+ 左下步驟字卡。
逐段編碼成 segNN.mp4 再用 concat demuxer 接起來，避免一條超長 filter。
輸出到 ~/Videos/pi5-drill/digest/<code>/，並在 beats.json 同目錄寫
digest_plan.json 與 description.txt。
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

VOICE = "zh-TW-HsiaoChenNeural"
WIDTH, HEIGHT, FPS = 1280, 720, 10
TAIL_PAD = 0.6          # 旁白後留白，避免下一段一開口就切畫面
FAST_RATIO = 0.35       # 段長中給快轉的比例
TITLE_SECS = 4.0
CHARS_PER_SEC = 5.5     # dry-run 估算旁白長度用（實測 +5% 語速約這個數）
TTS_RETRY, TTS_WAIT = 3, 3
FONT_BOLD = "C:/Windows/Fonts/msjhbd.ttc"
FONT_REGULAR = "C:/Windows/Fonts/msjh.ttc"
OUT_ROOT = Path.home() / "Videos" / "pi5-drill" / "digest"

# 所有片段（含片頭）編碼參數一致，concat -c copy 才接得起來
ENC_ARGS = [
    "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
    "-pix_fmt", "yuv420p", "-video_track_timescale", "10240",
    "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "48000",
]


class DigestError(Exception):
    """可預期的錯誤：印出繁中訊息後 exit 1。"""


# ───────────────────────── 純函式（selftest 會測） ─────────────────────────

def resolve_beats(beats):
    """補齊每段的 rec：沒寫就沿用上一段，第一段預設 0。"""
    resolved, last_rec = [], 0
    for idx, beat in enumerate(beats):
        if "key" not in beat or "text" not in beat:
            raise DigestError(f"第 {idx} 段 beat 缺 key 或 text：{beat}")
        item = dict(beat)
        if item.get("rec") is not None:
            last_rec = int(item["rec"])
        item["rec"] = last_rec
        item.setdefault("id", f"{idx:02d}")
        item.setdefault("label", "")
        resolved.append(item)
    return resolved


def split_fast_hold(seg_len, frm, key):
    """回傳 (fast, hold, speed)。from 缺或 key-from ≤ 1 就不快轉。"""
    if frm is None or key - frm <= 1:
        return 0.0, seg_len, 1.0
    fast = FAST_RATIO * seg_len
    hold = seg_len - fast
    speed = round((key - frm) / fast, 1)
    return fast, hold, speed


def fmt_mmss(seconds):
    """秒數 → MM:SS（無條件捨去到整秒，章節時間才不會跳到下一段）。"""
    total = int(max(0.0, seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def overlaps(a0, a1, b0, b1):
    """兩個時間區間 [a0,a1) 與 [b0,b1) 是否重疊。"""
    return a0 < b1 and b0 < a1


def blur_boxes_for(blur, src0, src1):
    """挑出與錄影區間 [src0,src1) 重疊的 blur，時間換算成段內（從 0 起）。"""
    boxes = []
    for item in blur or []:
        t0, t1 = float(item["t0"]), float(item["t1"])
        if not overlaps(t0, t1, src0, src1):
            continue
        rel0 = max(0.0, t0 - src0)
        rel1 = min(src1, t1) - src0
        boxes.append((rel0, rel1, list(item["box"])))
    return boxes


def blur_radius(width, height):
    """boxblur 半徑要小於區塊短邊一半，否則 ffmpeg 會拒絕。"""
    return max(1, min(30, min(width, height) // 2 - 1))


def even_box(box):
    """yuv420p 的 crop 要偶數座標與尺寸，並夾在畫面內。"""
    x, y, w, h = (int(v) // 2 * 2 for v in box)
    x, y = max(0, min(x, WIDTH - 2)), max(0, min(y, HEIGHT - 2))
    w, h = max(2, min(w, WIDTH - x)), max(2, min(h, HEIGHT - y))
    return x, y, w // 2 * 2, h // 2 * 2


def chapter_name(label):
    """「③ 警衛：限速閥」→「③ 警衛」；同一步驟的多段合成一個章節。"""
    return label.split("：")[0].strip() or label


def build_chapters(labels, seg_lens, offset=TITLE_SECS):
    """依各段長度算章節起點；連續同名章節只留第一筆。"""
    chapters, cursor = [["00:00", "片頭"]], offset
    for label, seg_len in zip(labels, seg_lens):
        name = chapter_name(label)
        if chapters[-1][1] != name:
            chapters.append([fmt_mmss(cursor), name])
        cursor += seg_len
    return chapters


def estimate_secs(text):
    """dry-run 用：依字數估旁白秒數。"""
    return len(text) / CHARS_PER_SEC


def plan_clip(beat, seg_len):
    """算出一段的錄影取用範圍與快轉參數。"""
    key = float(beat["key"])
    frm = beat.get("from")
    frm = float(frm) if frm is not None else None
    fast, hold, speed = split_fast_hold(seg_len, frm, key)
    start = frm if fast > 0 else key
    src_dur = (key - start) + hold
    return {"id": beat["id"], "rec": beat["rec"], "start": round(start, 1),
            "key": key, "speed": speed, "fast": round(fast, 1),
            "hold": round(hold, 1), "_fast": fast, "_hold": hold,
            "_start": start, "_src_dur": src_dur, "_seg_len": seg_len}


# ───────────────────────── 外部指令 ─────────────────────────

def run_cmd(cmd, what):
    """跑外部指令；失敗時把 stderr 末段帶進錯誤訊息。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise DigestError(f"{what}失敗：找不到指令 {cmd[0]}（{exc}）") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-1500:]
        raise DigestError(f"{what}失敗（回傳 {proc.returncode}）：\n{tail}")
    return proc.stdout


def probe_duration(path):
    """用 ffprobe 取媒體長度（秒）。"""
    out = run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=nw=1:nk=1", str(path)], f"ffprobe 讀取 {path}")
    try:
        return float(out.strip())
    except ValueError as exc:
        raise DigestError(f"ffprobe 回傳的長度無法解析：{out!r}（{path}）") from exc


def make_tts(text, rate, mp3, cache_txt):
    """產生旁白 mp3；text 與 rate 都沒變就沿用舊檔。網路不穩重試 3 次。"""
    signature = f"{rate}\n{text}"
    if mp3.exists() and cache_txt.exists() \
            and cache_txt.read_text(encoding="utf-8") == signature:
        return
    cmd = [sys.executable, "-m", "edge_tts", "--voice", VOICE, f"--rate={rate}",
           "--text", text, "--write-media", str(mp3)]
    last_err = ""
    for attempt in range(1, TTS_RETRY + 1):
        try:
            run_cmd(cmd, "edge-tts 產生旁白")
            cache_txt.write_text(signature, encoding="utf-8")
            return
        except DigestError as exc:
            last_err = str(exc)
            print(f"  edge-tts 第 {attempt} 次失敗，{TTS_WAIT} 秒後重試", file=sys.stderr)
            time.sleep(TTS_WAIT)
    raise DigestError(f"edge-tts 連續 {TTS_RETRY} 次失敗（{mp3.name}）：{last_err}")


# ───────────────────────── 字卡（Pillow） ─────────────────────────

def load_font(size, bold=True):
    """載入微軟正黑體；找不到就退回 Pillow 內建字型（中文會變方塊但不致當掉）。"""
    from PIL import ImageFont
    for path in ([FONT_BOLD, FONT_REGULAR] if bold else [FONT_REGULAR, FONT_BOLD]):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    print("警告：找不到微軟正黑體，改用內建字型", file=sys.stderr)
    return ImageFont.load_default()


def render_badge(text, path, size=30, fill=(0, 0, 0, 170), color=(255, 255, 255)):
    """畫半透明深色圓角底 + 白色粗體字，存成 RGBA PNG。"""
    from PIL import Image, ImageDraw
    font = load_font(size)
    left, top, right, bottom = font.getbbox(text)
    pad_x, pad_y = 16, 10
    width, height = right - left + pad_x * 2, bottom - top + pad_y * 2
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=12, fill=fill)
    draw.text((pad_x - left, pad_y - top), text, font=font, fill=color)
    img.save(path)


def render_title(title, subtitle, minutes, path):
    """片頭：深藍底，置中三行。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (WIDTH, HEIGHT), (18, 30, 58))
    draw = ImageDraw.Draw(img)
    lines = [(title, load_font(52, True), (255, 255, 255)),
             (subtitle, load_font(32, False), (170, 200, 255)),
             (f"約 {minutes} 分鐘看完；完整版見說明欄", load_font(30, False), (240, 210, 140))]
    gap = 34
    heights = [font.getbbox(text)[3] - font.getbbox(text)[1] for text, font, _ in lines]
    y = (HEIGHT - sum(heights) - gap * (len(lines) - 1)) // 2
    for (text, font, color), line_h in zip(lines, heights):
        left, top, right, _ = font.getbbox(text)
        draw.text(((WIDTH - (right - left)) // 2 - left, y - top), text, font=font, fill=color)
        y += line_h + gap
    img.save(path)


# ───────────────────────── 逐段編碼 ─────────────────────────

def blur_filters(boxes, cur):
    """在原始時間軸（段內從 0 起）上做 crop+boxblur+overlay。"""
    parts = []
    for i, (t0, t1, box) in enumerate(boxes):
        x, y, w, h = even_box(box)
        luma = blur_radius(w, h)
        chroma = max(1, min(luma, min(w, h) // 4 - 1))  # 色度平面只有一半大
        parts.append(
            f"[{cur}]split[bm{i}][bs{i}];[bs{i}]crop={w}:{h}:{x}:{y},"
            f"boxblur=luma_radius={luma}:luma_power=2:chroma_radius={chroma}:chroma_power=2[bb{i}];"
            f"[bm{i}][bb{i}]overlay={x}:{y}:enable='between(t,{t0:.2f},{t1:.2f})'[vb{i}]")
        cur = f"vb{i}"
    return parts, cur


def build_seg_filter(clip, boxes):
    """組一段的 filtergraph：縮放 → 打碼 → 快轉/原速 → 補滿 → 字卡。"""
    seg_len = clip["_seg_len"]
    parts, cur = blur_filters(boxes, "v0")
    parts.insert(0, f"[0:v]scale={WIDTH}:{HEIGHT},setsar=1[v0]")
    if clip["_fast"] > 0:
        fast_src = clip["key"] - clip["_start"]
        factor = clip["_fast"] / fast_src
        parts.append(
            f"[{cur}]split[fa][ho];[fa]trim=duration={fast_src:.3f},"
            f"setpts=(PTS-STARTPTS)*{factor:.6f}[fs];[fs][3:v]overlay=W-w-20:20[fb];"
            f"[ho]trim=start={fast_src:.3f},setpts=PTS-STARTPTS[hs];"
            f"[fb][hs]concat=n=2:v=1:a=0[vc]")
        cur = "vc"
    parts.append(
        f"[{cur}]fps={FPS},tpad=stop_mode=clone:stop_duration={seg_len:.2f},"
        f"trim=duration={seg_len:.3f},setpts=PTS-STARTPTS[vt];"
        f"[vt][2:v]overlay=20:H-h-20,format=yuv420p[vout]")
    parts.append(f"[1:a]apad=whole_dur={seg_len:.3f},atrim=duration={seg_len:.3f}[aout]")
    return ";".join(parts)


def encode_segment(clip, rec_path, rec_len, files, blur):
    """把一段編成 segNN.mp4。files：mp3／label／badge／out 的路徑。"""
    start = clip["_start"]
    if start >= rec_len:
        raise DigestError(f"第 {clip['id']} 段起點 {start:.1f}s 超過錄影長度 {rec_len:.1f}s")
    boxes = blur_boxes_for(blur, start, start + clip["_src_dur"])
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{clip['_src_dur'] + 0.5:.3f}", "-i", str(rec_path),
           "-i", str(files["mp3"]), "-i", str(files["label"])]
    if clip["_fast"] > 0:
        cmd += ["-i", str(files["badge"])]
    cmd += ["-filter_complex", build_seg_filter(clip, boxes),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{clip['_seg_len']:.3f}",
            *ENC_ARGS, str(files["out"])]
    run_cmd(cmd, f"ffmpeg 編碼第 {clip['id']} 段")


def encode_title(png, out):
    """片頭 4 秒，靜音。"""
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-loop", "1", "-framerate", str(FPS), "-i", str(png),
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
             "-t", f"{TITLE_SECS:.1f}", "-vf", "format=yuv420p",
             *ENC_ARGS, str(out)], "ffmpeg 編碼片頭")


def concat_segments(seg_paths, list_path, out):
    """concat demuxer 直接 copy 接起來。"""
    lines = [f"file '{p.as_posix()}'" for p in seg_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run_cmd(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c", "copy", "-movflags", "+faststart", str(out)], "ffmpeg 合併片段")


# ───────────────────────── 流程 ─────────────────────────

def load_config(beats_path):
    """讀 beats.json，展開錄影路徑並檢查存在。"""
    try:
        cfg = json.loads(beats_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DigestError(f"找不到 beats 檔：{beats_path}") from exc
    except json.JSONDecodeError as exc:
        raise DigestError(f"beats.json 格式錯誤：{exc}") from exc
    recs = [Path(p).expanduser() for p in cfg.get("recordings", [])]
    missing = [str(p) for p in recs if not p.exists()]
    if not recs or missing:
        raise DigestError(f"錄影不存在：{missing or '（recordings 是空的）'}")
    cfg["_recs"] = recs
    cfg["_beats"] = resolve_beats(cfg.get("beats", []))
    for beat in cfg["_beats"]:
        if beat["rec"] >= len(recs):
            raise DigestError(f"第 {beat['id']} 段 rec={beat['rec']} 超出 recordings 範圍")
    return cfg


def print_plan(clips, labels, est=False):
    """印出每段 from/key/秒數與總長。"""
    tag = "預估" if est else "實際"
    for clip, label in zip(clips, labels):
        mode = f"快轉 {clip['speed']}× {clip['fast']}s + 原速 {clip['hold']}s" \
            if clip["_fast"] > 0 else f"原速 {clip['hold']}s"
        print(f"  [{clip['id']}] rec{clip['rec']} from={clip['start']:>7.1f} "
              f"key={clip['key']:>7.1f} {tag} {clip['_seg_len']:5.1f}s  {mode}  {label}")
    total = TITLE_SECS + sum(c["_seg_len"] for c in clips)
    print(f"  {tag}總長：{total:.1f} 秒（{fmt_mmss(total)}，含片頭 {TITLE_SECS:.0f} 秒）")
    return total


def dry_run(cfg):
    """不呼叫 ffmpeg、不寫檔，只估算。"""
    beats = cfg["_beats"]
    clips = [plan_clip(b, estimate_secs(b["text"]) + TAIL_PAD) for b in beats]
    print(f"錄影：{[str(p) for p in cfg['_recs']]}")
    print_plan(clips, [b["label"] for b in beats], est=True)


def tts_all(cfg, work):
    """產生所有旁白，回傳各段段長（旁白長 + 留白）。"""
    seg_lens = []
    for beat in cfg["_beats"]:
        mp3 = work / f"{beat['id']}.mp3"
        make_tts(beat["text"], cfg.get("rate", "+0%"), mp3, work / f"{beat['id']}.txt")
        seg_lens.append(probe_duration(mp3) + TAIL_PAD)
    return seg_lens


def write_outputs(cfg, beats_path, clips, total):
    """寫 digest_plan.json 與 description.txt（放 beats.json 同目錄）。"""
    labels = [b["label"] for b in cfg["_beats"]]
    chapters = build_chapters(labels, [c["_seg_len"] for c in clips])
    public = [{k: v for k, v in c.items() if not k.startswith("_")} for c in clips]
    plan = {"chapters": chapters, "clips": public, "total": round(total, 1)}
    out_dir = beats_path.parent
    (out_dir / "digest_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    minutes = round(total / 60)
    desc = [f"{cfg.get('subtitle', '')}，{minutes} 分鐘精華版。", "",
            f"完整版（約 {cfg.get('full_minutes', '?')} 分鐘）：{cfg.get('full_version', '')}", ""]
    desc += [f"{t} {name}" for t, name in chapters]
    (out_dir / "description.txt").write_text("\n".join(desc) + "\n", encoding="utf-8")


def build_video(cfg, beats_path, code, work, seg_lens):
    """逐段編碼 + 片頭 + 合併。"""
    clips = [plan_clip(b, s) for b, s in zip(cfg["_beats"], seg_lens)]
    total = print_plan(clips, [b["label"] for b in cfg["_beats"]])
    rec_lens = [probe_duration(p) for p in cfg["_recs"]]
    render_title(cfg.get("title", ""), cfg.get("subtitle", ""), round(total / 60), work / "title.png")
    encode_title(work / "title.png", work / "title.mp4")
    seg_paths = [work / "title.mp4"]
    for beat, clip in zip(cfg["_beats"], clips):
        nn = beat["id"]
        files = {"mp3": work / f"{nn}.mp3", "label": work / f"label{nn}.png",
                 "badge": work / f"badge{nn}.png", "out": work / f"seg{nn}.mp4"}
        render_badge(beat["label"], files["label"])
        if clip["_fast"] > 0:
            render_badge(f"快轉 {round(clip['speed'])}×", files["badge"], size=24,
                         fill=(200, 90, 0, 190))
        print(f"  編碼第 {nn} 段…")
        encode_segment(clip, cfg["_recs"][beat["rec"]], rec_lens[beat["rec"]], files,
                       cfg.get("blur"))
        seg_paths.append(files["out"])
    final = work.parent / f"{code}-digest.mp4"
    concat_segments(seg_paths, work / "concat.txt", final)
    write_outputs(cfg, beats_path, clips, total)
    print(f"完成：{final}")


def run(args):
    """依參數分派 dry-run／only-tts／完整流程。"""
    beats_path = Path(args.beats).expanduser().resolve()
    cfg = load_config(beats_path)
    if args.dry_run:
        dry_run(cfg)
        return
    work = OUT_ROOT / args.code / "work"
    work.mkdir(parents=True, exist_ok=True)
    seg_lens = tts_all(cfg, work)
    if args.only_tts:
        for beat, seg_len in zip(cfg["_beats"], seg_lens):
            print(f"  [{beat['id']}] 旁白 {seg_len - TAIL_PAD:5.1f}s  {beat['label']}")
        total = TITLE_SECS + sum(seg_lens)
        print(f"  總長：{total:.1f} 秒（{fmt_mmss(total)}，含片頭與每段留白）")
        return
    build_video(cfg, beats_path, args.code, work, seg_lens)


# ───────────────────────── selftest ─────────────────────────

def selftest():
    """不需錄影與網路，只測純函式。"""
    fast, hold, speed = split_fast_hold(20.0, 100.0, 170.0)
    assert abs(fast - 7.0) < 1e-9 and abs(hold - 13.0) < 1e-9 and speed == 10.0
    assert split_fast_hold(10.0, None, 50.0) == (0.0, 10.0, 1.0)
    assert split_fast_hold(10.0, 49.5, 50.0) == (0.0, 10.0, 1.0)   # key-from ≤ 1
    assert fmt_mmss(0) == "00:00" and fmt_mmss(65.9) == "01:05" and fmt_mmss(600) == "10:00"
    assert overlaps(0, 10, 9, 20) and not overlaps(0, 10, 10, 20)
    boxes = blur_boxes_for([{"t0": 655, "t1": 690, "box": [1, 2, 3, 4]},
                            {"t0": 2110, "t1": 99999, "box": [5, 6, 7, 8]}], 600, 700)
    assert boxes == [(55.0, 90.0, [1, 2, 3, 4])]
    assert blur_boxes_for(None, 0, 10) == []
    assert blur_radius(640, 490) == 30 and blur_radius(20, 40) == 9
    assert even_box([457, 171, 641, 491]) == (456, 170, 640, 490)
    beats = resolve_beats([{"key": 1, "text": "a", "rec": 1}, {"key": 2, "text": "b"},
                           {"key": 3, "text": "c", "rec": 0}])
    assert [b["rec"] for b in beats] == [1, 1, 0] and beats[1]["id"] == "01"
    assert resolve_beats([{"key": 1, "text": "a"}])[0]["rec"] == 0
    chapters = build_chapters(["開場", "③ 警衛：甲", "③ 警衛：乙", "總結"], [10, 20, 30, 5])
    assert chapters == [["00:00", "片頭"], ["00:04", "開場"], ["00:14", "③ 警衛"],
                        ["01:04", "總結"]]
    clip = plan_clip({"id": "04", "rec": 0, "key": 1653.3, "text": "x"}, 12.0)
    assert clip["start"] == 1653.3 and clip["fast"] == 0.0 and clip["_src_dur"] == 12.0
    try:
        resolve_beats([{"text": "沒有 key"}])
        raise AssertionError("缺 key 應該報錯")
    except DigestError:
        pass
    print("selftest OK")


def parse_args():
    parser = argparse.ArgumentParser(description="把逐步演練錄影做成精華版影片")
    parser.add_argument("beats", nargs="?", help="beats.json 路徑")
    parser.add_argument("--code", help="輸出代號，例如 m5")
    parser.add_argument("--dry-run", action="store_true", help="只估算，不編碼")
    parser.add_argument("--only-tts", action="store_true", help="只產生旁白 mp3")
    parser.add_argument("--selftest", action="store_true", help="跑內建自我測試")
    return parser


def main():
    parser = parse_args()
    args = parser.parse_args()
    try:
        if args.selftest:
            selftest()
            return
        if not args.beats or (not args.code and not args.dry_run):
            parser.error("需要 <beats.json> 與 --code（--dry-run 可省略 --code）")
        run(args)
    except DigestError as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
