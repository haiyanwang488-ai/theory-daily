"""每日一次完整流程：确保数据最新 → 推送到微信（当天只推一次）。

定时触发和手动触发都走这里，重复执行是安全的：
抓取是幂等的（已有的不会重抓），推送有 pushes 表挡重复。

用法：
    python morning.py               抓取 + 建页 + 推送
    python morning.py --no-push     只抓取 + 建页（晚间刷新网页用）
    python morning.py --force       忽略「今天已推过」，强制重推
"""

import sys
import traceback

import build
import fetch
import normalize
import push


def main() -> int:
    # 1. 抓取 + 清洗 + 重建页面（幂等，已抓过的源返回"新增 0 条"）
    try:
        fetch.run(days_back=2, enrich_limit=150, workers=4)
    except Exception:
        traceback.print_exc()
        print("抓取失败，用现有数据继续", file=sys.stderr)

    try:
        normalize.main()
        build.main()
    except Exception:
        traceback.print_exc()
        return 1

    # 2. 晚间那次只要网页新，不要重复推送
    if "--no-push" in sys.argv:
        print("--no-push：已跳过推送")
        return 0

    # 3. 推送（内部判断今天是否已推过，推过就跳过）
    return push.main()


if __name__ == "__main__":
    raise SystemExit(main())
