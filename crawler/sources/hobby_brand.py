"""호비사이트 브랜드 목록 (https://bandai-hobby.net/brand/<key>/, 2쪽부터 ?p=N).

걸프라 브랜드(config.GIRL_BRANDS)를 전체 열거하는 데 쓴다. 카드는 일정 카드와 같은 `a.p-card` 구조이고
브랜드 키가 이미 알려져 있어 상세 없이도 line·grade가 확정된다. 상단 슬라이드(`a.p-slide__link`)는 카드가 아니라 제외.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from .. import config
from ..http import HttpClient
from .hobby_schedule import parse_card

log = logging.getLogger("plamo.hobby_brand")

_PAGE_RX = re.compile(r"[?&]p=(\d+)")


def brand_url(key: str, page: int = 1) -> str:
    base = config.HOBBY_BRAND_URL.format(key=key)
    return base if page <= 1 else f"{base}?p={page}"


def parse_brand_page(html: str) -> dict:
    """→ {"items": [카드...], "last_page": N}. 페이저가 없으면 last_page=1."""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for a in soup.select("a.p-card"):
        card = parse_card(a)
        if card and card["id"] not in seen:
            seen.add(card["id"])
            items.append(card)
    last = 1
    for a in soup.select("a.c-archives__pagination-list-item-link, a.c-archives__pagination-btn-link"):
        m = _PAGE_RX.search(a.get("href", ""))
        if m:
            last = max(last, int(m.group(1)))
    return {"items": items, "last_page": min(last, config.BRAND_MAX_PAGES)}


def fetch_page(client: HttpClient, key: str, page: int = 1) -> dict | None:
    """한 쪽. 요청이 실패하면 None."""
    res = client.get(brand_url(key, page), kind="brand")
    if not res.ok:
        log.warning("브랜드 %s %d쪽 실패: %s", key, page, res.status or res.error)
        return None
    return parse_brand_page(res.text)
