"""실행 파이프라인 — 이전 상태 로드 → 일정 → 걸프라 브랜드 → 상세 → 번역 → 피드 → 파일 쓰기 → 디스코드.

소스(단계)는 각각 격리한다: 한 단계가 실패해도 나머지는 계속하고, 실패는 meta.sources에 남긴다.
`main.py`는 인자 처리만 하고 이 모듈의 run()을 부른다 (테스트는 가짜 HttpClient로 run()을 직접 부른다).
"""
from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from . import config, discord, feed, translate
from .catalog import Catalog
from .http import Blocked, HttpClient, SourceAborted
from .sources import hobby_brand, hobby_item, hobby_schedule
from .store import iso, now_kst, read_json, write_json

log = logging.getLogger("plamo.pipeline")

HOBBY_STAGES = ("hobby_schedule", "hobby_brand", "hobby_item")
ALL_STAGES = (*HOBBY_STAGES, "translate")


@dataclass
class Options:
    dry_run: bool = False
    no_discord: bool = False
    only: set[str] | None = None            # None이면 전부. "hobby"는 hobby_* 세 단계
    bootstrap: bool = False
    from_month: str | None = None           # --bootstrap 때 일정을 거슬러 올라갈 시작 달 (YYYY-MM)
    max_new: int = config.DETAIL_NEW_MAX
    max_backlog: int = config.DETAIL_BACKLOG_MAX
    data_dir: Path = field(default_factory=lambda: config.DATA_DIR)

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
    """상세: 새 상품 최대 max_new + 밀린 상품 최대 max_backlog."""
    new_sel, back_sel = ctx.catalog.select_details(ctx.opts.max_new, ctx.opts.max_backlog, ctx.new_ids)
    ctx.http.detail_limit = len(new_sel) + len(back_sel)
    failed: list[str] = []
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
    return ctx.detail_counts["new"] + ctx.detail_counts["backlog"] + ctx.detail_counts["excluded"], failed


STAGE_FUNCS = {"hobby_schedule": stage_schedule, "hobby_brand": stage_brand, "hobby_item": stage_item}


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
    crawl = {"scheduleFrom": None, "girlBrandsDone": [], **(prev_meta.get("crawl") or {})}
    ctx = _Ctx(opts, http, catalog, crawl, now)
    ctx.unknown_keys.update(prev_meta.get("unknownBrandKeys", []))
    sources: dict[str, dict] = {}

    for name in HOBBY_STAGES:
        if name in stages:
            sources[name] = _run_stage(ctx, name)

    if "translate" in stages:
        res = translate.translate_pending(catalog, now_iso, client=anthropic_client)
        sources["translate"] = {"ok": res["ok"], "at": iso(now_kst()), "items": res["done"], "error": res["error"],
                                "pending": res["pending"], "skipped": res["skipped"], "model": res["model"],
                                "kanaRetried": res["kanaRetried"], "kanaRejected": res["kanaRejected"]}
    elif opts.dry_run and opts.only is None:
        sources["translate"] = {"ok": True, "at": iso(now_kst()), "items": 0, "error": None, "skipped": "dry-run"}

    # 피드: 이번에 처음 발견한 항목 + 이전 피드
    prev_snapshot = copy.deepcopy(prev_feed)               # merge_feed가 빈 칸(titleKo·image)을 제자리에서 보충하므로 비교용 복사
    new_items = feed.new_feed_items(catalog, ctx.new_ids, now, now_iso)
    merged, added = feed.merge_feed(prev_feed, new_items, catalog)

    # 파일 쓰기 (dry-run도 파일은 쓴다. 디스코드만 보내지 않는다)
    counts = catalog.save(data_dir, now_iso)
    feed_updated = prev_feed_doc.get("updatedAt", now_iso) if merged == prev_snapshot else now_iso
    write_json(data_dir / config.FEED_FILE, {"updatedAt": feed_updated, "items": merged})
    crawl["backlog"] = catalog.backlog_count()
    crawl["counts"] = catalog.counts()
    stats = http.stats.as_dict()
    stats["minGapSec"] = round(http.stats.min_gap, 2) if http.stats.min_gap is not None else None
    meta = {
        "updatedAt": now_iso,
        "since": prev_meta.get("since") or now.date().isoformat(),
        "sources": {**(prev_meta.get("sources") or {}), **sources},
        "crawl": crawl,
        "stats": stats,
        "unknownBrandKeys": sorted(ctx.unknown_keys),
    }
    write_json(data_dir / config.META_FILE, meta)

    notified = _notify(opts, added, prev_feed_empty=not prev_feed, prev_catalog_empty=catalog.was_empty, post=post, out=out)
    return {"meta": meta, "catalog": counts, "newItems": len(ctx.new_ids), "feedAdded": len(added),
            "details": ctx.detail_counts, "notified": notified}


def _notify(opts: Options, added: list[dict], *, prev_feed_empty: bool, prev_catalog_empty: bool, post, out) -> int:
    """디스코드. 반환: 실제로 보낸 메시지 수 (dry-run·건너뜀은 0)."""
    reason = discord.skip_reason(prev_feed_empty=prev_feed_empty, prev_catalog_empty=prev_catalog_empty,
                                 bootstrap=opts.bootstrap)
    messages, overflow = discord.plan_messages(added)
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
