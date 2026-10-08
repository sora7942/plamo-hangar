"""반다이남코코리아몰(https://www.bnkrmall.co.kr) 상품 목록 — 한국 정식 상품명·시리즈명·판매가(원)를 모은다. (7a)

- **목록 페이지만** 받는다(상세·이미지는 받지 않는다). 카테고리 목록: `/goods/category.do?cate=<N>&page=<P>&cateName=…&soldout=Y&endGoods=Y`
  (`soldout=Y&endGoods=Y`가 사이트 "전체상품" 링크의 값 — 품절·판매 종료 상품도 목록에 나온다). 쪽당 40개.
- 한 줄(`li[data-childno]`): `a.thumb[href=../goods/detail.do?gno=N]`, `.caption`(시리즈, 없을 수 있음), `h5`(상품명), `.price .num`(판매가), `.badge`
- 이미지 URL(`.img_box` 배경)은 읽지 않는다 — 몰 이미지는 저장하지도 쓰지도 않는다 (CLAUDE.md Critical)
- 요청은 `HttpClient`(robots 준수·1.2초 간격·timeout·UA)로, 실행당 `config.MALL_MAX_REQUESTS`회 이내. 구조가 바뀌면 소스 실패로 기록하고 계속한다
- 반환의 `complete`는 "모든 카테고리의 모든 쪽을 정상으로 읽었다"는 뜻이다. 이때만 호출자가 "몰에서 사라진 상품"을 판정한다
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .. import config
from ..http import HttpClient

log = logging.getLogger("plamo.mall")

_GNO_RX = re.compile(r"gno=(\d+)")
_PAGE_RX = re.compile(r"pageLink\('(\d+)'\)")
_PRICE_RX = re.compile(r"[\d,]+")
_SOLDOUT_RX = re.compile(r"품절|sold[\s_-]?out", re.I)


class MallStructureError(Exception):
    """목록 HTML이 예상한 구조가 아니다 (사이트 개편 등)."""


def list_url(params: dict[str, str], page: int) -> str:
    q = {"cate": params["cate"], "page": str(page), "cateName": params.get("cateName", "")}
    if params.get("brandIdx"):
        q["brandIdx"] = params["brandIdx"]
    q.update({"soldout": "Y", "endGoods": "Y"})
    return f"{config.MALL_BASE}/goods/category.do?{urlencode(q, safe=',')}"


def goods_url(gno: str) -> str:
    return config.MALL_GOODS_URL.format(gno=gno)


def parse_list(html: str) -> dict:
    """→ {"items": [{gno, name, series, price, soldOut}], "pages": 쪽수(알 수 없으면 1), "skipped": 못 읽은 줄 수}.
    줄이 하나도 없거나 읽은 줄이 절반 미만이면 MallStructureError (빈 카테고리는 쪽 안내 문구로 구별하지 않는다 — 목록은 늘 있어야 한다)."""
    soup = BeautifulSoup(html, "html.parser")
    lis = soup.select("li[data-childno]")
    items, skipped, seen = [], 0, set()
    for li in lis:
        a = li.select_one("a.thumb[href]")
        m = _GNO_RX.search(a["href"]) if a else None
        h = li.select_one("h5")
        num = li.select_one(".price .num")
        pm = _PRICE_RX.search(num.get_text()) if num else None
        name = re.sub(r"\s+", " ", h.get_text(" ", strip=True)) if h else ""
        if not (m and name and pm):
            skipped += 1
            continue
        if m.group(1) in seen:
            continue
        seen.add(m.group(1))
        cap = li.select_one(".caption")
        series = re.sub(r"\s+", " ", cap.get_text(" ", strip=True)) if cap else ""
        badge = li.select_one(".badge")
        sold = bool(_SOLDOUT_RX.search((badge.get_text(" ", strip=True) if badge else "") + " " + " ".join(li.get("class") or [])))
        items.append({"gno": m.group(1), "name": name, "series": series or None, "price": int(pm.group(0).replace(",", "")), "soldOut": sold})
    if not lis or len(items) * 2 < len(lis):
        raise MallStructureError(f"상품 줄 {len(lis)}개 중 {len(items)}개만 읽었습니다 (구조가 바뀌었을 수 있음)")
    pages = [int(x) for x in _PAGE_RX.findall(html)]
    return {"items": items, "pages": max(pages) if pages else 1, "skipped": skipped}


def scan(http: HttpClient, categories: list[dict] | None = None, *, max_requests: int | None = None) -> dict:
    """모든 카테고리의 목록을 쪽마다 받는다. → {goods: {gno: {name, series, price, soldOut, cate}}, requests, complete, errors, pages}.
    한 카테고리가 실패해도 다음 카테고리는 계속한다. 요청 상한에 닿으면 멈추고 complete=False."""
    categories = config.MALL_CATEGORIES if categories is None else categories
    cap = config.MALL_MAX_REQUESTS if max_requests is None else max_requests
    out: dict = {"goods": {}, "requests": 0, "complete": True, "errors": [], "pages": {}}
    for cat in categories:
        page, last = 1, 1
        while page <= last:
            if out["requests"] >= cap:
                out["complete"] = False
                out["errors"].append(f"{cat['key']}: 요청 상한({cap}회)에 닿아 {page}쪽부터 받지 못함")
                break
            res = http.get(list_url(cat["params"], page), kind="mall")
            out["requests"] += 1
            if not res.ok:
                out["complete"] = False
                out["errors"].append(f"{cat['key']} {page}쪽: HTTP {res.status}")
                break
            try:
                parsed = parse_list(res.text)
            except MallStructureError as e:
                out["complete"] = False
                out["errors"].append(f"{cat['key']} {page}쪽: {e}")
                break
            if page == 1:
                last = min(parsed["pages"], config.MALL_MAX_PAGES)
                out["pages"][cat["key"]] = last
                if parsed["pages"] > config.MALL_MAX_PAGES:
                    out["complete"] = False
                    out["errors"].append(f"{cat['key']}: {parsed['pages']}쪽 중 {config.MALL_MAX_PAGES}쪽까지만 받음")
            for it in parsed["items"]:
                out["goods"].setdefault(it["gno"], {"name": it["name"], "series": it["series"], "price": it["price"],
                                                    "soldOut": it["soldOut"], "cate": cat["key"]})
            page += 1
    return out
