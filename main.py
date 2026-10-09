"""plamo-hangar 크롤러 진입점.

    python main.py                         # 수집 → docs/data 갱신 → 디스코드 발송
    python main.py --dry-run               # 파일은 쓰되 디스코드로 보내지 않고 보낼 내용을 출력
    python main.py --only hobby_item       # 일부 단계만 (hobby, hobby_schedule, hobby_brand, hobby_item, joyhobby, mall, translate, hobby_backfill)
    python main.py --bootstrap --only joyhobby   # 조이하비 과거 글 채우기 (실행당 --joy-pages쪽, 진행 위치는 meta.crawl.joyNext)
    python main.py --bootstrap --from 2025-10 --data-dir /tmp/data   # 최초 채우기(범위를 줄여 확인용으로)
    python main.py --brand-backfill        # 2015년 이전 상품 채우기(목록 카드만, 커서로 이어 함)
    python main.py --translate-only --translate-max 1500   # 수집 없이 번역만 (밀린 번역을 한 번에 채울 때)
    python main.py --discord-test          # 수집 없이 디스코드 테스트 알림 1건(feed.json 최근 3개). docs/data는 바꾸지 않는다. --dry-run이면 내용만 출력
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from crawler import config
from crawler.http import HttpClient
from crawler.pipeline import Options, run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="반다이 호비사이트 카탈로그·신제품 피드 수집")
    ap.add_argument("--dry-run", action="store_true", help="파일은 쓰되 디스코드로 보내지 않는다 (보낼 내용을 콘솔에 출력)")
    ap.add_argument("--no-discord", action="store_true", help="디스코드 발송을 끈다")
    ap.add_argument("--only", help="콤마로 구분한 단계만 실행: hobby, hobby_schedule, hobby_brand, hobby_item, joyhobby, mall, translate")
    ap.add_argument("--bootstrap", action="store_true", help="최초 채우기: 일정을 과거로, 걸프라 브랜드를 전체 쪽수로")
    ap.add_argument("--from", dest="from_month", metavar="YYYY-MM", help=f"--bootstrap 일정 시작 달 (기본 {config.SCHEDULE_START})")
    ap.add_argument("--max-new", type=int, default=config.DETAIL_NEW_MAX, help="실행당 상세: 새 상품 상한")
    ap.add_argument("--max-backlog", type=int, default=config.DETAIL_BACKLOG_MAX, help="실행당 상세: 밀린 상품 상한")
    ap.add_argument("--joy-pages", type=int, default=None, help=f"--bootstrap 때 조이하비 과거 목록을 훑을 쪽 수 (기본 {config.JOY_BACKFILL_PAGES})")
    ap.add_argument("--data-dir", type=Path, default=None, help=f"데이터 폴더 (기본 {config.DATA_DIR})")
    ap.add_argument("--brand-backfill", action="store_true", help="2015년 이전 상품 채우기: 건프라 등급 브랜드 목록(hg·hguc·mg·rg·mgsd·sd 계열)을 전체 쪽수로 훑는다. 커서로 이어 하고, 알림 없음")
    ap.add_argument("--translate-only", action="store_true", help="수집 없이 번역 단계만 실행한다 (--only translate와 같다). 상한은 --translate-max")
    ap.add_argument("--translate-max", type=int, default=config.TRANSLATE_MAX_PER_RUN, help=f"이번 실행에서 번역할 항목 수 상한 (기본 {config.TRANSLATE_MAX_PER_RUN}, 최신 발매순)")
    ap.add_argument("--mall-dump", type=Path, default=None, metavar="DIR", help="몰 단계가 받은 목록 응답 HTML과 summary.json을 이 폴더에 저장한다 (Actions mall_debug 진단용, 커밋하지 않음)")
    ap.add_argument("--discord-test", action="store_true", help="수집 없이 디스코드 테스트 알림 1건만 보낸다 (feed.json 최근 3개, 내 프라 연결 항목 포함)")
    args = ap.parse_args(argv)
    if args.from_month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.from_month):
        ap.error("--from은 YYYY-MM 형식이어야 합니다")
    if args.translate_max < 1 or args.translate_max > config.TRANSLATE_MAX_HARD:
        ap.error(f"--translate-max는 1 이상 {config.TRANSLATE_MAX_HARD} 이하여야 합니다")
    if args.translate_only and (args.only or args.bootstrap or args.brand_backfill or args.discord_test):
        ap.error("--translate-only는 --only, --bootstrap, --brand-backfill, --discord-test와 함께 쓸 수 없습니다")
    if args.max_new < 0 or args.max_backlog < 0:
        ap.error("--max-new/--max-backlog는 0 이상이어야 합니다")
    if args.joy_pages is not None and args.joy_pages < 1:
        ap.error("--joy-pages는 1 이상이어야 합니다")
    if args.discord_test and (args.bootstrap or args.only or args.from_month or args.joy_pages is not None):
        ap.error("--discord-test는 수집 옵션(--bootstrap, --only, --from, --joy-pages)과 함께 쓸 수 없습니다")
    if args.brand_backfill and (args.bootstrap or args.only or args.discord_test):
        ap.error("--brand-backfill은 --bootstrap, --only, --discord-test와 함께 쓸 수 없습니다 (그 단계만 따로 실행합니다)")
    return args


def _write_step_summary(result: dict) -> None:
    """GitHub Actions 실행 요약(마크다운)과 실패 소스 경고 주석."""
    meta = result["meta"]
    for name, s in meta["sources"].items():
        if not s.get("ok", True):
            print(f"::warning title=소스 실패 {name}::{s.get('error')}")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    st, cr = meta["stats"], meta["crawl"]
    lines = [
        "### crawl 요약", "",
        f"- 요청 {st['requests']}회 (종류별 {st['byKind']}), 소요 {st['elapsedSec']}초, 요청 간격 최소 {st.get('minGapSec')}초",
        f"- 카탈로그 {cr['counts']}, 밀린 상품(상세 대기) {cr['backlog']}",
        f"- 이번에 새로 발견 {result['newItems']}건 / 피드 추가 {result['feedAdded']}건 / 상세 {result['details']}",
        f"- 일정 커서 {cr.get('scheduleFrom')}, 걸프라 브랜드 완료 {cr.get('girlBrandsDone')}",
        *([f"- 2015년 이전 채우기 커서 {cr['brandBackfill']}"] if cr.get("brandBackfill") else []),
        f"- 조이하비 커서 다음 쪽 {cr.get('joyNext')}, 끝까지 훑음 {bool(cr.get('joyDone'))}, 기록 시작 {cr.get('joyOldest')}",
        "", "| 소스 | 결과 | 항목 | 오류 |", "|---|---|---|---|",
    ]
    for name, s in meta["sources"].items():
        lines.append(f"| {name} | {'ok' if s.get('ok') else 'FAIL'} | {s.get('items')} | {s.get('error') or s.get('skipped') or ''} |")
    diag = (meta["sources"].get("mall") or {}).get("diag") or []
    if diag:                                                  # 몰이 실패한 쪽의 응답 요약 — 실행 요약만 봐도 차단/개편을 가를 수 있게
        lines += ["", "#### 몰 실패 진단", "", "| 쪽 | HTTP | 최종 URL | 바이트 | title | 본문 앞부분 |", "|---|---|---|---|---|---|"]
        for d in diag:
            cells = [d["where"], d.get("status") or d.get("error"), d.get("finalUrl"), d.get("bytes"), d.get("title"), d.get("head")]
            lines.append("| " + " | ".join(str(c if c is not None else "").replace("|", "\\|") for c in cells) + " |")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv()
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "anthropic", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)       # SDK 요청 로그에 URL·키 정보가 섞이지 않게

    if args.discord_test:                                           # 수집·파일 쓰기 없이 알림 형식만 확인
        from crawler import discord_test
        return discord_test.run(args.data_dir or config.DATA_DIR, dry_run=args.dry_run)

    opts = Options(
        dry_run=args.dry_run, no_discord=args.no_discord,
        only={"translate"} if args.translate_only else {s.strip() for s in args.only.split(",") if s.strip()} if args.only else None,
        bootstrap=args.bootstrap, from_month=args.from_month,
        max_new=args.max_new, max_backlog=args.max_backlog, joy_pages=args.joy_pages,
        data_dir=args.data_dir or config.DATA_DIR, report_dir=config.REQUEST_LOG.parent, brand_backfill=args.brand_backfill,
        translate_max=args.translate_max, mall_dump=args.mall_dump,
    )
    opts.stages()                                                  # 잘못된 --only는 여기서 바로 실패
    http = HttpClient(log_path=config.REQUEST_LOG)
    result = run(opts, http)

    meta = result["meta"]
    print(f"\n완료: 카탈로그 {meta['crawl']['counts']} · 밀린 상품 {meta['crawl']['backlog']} · "
          f"새로 발견 {result['newItems']} · 피드 추가 {result['feedAdded']} · 상세 {result['details']} · "
          f"요청 {meta['stats']['requests']}회 {meta['stats']['elapsedSec']}초 (간격 최소 {meta['stats'].get('minGapSec')}초)")
    _write_step_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
