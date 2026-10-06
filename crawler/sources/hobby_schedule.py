"""호비사이트 월별 일정 (https://bandai-hobby.net/schedule/index.php?saledate=YYYYMM).

한 페이지에 카드(`a.p-card`)가 3묶음 있다 — ① 일반 판매 ② ホビーオンライン(P-반다이 링크, 월 단위) ③ ガンダムベース.
이 모듈은 파서(순수 함수)와 월 목록 만들기, 요청 루프를 가진다. 썸네일 img는 서명 URL이라 읽지도 저장하지도 않는다.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from .. import config
from ..http import Blocked, HttpClient, SourceAborted

log = logging.getLogger("plamo.hobby_schedule")

_DATE_RX = re.compile(r"(\d{4})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?")
_PRICE_RX = re.compile(r"(\d[\d,]*)\s*円")
_HOBBY_ID_RX = re.compile(r"/item/(01_\d+)/?(?:[?#].*)?$")
_PB_ID_RX = re.compile(r"/item/(item-\d+)/?(?:[?#].*)?$")


def parse_release(text: str | None) -> dict | None:
    """`2026年10月17日 (土)` → {"month":"2026-10","date":"2026-10-17"}, `2027年03月` → {"month":"2027-03"}."""
    m = _DATE_RX.search(text or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
    if not 1 <= mo <= 12:
        return None
    rel = {"month": f"{y:04d}-{mo:02d}"}
    if d:
        rel["date"] = f"{y:04d}-{mo:02d}-{int(d):02d}"
    return rel


def parse_price(text: str | None) -> int | None:
    m = _PRICE_RX.search(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def _channel(tag_classes: list[str]) -> str:
    if "-online" in tag_classes:
        return "online"
    if "-gbase" in tag_classes or "-sidef" in tag_classes:   # GUNDAM SIDE-F도 건담베이스 계열 채널로 묶는다
        return "gbase"
    return "general"


def parse_card(a) -> dict | None:
    """`a.p-card` 하나 → 카탈로그 입력 카드. 상품 링크가 아니면 None."""
    tit = a.select_one(".p-card__tit")
    if not tit:
        return None
    href = (a.get("href") or "").strip()
    m = _HOBBY_ID_RX.search(href)
    pm = _PB_ID_RX.search(href)
    if m:
        item_id, num = f"bh-{m.group(1)}", m.group(1)
    elif pm:
        item_id, num = f"pb-{pm.group(1)}", pm.group(1)
    else:
        return None
    tag = a.select_one(".p-card__tag")
    price_el = a.select_one(".p-card__price")
    date_el = a.select_one(".p-card_date")
    is_pb = pm is not None and m is None          # 호비 상세가 없는 P-반다이 카드
    return {
        "id": item_id,
        "url": config.PBANDAI_ITEM_URL.format(num=num) if is_pb else config.HOBBY_ITEM_URL.format(num=num),
        "nameJa": re.sub(r"\s+", " ", tit.get_text(" ", strip=True)),
        "priceJpy": parse_price(price_el.get_text(" ", strip=True)) if price_el else None,
        "channel": "online" if is_pb else _channel(tag.get("class", []) if tag else []),
        "pbUrl": config.PBANDAI_ITEM_URL.format(num=num) if is_pb else None,
        "release": parse_release(date_el.get_text(" ", strip=True)) if date_el else None,
    }


def parse_schedule(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards, seen = [], set()
    for a in soup.select("a.p-card"):
        card = parse_card(a)
        if card and card["id"] not in seen:
            seen.add(card["id"])
            cards.append(card)
    return cards


# ---------------------------------------------------------------- 월 목록
def month_add(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    """start..end (양끝 포함), 'YYYY-MM' 오름차순."""
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = month_add(cur, 1)
    return out


def current_month(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


def schedule_url(ym: str) -> str:
    return config.HOBBY_SCHEDULE_URL.format(ym=ym.replace("-", ""))


# ---------------------------------------------------------------- 요청
def fetch_month(client: HttpClient, ym: str) -> list[dict] | None:
    """한 달 일정. 요청이 실패하면 None (카드가 0개인 달과 구분한다)."""
    res = client.get(schedule_url(ym), kind="schedule")
    if not res.ok:
        log.warning("일정 %s 실패: %s", ym, res.status or res.error)
        return None
    return parse_schedule(res.text)


__all__ = ["parse_schedule", "parse_card", "parse_release", "parse_price", "month_add", "month_range",
           "current_month", "schedule_url", "fetch_month", "Blocked", "SourceAborted"]
