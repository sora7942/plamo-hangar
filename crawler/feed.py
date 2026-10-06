"""피드 — 이번 실행에서 처음 발견된 신제품을 feed.json 형식(SPEC 4장)으로 만들고 이전 피드와 합친다.

2단계 종류: `new`(호비 신제품 발매 일정), `pb-new`(P-반다이 한정 신규). `kr-*`는 3단계(조이하비).
`added`는 처음 발견한 시각으로 한 번 정해지면 바꾸지 않는다.
"""
from __future__ import annotations

from datetime import datetime

from . import config
from .catalog import LINES, Catalog, apply_replacements


def _feed_item(item: dict, now_iso: str) -> dict:
    is_pb = item["id"].startswith("pb-")
    prefix, num = item["id"].split("-", 1)                      # 'bh-01_7249' → '01_7249', 'pb-item-1000…' → 'item-1000…'
    rel = item.get("release") or {}
    return {
        "id": f"{prefix}-new-{num}",
        "type": "pb-new" if is_pb else "new",
        "date": rel.get("date") or rel.get("month"),
        "added": now_iso,
        "catalogId": item["id"],
        "title": item["nameJa"],
        "titleKo": item.get("nameKo"),
        "url": (item.get("pbUrl") or item["url"]) if is_pb else item["url"],
        "image": (item.get("images") or [None])[0],             # 안정 URL뿐이라 그대로 링크할 수 있다. 없으면 null
        "source": "bandai-hobby",
    }


def new_feed_items(catalog: Catalog, new_ids: list[str], now: datetime, now_iso: str) -> list[dict]:
    """이번에 처음 발견됐고(new_ids), 판정이 끝나 건프라·걸프라이며, 발매월이 이번 달 이후인 항목."""
    cur = f"{now.year:04d}-{now.month:02d}"
    out = []
    for cid in new_ids:
        item = catalog.items.get(cid)
        if not item or item.get("line") not in LINES:
            continue
        month = (item.get("release") or {}).get("month")
        if not month or month < cur:
            continue
        out.append(_feed_item(item, now_iso))
    return out


def apply_title_ko_replacements(items: list[dict], replacements: dict[str, str]) -> int:
    """피드의 titleKo(= nameKo의 복사본)에도 같은 부분 치환을 적용한다. 바뀐 항목 수를 돌려준다."""
    changed = 0
    for it in items:
        ko = it.get("titleKo")
        if ko:
            new = apply_replacements(ko, replacements)
            if new != ko:
                it["titleKo"] = new
                changed += 1
    return changed


def merge_feed(prev: list[dict], new: list[dict], catalog: Catalog) -> tuple[list[dict], list[dict]]:
    """→ (합친 피드 `added` 내림차순 최대 FEED_MAX, 이번에 실제로 추가된 항목). 이미 있는 id는 무시한다."""
    # 상세로 비대상(제외)이 확인된 상품은 피드에서도 뺀다 (임시 판정으로 먼저 들어간 항목 정리)
    by_id = {i["id"]: i for i in prev if i.get("catalogId") not in catalog.excluded}
    prev = [i for i in prev if i["id"] in by_id]
    added = []
    for it in new:
        if it["id"] not in by_id:
            by_id[it["id"]] = it
            added.append(it)
    for it in prev:                                              # 번역·상세가 나중에 채워지면 빈 칸만 보충 (added는 그대로)
        cat = catalog.items.get(it.get("catalogId") or "")
        if not cat:
            continue
        if not it.get("titleKo") and cat.get("nameKo"):
            it["titleKo"] = cat["nameKo"]
        if not it.get("image") and cat.get("images"):
            it["image"] = cat["images"][0]
    merged = sorted(by_id.values(), key=lambda i: (i["added"], i["id"]), reverse=True)[:config.FEED_MAX]
    kept = {i["id"] for i in merged}
    return merged, [a for a in added if a["id"] in kept]
