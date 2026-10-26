"""把 lessons/*.md 建成互動學習網站（site/），並用 edge-tts 為每節旁白產生中文語音。

用法：
  PYTHONUTF8=1 python tools/build_site.py [--lessons lessons] [--out site] [--no-tts] [--only W2]
"""
import argparse
import asyncio
import hashlib
import html
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lesson_parser  # noqa: E402

try:
    import markdown
except ImportError:
    print("錯誤：缺少 markdown 套件，請先執行 python -m pip install markdown", file=sys.stderr)
    sys.exit(1)

log = logging.getLogger("build_site")

ROOT = Path(__file__).resolve().parent.parent
VOICE = "zh-TW-HsiaoChenNeural"
RATE = "+0%"
TTS_CONCURRENCY = 4
TTS_RETRIES = 3
TTS_RETRY_DELAY = 2
SITE_TITLE = "Yahboom MicroROS-Pi5 × ROS 2 學習地圖"
LEVELS = [("W", "暖身"), ("B", "初級"), ("M", "中級"), ("A", "高級")]
ADMONITION_LABELS = {"tip": "💡 小提示", "warn": "⚠️ 注意", "info": "ℹ️ 補充"}
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
FENCE_OPEN_RE = re.compile(r"^(\s*)(```+|~~~+)\s*([^\s`]*)(.*)$")
ADMON_OPEN_RE = re.compile(r"^:::\s*(tip|warn|info)\b\s*(.*)$")
TITLE_ATTR_RE = re.compile(r'title\s*=\s*"([^"]*)"')

esc = html.escape


# ───────────────────────── Markdown 轉換 ─────────────────────────

class _Stash:
    """先把程式碼區塊與提示框換成佔位符，避免 markdown 套件把裡面的內容再轉一次。"""

    def __init__(self):
        self.items = {}

    def put(self, fragment):
        key = f"YMPPH{len(self.items)}XQ"
        self.items[key] = fragment
        return f"\n\n{key}\n\n"

    def restore(self, text):
        # 佔位符可能巢狀（提示框裡有程式碼），反覆替換到沒有為止
        for _ in range(5):
            if "YMPPH" not in text:
                break
            for key, fragment in self.items.items():
                text = text.replace(f"<p>{key}</p>", fragment).replace(key, fragment)
        return text


def _render_code_block(info_lang, info_rest, code_lines):
    title_match = TITLE_ATTR_RE.search(info_rest)
    title = title_match.group(1) if title_match else ""
    label = title or info_lang
    lang_class = f' class="language-{esc(info_lang)}"' if info_lang else ""
    code = esc("\n".join(code_lines))
    title_html = f'<span class="code-title">{esc(label)}</span>' if label else '<span class="code-title"></span>'
    return (
        f'<div class="code-block">\n<div class="code-head">{title_html}'
        f'<button class="copy-btn" type="button">複製</button></div>\n'
        f"<pre><code{lang_class}>{code}</code></pre>\n</div>"
    )


def _stash_code_blocks(md_text, stash):
    out, lines, i = [], md_text.split("\n"), 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        marker, lang, rest = m.group(2), m.group(3), m.group(4)
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith(marker[:3]):
            j += 1
        out.append(stash.put(_render_code_block(lang, rest, lines[i + 1:j])))
        i = j + 1
    return "\n".join(out)


def _md(text):
    return markdown.markdown(text, extensions=["fenced_code", "tables", "sane_lists"])


def _stash_admonitions(md_text, stash):
    out, lines, i = [], md_text.split("\n"), 0
    while i < len(lines):
        m = ADMON_OPEN_RE.match(lines[i].strip())
        if not m:
            out.append(lines[i])
            i += 1
            continue
        kind, custom_title = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(lines) and lines[j].strip() != ":::":
            j += 1
        inner_html = _md("\n".join(lines[i + 1:j]))
        label = custom_title or ADMONITION_LABELS[kind]
        out.append(stash.put(
            f'<div class="callout callout-{kind}"><div class="callout-title">{esc(label)}</div>\n{inner_html}\n</div>'
        ))
        i = j + 1
    return "\n".join(out)


def render_markdown(md_text):
    """講義 markdown → HTML：程式碼區塊加標籤與複製鈕、:::tip/warn/info 轉提示框。"""
    stash = _Stash()
    text = _stash_code_blocks(md_text, stash)
    text = _stash_admonitions(text, stash)
    return stash.restore(_md(text))


# ───────────────────────── 語音 ─────────────────────────

def text_sha1(text):
    return hashlib.sha1(f"{VOICE}|{RATE}|{text}".encode("utf-8")).hexdigest()


def intro_text(lesson):
    goal = lesson["goal"].rstrip("。")
    done = lesson["done"].rstrip("。")
    unit_no = lesson_parser.unit_number(lesson["id"])
    return f"這是{lesson['level']}第 {unit_no} 單元：{lesson['title']}。學習目標：{goal}。完成標準：{done}。"


def audio_jobs(lesson):
    """回傳 [(n, 檔名, 文字)]；n=0 是單元導讀。"""
    jobs = [(0, f"{lesson['id']}-0.mp3", intro_text(lesson))]
    for sec in lesson["sections"]:
        if sec["narration"]:
            jobs.append((sec["n"], f"{lesson['id']}-{sec['n']}.mp3", sec["narration"]))
    return jobs


def probe_duration(path):
    """用 ffprobe 量音檔秒數；沒有 ffprobe 或失敗回 None（不讓建站失敗）。"""
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
        )
        return round(float(result.stdout.strip()), 3)
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        log.warning("無法量測音檔長度 %s：%s", path, e)
        return None


def load_cache(cache_path):
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("語音快取 %s 讀取失敗，視為空快取：%s", cache_path, e)
        return {}


async def _synth_one(text, out_path, sem):
    import aiohttp
    import edge_tts

    async with sem:
        for attempt in range(1, TTS_RETRIES + 1):
            tmp_path = out_path.with_name(out_path.stem + ".part.mp3")
            try:
                await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(tmp_path))
                if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                    raise RuntimeError("edge-tts 產出空檔")
                tmp_path.replace(out_path)
                return True
            except (edge_tts.exceptions.EdgeTTSException, aiohttp.ClientError, asyncio.TimeoutError,
                    OSError, RuntimeError) as e:
                log.warning("TTS 失敗（%s，第 %d/%d 次）：%s", out_path.name, attempt, TTS_RETRIES, e)
                tmp_path.unlink(missing_ok=True)
                if attempt < TTS_RETRIES:
                    await asyncio.sleep(TTS_RETRY_DELAY)
    return False


async def _synth_all(pending):
    sem = asyncio.Semaphore(TTS_CONCURRENCY)
    results = await asyncio.gather(*(_synth_one(text, path, sem) for path, text in pending))
    return dict(zip((p for p, _ in pending), results))


def build_audio(lessons, selected_ids, audio_dir, use_tts):
    """產生／沿用語音，回傳 ({lesson_id: {n: {file, duration}}}, 新產生數, 失敗數)。"""
    audio_dir.mkdir(parents=True, exist_ok=True)
    cache_path = audio_dir / "cache.json"
    cache = load_cache(cache_path)

    pending = []
    for lesson in lessons:
        if lesson["id"] not in selected_ids:
            continue
        for _, name, text in audio_jobs(lesson):
            path = audio_dir / name
            entry = cache.get(name, {})
            if path.exists() and entry.get("sha1") == text_sha1(text):
                continue
            if use_tts:
                pending.append((path, text))
            elif path.exists():
                log.warning("%s 的旁白已改但 --no-tts，沿用舊語音", name)

    created, failed = 0, 0
    if pending:
        print(f"產生語音 {len(pending)} 段（並行 {TTS_CONCURRENCY}）…")
        for path, ok in asyncio.run(_synth_all(pending)).items():
            text = dict(pending)[path]
            if ok:
                created += 1
                cache[path.name] = {"sha1": text_sha1(text), "duration": probe_duration(path)}
            else:
                failed += 1
                log.error("語音產生失敗（已重試 %d 次）：%s", TTS_RETRIES, path.name)

    audio_map = {}
    for lesson in lessons:
        entries = {}
        for n, name, _ in audio_jobs(lesson):
            path = audio_dir / name
            if not path.exists():
                continue
            entry = cache.setdefault(name, {})
            if entry.get("duration") is None:
                entry["duration"] = probe_duration(path)
            entries[n] = {"file": f"audio/{name}", "duration": entry.get("duration")}
        audio_map[lesson["id"]] = entries

    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        log.error("無法寫入語音快取 %s：%s", cache_path, e)
    return audio_map, created, failed


# ───────────────────────── HTML 片段 ─────────────────────────

def page_shell(title, body, body_class=""):
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<link rel="stylesheet" href="style.css">
</head>
<body class="{body_class}">
{body}
<script src="app.js"></script>
</body>
</html>
"""


def minutes_text(minutes):
    if isinstance(minutes, int):
        if minutes >= 60 and minutes % 60 == 0:
            return f"{minutes // 60} 小時"
        return f"{minutes} 分鐘"
    return str(minutes)


def car_badge(needs_car):
    value = str(needs_car)
    if value.startswith("是"):
        cls = "car-yes"
    elif value.startswith("否"):
        cls = "car-no"
    else:
        cls = "car-part"
    return f'<span class="badge {cls}">🚗 真車：{esc(value)}</span>'


def youtube_embed(video_id, title):
    if not YT_ID_RE.match(video_id):
        log.warning("略過格式不正確的 YouTube ID：%s", video_id)
        return ""
    vid = esc(video_id)
    return (
        f'<figure class="yt" data-yt="{vid}">'
        f'<button class="yt-thumb" type="button" aria-label="播放影片：{esc(title)}">'
        f'<img src="https://i.ytimg.com/vi/{vid}/hqdefault.jpg" alt="" loading="lazy">'
        f'<span class="yt-play">▶</span></button>'
        f"<figcaption>{esc(title)}</figcaption></figure>"
    )


def read_optional_json(path, expected_type):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("%s 讀取失敗，略過：%s", path, e)
        return None
    if not isinstance(data, expected_type):
        log.warning("%s 格式不符（應為 %s），略過", path, expected_type.__name__)
        return None
    return data


def extract_architecture(plan_path):
    """取 LEARNING-PLAN.md 第一個程式碼區塊（三層架構 ASCII 圖）。"""
    if not plan_path.exists():
        return ""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("讀不到 %s：%s", plan_path, e)
        return ""
    m = re.search(r"^```[^\n]*\n(.*?)^```", text, re.S | re.M)
    return m.group(1).rstrip() if m else ""


# ───────────────────────── 單元頁 ─────────────────────────

def render_demos(demos):
    if not demos:
        return ""
    items = "".join(f'<li><a href="https://youtu.be/{esc(d["youtube"])}" target="_blank" rel="noopener">▶ {esc(d.get("title", "示範影片"))}</a>（YouTube 私人影片，需登入擁有者帳號觀看）</li>' for d in demos if isinstance(d, dict) and YT_ID_RE.match(d.get("youtube", "")))
    if not items:
        return ""
    return f'<section class="demos card-box"><h2>🎬 先看示範（電腦模擬實錄）</h2><ul class="demo-links">{items}</ul></section>'


def render_head(lesson, audio):
    intro = audio.get(0)
    intro_attr = f' data-audio="{esc(intro["file"])}"' if intro else ""
    return f"""<section class="lesson-head card-box" id="sec-0"{intro_attr}>
<div class="eyebrow"><span class="badge level-{esc(lesson['id'][0])}">{esc(lesson['level'])}</span>
<span class="unit-id">{esc(lesson['id'])}</span></div>
<h1>{esc(lesson['title'])}</h1>
<div class="meta"><span class="badge">⏱ {esc(minutes_text(lesson['minutes']))}</span>{car_badge(lesson['needs_car'])}</div>
<dl class="goal">
<dt>🎯 學習目標</dt><dd>{esc(lesson['goal'])}</dd>
<dt>✅ 完成標準</dt><dd>{esc(lesson['done'])}</dd>
</dl>
<div class="player-bar">
<button class="btn primary" id="play-all" type="button">▶ 全部播放</button>
<label class="rate">播放速度
<select id="rate">
<option value="0.8">0.8×</option><option value="1" selected>1×</option>
<option value="1.25">1.25×</option><option value="1.5">1.5×</option>
</select></label>
<span class="now-playing" id="now-playing" aria-live="polite"></span>
</div>
</section>"""


def render_section(lesson, sec, audio):
    entry = audio.get(sec["n"])
    if entry:
        audio_attr = f' data-audio="{esc(entry["file"])}"'
        button = '<button class="btn play-one" type="button">▶ 播放旁白</button>'
    else:
        audio_attr = ""
        button = '<span class="no-audio">（尚無語音）</span>'
    narration = ""
    if sec["narration"]:
        narration = (f'<details class="narration"><summary>🔊 旁白文字</summary>'
                     f'<p>{esc(sec["narration"])}</p></details>')
    return f"""<section class="sec card-box" id="sec-{sec['n']}"{audio_attr}>
<div class="sec-head"><h2>{sec['n']}. {esc(sec['title'])}</h2>{button}</div>
{narration}
<div class="md">{render_markdown(sec['body_md'])}</div>
</section>"""


def render_videos(lesson):
    items = "".join(youtube_embed(v, f"官方影片 {i}") for i, v in enumerate(lesson["videos"], 1))
    if not items:
        return ""
    return f'<section class="videos card-box"><h2>📺 官方影片</h2><div class="yt-grid">{items}</div></section>'


def render_quiz(quiz):
    if not quiz:
        return ""
    items = []
    for i, item in enumerate(quiz, 1):
        opts = "".join(
            f'<button class="opt" type="button" data-i="{j}">{esc(str(o))}</button>'
            for j, o in enumerate(item["options"])
        )
        items.append(
            f'<div class="quiz-item" data-answer="{int(item["answer"])}">'
            f'<p class="q">{i}. {esc(str(item["q"]))}</p><div class="opts">{opts}</div>'
            f'<p class="explain" hidden></p><template class="explain-text">{esc(str(item["explain"]))}</template></div>'
        )
    return (f'<section class="quiz card-box" id="quiz"><h2>📝 小測驗</h2>{"".join(items)}'
            f'<p class="quiz-score">得分：<span class="score">0</span> / {len(quiz)}</p></section>')


def render_lesson_page(lesson, prev_lesson, next_lesson, audio, demos):
    nav_prev = (f'<a class="btn" href="{esc(prev_lesson["id"])}.html">← {esc(prev_lesson["id"])} 上一單元</a>'
                if prev_lesson else '<span></span>')
    nav_next = (f'<a class="btn" href="{esc(next_lesson["id"])}.html">{esc(next_lesson["id"])} 下一單元 →</a>'
                if next_lesson else '<span></span>')
    sections = "\n".join(render_section(lesson, s, audio) for s in lesson["sections"])
    body = f"""<header class="topbar"><a href="index.html">← 學習地圖</a><span>{esc(lesson['id'])}</span></header>
<main class="container lesson" data-lesson-id="{esc(lesson['id'])}">
{render_demos(demos)}
{render_head(lesson, audio)}
{sections}
{render_videos(lesson)}
{render_quiz(lesson['quiz'])}
<footer class="lesson-foot card-box">
<button class="btn primary" id="mark-done" type="button">✔ 標記為完成</button>
<nav class="pager">{nav_prev}{nav_next}</nav>
</footer>
</main>
<audio id="player" preload="none"></audio>"""
    return page_shell(f"{lesson['id']} {lesson['title']}｜{SITE_TITLE}", body, "page-lesson")


# ───────────────────────── 首頁 ─────────────────────────

def render_index(lessons, links, architecture):
    blocks = []
    for key, name in LEVELS:
        group = [l for l in lessons if l["id"].startswith(key)]
        if group:
            cards = "".join(
                f'<a class="unit-card" href="{esc(l["id"])}.html" data-id="{esc(l["id"])}">'
                f'<span class="unit-id">{esc(l["id"])}</span><span class="done-mark" aria-label="已完成">✔</span>'
                f'<strong>{esc(l["title"])}</strong>'
                f'<span class="meta"><span class="badge">⏱ {esc(minutes_text(l["minutes"]))}</span>'
                f'{car_badge(l["needs_car"])}</span></a>'
                for l in group
            )
        else:
            cards = '<p class="muted">（講義撰寫中）</p>'
        blocks.append(f'<section class="level card-box level-{key}"><h2>{name}</h2><div class="card-grid">{cards}</div></section>')

    links_html = ""
    if links:
        groups = {}
        for item in links:
            # 只收 http(s)，避免 javascript: 之類的網址被塞進連結
            if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://")):
                groups.setdefault(item.get("group", "其他"), []).append(item)
        parts = []
        for group_name, items in groups.items():
            lis = "".join(
                f'<li><a href="{esc(i["url"])}" target="_blank" rel="noopener">{esc(i.get("title", i["url"]))}</a>'
                + (f'<span class="muted">－{esc(i["desc"])}</span>' if i.get("desc") else "")
                + "</li>"
                for i in items
            )
            parts.append(f"<h3>{esc(group_name)}</h3><ul class=\"links\">{lis}</ul>")
        links_html = f'<section class="card-box"><h2>📚 學習資源</h2>{"".join(parts)}</section>'

    arch_html = ""
    if architecture:
        arch_html = (f'<section class="card-box"><h2>🧩 這台車的架構</h2>'
                     f'<div class="pre-wrap"><pre class="arch">{esc(architecture)}</pre></div></section>')

    body = f"""<header class="hero"><div class="container">
<h1>{esc(SITE_TITLE)}</h1>
<div class="progress"><div class="progress-bar"><span id="progress-fill"></span></div>
<span id="progress-text" data-total="{len(lessons)}">0 / {len(lessons)} 單元完成</span></div>
</div></header>
<main class="container index">
{"".join(blocks)}
{links_html}
{arch_html}
</main>"""
    return page_shell(SITE_TITLE, body, "page-index")


# ───────────────────────── 靜態資源 ─────────────────────────

STYLE_CSS = r"""/* 由 tools/build_site.py 產生，請改產生器而不是改這個檔 */
:root {
  --bg: #f6f7fb; --surface: #ffffff; --text: #1f2430; --muted: #667085; --border: #e3e6ee;
  --accent: #2563eb; --accent-text: #ffffff; --highlight: #fff7d6;
  --code-bg: #1e2430; --code-text: #e8ecf3; --code-head: #2b3242;
  --tip-bg: #e9f8ef; --tip-border: #22a05a; --warn-bg: #fff3e6; --warn-border: #e07b00;
  --info-bg: #e8f1ff; --info-border: #2563eb;
  --ok: #16a34a; --bad: #dc2626;
  --lv-W: #8b5cf6; --lv-B: #16a34a; --lv-M: #ea8a00; --lv-A: #dc2626;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151c; --surface: #1b1f29; --text: #e6e9f0; --muted: #9aa3b5; --border: #2c3240;
    --accent: #5b8cff; --highlight: #3a3418;
    --code-bg: #0d1017; --code-head: #1c2230;
    --tip-bg: #12301f; --warn-bg: #3a2610; --info-bg: #142440;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--text); line-height: 1.7;
  font-family: "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif; overflow-x: hidden; }
a { color: var(--accent); }
img { max-width: 100%; height: auto; }
.container { max-width: 900px; margin: 0 auto; padding: 0 16px 48px; }
.muted { color: var(--muted); }
.card-box { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin: 16px 0; }
.hero { background: linear-gradient(135deg, #1e3a8a, #2563eb); color: #fff; padding: 28px 0 20px; }
.hero h1 { margin: 0 0 12px; font-size: clamp(1.3rem, 4vw, 2rem); }
.progress { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.progress-bar { flex: 1 1 200px; height: 12px; background: rgba(255,255,255,.3); border-radius: 6px; overflow: hidden; }
.progress-bar span { display: block; height: 100%; width: 0; background: #facc15; transition: width .3s; }
.level h2 { margin-top: 0; border-left: 6px solid var(--lv-W); padding-left: 10px; }
.level-B h2 { border-color: var(--lv-B); } .level-M h2 { border-color: var(--lv-M); } .level-A h2 { border-color: var(--lv-A); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.unit-card { position: relative; display: flex; flex-direction: column; gap: 6px; padding: 14px; border: 1px solid var(--border);
  border-radius: 10px; text-decoration: none; color: var(--text); background: var(--bg); }
.unit-card:hover { border-color: var(--accent); }
.unit-card.done { border-color: var(--ok); }
.unit-id { font-weight: 700; color: var(--accent); }
.done-mark { position: absolute; top: 10px; right: 12px; color: var(--ok); font-weight: 700; visibility: hidden; }
.unit-card.done .done-mark { visibility: visible; }
.meta { display: flex; flex-wrap: wrap; gap: 6px; }
.badge { display: inline-block; font-size: .8rem; padding: 2px 8px; border-radius: 999px; background: var(--border); color: var(--text); }
.car-yes { background: #fde2e2; color: #9b1c1c; } .car-no { background: #dcfce7; color: #166534; } .car-part { background: #fef3c7; color: #92400e; }
.level-W.badge { background: var(--lv-W); color: #fff; } .level-B.badge { background: var(--lv-B); color: #fff; }
.level-M.badge { background: var(--lv-M); color: #fff; } .level-A.badge { background: var(--lv-A); color: #fff; }
.links li { margin: 4px 0; overflow-wrap: anywhere; }
.pre-wrap { overflow-x: auto; }
pre.arch { font-family: Consolas, "Courier New", monospace; font-size: .8rem; line-height: 1.35; margin: 0; }
.topbar { position: sticky; top: 0; z-index: 10; display: flex; justify-content: space-between; padding: 10px 16px;
  background: var(--surface); border-bottom: 1px solid var(--border); }
.topbar a { text-decoration: none; font-weight: 600; }
.lesson-head h1 { margin: 6px 0; font-size: clamp(1.3rem, 4.5vw, 1.9rem); line-height: 1.35; }
.eyebrow { display: flex; gap: 8px; align-items: center; }
.goal { margin: 12px 0; } .goal dt { font-weight: 700; } .goal dd { margin: 0 0 8px 0; }
.player-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.now-playing { color: var(--muted); font-size: .9rem; }
.btn { display: inline-block; border: 1px solid var(--border); background: var(--surface); color: var(--text); padding: 6px 14px;
  border-radius: 8px; cursor: pointer; font: inherit; text-decoration: none; }
.btn:hover { border-color: var(--accent); }
.btn.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); }
select { font: inherit; padding: 4px; border-radius: 6px; }
.sec-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px; }
.sec-head h2 { margin: 0; font-size: 1.25rem; }
.sec.playing, .lesson-head.playing { background: var(--highlight); border-color: var(--lv-M); }
.no-audio { color: var(--muted); font-size: .85rem; }
.narration { margin: 8px 0; color: var(--muted); }
.narration summary { cursor: pointer; }
.md { overflow-wrap: anywhere; }
.md table { display: block; overflow-x: auto; border-collapse: collapse; max-width: 100%; }
.md th, .md td { border: 1px solid var(--border); padding: 6px 10px; }
.md code { font-family: Consolas, "Courier New", monospace; background: var(--border); padding: 0 4px; border-radius: 4px; }
.code-block { margin: 12px 0; border-radius: 10px; overflow: hidden; background: var(--code-bg); }
.code-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 4px 10px; background: var(--code-head); }
.code-title { color: #ffd479; font-size: .85rem; }
.copy-btn { background: transparent; color: var(--code-text); border: 1px solid #556; border-radius: 6px; padding: 2px 10px; cursor: pointer; font: inherit; font-size: .8rem; }
.code-block pre { margin: 0; padding: 12px; overflow-x: auto; }
.code-block code { background: none; color: var(--code-text); padding: 0; white-space: pre; }
.callout { border-left: 5px solid var(--info-border); background: var(--info-bg); padding: 8px 14px; border-radius: 8px; margin: 12px 0; }
.callout-tip { border-color: var(--tip-border); background: var(--tip-bg); }
.callout-warn { border-color: var(--warn-border); background: var(--warn-bg); }
.callout-title { font-weight: 700; }
.callout p { margin: 4px 0; }
.yt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.yt { margin: 0; }
.yt-thumb { position: relative; display: block; width: 100%; aspect-ratio: 16 / 9; padding: 0; border: 0; cursor: pointer; background: #000; border-radius: 8px; overflow: hidden; }
.yt-thumb img { width: 100%; height: 100%; object-fit: cover; }
.yt-play { position: absolute; inset: 0; margin: auto; width: 64px; height: 44px; border-radius: 12px; background: rgba(220,0,0,.9);
  color: #fff; font-size: 22px; display: flex; align-items: center; justify-content: center; }
.yt iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 8px; }
.yt figcaption { font-size: .85rem; color: var(--muted); }
.quiz-item { margin: 12px 0; }
.quiz-item .q { font-weight: 700; margin: 0 0 6px; }
.opts { display: flex; flex-direction: column; gap: 6px; }
.opt { text-align: left; border: 1px solid var(--border); background: var(--bg); color: var(--text); padding: 8px 12px; border-radius: 8px; cursor: pointer; font: inherit; }
.opt.correct { border-color: var(--ok); background: color-mix(in srgb, var(--ok) 18%, transparent); }
.opt.wrong { border-color: var(--bad); background: color-mix(in srgb, var(--bad) 18%, transparent); }
.explain { margin: 6px 0 0; }
.explain.ok { color: var(--ok); } .explain.bad { color: var(--bad); }
.quiz-score { font-weight: 700; }
.lesson-foot { display: flex; flex-direction: column; gap: 12px; }
.lesson-foot.is-done #mark-done { background: var(--ok); border-color: var(--ok); }
.pager { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.toast { position: fixed; left: 16px; right: 16px; bottom: 16px; max-width: 480px; margin: 0 auto; background: #333; color: #fff;
  padding: 10px 14px; border-radius: 8px; z-index: 50; text-align: center; }
"""

APP_JS = r"""// 由 tools/build_site.py 產生，請改產生器而不是改這個檔
(function () {
  'use strict';
  var PREFIX = 'ymp5-';

  // 私密視窗或封鎖儲存時 localStorage 會丟例外，一律吞掉讓頁面照常運作
  function storeGet(key) {
    try { return window.localStorage.getItem(PREFIX + key); } catch (e) { return null; }
  }
  function storeSet(key, value) {
    try {
      if (value === null) { window.localStorage.removeItem(PREFIX + key); }
      else { window.localStorage.setItem(PREFIX + key, value); }
    } catch (e) { /* 無法儲存時只是不記住 */ }
  }
  function isDone(id) { return storeGet('done-' + id) === '1'; }

  function toast(msg) {
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  // ── 首頁：完成打勾與進度條 ──
  function initIndex() {
    var cards = document.querySelectorAll('.unit-card');
    var doneCount = 0;
    cards.forEach(function (card) {
      if (isDone(card.dataset.id)) { card.classList.add('done'); doneCount++; }
    });
    var text = document.getElementById('progress-text');
    var fill = document.getElementById('progress-fill');
    if (!text || !fill) return;
    var total = Number(text.dataset.total) || 0;
    text.textContent = doneCount + ' / ' + total + ' 單元完成';
    fill.style.width = (total ? Math.round(doneCount * 100 / total) : 0) + '%';
  }

  // ── 程式碼複製 ──
  function copyText(str) {
    if (navigator.clipboard && window.isSecureContext) { return navigator.clipboard.writeText(str); }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = str; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(new Error('copy failed')); }
      catch (e) { reject(e); } finally { ta.remove(); }
    });
  }
  function initCopy() {
    document.querySelectorAll('.copy-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var code = btn.closest('.code-block').querySelector('code');
        copyText(code.textContent).then(function () {
          btn.textContent = '已複製 ✔';
          setTimeout(function () { btn.textContent = '複製'; }, 1500);
        }).catch(function () { toast('複製失敗，請手動選取文字'); });
      });
    });
  }

  // ── YouTube：點縮圖才載入 iframe ──
  function initYoutube() {
    document.querySelectorAll('.yt-thumb').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var fig = btn.closest('.yt');
        var iframe = document.createElement('iframe');
        iframe.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(fig.dataset.yt) + '?autoplay=1&rel=0';
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
        iframe.allowFullscreen = true;
        iframe.title = btn.getAttribute('aria-label') || 'YouTube';
        btn.replaceWith(iframe);
      });
    });
  }

  // ── 旁白播放 ──
  function initPlayer() {
    var player = document.getElementById('player');
    if (!player) return;
    var rateSel = document.getElementById('rate');
    var status = document.getElementById('now-playing');
    var playAllBtn = document.getElementById('play-all');
    var targets = Array.prototype.slice.call(document.querySelectorAll('[data-audio]'));
    var queue = [], current = null;

    var savedRate = storeGet('rate');
    if (savedRate && rateSel.querySelector('option[value="' + savedRate + '"]')) { rateSel.value = savedRate; }
    rateSel.addEventListener('change', function () {
      player.playbackRate = Number(rateSel.value);
      storeSet('rate', rateSel.value);
    });

    function label(el) {
      var h = el.querySelector('h2, h1');
      return h ? h.textContent : '';
    }
    function clearHighlight() { targets.forEach(function (t) { t.classList.remove('playing'); }); }
    function stop() {
      player.pause(); queue = []; current = null; clearHighlight();
      status.textContent = ''; playAllBtn.textContent = '▶ 全部播放';
    }
    function playEl(el) {
      current = el;
      clearHighlight();
      el.classList.add('playing');
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      player.src = el.dataset.audio;
      player.playbackRate = Number(rateSel.value);
      status.textContent = '播放中：' + label(el);
      var p = player.play();
      if (p && p.catch) {
        p.catch(function (err) {
          if (err && err.name === 'AbortError') return;
          toast('語音無法播放：' + (err && err.message ? err.message : '未知錯誤'));
          stop();
        });
      }
    }
    player.addEventListener('ended', function () {
      if (queue.length) { playEl(queue.shift()); } else { stop(); }
    });
    player.addEventListener('error', function () {
      toast('找不到語音檔：' + (current ? current.dataset.audio : ''));
      if (queue.length) { playEl(queue.shift()); } else { stop(); }
    });

    playAllBtn.addEventListener('click', function () {
      if (current) { stop(); return; }
      if (!targets.length) { toast('這個單元還沒有語音'); return; }
      queue = targets.slice(1);
      playAllBtn.textContent = '■ 停止播放';
      playEl(targets[0]);
    });
    document.querySelectorAll('.play-one').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sec = btn.closest('[data-audio]');
        queue = [];
        playAllBtn.textContent = '■ 停止播放';
        playEl(sec);
      });
    });
  }

  // ── 小測驗 ──
  function initQuiz() {
    var quiz = document.getElementById('quiz');
    if (!quiz) return;
    var scoreEl = quiz.querySelector('.score');
    var score = 0;
    quiz.querySelectorAll('.quiz-item').forEach(function (item) {
      var answer = Number(item.dataset.answer);
      var explainEl = item.querySelector('.explain');
      var explainText = item.querySelector('.explain-text').innerHTML;
      var opts = item.querySelectorAll('.opt');
      opts.forEach(function (opt) {
        opt.addEventListener('click', function () {
          if (item.dataset.answered) return;
          item.dataset.answered = '1';
          var chosen = Number(opt.dataset.i);
          opts.forEach(function (o) { o.disabled = true; });
          opts[answer].classList.add('correct');
          var ok = chosen === answer;
          if (!ok) { opt.classList.add('wrong'); } else { score++; }
          explainEl.hidden = false;
          explainEl.className = 'explain ' + (ok ? 'ok' : 'bad');
          explainEl.textContent = (ok ? '✔ 答對了！' : '✘ 答錯了。') + ' ';
          var span = document.createElement('span');
          span.innerHTML = explainText; // 已在產生器端跳脫
          explainEl.appendChild(span);
          scoreEl.textContent = String(score);
        });
      });
    });
  }

  // ── 標記完成 ──
  function initDone() {
    var main = document.querySelector('main.lesson');
    var btn = document.getElementById('mark-done');
    if (!main || !btn) return;
    var id = main.dataset.lessonId;
    var foot = btn.closest('.lesson-foot');
    function render() {
      var done = isDone(id);
      btn.textContent = done ? '✔ 已完成（再按取消）' : '✔ 標記為完成';
      foot.classList.toggle('is-done', done);
    }
    btn.addEventListener('click', function () {
      storeSet('done-' + id, isDone(id) ? null : '1');
      render();
    });
    render();
  }

  document.addEventListener('DOMContentLoaded', function () {
    try {
      initIndex(); initCopy(); initYoutube(); initPlayer(); initQuiz(); initDone();
    } catch (e) {
      toast('頁面初始化失敗：' + e.message);
    }
  });
})();
"""


# ───────────────────────── 主流程 ─────────────────────────

def write_text(path, text):
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"無法寫入 {path}：{e}") from e


def build(args):
    lessons_dir = Path(args.lessons).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    lessons = lesson_parser.load_all(lessons_dir)
    if not lessons:
        raise RuntimeError(f"{lessons_dir} 裡沒有任何講義")
    all_ids = [l["id"] for l in lessons]
    if args.only:
        selected = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = selected - set(all_ids)
        if unknown:
            raise RuntimeError(f"--only 指定的單元不存在：{sorted(unknown)}（現有：{all_ids}）")
    else:
        selected = set(all_ids)

    audio_map, created, failed = build_audio(lessons, selected, out_dir / "audio", not args.no_tts)
    demos_all = read_optional_json(out_dir / "demos.json", dict) or {}
    links = read_optional_json(out_dir / "links.json", list)

    write_text(out_dir / "style.css", STYLE_CSS)
    write_text(out_dir / "app.js", APP_JS)
    pages = 0
    for i, lesson in enumerate(lessons):
        if lesson["id"] not in selected:
            continue
        prev_lesson = lessons[i - 1] if i > 0 else None
        next_lesson = lessons[i + 1] if i + 1 < len(lessons) else None
        page = render_lesson_page(lesson, prev_lesson, next_lesson, audio_map[lesson["id"]],
                                  demos_all.get(lesson["id"], []))
        write_text(out_dir / f"{lesson['id']}.html", page)
        pages += 1
    write_text(out_dir / "index.html", render_index(lessons, links, extract_architecture(Path(args.plan))))
    pages += 1

    export = []
    for lesson in lessons:
        item = dict(lesson)
        item["level_name"] = lesson_parser.level_name(lesson["id"])
        item["unit"] = lesson_parser.unit_number(lesson["id"])
        item["intro"] = intro_text(lesson)
        item["audio"] = {str(n): v for n, v in sorted(audio_map[lesson["id"]].items())}
        export.append(item)
    write_text(out_dir / "lessons.json", json.dumps(export, ensure_ascii=False, indent=1))

    selected_audio = [a for lid in selected for a in audio_map[lid].values()]
    total_seconds = sum(a["duration"] or 0 for a in selected_audio)
    print(f"完成：頁面 {pages} 頁（含首頁）｜語音檔 {len(selected_audio)} 個（本次新產生 {created}，失敗 {failed}）"
          f"｜總語音 {total_seconds:.1f} 秒（約 {total_seconds / 60:.1f} 分）")
    print(f"輸出目錄：{out_dir}")
    return 1 if failed else 0


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="建立 Yahboom MicroROS-Pi5 教材網站與語音")
    parser.add_argument("--lessons", default=str(ROOT / "lessons"), help="講義目錄")
    parser.add_argument("--out", default=str(ROOT / "site"), help="網站輸出目錄")
    parser.add_argument("--plan", default=str(ROOT / "LEARNING-PLAN.md"), help="取架構圖用的 LEARNING-PLAN.md")
    parser.add_argument("--no-tts", action="store_true", help="不產生語音，只沿用既有音檔")
    parser.add_argument("--only", help="只建指定單元（逗號分隔，例如 W2,B3）；首頁與 lessons.json 仍含全部")
    args = parser.parse_args()
    try:
        sys.exit(build(args))
    except (lesson_parser.LessonParseError, FileNotFoundError, RuntimeError) as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
