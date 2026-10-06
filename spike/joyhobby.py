"""joyhobby.co.kr 검증 (SPEC 12장 0단계).

확인 항목: 주별 재입고·신규 입고 목록의 주소와 구조, 상품명 형식(match.py 매칭용).
발견: 공지 게시판(BoardCode=notice)의 "N/N(요일) 판매예정 반다이 제품리스트 안내"(주 1~2회) 글에
      상품코드(BD…)·상품명·가격 목록이 있다. 같은 게시판의 "신제품 입고안내" 글도 있다.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from bs4 import BeautifulSoup

import common
from common import Blocked
from hobby import clean_html

SITE = "joyhobby"
BASE = "https://www.joyhobby.co.kr"
BOARD = f"{BASE}/mall/board_list.asp?siteid=joyhobby&BoardCode=notice"
POST = f"{BASE}/mall/board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID={{id}}"
ITEM = f"{BASE}/mall/Item.asp?siteid=joyhobby&productcode={{code}}"
EXTRA_LISTS = {"NewGoods(신상품)": f"{BASE}/mall/NewGoods.asp?siteid=joyhobby",
               "ipgo": f"{BASE}/mall/ipgo.asp?siteid=joyhobby"}

# 상세 샘플: 9/29 재입고 리스트 / 10-03 리스트 / 신제품 입고안내 / 9/19 리스트 (+ 상품 1개). 상한 6
POST_SAMPLES = ["139459", "139506", "139432", "139407"]
FIXTURE_POSTS = {"139459", "139506", "139432"}

BANDAI_LIST_RX = re.compile(r"판매예정\s*반다이\s*제품리스트")
ITEM_RX = re.compile(r"\[([^\]]+)\]\s*(.*)")
SCALE_RX = re.compile(r"\b1/\d{1,4}\b")
PRICE_RX = re.compile(r"([\d,]+)\s*원")
CODE_RX = re.compile(r"[A-Z]{2,4}\d{4,8}")   # BD(반다이) / KB(코토부키야) / ANN / TKT / MFT …


def parse_board_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"board_view\.asp\?.*?B_iID=(\d+)", a["href"], re.I)
        if not m or m.group(1) in seen:
            continue
        tr = a.find_parent("tr")
        if not tr:
            continue
        txt = re.sub(r"\s+", " ", tr.get_text(" ", strip=True))
        date = re.search(r"\d{4}-\d{2}-\d{2}", txt)
        cat = re.search(r"\b(프라모델|피규어|전체공지|공지|기타)\b", txt)
        seen.add(m.group(1))
        rows.append({"id": m.group(1), "category": cat.group(1) if cat else None,
                     "title": a.get_text(" ", strip=True) or txt, "date": date.group(0) if date else None,
                     "is_bandai_weekly_list": bool(BANDAI_LIST_RX.search(txt))})
    return rows


def parse_post(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    top = soup.select_one("td.Board_View_top")
    title = re.sub(r"\s+", " ", top.get_text(" ", strip=True)) if top else None
    tbl = top.find_parent("table") if top else soup
    lines = [l for l in tbl.get_text("\n", strip=True).split("\n") if l]
    # 소개글: 첫 상품코드 이전
    first = next((i for i, l in enumerate(lines) if CODE_RX.fullmatch(l)), len(lines))
    intro = " ".join(lines[:first])
    items = []
    i = first
    while i < len(lines):
        if CODE_RX.fullmatch(lines[i]) and i + 2 < len(lines):
            name, price = lines[i + 1], PRICE_RX.search(lines[i + 2])
            m = ITEM_RX.match(name)
            items.append({
                "code": lines[i],
                "maker_prefix": re.match(r"[A-Z]+", lines[i]).group(0),
                "name": name,
                "bracket": m.group(1) if m else None,           # 예: HGUC011, RG42, MGSD06, 30MM_EXM_80
                "scale": (SCALE_RX.search(name) or [None])[0] if SCALE_RX.search(name) else None,
                "price_krw": int(price.group(1).replace(",", "")) if price else None,
                "ends_with_plamo_tag": name.endswith("(프라모델)"),
                "url": ITEM.format(code=lines[i]),
            })
            i += 3
        else:
            i += 1
    meta_date = re.search(r"(\d{2}-\d{2}) (오전|오후) [\d:]+", " ".join(lines))
    return {"title": title, "posted": meta_date.group(0) if meta_date else None,
            "intro_keywords": sorted({k for k in ("재입고", "신제품", "신규", "출시예정", "판매예정", "연기", "입고") if k in intro}),
            "intro_excerpt": intro[:220], "items": items,
            "maker_prefixes": dict(Counter(x["maker_prefix"] for x in items)),
            "dup_codes": [c for c, n in Counter(x["code"] for x in items).items() if n > 1]}


def parse_item_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return {"len": len(text),
            "price": (PRICE_RX.search(text) or [None])[0] if PRICE_RX.search(text) else None,
            "status_words": sorted(set(re.findall(r"품절|재입고|입고예정|예약|판매중|재고", text))),
            "title_tag": (soup.title.get_text(strip=True) if soup.title else None)}


def run(b: common.Browser) -> dict:
    res: dict = {"site": SITE, "errors": []}
    rb = common.load_robots(SITE)
    res["robots_rules"] = [list(r) for r in rb.rules]
    res["board_url_allowed"] = rb.allowed(BOARD)

    # 1) 메인 (리다이렉트 여부)
    try:
        d = b.goto(SITE, f"{BASE}/")
        res["home"] = {"status": d["status"], "final": d["final"], "redirects": d["redirects"], "title": d["title"]}
    except Blocked as e:
        res["errors"].append(str(e))

    # 2) 공지 게시판 목록 1~2쪽
    posts = []
    for page in (1, 2):
        url = BOARD + (f"&nowPage={page}" if page > 1 else "")
        try:
            d = b.goto(SITE, url)
        except Blocked as e:
            res["errors"].append(str(e)); continue
        rows = parse_board_list(d["html"])
        posts += rows
        if page == 1:
            common.save_fixture("joyhobby-board-notice-p1.html", clean_html(d["html"]))
    res["board"] = {"rows": len(posts),
                    "bandai_weekly_lists": [(p["id"], p["date"], p["title"]) for p in posts if p["is_bandai_weekly_list"]],
                    "new_arrival_posts": [(p["id"], p["date"], p["title"]) for p in posts if re.search(r"입고안내|신규입고|신상", p["title"])],
                    "sample": posts[:8]}

    # 3) 글 상세: 상품 목록 구조
    parsed = {}
    for pid in POST_SAMPLES:
        try:
            d = b.goto(SITE, POST.format(id=pid), kind="detail")
        except Blocked as e:
            res["errors"].append(f"post {pid}: {e}"); continue
        if d.get("error") or d["status"] != 200:
            parsed[pid] = {"status": d["status"], "error": d.get("error")}; continue
        p = parse_post(d["html"])
        p["id"], p["status"] = pid, d["status"]
        parsed[pid] = p
        if pid in FIXTURE_POSTS:
            common.save_fixture(f"joyhobby-post-{pid}.html", clean_html(d["html"]))
    res["posts"] = parsed

    # 4) 상품 페이지 1개 (글 안의 링크가 실제로 열리는지)
    sample_code = next((it["code"] for p in parsed.values() for it in p.get("items", [])), None)
    if sample_code:
        try:
            d = b.goto(SITE, ITEM.format(code=sample_code), kind="detail")
            res["item_page"] = {"code": sample_code, "status": d["status"], **parse_item_page(d["html"])}
            common.save_fixture(f"joyhobby-item-{sample_code}.html", clean_html(d["html"]))
        except Blocked as e:
            res["errors"].append(f"item: {e}")

    # 5) 신상품·입고 목록 페이지 (대안/보조 소스 후보)
    extra = {}
    for name, url in EXTRA_LISTS.items():
        try:
            d = b.goto(SITE, url)
        except Blocked as e:
            res["errors"].append(f"{name}: {e}"); continue
        soup = BeautifulSoup(d["html"], "html.parser")
        links = {}
        for a in soup.find_all("a", href=True):
            if re.search(r"item\.asp\?.*(itemid|productcode)=", a["href"], re.I):
                t = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
                if t:
                    links[a["href"]] = t
        extra[name] = {"status": d["status"], "item_links": len(links), "samples": list(links.values())[:6]}
    res["extra_lists"] = extra

    # 6) 상품명 표본 (match.py용): 글에서 나온 이름 12개
    names = [it["name"] for p in parsed.values() for it in p.get("items", [])]
    res["name_samples"] = names[:12]
    res["name_stats"] = {
        "total_items": len(names),
        "with_scale": sum(1 for p in parsed.values() for it in p.get("items", []) if it["scale"]),
        "with_bracket_code": sum(1 for p in parsed.values() for it in p.get("items", []) if it["bracket"]),
        "with_plamo_tag": sum(1 for p in parsed.values() for it in p.get("items", []) if it["ends_with_plamo_tag"]),
    }
    res["detail_requests_used"] = common.detail_used(SITE)
    common.summary_write("joyhobby-summary.json", res)
    return res


if __name__ == "__main__":
    br = common.Browser("ko-KR")
    try:
        out = run(br)
    finally:
        br.close(); common.shutdown()
    print("detail used:", out["detail_requests_used"], "errors:", out["errors"])
