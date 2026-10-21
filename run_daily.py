"""每日入口：抓取 → 清洗 → 生成页面。双击「更新.bat」即走这个流程。

用法：
    python run_daily.py            日常更新（回溯 2 天）
    python run_daily.py --backfill 30   首次建库，回溯 30 天
"""

import sys
import traceback
from datetime import datetime

import build
import fetch
import normalize


def main() -> int:
    days = 2
    if "--backfill" in sys.argv:
        i = sys.argv.index("--backfill")
        days = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 30

    print("=" * 52)
    print(f"理论日课 · 更新  {datetime.now():%Y-%m-%d %H:%M:%S}   回溯 {days} 天")
    print("=" * 52)
    try:
        fetch.run(days_back=days, enrich_limit=400 if days > 7 else 150, workers=4)
    except Exception:
        traceback.print_exc()
        print("抓取阶段失败，继续用现有数据生成页面", file=sys.stderr)
    try:
        normalize.main()
        build.main()
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
