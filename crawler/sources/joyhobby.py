"""조이하비 공지 게시판 (https://www.joyhobby.co.kr) — 반다이 입고 글의 상품 행을 모은다.

- 인코딩은 EUC-KR이다 (`http.decode_body`가 처리). fixture는 응답 원본 바이트(tests/fixtures/joyhobby-raw-*.html)
- 목록은 쪽당 일반 글 20개. **고정 공지 7개(`Notice=true`)가 쪽마다 맨 위에 반복**되므로 버린다.
  게시판 끝(2026-10 기준 20쪽)을 넘기면 마지막 행만 되풀이해서 돌려준다 → 쪽수는 호출자가 마지막 쪽 판정으로 멈춘다
- 후보 글: 제목에 "반다이" 또는 "입고" (config.JOY_TITLE_KEYWORDS). 본문에 BD####### 행이 있어야 기록한다
- 본문은 `상품코드 / 상품명 / 가격` 3줄 반복 (가격은 `22000원` 또는 `19,800원`)
- 판매예정일은 제목 앞의 `M/D(요일)`에서 뽑는다 (연도는 글 날짜에서 추정)
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .. import config
from ..http import HttpClient

log = logging.getLogger("plamo.joyhobby")

_VIEW_RX = re.compile(r"board_view\.asp\?.*?B_iID=(\d+)", re.I)
_DATE_RX = re.compile(r"\d{4}-\d{2}-\d{2}")
_BD_RX = re.compile(config.JOY_BANDAI_CODE)
_ANY_CODE_RX = re.compile(r"[A-Z]{2,4}\d{4,8}")          # BD(반다이) / KB / ANN / TKT … 소개글이 끝나는 지점을 찾는 데만 쓴다
_PRICE_RX = re.compile(r"([\d,]+)\s*원")
# 조회수(smallint)가 32767을 넘은 글은 사이트 자체 버그로 HTTP 500 + "데이터 형식 smallint에 산술 오버플로" 페이지가 나온다 (2026-10 확인).
# 누가 열어도 같으므로 재시도하지 않는다.
_SITE_BUG_RX = re.compile(r"smallint|산술 오버플로|arithmetic overflow", re.I)
_SALE_RX = re.compile(r"^\W*(?:\[[^\]]*\]\s*)?(\d{1,2})/(\d{1,2})(?!\d)")     # 제목 맨 앞의 M/D (선택: 앞의 [말머리])


def board_url(page: int) -> str:
    return config.JOY_BOARD_URL + (f"&nowPage={page}" if page > 1 else "")


def post_url(post_id: str) -> str:
    return config.JOY_POST_URL.format(id=post_id)


# ---------------------------------------------------------------- 목록
def is_candidate_title(title: str) -> bool:
    t = unicodedata.normalize("NFKC", title or "")
    return any(k in t for k in config.JOY_TITLE_KEYWORDS)


def parse_board_list(html: str) -> list[dict]:
    """일반 글만 (고정 공지 제외). → [{id, date, title, category}] 목록 순서(최신 먼저)."""
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = _VIEW_RX.search(a["href"])
        if not m or "notice=true" in a["href"].lower() or m.group(1) in seen:
            continue
        tr, td = a.find_parent("tr"), a.find_parent("td")
        if tr is None:
            continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        d = _DATE_RX.search(re.sub(r"\s+", " ", tr.get_text(" ", strip=True)))
        category = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).replace(title, "").strip() if td is not None else ""
        seen.add(m.group(1))
        rows.append({"id": m.group(1), "date": d.group(0) if d else None, "title": title, "category": category or None})
    return rows


def fetch_board_page(client: HttpClient, page: int) -> list[dict] | None:
    """목록 한 쪽. 실패하거나 글이 하나도 안 보이면(차단·구조 변경) None."""
    res = client.get(board_url(page), kind="list")
    if not res.ok:
        return None
    rows = parse_board_list(res.text)
    return rows or None


# ---------------------------------------------------------------- 글 본문
def parse_post(html: str) -> dict:
    """→ {title, intro, restock, rows:[{code, name, price}]} — rows는 BD 코드 행만, 같은 코드는 첫 번째만."""
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    top = soup.select_one("td.Board_View_top")
    title = re.sub(r"\s+", " ", top.get_text(" ", strip=True)) if top else None
    table = top.find_parent("table") if top else soup
    lines = [ln for ln in table.get_text("\n", strip=True).split("\n") if ln]
    first = next((i for i, ln in enumerate(lines) if _ANY_CODE_RX.fullmatch(ln)), len(lines))
    intro = " ".join(lines[:first])

    rows, seen = [], set()
    i = first
    while i < len(lines):
        if _BD_RX.fullmatch(lines[i]) and i + 1 < len(lines):
            code, name = lines[i], lines[i + 1]
            if _ANY_CODE_RX.fullmatch(name) or _PRICE_RX.fullmatch(name):     # 이름 자리에 코드·가격이 온 깨진 행
                i += 1
                continue
            price_m = _PRICE_RX.fullmatch(lines[i + 2]) if i + 2 < len(lines) else None
            if code not in seen:
                seen.add(code)
                rows.append({"code": code, "name": name,
                             "price": int(price_m.group(1).replace(",", "")) if price_m else None})
            i += 3 if price_m else 2
        else:
            i += 1
    return {"title": title, "intro": intro, "restock": config.JOY_RESTOCK_WORD in ((title or "") + " " + intro), "rows": rows}


def fetch_post(client: HttpClient, post_id: str) -> tuple[dict | None, int | None, bool]:
    """글 한 건. (파싱 결과 | None, HTTP status, 사이트 버그로 영구히 못 여는 글인가). 제목을 못 찾으면(차단 페이지 등) None."""
    res = client.get(post_url(post_id), kind="detail")
    if not res.ok:
        return None, res.status, res.status == 500 and bool(_SITE_BUG_RX.search(res.text))
    p = parse_post(res.text)
    return (p if p["title"] else None), res.status, False


# ---------------------------------------------------------------- 판매예정일
def parse_sale_date(title: str, post_date: date) -> date | None:
    """제목 맨 앞의 `M/D(요일)` → 판매예정일. 연도는 글 날짜 기준 전년·올해·다음 해 중 가장 가까운 날로 정한다
    (12월 글의 1월 판매는 다음 해). 글 날짜와 KR_SALE_DATE_MAX_DIFF_DAYS보다 멀거나 날짜가 아니면 None."""
    m = _SALE_RX.match(unicodedata.normalize("NFKC", title or ""))
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    best: date | None = None
    for year in (post_date.year - 1, post_date.year, post_date.year + 1):
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs(cand - post_date) < abs(best - post_date):
            best = cand
    if best is None or abs(best - post_date) > timedelta(days=config.KR_SALE_DATE_MAX_DIFF_DAYS):
        return None
    return best
