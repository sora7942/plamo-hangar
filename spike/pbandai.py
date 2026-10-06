"""p-bandai.jp 검증 + 막힐 때의 대안 후보 확인 (SPEC 12장 0단계).

1) p-bandai.jp: robots.txt / 목록 / 상세가 열리는지 (지역 리다이렉트 여부)
2) 대안 A: 해외 P-반다이(p-bandai.com/us) — robots 규칙, 홈 구조, 상세 필드
3) 대안 B: 호비사이트가 싣고 있는 P-반다이 정보 (일정의 ホビーオンライン 카드, pb_* 브랜드, online_shop 뉴스)
IP 위장·VPN·프록시 등 지역 제한 우회는 하지 않는다.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

import common
from common import Blocked
from hobby import clean_html

JP = "https://p-bandai.jp"
GL = "https://p-bandai.com"
JP_PROBES = [("top", f"{JP}/", "list"),
             ("category(hobby)", f"{JP}/hobby/", "list"),          # 호비사이트 상단 메뉴가 직접 링크하는 주소
             ("item", f"{JP}/item/item-1000188677", "detail")]       # 호비 상세(HG 에어리얼)가 링크하는 주소
GL_ITEMS = ["F2423965005", "F2835905002"]   # 홈에서 본 HG 건프라 2개 (P-반다이 US)
# robots.txt가 막는 검색·정렬 URL (요청은 하지 않고 판정만 기록)
GL_DISALLOWED_PROBE = f"{GL}/us/search?limit=20&sortType=NewArrival&_f_productStatuses=On"


def is_region_page(final: str, title: str) -> bool:
    return "global_newpc" in (final or "") or "INTERNATIONAL SHIPPING" in (title or "")


def parse_us_home(html: str) -> dict:
    """홈의 섹션(NEW ARRIVALS 등)별 상품 링크."""
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, list] = {}
    cur = "(top)"
    for el in soup.find_all(["h2", "a"]):
        if el.name == "h2":
            cur = el.get_text(" ", strip=True)
            continue
        href = el.get("href", "")
        m = re.match(r"/us/item/([A-Z0-9]+)", href)
        if not m:
            continue
        txt = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        sections.setdefault(cur, [])
        if m.group(1) not in [x["id"] for x in sections[cur]]:
            sections[cur].append({"id": m.group(1), "text": txt[:90]})
    return {"sections": {k: v for k, v in sections.items() if v},
            "counts": {k: len(v) for k, v in sections.items() if v}}


def parse_us_item(html: str, title: str) -> dict:
    if "PAGE NOT AVAILABLE" in title.upper():
        return {"available": False, "title": title}
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    text = re.sub(r"\s+", " ", (soup.find("main") or soup.body).get_text(" ", strip=True))
    h1 = soup.find("h1")
    def grab(rx):
        m = re.search(rx, text)
        return m.group(1).strip() if m else None
    return {
        "available": True,
        "title": h1.get_text(strip=True) if h1 else title,
        "price_usd": grab(r"\$\s*([\d.,]+)"),
        "flags": sorted(set(re.findall(r"\b(PRE-ORDER|EXCLUSIVE|IN STOCK|SOLD OUT|RE-?STOCK|RE-?RELEASE|RE-?ISSUE)\b", text))),
        "ships": grab(r"([A-Z][a-z]{2}\. \d{4}) SHIPS"),
        "preorder_open": grab(r"PRE-ORDERS OPEN (.+?) PRE-ORDERS CLOSE"),
        "preorder_close": grab(r"PRE-ORDERS CLOSE (.+?) Scheduled Shipping"),
        "scheduled_shipping": grab(r"Scheduled Shipping ([A-Z][a-z]{2}\. \d{4})"),
        "reissue_text_hits": sorted(set(re.findall(r"re-?release|re-?issue|re-?stock|restock", text, re.I))),
    }


def run(b_jp: common.Browser, b_en: common.Browser) -> dict:
    res: dict = {"site": "pbandai", "errors": []}

    # ---------- 1) p-bandai.jp
    rb = common.load_robots("pbandai")
    robots_txt = (common.OUT / "robots-pbandai.txt").read_text(encoding="utf-8")
    res["jp_robots"] = {"readable": not robots_txt.startswith("# (spike)"), "raw_first_line": robots_txt.splitlines()[0][:160]}
    probes = []
    for name, url, kind in JP_PROBES:
        try:
            d = b_jp.goto("pbandai", url, kind=kind)
        except Blocked as e:
            probes.append({"name": name, "url": url, "blocked": str(e)}); continue
        probes.append({"name": name, "url": url, "status": d["status"], "final": d["final"], "redirects": d["redirects"],
                       "title": d["title"][:70], "region_redirect": is_region_page(d["final"], d["title"])})
        if name == "top":
            common.save_fixture("pbandai-jp-region-redirect.html", clean_html(d["html"]))
    res["jp_probes"] = probes
    res["jp_blocked_region"] = all(p.get("region_redirect") for p in probes if "status" in p)

    # ---------- 2) 대안 A: 해외 P-반다이 (US)
    glb = {"robots_rules": [list(r) for r in common.load_robots("pbandai_global").rules]}
    glb["search_url_allowed"] = common.load_robots("pbandai_global").allowed(GL_DISALLOWED_PROBE)
    glb["item_url_allowed"] = common.load_robots("pbandai_global").allowed(f"{GL}/us/item/{GL_ITEMS[0]}")
    try:
        d = b_en.goto("pbandai_global", f"{GL}/us/")
        glb["home"] = {"status": d["status"], "final": d["final"], "redirects": d["redirects"], **parse_us_home(d["html"])}
        common.save_fixture("pbandai-global-us-top.html", clean_html(d["html"]))
    except Blocked as e:
        res["errors"].append(str(e))
    items = []
    for iid in GL_ITEMS:
        try:
            d = b_en.goto("pbandai_global", f"{GL}/us/item/{iid}", kind="detail")
        except Blocked as e:
            res["errors"].append(f"{iid}: {e}"); continue
        p = parse_us_item(d["html"], d["title"])
        p.update({"id": iid, "status": d["status"]})
        items.append(p)
        if p.get("available"):
            common.save_fixture(f"pbandai-global-us-item-{iid}.html", clean_html(d["html"]))
    glb["items"] = items
    res["alt_global_us"] = glb

    # ---------- 3) 대안 B: 호비사이트가 싣는 P-반다이 정보 (이미 받은 캐시만 사용, 추가 요청 없음)
    alt_b = {}
    try:
        import json
        hs = json.loads((common.OUT / "hobby-summary.json").read_text(encoding="utf-8"))
        alt_b["online_cards_per_month"] = {k: v.get("online(P-반다이 링크)") for k, v in hs["schedule"].items() if v.get("cards")}
        alt_b["pb_brand_keys"] = [b["value"] for b in hs["filters"]["brand"] if b["value"].startswith("pb_")]
    except Exception as e:  # hobby.py를 먼저 안 돌렸을 때
        alt_b["note"] = f"hobby-summary.json 없음: {e!r}"
    c = common.cache_get("https://bandai-hobby.net/news/?cat=online_shop")
    if c:
        soup = BeautifulSoup(c["html"], "html.parser")
        arts = {a["href"]: re.sub(r"\s+", " ", a.get_text(" ", strip=True)) for a in soup.select("a[href*='/news/01_']")}
        alt_b["news_online_shop_p1_items"] = len(arts)
        alt_b["news_online_shop_samples"] = list(arts.values())[:5]
    res["alt_hobby_site"] = alt_b

    common.summary_write("pbandai-summary.json", res)
    return res


if __name__ == "__main__":
    bj, be = common.Browser("ja-JP"), common.Browser("en-US")
    try:
        out = run(bj, be)
    finally:
        bj.close(); be.close(); common.shutdown()
    print("jp blocked by region:", out["jp_blocked_region"], "errors:", out["errors"])
