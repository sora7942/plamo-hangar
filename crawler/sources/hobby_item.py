"""호비사이트 상품 상세 (https://bandai-hobby.net/item/01_N/).

셀렉터는 spike/report.md 2.4절: 제목 `h1.p-heading__h1-product`, 값 `dl.pg-products__detail dt/dd`,
P-반다이 링크 `a.pg-products__pblink`, 브랜드·작품 `li.p-card__link a.p-card__flat`, 갤러리 `.pg-products__contentLeft img`.
이미지는 안정 URL(akamai, bandai-hobby.net/images/)만 돌려주고 서명 URL(`?Expires=…`)은 버린다.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .. import config
from ..http import HttpClient
from .hobby_schedule import parse_price, parse_release

log = logging.getLogger("plamo.hobby_item")

_LINK_RX = re.compile(r"/(brand|series)/([^/?#]+)")
_PB_RX = re.compile(r"/item/(item-\d+)")


def is_stable_image(url: str) -> bool:
    """서명 URL·상대 경로·data URI·CloudFront 등 안정 호스트가 아닌 것은 False."""
    if not url or any(marker in url for marker in config.UNSTABLE_URL_MARKERS):
        return False
    u = urlparse(url)
    if u.scheme not in ("http", "https") or u.netloc not in config.STABLE_IMAGE_HOSTS:
        return False
    need = config.STABLE_IMAGE_PATHS.get(u.netloc)
    if need and not u.path.startswith(need):
        return False
    return not u.path.startswith("/images/common/")    # 로고·아이콘


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1.p-heading__h1-product")
    fields: dict[str, str] = {}
    for dt in soup.select("dl.pg-products__detail dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            fields[dt.get_text(strip=True)] = re.sub(r"\s+", " ", dd.get_text(" ", strip=True))

    brand_keys: list[str] = []
    series: dict | None = None
    for a in soup.select("li.p-card__link a.p-card__flat"):
        m = _LINK_RX.search(a.get("href", ""))
        if not m:
            continue
        if m.group(1) == "brand":
            if m.group(2) not in brand_keys:
                brand_keys.append(m.group(2))
        elif series is None:
            label = a.select_one(".p-card__flatTit") or a
            series = {"key": m.group(2), "label": label.get_text(strip=True)}

    pb = soup.select_one("a.pg-products__pblink")
    pm = _PB_RX.search(pb.get("href", "")) if pb else None

    images: list[str] = []
    for img in soup.select(".pg-products__contentLeft img"):
        src = (img.get("src") or "").strip()
        if is_stable_image(src) and src not in images:
            images.append(src)

    return {
        "nameJa": h1.get_text(" ", strip=True) if h1 else None,
        "priceJpy": parse_price(fields.get("価格")),
        "release": parse_release(fields.get("発売日")),
        "brandKeys": brand_keys,
        "seriesKey": series["key"] if series else None,
        "series": series["label"] if series else None,
        "pbUrl": config.PBANDAI_ITEM_URL.format(num=pm.group(1)) if pm else None,
        "images": images,
    }


def fetch_detail(client: HttpClient, num: str) -> tuple[dict | None, int | None]:
    """상세 한 건. (파싱 결과 | None, HTTP status). 제목이 없으면(차단 페이지 등) None."""
    res = client.get(config.HOBBY_ITEM_URL.format(num=num), kind="detail")
    if not res.ok:
        return None, res.status
    d = parse_detail(res.text)
    return (d if d["nameJa"] else None), res.status
