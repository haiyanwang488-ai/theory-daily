"""抓取器：列表页解析 + 详情页补全 + 入库。"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sources import BY_KEY, SOURCES, Source, classify, clean_title, is_news, is_video, parse_date

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "theory.db"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# 正文容器候选选择器，按优先级尝试
BODY_SELECTORS = [
    "div.rm_txt_con",          # 人民网
    "div#articleContent",      # 光明网
    "div.article-content",     # 求是网 / 社科网
    "div.TRS_Editor",          # 学习时报
    "div#ozoom",               # 人民日报电子版
    "div.article",             # 通用
    "div.content",
    "article",
    "div.main-content",
]

NOISE_RE = re.compile(r"(责任编辑|来源：|原标题|分享到|扫一扫|打印本页|关闭窗口)")


def _id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def get(url: str, tries: int = 3, timeout: int = 20) -> str | None:
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and r.content:
                if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                    r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            if r.status_code in (403, 404, 410):
                return None
        except Exception:
            pass
        time.sleep(1.2 * (i + 1))
    return None


# ---------------------------------------------------------------- 列表解析

def parse_list(src: Source, html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        full = urljoin(page_url, href)
        m = src.match_href(full)
        if not m:
            continue
        pub = parse_date(src, full)
        if not pub:
            continue
        title = clean_title(a.get_text(" ", strip=True))
        if len(title) < 4:
            # 部分站点头条标题放在 img alt 或 title 属性里
            title = (a.get("title") or a.find("img").get("alt") if a.find("img") else "") or ""
            title = clean_title(title)
        if len(title) < 4:
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append(
            {
                "id": _id(full),
                "source": src.key,
                "source_name": src.name,
                "title": title,
                "url": full,
                "pub_date": pub,
                "section": src.section,
            }
        )
    return out


def rmrb_theory_pages(today: date) -> list[str]:
    """人民日报电子版：先读当日版面导航，定位标题含「理论」的版面。"""
    ym = today.strftime("%Y%m")
    base = f"http://paper.people.com.cn/rmrb/pc/layout/{ym}/{today:%d}/"
    nav = get(base + "node_01.html")
    if not nav:
        return []
    pages = []
    for a in BeautifulSoup(nav, "lxml").find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if "理论" in text and re.search(r"node_\d+\.html", a["href"]):
            pages.append(urljoin(base, a["href"]))
    # 兜底：第 9 版常为理论版
    if not pages:
        pages.append(base + "node_09.html")
    return list(dict.fromkeys(pages))


def collect(src: Source, days_back: int = 2) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    items: list[dict] = []

    urls = list(src.list_urls)
    if src.dynamic == "rmrb_layout":
        urls = rmrb_theory_pages(date.today())

    for u in urls:
        html = get(u)
        if not html:
            print(f"  ! 列表页失败 {u}", file=sys.stderr)
            continue
        got = parse_list(src, html, u)
        items.extend([x for x in got if x["pub_date"] >= cutoff])

    # 去重
    uniq = {x["url"]: x for x in items}
    return list(uniq.values())


# ---------------------------------------------------------------- 详情补全

def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def enrich(item: dict) -> dict:
    html = get(item["url"], tries=2, timeout=18)
    if not html:
        item["summary"] = ""
        item["chars"] = 0
        return item
    soup = BeautifulSoup(html, "lxml")

    # 标题：优先 og:title / <title>，去掉站点后缀
    full_title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        full_title = og["content"]
    elif soup.title:
        full_title = soup.title.get_text()
    full_title = re.split(r"[-—|_]*(?:人民网|光明网|求是网|中国社会科学网|学习时报|人民日报)", full_title)[0]
    full_title = clean_title(full_title).strip("—-|_ ")
    # 列表页标题被截断（以省略号结尾）或明显更短时，用详情页标题
    if full_title and (item["title"].endswith(("…", "...")) or len(full_title) > len(item["title"]) + 4):
        item["title"] = full_title

    body = None
    for sel in BODY_SELECTORS:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 150:
            body = el
            break
    if body is None:
        ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        ps = [p for p in ps if len(p) > 25]
        text = " ".join(ps)
    else:
        text = body.get_text(" ", strip=True)

    text = _clean(text)
    item["chars"] = len(text)
    paras = [p for p in re.split(r"(?<=。)\s*", text) if len(p) > 20 and not NOISE_RE.search(p)]
    item["summary"] = _clean("".join(paras)[:320])
    return item


# ---------------------------------------------------------------- 入库

DDL = """
CREATE TABLE IF NOT EXISTS articles(
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_name TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  pub_date TEXT NOT NULL,
  section TEXT,
  summary TEXT,
  chars INTEGER DEFAULT 0,
  topic TEXT,
  is_news INTEGER DEFAULT 0,
  fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pub ON articles(pub_date DESC);
CREATE INDEX IF NOT EXISTS idx_topic ON articles(topic);
CREATE TABLE IF NOT EXISTS runs(
  ts TEXT PRIMARY KEY,
  total INTEGER, added INTEGER, note TEXT
);
"""


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)
    return conn


def existing_ids(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT id FROM articles")}


def save(conn: sqlite3.Connection, items: list[dict]) -> int:
    n = 0
    for it in items:
        topic = classify(it["title"], it.get("summary") or "")
        news = 1 if (is_news(it["title"], it.get("summary") or "", it.get("chars", 0)) or is_video(it["title"], it["url"])) else 0
        cur = conn.execute(
            """INSERT OR IGNORE INTO articles
               (id,source,source_name,title,url,pub_date,section,summary,chars,topic,is_news,fetched_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                it["id"], it["source"], it["source_name"], it["title"], it["url"],
                it["pub_date"], it.get("section", ""), it.get("summary", ""),
                it.get("chars", 0), topic, news, datetime.now().isoformat(timespec="seconds"),
            ),
        )
        n += cur.rowcount
    conn.commit()
    return n


def run(days_back: int = 2, enrich_limit: int = 120, workers: int = 4) -> tuple[int, int]:
    conn = db()
    known = existing_ids(conn)
    all_new: list[dict] = []

    print(f"抓取开始 {datetime.now():%Y-%m-%d %H:%M}", flush=True)
    for src in SOURCES:
        try:
            items = collect(src, days_back)
        except Exception as e:
            print(f"  ! {src.name} 异常: {e}", file=sys.stderr)
            continue
        fresh = [x for x in items if x["id"] not in known]
        print(f"  {src.short}: 列表 {len(items)} 条，新增 {len(fresh)} 条", flush=True)
        all_new.extend(fresh)

    # 详情页补全（控制总量，避免一次性打太多请求）
    if all_new:
        todo = sorted(all_new, key=lambda x: x["pub_date"], reverse=True)[:enrich_limit]
        print(f"补全详情 {len(todo)} 篇…", flush=True)
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            enriched = list(ex.map(enrich, todo))
        added = save(conn, enriched)
        # 超出补全上限的仍入库（无摘要）
        rest = [x for x in all_new if x not in todo]
        if rest:
            added += save(conn, rest)
    else:
        added = 0

    conn.execute(
        "INSERT INTO runs(ts,total,added,note) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), len(all_new), added, ""),
    )
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()
    print(f"完成：新增 {added} 篇，库内共 {total} 篇", flush=True)
    return added, total


if __name__ == "__main__":
    run()
