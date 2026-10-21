"""回填正文：把 chars 为 0 的条目重新抓一次详情页。

主要用于浏览器源（解放日报、文汇报）首次抓取时正文没渲染出来的情况。
"""

import sqlite3

import browser
import fetch
from sources import BY_KEY, classify, is_news


def main(limit: int = 80) -> None:
    conn = fetch.db()
    rows = conn.execute(
        """SELECT id,source,source_name,title,url,pub_date,section
           FROM articles
           WHERE (chars IS NULL OR chars = 0)
           ORDER BY pub_date DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    print(f"待回填 {len(rows)} 篇", flush=True)

    ok = 0
    for _id, src_key, src_name, title, url, pub_date, section in rows:
        item = {
            "id": _id, "source": src_key, "source_name": src_name,
            "title": title, "url": url, "pub_date": pub_date,
            "section": section or "", "chars": 0, "summary": "",
        }
        try:
            r = fetch.enrich(item)
        except Exception as e:
            print(f"  ! {title[:30]}: {type(e).__name__}", flush=True)
            continue
        if r.get("chars", 0) < 100:
            continue
        topic = classify(r["title"], r.get("summary") or "")
        news = 1 if (is_news(r["title"], r.get("summary") or "", r["chars"])
                     or fetch.is_video(r["title"], r["url"])) else 0
        conn.execute(
            """UPDATE articles SET title=?, pub_date=?, summary=?, chars=?, topic=?, is_news=?
               WHERE id=?""",
            (r["title"], r["pub_date"], r.get("summary", ""), r["chars"], topic, news, _id),
        )
        ok += 1
        print(f"  ✓ {r['chars']:5d}字 {r['title'][:38]}", flush=True)

    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM articles WHERE chars=0 OR chars IS NULL").fetchone()[0]
    conn.close()
    browser.close()
    print(f"回填成功 {ok}/{len(rows)} 篇，仍为空 {left} 篇")


if __name__ == "__main__":
    main()
