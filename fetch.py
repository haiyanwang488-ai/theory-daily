"""抓取器：列表页解析 + 详情页补全 + 入库。"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import re
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import browser
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


# ------------------------------------- 中央党报电子版（人民日报 / 经济日报）

EPAPER = {
    "rmrb": {
        "base": "http://paper.people.com.cn/rmrb/pc/layout/{ym}/{dd}/",
        "fallback": "node_09.html",   # 人民日报理论版常在第 9 版
    },
    "ce": {
        "base": "http://paper.ce.cn/pc/layout/{ym}/{dd}/",
        "fallback": "node_10.html",   # 经济日报理论版常在第 10 版
    },
}


def epaper_theory_pages(key: str, today: date) -> list[str]:
    """读当日版面导航，定位标题含「理论」的版面；找不到就用固定兜底版。"""
    cfg = EPAPER[key]
    base = cfg["base"].format(ym=today.strftime("%Y%m"), dd=f"{today.day:02d}")
    nav = get(base + "node_01.html")
    if not nav:
        return []
    pages = []
    for a in BeautifulSoup(nav, "lxml").find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if "理论" in text and re.search(r"node_\d+\.html", a["href"]):
            pages.append(urljoin(base, a["href"]))
    if not pages:
        pages.append(base + cfg["fallback"])
    return list(dict.fromkeys(pages))


# ------------------------------------------------- 上观系（解放日报 / 文汇报）

REL_MIN_RE = re.compile(r"(\d+)\s*分钟前")
REL_HOUR_RE = re.compile(r"(\d+)\s*小时前")
REL_DAY_RE = re.compile(r"(\d+)\s*天前")
ABS_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def parse_rel_time(txt: str, now: datetime) -> str | None:
    """把「12小时前 / 1天前 / 昨天 / 2026-10-15」换算成 YYYY-MM-DD。"""
    t = txt or ""
    m = ABS_DATE_RE.search(t)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = REL_MIN_RE.search(t)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).date().isoformat()
    m = REL_HOUR_RE.search(t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).date().isoformat()
    m = REL_DAY_RE.search(t)
    if m:
        return (now - timedelta(days=int(m.group(1)))).date().isoformat()
    if "刚刚" in t:
        return now.date().isoformat()
    if "昨天" in t:
        return (now - timedelta(days=1)).date().isoformat()
    if "前天" in t:
        return (now - timedelta(days=2)).date().isoformat()
    return None


def _attrs_of(a) -> str:
    """找到标题链接对应的时间/栏目容器，返回其文本。"""
    p = a.parent
    for _ in range(3):
        if p is None:
            break
        el = p.select_one(".attrs") if hasattr(p, "select_one") else None
        if el:
            return el.get_text(" ", strip=True)
        p = p.parent
    sib = a.find_next_sibling(class_="attrs")
    if sib:
        return sib.get_text(" ", strip=True)
    return ""


def parse_observed(src: Source, html: str, page_url: str, days_back: int = 2) -> list[dict]:
    """上观新闻列表页：a.title + 同级 .attrs（含栏目名与相对时间）。"""
    soup = BeautifulSoup(html, "lxml")
    now = datetime.now()
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    best: dict[str, dict] = {}

    for a in soup.select("a[href*='newsDetail.html?id=']"):
        m = re.search(r"newsDetail\.html\?id=(\d+)", a["href"])
        if not m:
            continue
        aid = m.group(1)
        title = clean_title(a.get_text(" ", strip=True))
        if len(title) < 6:
            continue
        pub = parse_rel_time(_attrs_of(a), now)
        url = urljoin(src.base, f"newsDetail.html?id={aid}&sid=200")
        cand = {
            "id": _id(url),
            "source": src.key,
            "source_name": src.name,
            "title": title,
            "url": url,
            "pub_date": pub or "",
            "section": src.section,
            "chars": 0,
            "summary": "",
        }
        prev = best.get(aid)
        if prev is None or len(cand["title"]) > len(prev["title"]) or (pub and not prev["pub_date"]):
            best[aid] = cand

    return [c for c in best.values() if not c["pub_date"] or c["pub_date"] >= cutoff]


def collect_browser(src: Source, days_back: int = 2) -> list[dict]:
    items: list[dict] = []
    for u in src.list_urls:
        html = browser.render(u)
        if not html:
            print(f"  ! 列表页渲染失败 {u}", file=sys.stderr)
            continue
        got = parse_observed(src, html, u, days_back)
        print(f"    频道 {u.split('id=')[-1][:3]}: {len(got)} 条", flush=True)
        items.extend(got)
    uniq = {x["url"]: x for x in items}
    return list(uniq.values())


def collect(src: Source, days_back: int = 2) -> list[dict]:
    if src.needs_browser:
        return collect_browser(src, days_back)

    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    items: list[dict] = []

    urls = list(src.list_urls)
    if src.dynamic:
        urls = epaper_theory_pages(src.dynamic, date.today())

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


SHARE_RE = re.compile(r"打开微信.*?朋友圈。?|点击底部的\s*“?发现”?.*?扫一扫")


def enrich_browser(item: dict) -> dict:
    """上观系详情页：正文在 div.news-content，发布时间形如 2026-10-21 06:30。

    正文异步渲染，首次可能抓空，失败时加长等待重试一次。
    """
    soup = None
    body = None
    for attempt, wait in enumerate((3000, 5500)):
        html = browser.render(item["url"], wait_ms=wait)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        body = soup.select_one("div.news-content") or soup.select_one("div.article")
        if body is not None and len(body.get_text(strip=True)) > 200:
            break

    if soup is None:
        item["summary"] = ""
        item["chars"] = 0
        return item

    if soup.title:
        t = clean_title(re.split(r"[_|｜]", soup.title.get_text())[0])
        if len(t) > len(item["title"]):
            item["title"] = t

    m = re.search(r"(20\d{2}-\d{2}-\d{2})\s+\d{1,2}:\d{2}", str(soup))
    if m:
        item["pub_date"] = m.group(1)
    if not item.get("pub_date"):
        item["pub_date"] = date.today().isoformat()

    text = body.get_text(" ", strip=True) if body is not None else ""
    text = SHARE_RE.sub("", text)
    text = _clean(text)
    item["chars"] = len(text)
    paras = [p for p in re.split(r"(?<=。)\s*", text) if len(p) > 20]
    item["summary"] = _clean("".join(paras)[:320])
    return item


def enrich(item: dict) -> dict:
    src = BY_KEY.get(item.get("source"))
    if src is not None and src.needs_browser:
        return enrich_browser(item)

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


def run(
    days_back: int = 2,
    enrich_limit: int = 120,
    workers: int = 4,
    browser_limit: int = 40,
) -> tuple[int, int]:
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

    if all_new:
        is_b = lambda x: BY_KEY[x["source"]].needs_browser
        b_items = sorted([x for x in all_new if is_b(x)], key=lambda x: x["pub_date"], reverse=True)
        h_items = sorted([x for x in all_new if not is_b(x)], key=lambda x: x["pub_date"], reverse=True)
        b_todo, h_todo = b_items[:browser_limit], h_items[:enrich_limit]

        print(f"补全详情：浏览器 {len(b_todo)} 篇（串行）· 直连 {len(h_todo)} 篇（并发）…", flush=True)
        enriched: list[dict] = []
        for x in b_todo:
            enriched.append(enrich(x))
        if h_todo:
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                enriched.extend(ex.map(enrich, h_todo))

        added = save(conn, enriched)
        done = {x["url"] for x in b_todo} | {x["url"] for x in h_todo}
        rest = [x for x in all_new if x["url"] not in done]
        if rest:
            added += save(conn, rest)
    else:
        added = 0

    browser.close()

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
