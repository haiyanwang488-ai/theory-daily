"""就地清洗已有数据：剥标题后缀、重算主题、标记会议资讯。

抓取规则调整后跑一次即可，不重新请求源站。
"""

import sqlite3

from fetch import DB_PATH
from sources import classify, clean_title, is_news, is_video


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
    if "is_news" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN is_news INTEGER DEFAULT 0")
        conn.commit()

    rows = conn.execute("SELECT id,title,summary,url,chars FROM articles").fetchall()
    changed_title = changed_topic = news = 0
    for _id, title, summary, url, chars in rows:
        t2 = clean_title(title)
        topic = classify(t2, summary or "")
        flag = 1 if (is_news(t2, summary or "", chars or 0) or is_video(t2, url)) else 0
        old_topic = conn.execute("SELECT topic FROM articles WHERE id=?", (_id,)).fetchone()[0]
        if t2 != title:
            changed_title += 1
        if topic != old_topic:
            changed_topic += 1
        news += flag
        conn.execute(
            "UPDATE articles SET title=?, topic=?, is_news=? WHERE id=?",
            (t2, topic, flag, _id),
        )
    conn.commit()
    print(f"清洗完成：标题修正 {changed_title} 条，主题调整 {changed_topic} 条，标记资讯 {news} 条")
    conn.close()


if __name__ == "__main__":
    main()
