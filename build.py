"""把库里的文章渲染成一个自包含的静态页面（单文件，双击即用）。"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from fetch import DB_PATH
from sources import BY_KEY

ROOT = Path(__file__).resolve().parent
TPL = ROOT / "templates" / "index.html"
OUT = ROOT / "site" / "index.html"

TOPIC_ORDER = [
    "马克思主义", "党史党建", "政治经济学", "哲学", "法学", "政治学",
    "国际", "军事国防", "历史", "文化", "新闻传播", "社会", "经济", "科技教育", "生态", "其他",
]


def norm_key(title: str) -> str:
    """标题归一化，用于跨源去重（人民网理论频道常转发人民日报理论版）。"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", title or "")


def dedupe(arts: list[dict]) -> list[dict]:
    """同一篇文章被多个源收录时，只保留权重最高的那个源。"""
    best: dict[str, dict] = {}
    for a in arts:
        k = norm_key(a["title"])
        if not k:
            continue
        cur = best.get(k)
        if cur is None or a["weight"] > cur["weight"]:
            best[k] = a
    keep = {id(v) for v in best.values()}
    return [a for a in arts if id(a) in keep]


def load(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id,source,source_name,title,url,pub_date,topic,summary,chars
           FROM articles WHERE is_news=0
           ORDER BY pub_date DESC, source, id"""
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        src = BY_KEY.get(d["source"])
        d["short"] = src.short if src else d["source_name"]
        d["weight"] = src.weight if src else 50
        d["summary"] = (d["summary"] or "").strip().rstrip("…").strip()
        out.append(d)
    return dedupe(out)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    arts = load(conn)
    conn.close()

    today = date.today()
    counts = {
        "total": len(arts),
        "today": sum(1 for a in arts if a["pub_date"] == today.isoformat()),
        "week": sum(1 for a in arts if a["pub_date"] >= (today - timedelta(days=6)).isoformat()),
    }
    topics = {}
    for a in arts:
        topics[a["topic"]] = topics.get(a["topic"], 0) + 1
    topic_list = [{"name": t, "n": topics[t]} for t in TOPIC_ORDER if t in topics]
    for t, n in topics.items():  # 兜底：不在预设顺序里的主题
        if t not in TOPIC_ORDER:
            topic_list.append({"name": t, "n": n})

    sources = {}
    for a in arts:
        s = sources.setdefault(a["source"], {"name": a["source_name"], "short": a["short"], "n": 0, "weight": a["weight"]})
        s["n"] += 1
    source_list = sorted(sources.values(), key=lambda x: -x["weight"])

    payload = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today.isoformat(),
        "counts": counts,
        "topics": topic_list,
        "sources": source_list,
        "articles": arts,
    }

    html = TPL.read_text(encoding="utf-8")
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", data_json)
    html = html.replace("{{GENERATED}}", payload["generated"])
    html = html.replace("{{TOTAL}}", str(counts["total"]))
    html = html.replace("{{TODAY}}", str(counts["today"]))
    html = html.replace("{{WEEK}}", str(counts["week"]))
    html = html.replace("{{DATE}}", today.strftime("%Y年%m月%d日"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"已生成 {OUT}  （{counts['total']} 篇，今日 {counts['today']} 篇）")


if __name__ == "__main__":
    main()
