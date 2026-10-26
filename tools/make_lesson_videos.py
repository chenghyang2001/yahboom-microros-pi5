"""把每個單元做成一支 1920x1080 有聲投影片影片（videos-out/<id>.mp4）。

前置：先跑 tools/build_site.py 產生 site/lessons.json 與 site/audio/*.mp3。
用法：
  PYTHONUTF8=1 python tools/make_lesson_videos.py [--only W2] [--jobs 3] [--force]
"""
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("make_lesson_videos")

ROOT = Path(__file__).resolve().parent.parent
W, H = 1920, 1080
MARGIN = 100
BAND_H = 150
CONTENT_BOTTOM = 980
TAIL_PAD = 0.6  # 每張投影片在旁白結束後多停 0.6 秒，換頁才不會太急
PLAYLIST = "Yahboom MicroROS-Pi5 ROS 2 教材（有聲投影片）"
TITLE_PREFIX = "Yahboom MicroROS-Pi5 ROS 2 教材｜"
FFMPEG_BASE = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]

LEVEL_COLORS = {"W": (124, 77, 255), "B": (22, 150, 80), "M": (230, 128, 0), "A": (210, 40, 40)}
BG = (248, 249, 252)
TEXT = (30, 34, 45)
MUTED = (110, 118, 135)
CODE_BG = (30, 36, 48)
CODE_HEAD = (45, 52, 68)
CODE_TEXT = (232, 236, 243)
CODE_TITLE = (255, 212, 121)

TOKEN_RE = re.compile(r"[\x21-\x7e]+|\s+|.")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)\s*([^\s`]*)(.*)$")
TITLE_ATTR_RE = re.compile(r'title\s*=\s*"([^"]*)"')


# ───────────────────────── 字型與文字排版 ─────────────────────────

class Fonts:
    """每個工作執行緒各自載入字型；FreeType 物件不保證能跨執行緒共用。"""

    def __init__(self):
        windir = os.environ.get("WINDIR")
        if not windir:
            raise RuntimeError("缺少環境變數 WINDIR，找不到系統字型目錄")
        font_dir = Path(windir) / "Fonts"
        paths = {"regular": font_dir / "msjh.ttc", "bold": font_dir / "msjhbd.ttc", "mono": font_dir / "consola.ttf"}
        missing = [str(p) for p in paths.values() if not p.exists()]
        if missing:
            raise RuntimeError(f"找不到字型：{missing}")
        self.paths = paths
        self._cache = {}

    def get(self, kind, size):
        key = (kind, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(self.paths[kind]), size)
        return self._cache[key]


def wrap_text(text, font, max_width):
    """英數連續字當一個詞、中文逐字，依實際像素寬度換行。"""
    lines, line = [], ""
    for token in TOKEN_RE.findall(text.replace("\r", "")):
        if token == "\n" or "\n" in token:
            lines.append(line.rstrip())
            line = ""
            continue
        if token.isspace() and not line:
            continue
        if font.getlength(line + token) <= max_width:
            line += token
            continue
        if line.strip():
            lines.append(line.rstrip())
        line = "" if token.isspace() else token
        # 單一長詞（例如很長的指令）超寬就逐字硬切
        while font.getlength(line) > max_width and len(line) > 1:
            cut = len(line)
            while cut > 1 and font.getlength(line[:cut]) > max_width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    if line.strip():
        lines.append(line.rstrip())
    return lines


def fit_ellipsis(text, font, max_width):
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]
    return text + "…"


def draw_wrapped(draw, x, y, text, font, fill, max_width, max_lines, line_h):
    """畫多行文字，超過 max_lines 截斷並在最後一行加「…」；回傳下一個 y。"""
    lines = wrap_text(text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_ellipsis(lines[-1] + "…", font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _segments(text):
    """把程式碼行切成 ASCII／非 ASCII 段，非 ASCII（中文註解）改用中文字型，避免 consola 畫成方塊。"""
    return [(m.group(0), m.group(0).isascii()) for m in re.finditer(r"[\x00-\x7f]+|[^\x00-\x7f]+", text)]


def mixed_length(text, mono, cjk):
    return sum((mono if is_ascii else cjk).getlength(seg) for seg, is_ascii in _segments(text))


def draw_mixed(draw, x, y, text, mono, cjk, fill, max_width):
    if mixed_length(text, mono, cjk) > max_width:
        while text and mixed_length(text + "…", mono, cjk) > max_width:
            text = text[:-1]
        text += "…"
    for seg, is_ascii in _segments(text):
        font = mono if is_ascii else cjk
        draw.text((x, y), seg, font=font, fill=fill)
        x += font.getlength(seg)


# ───────────────────────── 從 body_md 摘重點 ─────────────────────────

def strip_inline_md(text):
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__|`)", "", text)
    return text.strip()


def extract_points(body_md):
    """回傳 (bullets[最多 6 條], code{title, lines} 或 None)。"""
    bullets, code = [], None
    lines = body_md.split("\n")
    i = 0
    while i < len(lines):
        fence = FENCE_RE.match(lines[i])
        if fence:
            marker = fence.group(1)[:3]
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(marker):
                j += 1
            if code is None:
                title_m = TITLE_ATTR_RE.search(fence.group(3))
                code = {"title": title_m.group(1) if title_m else fence.group(2), "lines": lines[i + 1:j]}
            i = j + 1
            continue
        bullet = BULLET_RE.match(lines[i])
        if bullet and len(bullets) < 6:
            item = strip_inline_md(bullet.group(1))
            bullets.append(item if len(item) <= 60 else item[:59] + "…")
        i += 1
    return bullets, code


# ───────────────────────── 投影片繪製 ─────────────────────────

def level_color(lesson):
    return LEVEL_COLORS.get(lesson["id"][0], (37, 99, 235))


def draw_page_number(draw, fonts, page, total):
    font = fonts.get("regular", 30)
    label = f"{page} / {total}"
    draw.text((W - MARGIN - font.getlength(label), H - 70), label, font=font, fill=MUTED)


def draw_badge(draw, x, y, text, font, fg, bg):
    pad_x, pad_y = 22, 10
    width = font.getlength(text) + pad_x * 2
    height = font.size + pad_y * 2 + 8
    draw.rounded_rectangle((x, y, x + width, y + height), radius=height // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return x + width + 20


def car_colors(needs_car):
    value = str(needs_car)
    if value.startswith("是"):
        return (155, 28, 28), (253, 226, 226)
    if value.startswith("否"):
        return (22, 101, 52), (220, 252, 231)
    return (146, 64, 14), (254, 243, 199)


def minutes_text(minutes):
    return f"{minutes} 分鐘" if isinstance(minutes, int) else str(minutes)


def render_cover(lesson, fonts, total):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    color = level_color(lesson)
    draw.rectangle((0, 0, W, BAND_H), fill=color)
    band_font = fonts.get("bold", 48)
    draw.text((MARGIN, (BAND_H - 60) // 2), f"{lesson.get('level', '')}　第 {lesson.get('unit', '')} 單元",
              font=band_font, fill=(255, 255, 255))

    y = BAND_H + 70
    id_font = fonts.get("bold", 150)
    draw.text((MARGIN, y), lesson["id"], font=id_font, fill=color)
    y += 200
    y = draw_wrapped(draw, MARGIN, y, lesson["title"], fonts.get("bold", 72), TEXT, W - 2 * MARGIN, 2, 100) + 30
    y = draw_wrapped(draw, MARGIN, y, f"學習目標：{lesson['goal']}", fonts.get("regular", 44), TEXT,
                     W - 2 * MARGIN, 3, 64) + 40
    badge_font = fonts.get("bold", 38)
    x = draw_badge(draw, MARGIN, y, f"時間：{minutes_text(lesson['minutes'])}", badge_font, TEXT, (227, 230, 238))
    fg, bg = car_colors(lesson["needs_car"])
    draw_badge(draw, x, y, f"真車：{lesson['needs_car']}", badge_font, fg, bg)
    draw_page_number(draw, fonts, 1, total)
    return img


def _draw_bullets(draw, fonts, bullets, y, bottom):
    font = fonts.get("regular", 44)
    line_h = 64
    for item in bullets:
        if y + line_h > bottom:
            break
        draw.ellipse((MARGIN, y + 22, MARGIN + 16, y + 38), fill=MUTED)
        max_lines = max(1, min(2, (bottom - y) // line_h))
        y = draw_wrapped(draw, MARGIN + 40, y, item, font, TEXT, W - 2 * MARGIN - 40, max_lines, line_h) + 14
    return y


def _draw_code(draw, fonts, code, y, bottom):
    mono, cjk = fonts.get("mono", 34), fonts.get("regular", 32)
    head_h, line_h, pad = 56, 48, 20
    code_lines = [l.rstrip() for l in code["lines"]][:8]
    room = (bottom - y - head_h - pad * 2) // line_h
    if room < 1 or not code_lines:
        return y
    if len(code_lines) > room:
        code_lines = code_lines[:room]
        code_lines[-1] = code_lines[-1] + " …" if room > 0 else "…"
    box_bottom = y + head_h + pad * 2 + line_h * len(code_lines)
    draw.rounded_rectangle((MARGIN, y, W - MARGIN, box_bottom), radius=16, fill=CODE_BG)
    draw.rounded_rectangle((MARGIN, y, W - MARGIN, y + head_h), radius=16, fill=CODE_HEAD)
    draw.rectangle((MARGIN, y + head_h - 16, W - MARGIN, y + head_h), fill=CODE_HEAD)
    if code["title"]:
        draw.text((MARGIN + 24, y + 8), fit_ellipsis(code["title"], fonts.get("bold", 32), W - 2 * MARGIN - 48),
                  font=fonts.get("bold", 32), fill=CODE_TITLE)
    ty = y + head_h + pad
    for line in code_lines:
        draw_mixed(draw, MARGIN + 30, ty, line.expandtabs(4), mono, cjk, CODE_TEXT, W - 2 * MARGIN - 60)
        ty += line_h
    return box_bottom + 20


def render_section_slide(lesson, sec, fonts, page, total):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W, BAND_H), fill=level_color(lesson))
    band_font = fonts.get("bold", 44)
    draw.text((MARGIN, (BAND_H - 56) // 2), fit_ellipsis(f"{lesson['id']} {lesson['title']}", band_font, W - 2 * MARGIN),
              font=band_font, fill=(255, 255, 255))

    y = draw_wrapped(draw, MARGIN, BAND_H + 50, f"{sec['n']}. {sec['title']}", fonts.get("bold", 72), TEXT,
                     W - 2 * MARGIN, 2, 96) + 30
    bullets, code = extract_points(sec.get("body_md", ""))
    if bullets:
        y = _draw_bullets(draw, fonts, bullets, y, CONTENT_BOTTOM)
    if code:
        y = _draw_code(draw, fonts, code, y + 10, CONTENT_BOTTOM)
    if not bullets and not code:
        narration = sec.get("narration", "")
        snippet = narration[:120] + ("…" if len(narration) > 120 else "")
        draw_wrapped(draw, MARGIN, y, snippet, fonts.get("regular", 46), MUTED, W - 2 * MARGIN,
                     max(1, (CONTENT_BOTTOM - y) // 70), 70)
    draw_page_number(draw, fonts, page, total)
    return img


# ───────────────────────── ffmpeg ─────────────────────────

def run_ffmpeg(cmd):
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg 失敗：{' '.join(cmd[:8])}…\n{e.stderr.strip()}") from e


def probe_duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        raise RuntimeError(f"無法量測音檔長度 {path}：{e}") from e


def make_segment(png, mp3, duration, out):
    total = duration + TAIL_PAD
    run_ffmpeg(FFMPEG_BASE + [
        "-loop", "1", "-i", str(png), "-i", str(mp3),
        "-af", f"apad=pad_dur={TAIL_PAD}", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(out),
    ])


def concat_segments(segments, list_path, out_path):
    # concat demuxer 的路徑要用單引號包，檔名內的單引號需跳脫
    lines = ["file '" + s.resolve().as_posix().replace("'", r"'\''") + "'" for s in segments]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    run_ffmpeg(FFMPEG_BASE + ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy",
                              "-movflags", "+faststart", str(tmp)])
    tmp.replace(out_path)


# ───────────────────────── 單元流程 ─────────────────────────

def slide_plan(lesson, audio_dir):
    """回傳 [(kind, section 或 None, mp3 路徑, 秒數)]；缺導讀語音直接丟錯。"""
    audio = lesson.get("audio", {})
    intro = audio.get("0")
    if not intro or not (audio_dir.parent / intro["file"]).exists():
        raise RuntimeError(f"{lesson['id']} 缺少單元導讀語音 {lesson['id']}-0.mp3，請先跑 build_site.py")
    plan = [("cover", None, audio_dir.parent / intro["file"], intro.get("duration"))]
    for sec in lesson["sections"]:
        entry = audio.get(str(sec["n"]))
        if not entry or not (audio_dir.parent / entry["file"]).exists():
            log.warning("%s 第 %d 節沒有語音，略過這張投影片", lesson["id"], sec["n"])
            continue
        plan.append(("section", sec, audio_dir.parent / entry["file"], entry.get("duration")))
    return plan


def is_up_to_date(out_path, plan):
    if not out_path.exists():
        return False
    newest_audio = max(mp3.stat().st_mtime for _, _, mp3, _ in plan)
    return out_path.stat().st_mtime > newest_audio


def build_lesson_video(lesson, site_dir, out_dir, force):
    """產生單一單元影片；回傳 (狀態字串, 影片秒數)。"""
    audio_dir = site_dir / "audio"
    out_path = out_dir / f"{lesson['id']}.mp4"
    plan = slide_plan(lesson, audio_dir)
    if not force and is_up_to_date(out_path, plan):
        return "skip", 0.0

    work_dir = out_dir / "_work" / lesson["id"]
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)
    fonts = Fonts()
    total_pages = len(plan)
    segments, seconds = [], 0.0
    for page, (kind, sec, mp3, duration) in enumerate(plan, 1):
        if kind == "cover":
            img = render_cover(lesson, fonts, total_pages)
        else:
            img = render_section_slide(lesson, sec, fonts, page, total_pages)
        png = work_dir / f"{page:02d}.png"
        img.save(png)
        duration = duration or probe_duration(mp3)
        seg = work_dir / f"{page:02d}.mp4"
        make_segment(png, mp3, duration, seg)
        segments.append(seg)
        seconds += duration + TAIL_PAD
    concat_segments(segments, work_dir / "list.txt", out_path)
    shutil.rmtree(work_dir, ignore_errors=True)
    return "built", seconds


def build_description(lesson):
    lines = [
        f"{lesson['id']} {lesson['title']}",
        "",
        f"學習目標：{lesson['goal']}",
        f"完成標準：{lesson['done']}",
        f"時間：{minutes_text(lesson['minutes'])}｜真車：{lesson['needs_car']}",
        "",
        "本集內容：",
        "0. 單元導讀",
    ]
    lines += [f"{s['n']}. {s['title']}" for s in lesson["sections"]]
    lines += ["", "Yahboom MicroROS-Pi5 機器人車 × ROS 2 繁體中文教材（有聲投影片版）"]
    return "\n".join(lines)


def write_manifest(lessons, out_dir):
    manifest, position = [], 0
    for lesson in lessons:
        video = out_dir / f"{lesson['id']}.mp4"
        if not video.exists():
            continue
        position += 1
        title = f"{TITLE_PREFIX}{lesson['id']} {lesson['title']}"
        manifest.append({
            "key": lesson["id"],
            "file": str(video.resolve()),
            "title": title[:100],  # YouTube 標題上限 100 字
            "description": build_description(lesson),
            "playlist": PLAYLIST,
            "position": position,
        })
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, len(manifest)


def load_lessons(site_dir):
    path = site_dir / "lessons.json"
    if not path.exists():
        raise RuntimeError(f"找不到 {path}，請先執行 build_site.py")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(f"{path} 解析失敗：{e}") from e
    if not isinstance(data, list):
        raise RuntimeError(f"{path} 格式錯誤：應為陣列")
    return data


def run(args):
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"找不到 {tool}，請確認已安裝並在 PATH 中")
    site_dir = Path(args.site).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    lessons = load_lessons(site_dir)
    targets = lessons
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        targets = [l for l in lessons if l["id"] in wanted]
        missing = wanted - {l["id"] for l in targets}
        if missing:
            raise RuntimeError(f"--only 指定的單元不在 lessons.json：{sorted(missing)}")

    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(build_lesson_video, l, site_dir, out_dir, args.force): l["id"] for l in targets}
        for future in as_completed(futures):
            lesson_id = futures[future]
            try:
                status, seconds = future.result()
            except (RuntimeError, OSError) as e:
                failures += 1
                log.error("%s 失敗：%s", lesson_id, e)
                continue
            if status == "skip":
                print(f"{lesson_id}：已是最新，跳過")
            else:
                print(f"{lesson_id}：完成（約 {seconds:.1f} 秒）")
    manifest_path, count = write_manifest(lessons, out_dir)
    work_root = out_dir / "_work"
    # 失敗單元的暫存圖留著方便除錯；全部成功才清掉
    if work_root.exists() and not any(work_root.iterdir()):
        work_root.rmdir()
    print(f"manifest：{manifest_path}（{count} 支）｜失敗 {failures} 個單元")
    return 1 if failures else 0


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="每單元產生一支有聲投影片影片")
    parser.add_argument("--site", default=str(ROOT / "site"), help="build_site.py 的輸出目錄")
    parser.add_argument("--out", default=str(ROOT / "videos-out"), help="影片輸出目錄")
    parser.add_argument("--only", help="只做指定單元（逗號分隔）")
    parser.add_argument("--jobs", type=int, default=3, help="同時處理幾個單元")
    parser.add_argument("--force", action="store_true", help="即使影片比音檔新也重做")
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except RuntimeError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
