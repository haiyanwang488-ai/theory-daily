"""微信推送：把当日文章整理成标题清单，通过 Server酱 发到微信。

用法：
    python push.py             正常推送（每天只推一次，重复运行会跳过）
    python push.py --dry-run   只打印将要发送的内容，不发请求
    python push.py --force     忽略「今天已推过」的限制

配置在 config.json，SendKey 从 https://sct.ftqq.com/sendkey 获取。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import requests

import build

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "data" / "theory.db"

API = "https://sctapi.ftqq.com/{key}.send"
DEFAULT_CONFIG = {
    "serverchan": {"sendkey": ""},
    "push": {"max_items": 80, "skip_empty": True},
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for k, v in user.items():
            if isinstance(v, dict):
                cfg.setdefault(k, {}).update(v)
            else:
                cfg[k] = v
    return cfg


def get_sendkey(cfg: dict) -> str:
    """环境变量优先（云端用 Secrets），其次本地 config.json。"""
    return (os.environ.get("SERVERCHAN_SENDKEY") or cfg["serverchan"].get("sendkey") or "").strip()


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pushes(
             day TEXT PRIMARY KEY, ts TEXT, n INTEGER, ok INTEGER, msg TEXT)"""
    )
    conn.commit()


def already_pushed(conn: sqlite3.Connection, day: str) -> bool:
    row = conn.execute("SELECT ok FROM pushes WHERE day=?", (day,)).fetchone()
    return bool(row and row[0])


# ---------------------------------------------------------------- 内容组织

def collect_today(conn: sqlite3.Connection, day: str) -> list[dict]:
    """复用 build 的去重与过滤逻辑，保证推送与页面看到的一致。"""
    arts = build.load(conn)
    return [a for a in arts if a["pub_date"] == day]


def group_by_topic(arts: list[dict]) -> list[tuple[str, list[dict]]]:
    order = {t: i for i, t in enumerate(build.TOPIC_ORDER)}
    buckets: dict[str, list[dict]] = {}
    for a in arts:
        buckets.setdefault(a["topic"], []).append(a)
    for v in buckets.values():
        v.sort(key=lambda x: (-x["weight"], -len(x["summary"] or "")))
    return sorted(buckets.items(), key=lambda kv: order.get(kv[0], 99))


def render(arts: list[dict], day: str, site_ok: bool = True) -> tuple[str, str]:
    d = datetime.strptime(day, "%Y-%m-%d")
    title = f"理论日课 · {d.month}月{d.day}日 · {len(arts)}篇"

    lines = [
        f"**{day}　共 {len(arts)} 篇**",
        "",
    ]
    for topic, items in group_by_topic(arts):
        lines.append(f"**{topic}（{len(items)}）**")
        for a in items:
            src = a["short"]
            lines.append(f"- [{a['title']}]({a['url']}) — {src}")
        lines.append("")
    lines.append("---")
    lines.append("点标题直达原文。完整页面见本地「理论日课」。")
    return title, "\n".join(lines)


def send(sendkey: str, title: str, desp: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            API.format(key=sendkey),
            data={"title": title[:100], "desp": desp},
            timeout=25,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        j = r.json()
        if j.get("code") == 0:
            return True, "ok"
        return False, json.dumps(j, ensure_ascii=False)[:200]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    cfg = load_config()
    day = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    arts = collect_today(conn, day)

    if not arts:
        print(f"{day} 没有新文章，不推送。")
        conn.close()
        return 0
    if cfg["push"].get("skip_empty", True) and len(arts) == 0:
        conn.close()
        return 0
    if not dry and not force and already_pushed(conn, day):
        print(f"{day} 已经推过，跳过（用 --force 强制重推）。")
        conn.close()
        return 0

    max_items = int(cfg["push"].get("max_items", 80))
    if len(arts) > max_items:
        arts = arts[:max_items]

    title, desp = render(arts, day)

    if dry:
        print("=" * 60)
        print("标题：", title)
        print("=" * 60)
        print(desp[:3000])
        print("=" * 60)
        print(f"正文 {len(desp)} 字符，共 {len(arts)} 篇")
        conn.close()
        return 0

    key = get_sendkey(cfg)
    if not key:
        print("未配置 SendKey。本地填 config.json，云端设环境变量 SERVERCHAN_SENDKEY。")
        print("获取地址：https://sct.ftqq.com/sendkey")
        conn.close()
        return 2

    ok, msg = send(key, title, desp)
    conn.execute(
        "INSERT OR REPLACE INTO pushes(day,ts,n,ok,msg) VALUES(?,?,?,?,?)",
        (day, datetime.now().isoformat(timespec="seconds"), len(arts), 1 if ok else 0, msg),
    )
    conn.commit()
    conn.close()
    print(("推送成功" if ok else "推送失败") + f"：{title}　{msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
