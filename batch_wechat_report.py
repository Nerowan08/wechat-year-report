import argparse
import base64
import io
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple

import jieba
import matplotlib.pyplot as plt
import pandas as pd
from wordcloud import WordCloud

# =========================================================
# 你的 TXT：
# 头部：
#   聊天对象：xxx
#   with_id：wxid_xxx 或 12345@chatroom
# 正文：
#   [2025-02-01 16:34:42] wxid_a -> wxid_b: 内容
# =========================================================

RE_LINE = re.compile(
    r"^\s*\[(?P<dt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+"
    r"(?P<from>\S+)\s*->\s*(?P<to>\S+)\s*:\s*"
    r"(?P<content>.*)$"
)

RE_META_CHAT_NAME = re.compile(r"^\s*聊天对象：\s*(?P<name>.+?)\s*$")
RE_META_WITH_ID = re.compile(r"^\s*with_id：\s*(?P<id>\S+)\s*$")
RE_META_SPLIT = re.compile(r"^-{10,}\s*$")

def parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

@dataclass
class Msg:
    dt: datetime
    sender: str
    receiver: str
    content: str
    src: str

def parse_metadata(path: Path, max_lines: int = 80) -> Tuple[Optional[str], Optional[str]]:
    chat_name = None
    with_id = None
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:max_lines]
    for line in lines:
        if RE_META_SPLIT.match(line):
            break
        m1 = RE_META_CHAT_NAME.match(line)
        if m1:
            chat_name = m1.group("name").strip()
            continue
        m2 = RE_META_WITH_ID.match(line)
        if m2:
            with_id = m2.group("id").strip()
            continue
    return chat_name, with_id

def parse_txt(path: Path) -> List[Msg]:
    msgs: List[Msg] = []
    last: Optional[Msg] = None

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.rstrip("\n")
        m = RE_LINE.match(line)
        if m:
            dt = parse_dt(m.group("dt"))
            if not dt:
                continue
            sender = m.group("from").strip()
            receiver = m.group("to").strip()
            content = (m.group("content") or "").strip()
            msg = Msg(dt=dt, sender=sender, receiver=receiver, content=content, src=str(path))
            msgs.append(msg)
            last = msg
        else:
            if last:
                extra = line.strip()
                if extra:
                    last.content += "\n" + extra
    return msgs

# =======================
# NLP 去噪 + 分词（保留表情占位符）
# =======================

RE_XML_DECL  = re.compile(r"<\?xml.*?\?>", re.I)
RE_XML_BLOCK = re.compile(r"<msg>.*?</msg>", re.S | re.I)
RE_XML_TAG   = re.compile(r"<[^>]+>")

RE_WXID      = re.compile(r"\bwxid_[A-Za-z0-9]+\b", re.I)
RE_CHATROOM  = re.compile(r"\b\d+@chatroom\b", re.I)
RE_UUID      = re.compile(r"\b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\b", re.I)
RE_HEX_LONG  = re.compile(r"\b[a-f0-9]{16,}\b", re.I)

RE_EMOJI = re.compile(r"\[[A-Za-z0-9_]{1,30}\]")

STOPWORDS = set("""
的 了 和 是 就 都 而 及 与 着 或 一个 没有 我 你 他 她 它 我们 你们 他们 她们 它们
啊 呢 吧 哦 哈 嗯 诶 哎呀 这个 那个 这样 那样
wxid xml version link msg img emoji aeskey md5 cdn cdnurl cdnthumburl cdnmidimgurl cdnbigimgurl
length hdlength width height encryver filekey storeid bizid hy amp http https com tencent qpic mmbiz
""".split())

EN_STOPWORDS = set("""
a an and are as at be been being but by did do does doing for from had has have having he her hers him his
i if in into is it its me my mine more most of on once only or our ours out over she so than that the their
theirs them then there these they this those to too under up us very was we were what when where which who
why will with you your yours ok okay yeah yep pls please thx thanks
message msg recalled recall
""".split())
STOPWORDS |= EN_STOPWORDS

def clean_for_nlp(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\bYou recalled a message\b", " ", text, flags=re.I)
    text = re.sub(r"\brecalled a message\b", " ", text, flags=re.I)
    text = re.sub(r"撤回了一条消息|你撤回了一条消息|对方撤回了一条消息", " ", text)

    text = RE_XML_DECL.sub(" ", text)
    text = RE_XML_BLOCK.sub(" ", text)
    text = RE_XML_TAG.sub(" ", text)

    text = re.sub(r"http[s]?://\S+", " ", text)

    text = RE_WXID.sub(" ", text)
    text = RE_CHATROOM.sub(" ", text)
    text = RE_UUID.sub(" ", text)
    text = RE_HEX_LONG.sub(" ", text)

    # 保留 [] 以保留表情占位符
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\[\]_]+", " ", text)
    return text.strip()

def tokenize_all(text: str) -> Tuple[List[str], List[str]]:
    text = clean_for_nlp(text)
    if not text:
        return [], []

    emojis = [e.lower() for e in RE_EMOJI.findall(text)]
    text_wo_emoji = RE_EMOJI.sub(" ", text)

    words: List[str] = []
    for w in jieba.cut(text_wo_emoji, cut_all=False):
        w = w.strip().lower()
        if not w:
            continue
        if w in STOPWORDS:
            continue
        if len(w) <= 1:
            continue
        if w.isdigit():
            continue
        # 过滤包含数字的账号/编号类词
        if any(ch.isdigit() for ch in w):
            continue
        if w.startswith("wxid"):
            continue
        if "@chatroom" in w:
            continue
        if RE_HEX_LONG.fullmatch(w):
            continue
        words.append(w)

    # 你要保留表情：把表情也并入 words
    words.extend(emojis)
    return words, emojis

def pick_font() -> Optional[str]:
    candidates = [
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/PingFang.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None

def fig_to_base64_png() -> str:
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=160)
    plt.close()
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def render_report_html(df: pd.DataFrame, title: str) -> str:
    df = df.copy()
    df["date"] = df["dt"].dt.date
    df["hour"] = df["dt"].dt.hour

    total = len(df)
    day_first = df["dt"].min()
    day_last = df["dt"].max()

    senders = df["sender_display"].value_counts().head(10)

    daily = df.groupby("date").size().reset_index(name="count").sort_values("date")
    plt.figure()
    plt.plot(daily["date"], daily["count"])
    plt.xticks(rotation=45, ha="right")
    plt.title("Messages per Day")
    plt.xlabel("Date")
    plt.ylabel("Count")
    daily_png = fig_to_base64_png()

    hourly = df.groupby("hour").size().reindex(range(24), fill_value=0)
    plt.figure()
    plt.bar(hourly.index, hourly.values)
    plt.title("Messages by Hour")
    plt.xlabel("Hour")
    plt.ylabel("Count")
    hour_png = fig_to_base64_png()

    dates_sorted = sorted(pd.to_datetime(daily["date"]).dt.date.tolist())
    longest_streak, cur = (1, 1) if dates_sorted else (0, 0)
    for i in range(1, len(dates_sorted)):
        if (dates_sorted[i] - dates_sorted[i - 1]).days == 1:
            cur += 1
            longest_streak = max(longest_streak, cur)
        else:
            cur = 1

    all_text = "\n".join(df["content"].astype(str).tolist())
    tokens, emojis = tokenize_all(all_text)
    freq = pd.Series(tokens).value_counts().head(80)
    emoji_freq = pd.Series(emojis).value_counts().head(20)

    wc_png = ""
    font_path = pick_font()
    if font_path and len(freq) > 0:
        wc = WordCloud(
            width=1200, height=800, background_color="white",
            font_path=font_path, max_words=200
        ).generate_from_frequencies(freq.to_dict())
        buf = io.BytesIO()
        wc.to_image().save(buf, format="PNG")
        wc_png = base64.b64encode(buf.getvalue()).decode("utf-8")

    top_words_html = "\n".join(f"<li>{w}: {c}</li>" for w, c in freq.items())
    top_senders_html = "\n".join(f"<li>{name}: {cnt}</li>" for name, cnt in senders.items())
    top_emoji_html = "\n".join(f"<li>{w}: {c}</li>" for w, c in emoji_freq.items()) if len(emoji_freq) else "<li>（无）</li>"

    return f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif; margin: 24px; line-height: 1.6; }}
h1,h2 {{ margin: 0.6em 0 0.3em; }}
.card {{ border: 1px solid #eee; border-radius: 14px; padding: 16px; margin: 14px 0; }}
.small {{ color: #666; font-size: 0.92em; }}
img {{ max-width: 100%; height: auto; border-radius: 12px; border: 1px solid #f2f2f2; }}
ul {{ margin: 0.3em 0 0.3em 1.2em; }}
code {{ background: #f5f5f5; padding: 1px 6px; border-radius: 6px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="small"></div>

<div class="card">
  <h2>概览</h2>
  <ul>
    <li>消息总数：<b>{total}</b></li>
    <li>时间范围：{day_first} → {day_last}</li>
    <li>最长连续聊天天数（按有消息的日子）：<b>{longest_streak}</b> 天</li>
  </ul>
</div>

<div class="card">
  <h2>谁最爱发（Top10）</h2>
  <ul>{top_senders_html}</ul>
</div>

<div class="card">
  <h2>每天消息量</h2>
  <img src="data:image/png;base64,{daily_png}" alt="daily"/>
</div>

<div class="card">
  <h2>一天中最活跃时段</h2>
  <img src="data:image/png;base64,{hour_png}" alt="hourly"/>
</div>

<div class="card">
  <h2>Top表情（Top20）</h2>
  <div class="small">统计形如 <code>[doge]</code> 的表情占位符（来自你的导出文本）。</div>
  <ol>{top_emoji_html}</ol>
</div>

<div class="card">
  <h2>高频词（Top）</h2>
  <ol>{top_words_html}</ol>
</div>

<div class="card">
  <h2>词云</h2>
  {"<img src='data:image/png;base64," + wc_png + "' alt='wordcloud'/>" if wc_png else "<div class='small'>未生成词云：可能缺少中文字体或词频为空。</div>"}
</div>

<div class="small">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
</body>
</html>
"""

def build_index(out_dir: Path, links: List[Tuple[str, str]]) -> None:
    items = "\n".join([f"<li><a href='{href}'>{text}</a></li>" for text, href in links])
    html = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>微信年度报告 - 入口</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif; margin: 24px; line-height: 1.6; }}
.card {{ border: 1px solid #eee; border-radius: 14px; padding: 16px; margin: 14px 0; }}
</style>
</head>
<body>
<h1>微信年度报告 - 入口</h1>
<div class="card"><ul>{items}</ul></div>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")

def resolve_file(in_dir: Path, file_arg: str) -> Path:
    """
    支持：
    - 传完整路径
    - 传文件名（在 in_dir 下递归查找第一个匹配）
    """
    p = Path(file_arg)
    if p.exists():
        return p
    # 用文件名在目录里找
    matches = list(in_dir.rglob(file_arg))
    if matches:
        return matches[0]
    # 有些人不加 .txt
    if not file_arg.endswith(".txt"):
        matches = list(in_dir.rglob(file_arg + ".txt"))
        if matches:
            return matches[0]
    raise SystemExit(f"找不到指定文件：{file_arg}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/Users/neowan/Desktop/wechat/wechatnero/txt", help="TXT 根目录（会递归）")
    ap.add_argument("--file", default=None, help="只分析某一个 TXT（文件名或完整路径）")
    ap.add_argument("--year", type=int, default=None, help="只统计某一年（如 2025）。不填=全部年份")
    ap.add_argument("--outdir", default=str(Path.home() / "Desktop/wechat_year_report/out"), help="输出目录")
    args = ap.parse_args()

    in_dir = Path(args.dir)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 如果指定 --file，就只处理这一份
    if args.file:
        target = resolve_file(in_dir, args.file)
        chat_name, with_id = parse_metadata(target)
        # 昵称映射：只要该文件头信息即可
        id_to_name: Dict[str, str] = {}
        if chat_name and with_id:
            id_to_name[with_id] = chat_name

        msgs = parse_txt(target)
        if not msgs:
            raise SystemExit("该文件里没有解析到消息。")

        df = pd.DataFrame([{
            "dt": m.dt, "sender": m.sender, "receiver": m.receiver, "content": m.content, "chat_file": m.src
        } for m in msgs])
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df = df.dropna(subset=["dt"])

        if args.year is not None:
            df = df[df["dt"].dt.year == args.year].copy()

        if df.empty:
            raise SystemExit("筛选后没有消息（可能该文件没有该年份数据）。")

        df["sender_display"] = df["sender"].map(id_to_name).fillna(df["sender"])
        df["receiver_display"] = df["receiver"].map(id_to_name).fillna(df["receiver"])

        tag = str(args.year) if args.year else "ALL"
        safe = re.sub(r"[\\/:*?\"<>|]+", "_", target.stem)[:120]
        out_name = f"report_SINGLE_{safe}_{tag}.html"
        (out_dir / out_name).write_text(
            render_report_html(df, f"微信聊天年度报告（单文件） - {safe} - {tag}"),
            encoding="utf-8"
        )
        build_index(out_dir, [(f"单文件报告：{safe}（{tag}）", out_name)])
        print("✅ 单文件分析完成")
        print(f"- 文件：{target}")
        print(f"- 输出：{(out_dir / out_name).resolve()}")
        print(f"- 入口：{(out_dir / 'index.html').resolve()}")
        return

    # 否则：全目录汇总（保持旧行为）
    txt_files = sorted([p for p in in_dir.rglob("*.txt") if p.is_file()])
    if not txt_files:
        raise SystemExit(f"在 {in_dir} 里找不到 .txt 文件")

    id_to_name: Dict[str, str] = {}
    for p in txt_files:
        chat_name, with_id = parse_metadata(p)
        if chat_name and with_id:
            id_to_name[with_id] = chat_name

    all_rows = []
    used_files = 0
    for p in txt_files:
        msgs = parse_txt(p)
        if not msgs:
            continue
        df = pd.DataFrame([{
            "dt": m.dt, "sender": m.sender, "receiver": m.receiver, "content": m.content, "chat_file": m.src
        } for m in msgs])
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df = df.dropna(subset=["dt"])
        if df.empty:
            continue
        if args.year is not None:
            df = df[df["dt"].dt.year == args.year].copy()
            if df.empty:
                continue
        df["sender_display"] = df["sender"].map(id_to_name).fillna(df["sender"])
        df["receiver_display"] = df["receiver"].map(id_to_name).fillna(df["receiver"])
        used_files += 1
        all_rows.append(df)

    if not all_rows:
        raise SystemExit("没有解析到任何可用消息。")

    all_df = pd.concat(all_rows, ignore_index=True)
    all_df["dt"] = pd.to_datetime(all_df["dt"])

    tag = str(args.year) if args.year else "ALL"
    global_name = f"report_ALL_{tag}.html"
    (out_dir / global_name).write_text(
        render_report_html(all_df, f"微信聊天年度报告（汇总） - {tag}"),
        encoding="utf-8"
    )
    build_index(out_dir, [(f"汇总报告（{tag}）", global_name)])
    print("✅ 汇总完成")
    print(f"- 参与统计文件数：{used_files} / {len(txt_files)}")
    print(f"- 入口：{(out_dir / 'index.html').resolve()}")

if __name__ == "__main__":
    main()
