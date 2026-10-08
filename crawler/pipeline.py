"""실행 파이프라인 — 이전 상태 로드 → 일정 → 걸프라 브랜드 → 상세 → 조이하비 국내 입고 → 번역 → 피드 → 파일 쓰기 → 디스코드.

소스(단계)는 각각 격리한다: 한 단계가 실패해도 나머지는 계속하고, 실패는 meta.sources에 남긴다.
`main.py`는 인자 처리만 하고 이 모듈의 run()을 부른다 (테스트는 가짜 HttpClient로 run()을 직접 부른다).
"""
from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from . import config, discord, feed, kr, mine, series, translate
from .catalog import Catalog
from .http import Blocked, HttpClient, SourceAborted
from .sources import hobby_brand, hobby_item, hobby_schedule, joyhobby
from .store import iso, now_kst, read_json, write_json

log = logging.getLogger("plamo.pipeline")

HOBBY_STAGES = ("hobby_schedule", "hobby_brand", "hobby_item")
SOURCE_STAGES = (*HOBBY_STAGES, "joyhobby")            # 수집 단계 (translate 앞)
ALL_STAGES = (*SOURCE_STAGES, "translate")


@dataclass
class Options:
    dry_run: bool = False
    no_discord: bool = False
    only: set[str] | None = None            # None이면 전부. "hobby"는 hobby_* 세 단계
    bootstrap: bool = False
    from_month: str | None = None           # --bootstrap 때 일정을 거슬러 올라갈 시작 달 (YYYY-MM)
    max_new: int = config.DETAIL_NEW_MAX
    max_backlog: int = config.DETAIL_BACKLOG_MAX
    joy_pages: int | None = None            # --bootstrap 때 조이하비 과거 쪽 수 (None이면 config.JOY_BACKFILL_PAGES)
    data_dir: Path = field(default_factory=lambda: config.DATA_DIR)
    report_dir: Path | None = None          # 조이하비 전체 보고서(joy-report.json)를 쓸 폴더. None이면 쓰지 않는다

    def stages(self) -> set[str]:
        if self.only is None:
            # dry-run은 Claude API 비용이 드는 번역을 기본으로 건너뛴다 (필요하면 --only translate로 명시)
            return set(ALL_STAGES) - ({"translate"} if self.dry_run else set())
        out: set[str] = set()
        for name in self.only:
            if name == "hobby":
                out |= set(HOBBY_STAGES)
            elif name in ALL_STAGES:
                out.add(name)
            else:
                raise ValueError(f"알 수 없는 --only 값: {name} (가능: hobby, {', '.join(ALL_STAGES)})")
        return out


class _Ctx:
    """한 실행의 가변 상태."""

    def __init__(self, opts: Options, http: HttpClient, catalog: Catalog, crawl: dict, now: datetime):
        self.opts, self.http, self.catalog, self.crawl = opts, http, catalog, crawl
        self.now, self.now_iso = now, iso(now)
        self.new_ids: list[str] = []              # 이번 실행에서 처음 발견한 항목 (발견 순서)
        self.unknown_keys: set[str] = set()
        self.detail_counts = {"new": 0, "backlog": 0, "excluded": 0, "failed": 0}
        self.arrivals = kr.Arrivals()
        self.manual: dict = {}                    # 사용자가 연결한 미등록 상품 처리 결과 (meta.sources.hobby_item.manual)
        self.joy_scan: dict = {}                  # 조이하비 단계의 이번 실행 통계

    def add_card(self, card: dict, brand_key: str | None = None) -> None:
        item, is_new = self.catalog.upsert_card(card, self.now_iso, brand_key)
        if is_new and item is not None:
            self.new_ids.append(item["id"])


# ---------------------------------------------------------------- 단계
def stage_schedule(ctx: _Ctx) -> tuple[int, list[str]]:
    """일정 카드를 카탈로그에 올린다. → (처리한 카드 수, 실패한 달들)."""
    cur = hobby_schedule.current_month(ctx.now.date())
    months = hobby_schedule.month_range(cur, hobby_schedule.month_add(cur, config.SCHEDULE_AHEAD_MONTHS))
    past: list[str] = []
    start = ctx.opts.from_month or config.SCHEDULE_START
    sf = ctx.crawl.get("scheduleFrom")
    if ctx.opts.bootstrap and (sf is None or start < sf):
        end = hobby_schedule.month_add(sf, -1) if sf else hobby_schedule.month_add(cur, -1)
        past = list(reversed(hobby_schedule.month_range(start, end)))      # 최신 달부터 거슬러 올라간다 (재개 가능)

    cards_n, failed = 0, []
    for ym in months:
        cards = hobby_schedule.fetch_month(ctx.http, ym)
        if cards is None:
            failed.append(ym)
            continue
        for c in cards:
            ctx.add_card(c)
        cards_n += len(cards)

    lowest_ok = None
    for ym in past:
        cards = hobby_schedule.fetch_month(ctx.http, ym)
        if cards is None:                                                   # 빠진 달이 생기면 거기서 멈추고 커서를 남긴다
            failed.append(ym)
            break
        for c in cards:
            ctx.add_card(c)
        cards_n += len(cards)
        lowest_ok = ym
    if lowest_ok is not None:
        ctx.crawl["scheduleFrom"] = lowest_ok if sf is None else min(sf, lowest_ok)
    return cards_n, failed


def stage_brand(ctx: _Ctx) -> tuple[int, list[str]]:
    """걸프라 브랜드 목록. 일반 실행은 1쪽, --bootstrap이면 아직 끝나지 않은 브랜드는 전체 쪽수."""
    done: list[str] = list(ctx.crawl.get("girlBrandsDone", []))
    cards_n, failed = 0, []
    for key in config.GIRL_BRANDS:
        first = hobby_brand.fetch_page(ctx.http, key, 1)
        if first is None:
            failed.append(key)
            continue
        for c in first["items"]:
            ctx.add_card(c, brand_key=key)
        cards_n += len(first["items"])
        if not (ctx.opts.bootstrap and key not in done):
            continue
        complete = True
        for page in range(2, first["last_page"] + 1):
            data = hobby_brand.fetch_page(ctx.http, key, page)
            if data is None:
                failed.append(f"{key}:{page}")
                complete = False
                break
            for c in data["items"]:
                ctx.add_card(c, brand_key=key)
            cards_n += len(data["items"])
        if complete:
            done.append(key)
    ctx.crawl["girlBrandsDone"] = done
    return cards_n, failed


def stage_item(ctx: _Ctx) -> tuple[int, list[str]]:
    """상세: 사용자가 사이트에서 연결한 미등록 상품(먼저, 최대 MANUAL_DETAIL_MAX) + 새 상품 최대 max_new + 밀린 상품 최대 max_backlog."""
    failed: list[str] = []
    wanted, unsupported = ctx.catalog.manual_wanted(mine.catalog_ids(ctx.opts.data_dir), config.MANUAL_DETAIL_MAX, ctx.now_iso)
    ctx.manual = {"requested": len(wanted), "added": 0, "other": 0, "unsupported": unsupported, "failed": []}
    new_sel, back_sel = ctx.catalog.select_details(ctx.opts.max_new, ctx.opts.max_backlog, ctx.new_ids)
    new_sel = [i for i in new_sel if i not in wanted]
    back_sel = [i for i in back_sel if i not in wanted]
    ctx.http.detail_limit = len(wanted) + len(new_sel) + len(back_sel)
    for cid in wanted:
        detail, status = hobby_item.fetch_detail(ctx.http, cid[3:])
        if detail is None:
            ctx.catalog.record_detail_failure(cid, status)          # 404면 제외 목록으로, 아니면 실패 횟수만
            ctx.catalog.drop_unresolved_manual(cid)
            ctx.manual["failed"].append(cid)
            if status != 404:
                failed.append(cid)
            continue
        outcome, unknown = ctx.catalog.apply_detail(cid, detail, ctx.now_iso)
        ctx.unknown_keys.update(unknown)
        ctx.manual["added"] += 1
        ctx.manual["other"] += ctx.catalog.items[cid].get("line") == "other"
    for kind, ids in (("new", new_sel), ("backlog", back_sel)):
        for cid in ids:
            detail, status = hobby_item.fetch_detail(ctx.http, cid[3:])
            if detail is None:
                ctx.catalog.record_detail_failure(cid, status)
                ctx.detail_counts["failed"] += 1
                failed.append(cid)
                continue
            outcome, unknown = ctx.catalog.apply_detail(cid, detail, ctx.now_iso)
            ctx.unknown_keys.update(unknown)
            ctx.detail_counts["excluded" if outcome == "excluded" else kind] += 1
    return ctx.manual["added"] + ctx.detail_counts["new"] + ctx.detail_counts["backlog"] + ctx.detail_counts["excluded"], failed


def stage_joyhobby(ctx: _Ctx) -> tuple[int, list[str]]:
    """조이하비 공지 게시판 → 반다이 입고 글의 원본 행. → (본문을 읽은 글 수, 실패한 목록/글).

    매 실행 1~JOY_DAILY_PAGES쪽을 훑어 새 글을 찾는다. --bootstrap이면 거기에 더해 과거 쪽을 JOY_BACKFILL_PAGES(또는 --joy-pages)만큼
    `meta.crawl.joyNext`(연속으로 훑은 다음 쪽)부터 이어서 훑는다. 게시판 끝(마지막 쪽)에 닿으면 joyDone.
    연결·kr·피드는 이 단계가 끝난 뒤 run()이 한다."""
    arr, crawl = ctx.arrivals, ctx.crawl
    failed: list[str] = []
    cursor = crawl.get("joyNext") or 1
    pages = list(range(1, config.JOY_DAILY_PAGES + 1))
    if ctx.opts.bootstrap and not crawl.get("joyDone"):
        start = max(cursor, config.JOY_DAILY_PAGES + 1)
        pages += list(range(start, start + (ctx.opts.joy_pages or config.JOY_BACKFILL_PAGES)))
    seen_ids: set[str] = set()
    scanned = new_posts = 0
    for page in pages:
        if page > config.JOY_BOARD_MAX_PAGE:
            break
        rows = joyhobby.fetch_board_page(ctx.http, page)
        if rows is None:
            failed.append(f"list:{page}")
            break
        fresh = [r for r in rows if r["id"] not in seen_ids]
        seen_ids.update(r["id"] for r in rows)
        if not fresh and page > 1:                   # 게시판 끝을 넘은 쪽은 마지막 행만 되풀이한다
            if page == cursor:
                crawl["joyDone"] = True
            break
        scanned += 1
        new_posts += sum(arr.note_board_row(r) for r in fresh)
        if page == cursor:                           # 1쪽부터 끊김 없이 훑은 범위만 커서와 "기록 시작일"에 반영한다
            cursor += 1
            crawl["joyNext"] = cursor
            dates = [r["date"] for r in rows if r["date"]]
            if dates:
                crawl["joyOldest"] = min([*dates, crawl["joyOldest"]] if crawl.get("joyOldest") else dates)
        if len(rows) < config.JOY_BOARD_PAGE_SIZE:   # 마지막 쪽
            if page == cursor - 1:
                crawl["joyDone"] = True
            break

    todo = arr.pending(config.JOY_POSTS_PER_RUN_MAX)
    ctx.http.detail_limit = ctx.http.stats.by_kind["detail"] + len(todo)     # 안전장치: 계획한 수 이상은 요청하지 않는다
    fetched = broken = 0
    try:
        for pid in todo:
            parsed, status, site_bug = joyhobby.fetch_post(ctx.http, pid)
            if parsed is None:
                arr.record_failure(pid, status, site_bug=site_bug)
                if site_bug:                         # 글 하나의 사이트 버그이지 차단·장애가 아니다: 연속 실패로 세지 않고 다음 글로
                    ctx.http.reset_breaker()
                    broken += 1
                else:
                    failed.append(f"post:{pid}")
                continue
            arr.record_post(pid, parsed)
            fetched += 1
    finally:
        ctx.http.detail_limit = None
        ctx.joy_scan = {"pagesScanned": scanned, "newPosts": new_posts, "postsFetched": fetched, "postsBroken": broken,
                        "pendingLeft": len(arr.pending(10**9))}      # 중간에 멎어도 지금까지의 통계를 남긴다
    return fetched, failed


STAGE_FUNCS = {"hobby_schedule": stage_schedule, "hobby_brand": stage_brand, "hobby_item": stage_item,
               "joyhobby": stage_joyhobby}


def _run_stage(ctx: _Ctx, name: str) -> dict:
    ctx.http.reset_breaker()
    status = {"ok": True, "at": iso(now_kst()), "items": 0, "error": None}
    try:
        n, failed = STAGE_FUNCS[name](ctx)
        status["items"] = n
        if failed:
            status["ok"], status["error"] = False, f"{len(failed)}건 실패: " + ", ".join(failed[:8]) + (" …" if len(failed) > 8 else "")
    except (SourceAborted, Blocked) as e:
        log.warning("%s 중단: %s", name, e)
        status["ok"], status["error"] = False, f"중단: {e}"
    except Exception as e:    # 한 소스의 예기치 못한 오류가 전체 실행을 멈추지 않게 한다 (CLAUDE.md Rules)
        log.exception("%s 오류", name)
        status["ok"], status["error"] = False, f"{type(e).__name__}: {e}"[:200]
    return status


# ---------------------------------------------------------------- 실행
def run(opts: Options, http: HttpClient, *, now: datetime | None = None, anthropic_client=None,
        post=requests.post, out=print) -> dict:
    now = now or now_kst()
    now_iso = iso(now)
    data_dir = Path(opts.data_dir)
    stages = opts.stages()

    prev_meta = read_json(data_dir / config.META_FILE, {}) or {}
    prev_feed_doc = read_json(data_dir / config.FEED_FILE, {}) or {}
    prev_feed: list[dict] = prev_feed_doc.get("items", [])
    catalog = Catalog.load(data_dir)
    series_known = series.load(data_dir)
    crawl = {"scheduleFrom": None, "girlBrandsDone": [], **(prev_meta.get("crawl") or {})}
    # 분류표에서 걸프라가 아니게 된 브랜드는 커서에서도 뺀다 (--only와 무관하게 실행 시작에 정리)
    crawl["girlBrandsDone"] = [k for k in crawl["girlBrandsDone"] if k in config.GIRL_BRANDS]
    ctx = _Ctx(opts, http, catalog, crawl, now)
    ctx.unknown_keys.update(prev_meta.get("unknownBrandKeys", []))
    sources: dict[str, dict] = {}

    # 분류표·용어집을 고친 뒤 이전 실행에서 쌓인 항목에도 반영한다 (수집 단계 전에, --only와 무관하게)
    fixups = catalog.reclassify(now_iso)
    fixups["nameKoReplaced"] = catalog.apply_name_ko_replacements(config.NAME_KO_REPLACEMENTS)
    # 번역에 원문에 없는 한자가 섞인 기존 결과는 비워 이번 실행에서 다시 번역한다 (가나 검사가 못 거르는 오번역)
    reset_names = catalog.reset_stray_han()
    reset_series = series.drop_stray_han(series_known)
    fixups["strayHanReset"] = len(reset_names) + len(reset_series)
    if reset_names or reset_series:
        log.info("한자 혼입 번역을 비웠습니다(재번역 대상): 이름 %s, 시리즈 %s", reset_names, reset_series)

    if "joyhobby" in stages:
        ctx.arrivals = kr.Arrivals.load(data_dir)
    for name in SOURCE_STAGES:
        if name in stages:
            sources[name] = _run_stage(ctx, name)
    if "hobby_item" in sources and ctx.manual:
        sources["hobby_item"]["manual"] = ctx.manual
    if "joyhobby" in stages:       # 수집이 중간에 멎었어도 지금까지 모은 행으로 (다시) 연결한다
        joy_rep = kr.link_all(ctx.arrivals, catalog, now_iso)
        ctx.arrivals.save(data_dir, now_iso)
        sources["joyhobby"].update({**ctx.arrivals.stats(), **ctx.joy_scan, "newLinks": len(joy_rep["newLinks"]),
                                    "nameChanged": joy_rep["nameChanged"], "krAdded": joy_rep["krAdded"]})
        _report_joy(out, ctx, joy_rep, opts.report_dir, catalog)

    if "translate" in stages:
        res = translate.translate_pending(catalog, now_iso, client=anthropic_client)
        sources["translate"] = {"ok": res["ok"], "at": iso(now_kst()), "items": res["done"], "error": res["error"],
                                "pending": res["pending"], "skipped": res["skipped"], "model": res["model"],
                                "kanaRetried": res["kanaRetried"], "kanaRejected": res["kanaRejected"]}
        fixups["nameKoReplaced"] += catalog.apply_name_ko_replacements(config.NAME_KO_REPLACEMENTS)
        sres = series.translate_pending(catalog, series_known, client=anthropic_client)       # 새 시리즈만 (사전에 있으면 API를 부르지 않는다)
        t = sources["translate"]
        t.update({"ok": t["ok"] and sres["ok"], "error": t["error"] or sres["error"], "seriesDone": sres["done"], "seriesPending": sres["pending"], "seriesSkipped": sres["skipped"]})
    elif opts.dry_run and opts.only is None:
        sources["translate"] = {"ok": True, "at": iso(now_kst()), "items": 0, "error": None, "skipped": "dry-run"}

    # 시리즈 한국어: 사전(+덮어쓰기 표)을 항목에 채운다. API 키가 없거나 dry-run이어도 이미 아는 시리즈는 항상 채운다
    fixups["seriesKoApplied"] = series.apply(catalog, series_known)

    # 피드: 이번에 처음 발견한 항목 + 이전 피드
    prev_snapshot = copy.deepcopy(prev_feed)               # merge_feed가 빈 칸(titleKo·image)을 제자리에서 보충하므로 비교용 복사
    new_items = feed.new_feed_items(catalog, ctx.new_ids, now, now_iso)
    notify_kr: set[str] = set()
    if "joyhobby" in stages:
        kr.refresh_feed(prev_feed, ctx.arrivals, catalog)            # 나중에 연결된 입고 항목의 catalogId·image·type 보충 (added는 그대로)
        kr_items, notify_kr = kr.feed_items(ctx.arrivals, catalog, now.astimezone(config.KST).date(), now_iso)
        new_items = new_items + kr_items
    merged, added = feed.merge_feed(prev_feed, new_items, catalog)
    feed.reset_stray_han(merged)
    merged, _ = feed.merge_feed(merged, [], catalog)                     # 비운 titleKo는 카탈로그의 (다시 번역된) 이름으로 채운다
    fixups["feedTitleKoReplaced"] = feed.apply_title_ko_replacements(merged, config.NAME_KO_REPLACEMENTS)

    # 파일 쓰기 (dry-run도 파일은 쓴다. 디스코드만 보내지 않는다)
    counts = catalog.save(data_dir, now_iso)
    series.save(data_dir, series_known, now_iso)
    feed_updated = prev_feed_doc.get("updatedAt", now_iso) if merged == prev_snapshot else now_iso
    write_json(data_dir / config.FEED_FILE, {"updatedAt": feed_updated, "items": merged})
    crawl["backlog"] = catalog.backlog_count()
    crawl["counts"] = catalog.counts()
    crawl["lastFixups"] = fixups                      # 이번 실행의 재분류·후처리 결과 (매 실행 덮어쓴다)
    stats = http.stats.as_dict()
    stats["minGapSec"] = round(http.stats.min_gap, 2) if http.stats.min_gap is not None else None
    meta = {
        "updatedAt": now_iso,
        "since": crawl.get("joyOldest") or prev_meta.get("since") or now.date().isoformat(),   # 조이하비 기록 시작일(훑은 가장 오래된 글 날짜)이 있으면 그것
        "sources": {**(prev_meta.get("sources") or {}), **sources},
        "crawl": crawl,
        "stats": stats,
        "unknownBrandKeys": sorted(ctx.unknown_keys),
    }
    write_json(data_dir / config.META_FILE, meta)

    # 조이하비 항목은 글 날짜가 KR_NOTIFY_DAYS일 이내인 것만 알린다 (피드 노출은 KR_FEED_DAYS일)
    to_notify = [a for a in added if not a["id"].startswith("jh-") or a["id"] in notify_kr]
    notified = _notify(opts, to_notify, prev_feed_empty=not prev_feed, prev_catalog_empty=catalog.was_empty, post=post, out=out,
                       mine_map=mine.owned_map(data_dir))      # collection.json은 읽기만 한다
    return {"meta": meta, "catalog": counts, "newItems": len(ctx.new_ids), "feedAdded": len(added),
            "details": ctx.detail_counts, "notified": notified}


def _links_table(arr: kr.Arrivals, catalog) -> str:
    """현재 codeMap 전체를 사람이 검토하기 쉬운 표로. 점수 낮은 순 — 틀린 연결은 위쪽에서 찾는다."""
    latest = arr.latest_rows()
    lines = ["점수 | 차이 | 방법 | 이름교체 | 상품코드 | 조이하비 상품명 | 카탈로그 id | 카탈로그 이름(교체 전) → (교체 후)"]
    for code, e in sorted(arr.code_map.items(), key=lambda kv: (kv[1]["score"] is not None, kv[1]["score"] or 0, kv[0])):
        item = catalog.items.get(e["catalogId"], {})
        before = item.get("nameKoAi") if item.get("nameKoSource") == "joyhobby" else item.get("nameKo")
        after = item.get("nameKo")
        lines.append(f"{e['score']} | {e['margin']} | {e['method']} | {'예' if e.get('nameApplied') else '-'} | {code} | "
                     f"{(latest.get(code) or {}).get('name', '?')} | {e['catalogId']} | {before} → {after}")
    return "\n".join(lines) + "\n"


def _report_joy(out, ctx: _Ctx, rep: dict, report_dir: Path | None, catalog, show: int = 25) -> None:
    """조이하비 단계 요약(콘솔) + 전체 보고서(joy-report.json: 새로 한 일이 있을 때만) + 연결표(joy-links.txt: 매번)."""
    arr, st = ctx.arrivals, ctx.arrivals.stats()
    pct = f"{100 * st['linkedCodes'] / st['codes']:.0f}%" if st["codes"] else "-"
    out(f"[조이하비] 글 {st['posts']}개 {st['postStates']} · 행 {st['rows']} · 코드 {st['codes']}개 중 연결 {st['linkedCodes']} ({pct}) "
        f"· 이번 실행: 목록 {ctx.joy_scan.get('pagesScanned', 0)}쪽, 새 글 {ctx.joy_scan.get('newPosts', 0)}, "
        f"본문 {ctx.joy_scan.get('postsFetched', 0)}건, 새 연결 {len(rep['newLinks'])}, nameKo 교체 {rep['nameChanged']}, kr 추가 {rep['krAdded']}")
    if rep["newLinks"]:
        out(f"[조이하비] codeMap 신규 연결 {len(rep['newLinks'])}건" + (f" (앞 {show}건)" if len(rep["newLinks"]) > show else ""))
        for n in rep["newLinks"][:show]:
            out(f"  {n['code']} 점수 {n['score']} 차이 {n['margin']}{' [이름교체]' if n['nameOk'] else ''}  {n['joy'][:46]}  ↔  {n['catalogId']} {n['catalogNameKo']}")
    no_bd = sorted(((pid, p) for pid, p in arr.posts.items() if p["state"] == "no-bd"), key=lambda kv: -int(kv[0]))
    if no_bd:
        out(f"[조이하비] 후보였지만 BD 행 없음 {len(no_bd)}건" + (f" (앞 {show}건)" if len(no_bd) > show else ""))
        for pid, p in no_bd[:show]:
            out(f"  {pid} {p['date']} {p['title']}")
    if report_dir is not None:
        Path(report_dir).mkdir(parents=True, exist_ok=True)
        (Path(report_dir) / "joy-links.txt").write_text(_links_table(arr, catalog), encoding="utf-8")
        if rep["newLinks"] or rep["nameChanged"] or rep["krAdded"] or ctx.joy_scan.get("postsFetched"):     # 아무 일도 없던 실행이 이전 보고서를 덮어쓰지 않게
            report = {"at": iso(ctx.now), "stats": st, "scan": ctx.joy_scan, "crawl": {k: v for k, v in ctx.crawl.items() if k.startswith("joy")},
                      "link": rep, "noBdPosts": [{"post": pid, **p} for pid, p in no_bd]}
            (Path(report_dir) / "joy-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def _notify(opts: Options, added: list[dict], *, prev_feed_empty: bool, prev_catalog_empty: bool, post, out, mine_map: dict | None = None) -> int:
    """디스코드. 반환: 실제로 보낸 메시지 수 (dry-run·건너뜀은 0)."""
    reason = discord.skip_reason(prev_feed_empty=prev_feed_empty, prev_catalog_empty=prev_catalog_empty,
                                 bootstrap=opts.bootstrap)
    messages, overflow = discord.plan_messages(added, mine_map)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if opts.dry_run:
        # dry-run은 형식을 눈으로 볼 수 있게 항상 보낼 내용을 출력한다 (규칙상 건너뛰는 경우는 그 사실을 먼저 알린다)
        if reason:
            out(f"[디스코드 dry-run] 실제 실행에서는 보내지 않음: {reason} — 아래는 형식 확인용")
        for line in discord.describe(messages, overflow):
            out(line)
        return 0
    if reason:
        out(f"[디스코드] {reason}")
        return 0
    if opts.no_discord or not webhook:
        out("[디스코드] " + ("--no-discord" if opts.no_discord else "DISCORD_WEBHOOK_URL 없음") + " — 발송하지 않고 내용만 출력")
        for line in discord.describe(messages, overflow):
            out(line)
        return 0
    if not messages:
        out("[디스코드] 보낼 항목 없음")
        return 0
    sent = discord.send(messages, webhook, post=post)
    out(f"[디스코드] {sent}/{len(messages)}개 메시지 발송" + (f" (외 {overflow}건 생략)" if overflow else ""))
    return sent
