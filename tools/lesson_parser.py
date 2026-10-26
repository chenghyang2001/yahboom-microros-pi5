"""講義解析共用模組：把 lessons/*.md（格式見 lessons/LESSON-FORMAT.md）解析成 dict。

build_site.py 與 make_lesson_videos.py 都靠這裡，格式規則只維護一份。
"""
import json
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger("lesson_parser")

REQUIRED_FIELDS = ("id", "level", "title", "minutes", "needs_car", "goal", "done", "videos", "docs")
# 級別排序：暖身 W → 初級 B → 中級 M → 高級 A
LEVEL_ORDER = {"W": 0, "B": 1, "M": 2, "A": 3}
LEVEL_NAMES = {"W": "暖身", "B": "初級", "M": "中級", "A": "高級"}
SKIP_FILES = {"LESSON-FORMAT.md"}

SECTION_RE = re.compile(r"^##\s+(\d+)\s*[.．、]\s*(.+?)\s*$")
QUIZ_HEADING_RE = re.compile(r"^##\s+小測驗\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
ID_RE = re.compile(r"^([WBMA])(\d+)$")


class LessonParseError(Exception):
    """解析失敗：訊息一律帶檔名與行號，作者才找得到要改哪裡。"""

    def __init__(self, path, line_no, message):
        self.path = str(path)
        self.line_no = line_no
        super().__init__(f"{path}:{line_no}: {message}")


def _parse_front_matter(lines, path):
    """回傳 (front_matter dict, 本文起始行 index)。"""
    if not lines or lines[0].strip() != "---":
        raise LessonParseError(path, 1, "檔案開頭缺少 front matter 的 '---'")
    meta = {}
    for idx in range(1, len(lines)):
        raw = lines[idx]
        if raw.strip() == "---":
            break
        if not raw.strip():
            continue
        if ":" not in raw:
            raise LessonParseError(path, idx + 1, f"front matter 行格式應為「key: value」：{raw.strip()}")
        key, value = raw.split(":", 1)
        meta[key.strip()] = value.strip()
    else:
        raise LessonParseError(path, 1, "front matter 沒有結尾的 '---'")

    missing = [k for k in REQUIRED_FIELDS if k not in meta]
    if missing:
        raise LessonParseError(path, 1, f"front matter 缺少欄位：{', '.join(missing)}")

    meta["videos"] = [v.strip() for v in meta["videos"].split(",") if v.strip()]
    try:
        meta["minutes"] = int(meta["minutes"])
    except ValueError:
        # 「4 小時以上」之類的寫法保留原字串，網站照樣顯示
        log.warning("%s: minutes 不是整數（%s），保留原字串", path, meta["minutes"])
    if not ID_RE.match(meta["id"]):
        raise LessonParseError(path, 1, f"id 格式應為 W/B/M/A + 數字，實際：{meta['id']}")
    return meta, idx + 1


def _strip_narration_prefix(line):
    text = line.lstrip()[1:]  # 去掉 '>'
    text = text.lstrip()
    if text.startswith("🔊"):
        text = text[len("🔊"):].lstrip()
    return text.strip()


def _split_narration(body_lines):
    """從小節內容最前面切出旁白（> 開頭的連續行，到空行或非 > 行為止）。"""
    pos = 0
    while pos < len(body_lines) and not body_lines[pos][1].strip():
        pos += 1
    parts = []
    while pos < len(body_lines) and body_lines[pos][1].lstrip().startswith(">"):
        parts.append(_strip_narration_prefix(body_lines[pos][1]))
        pos += 1
    narration = ""
    for part in (p for p in parts if p):
        # 中文接中文不加空白；英文單字跨行時要補空白，否則 TTS 會把兩個字念成一個
        if narration and narration[-1].isascii() and narration[-1].isalnum() and part[0].isascii() and part[0].isalnum():
            narration += " "
        narration += part
    rest = "\n".join(text for _, text in body_lines[pos:]).strip("\n")
    return narration, rest


def _parse_quiz(body_lines, path, heading_line):
    """從 ## 小測驗 小節裡找 ```quiz 區塊並 JSON 解析。"""
    start = None
    for i, (line_no, text) in enumerate(body_lines):
        if start is None and re.match(r"^\s*```\s*quiz\s*$", text):
            start = i
        elif start is not None and text.strip().startswith("```"):
            raw_json = "\n".join(t for _, t in body_lines[start + 1:i])
            json_line = body_lines[start][0] + 1
            try:
                quiz = json.loads(raw_json)
            except json.JSONDecodeError as e:
                raise LessonParseError(path, json_line + e.lineno - 1, f"quiz JSON 解析失敗：{e.msg}") from e
            return _validate_quiz(quiz, path, json_line)
    if start is not None:
        raise LessonParseError(path, body_lines[start][0], "```quiz 區塊沒有結尾的 ```")
    log.warning("%s:%d: 小測驗小節沒有 ```quiz 區塊", path, heading_line)
    return []


def _validate_quiz(quiz, path, line_no):
    if not isinstance(quiz, list):
        raise LessonParseError(path, line_no, "quiz 必須是 JSON 陣列")
    for i, item in enumerate(quiz, 1):
        if not isinstance(item, dict) or not all(k in item for k in ("q", "options", "answer")):
            raise LessonParseError(path, line_no, f"quiz 第 {i} 題缺少 q／options／answer")
        options = item["options"]
        answer = item["answer"]
        if not isinstance(options, list) or not isinstance(answer, int) or not 0 <= answer < len(options):
            raise LessonParseError(path, line_no, f"quiz 第 {i} 題 answer 超出 options 範圍")
        item.setdefault("explain", "")
    return quiz


def _group_body(lines, offset, path):
    """把本文切成 [(kind, n, title, heading_line, [(line_no, text), ...])]，程式碼區塊內的 ## 不算標題。"""
    groups = []
    current = None
    in_fence = None
    for idx in range(offset, len(lines)):
        text = lines[idx]
        line_no = idx + 1
        fence = FENCE_RE.match(text)
        if fence:
            marker = fence.group(1)[:3]
            if in_fence is None:
                in_fence = marker
            elif marker == in_fence:
                in_fence = None
        if in_fence is None and not fence:
            sec = SECTION_RE.match(text)
            if sec:
                current = ("section", int(sec.group(1)), sec.group(2), line_no, [])
                groups.append(current)
                continue
            if QUIZ_HEADING_RE.match(text):
                current = ("quiz", None, "小測驗", line_no, [])
                groups.append(current)
                continue
        if current is None:
            if text.strip():
                log.warning("%s:%d: 第一個小節之前的內容會被忽略", path, line_no)
            continue
        current[4].append((line_no, text))
    if in_fence is not None:
        raise LessonParseError(path, len(lines), "程式碼區塊沒有關閉（缺少結尾 ```）")
    return groups


def parse_lesson(path):
    """解析單一講義檔，回傳 dict（front matter 欄位 + sections + quiz + source）。"""
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise LessonParseError(path, 0, f"無法讀取檔案：{e}") from e
    lines = content.lstrip("﻿").splitlines()

    meta, offset = _parse_front_matter(lines, path)
    if meta["id"] != path.stem and path.stem not in SKIP_FILES:
        log.warning("%s: 檔名（%s）與 id（%s）不一致", path, path.stem, meta["id"])

    sections, quiz = [], []
    for kind, n, title, heading_line, body in _group_body(lines, offset, path):
        if kind == "quiz":
            quiz = _parse_quiz(body, path, heading_line)
            continue
        narration, body_md = _split_narration(body)
        if not narration:
            log.warning("%s:%d: 小節「%d. %s」缺少旁白（> 🔊）", path, heading_line, n, title)
        sections.append({"n": n, "title": title, "narration": narration, "body_md": body_md})

    if not sections:
        raise LessonParseError(path, offset + 1, "找不到任何「## 數字. 小節」")
    numbers = [s["n"] for s in sections]
    if len(set(numbers)) != len(numbers):
        raise LessonParseError(path, offset + 1, f"小節編號重複：{numbers}")

    lesson = dict(meta)
    lesson["sections"] = sections
    lesson["quiz"] = quiz
    lesson["source"] = path.name
    return lesson


def lesson_sort_key(lesson_id):
    """W1 < W4 < B1 < … < A5；未知格式排最後。"""
    m = ID_RE.match(lesson_id)
    if not m:
        return (99, 0, lesson_id)
    return (LEVEL_ORDER[m.group(1)], int(m.group(2)), lesson_id)


def level_name(lesson_id):
    m = ID_RE.match(lesson_id)
    return LEVEL_NAMES.get(m.group(1), "") if m else ""


def unit_number(lesson_id):
    m = ID_RE.match(lesson_id)
    return int(m.group(2)) if m else 0


def load_all(lessons_dir):
    """讀取目錄下全部講義並依級別排序；略過 LESSON-FORMAT.md。"""
    lessons_dir = Path(lessons_dir)
    if not lessons_dir.is_dir():
        raise FileNotFoundError(f"講義目錄不存在：{lessons_dir}")
    lessons = [parse_lesson(p) for p in sorted(lessons_dir.glob("*.md")) if p.name not in SKIP_FILES]
    ids = [l["id"] for l in lessons]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise LessonParseError(lessons_dir, 0, f"單元 id 重複：{sorted(dup)}")
    return sorted(lessons, key=lambda l: lesson_sort_key(l["id"]))


def main():
    """冒煙用：python tools/lesson_parser.py <講義目錄>，印出摘要。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "lessons"
    try:
        for lesson in load_all(target):
            print(f"{lesson['id']:4} {lesson['title']}｜{len(lesson['sections'])} 節｜{len(lesson['quiz'])} 題")
    except (LessonParseError, FileNotFoundError) as e:
        print(f"錯誤：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
