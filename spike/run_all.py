"""spike 전체 실행 (로컬/Actions 공용).

    python spike/run_all.py --env local    # 결과: spike/out/, fixtures: tests/fixtures/
    python spike/run_all.py --env actions --out spike/out-actions

한 사이트가 실패해도 나머지는 계속한다. 상세 페이지는 합계 30개 이하(common.DETAIL_TOTAL_CAP),
요청 간격은 1.2초 이상이다. 캐시(out/cache)가 있으면 그 URL은 다시 요청하지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--env", choices=["local", "actions"], default="local")
ap.add_argument("--out", default=None, help="결과 폴더 (repo 기준 상대경로)")
ap.add_argument("--only", default="hobby,pbandai,joyhobby,hotlink", help="콤마 구분 부분 실행")
args = ap.parse_args()

# common이 import 시점에 환경변수를 읽으므로 먼저 설정
os.environ["SPIKE_ENV"] = args.env
os.environ["SPIKE_OUT"] = args.out or ("spike/out" if args.env == "local" else "spike/out-actions")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import hobby  # noqa: E402
import hotlink_check  # noqa: E402
import joyhobby  # noqa: E402
import pbandai  # noqa: E402


def main() -> int:
    only = set(args.only.split(","))
    status: dict[str, str] = {}
    ja = common.Browser("ja-JP")
    en = common.Browser("en-US")
    ko = common.Browser("ko-KR")
    steps = [
        ("hobby", lambda: hobby.run(ja)),
        ("pbandai", lambda: pbandai.run(ja, en)),
        ("joyhobby", lambda: joyhobby.run(ko)),
        ("hotlink", lambda: hotlink_check.run(ja)),
    ]
    try:
        for name, fn in steps:
            if name not in only:
                continue
            print(f"\n===== {name} =====")
            try:
                fn()
                status[name] = "ok"
            except Exception as e:  # 한 소스 실패가 전체를 멈추지 않는다
                status[name] = f"FAILED: {e!r}"
                traceback.print_exc()
    finally:
        for b in (ja, en, ko):
            try:
                b.close()
            except Exception:
                pass
        common.shutdown()

    summary = {
        "env": args.env, "out": os.environ["SPIKE_OUT"], "python": platform.python_version(),
        "platform": platform.platform(), "steps": status,
        "detail_pages_used": common._budget()["detail"], "detail_total": common.detail_used(),
        "detail_total_cap": common.DETAIL_TOTAL_CAP,
    }
    common.summary_write("run-summary.json", summary)
    print("\n", json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if all(v == "ok" for v in status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
