"""bandai-hobby.net 검증 (SPEC 12장 0단계).

확인 항목: 접속(requests vs Playwright), 월별 일정 URL, 과거 월 범위, 再販 표시,
상세 필드, 이미지 URL 패턴/만료, 걸프라 라인 분류.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import common
from common import Blocked

SITE = "hobby"
BASE = "https://bandai-hobby.net"

# 월별 일정: 현재월(index 없이 /schedule/) + 미래/과거 샘플. 월당 1요청
SCHEDULE_MONTHS = ["202610", "202611", "202609", "202607", "202510", "202410",
                   "202210", "202010", "201810", "201510", "201010", "200510", "199510",
                   "199307", "199007", "198507", "198007", "198010"]
# 픽스처로 저장할 월 (현재 / 과거 / 아주 오래된 달)
FIXTURE_MONTHS = {"202610", "202210", "199510"}

# 상세 샘플 (등급·라인·신구·한정 다양하게). 상한 18개 중 16개 + 이미 본 1개
DETAIL_SAMPLES = [
    ("01_4257", "HG 2022 초회 (P-반다이 링크 있음)"),
    ("01_7249", "HG 2026-10 신제품(미발매)"),
    ("01_7142", "30MS 걸프라"),
    ("01_7260", "30MS 캐릭터(2026-11)"),
    ("01_7263", "30MP 캐릭터"),
    ("01_4259", "Figure-rise Standard"),
    ("01_6753", "ENTRY GRADE"),
    ("01_7135", "MGSD"),
    ("01_7145", "HG 1/100 매크로스"),
    ("01_1547", "1995 구형 1/60"),
    ("01_52", "1995 BB전사 (번호 52)"),
    ("01_6969", "건담베이스 한정 Figure-rise"),
    ("01_7414", "건담베이스 한정 MG"),
    ("01_5373", "베스트메카콜렉션 2024"),
    ("01_3024", "2020 호비온라인 판매 (01_ 상세 있음)"),
]
# 픽스처로 저장할 상세 (용량 때문에 대표만)
FIXTURE_ITEMS = {"01_4257", "01_7142", "01_4259", "01_6969", "01_1547", "01_3024"}

REISSUE_RX = re.compile(r"再販|再生産|再出荷|再発売|再入荷|リバイバル|REISSUE", re.I)
DATE_RX = re.compile(r"\d{4}年\d{1,2}月(?:\d{1,2}日)?")


def clean_html(html: str) -> str:
    """fixture용: script/style/noscript 제거 (용량·추적 ID 제거). 나머지 DOM은 그대로."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return str(soup)


def expires_of(url: str):
    m = re.search(r"Expires=(\d+)", url)
    return int(m.group(1)) if m else None


def epoch_of(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def classify_host(url: str) -> str:
    h = urlparse(url).netloc
    if "akamaihd.net" in h:
        return "akamai(비서명)"
    if "cloudfront.net" in h:
        return "cloudfront(서명, 만료)" if expires_of(url) else "cloudfront(비서명)"
    if h.endswith("bandai-hobby.net"):
        return "hobby-site(정적)"
    return h


# ---------------------------------------------------------------- 파서
def parse_schedule(html: str) -> dict:
    """월별 일정 페이지 → 카드 목록 (제목·가격·날짜·태그·링크·썸네일)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for a in soup.select("a.p-card"):
        tit = a.select_one(".p-card__tit")
        if not tit:
            continue
        href = a.get("href", "")
        m = re.search(r"/item/(01_\d+)/?$", href)
        pm = re.search(r"/item/(item-\d+)", href)
        img = a.select_one("img")
        src = img.get("src", "") if img else ""
        tag = a.select_one(".p-card__tag")
        cards.append({
            "href": href,
            "hobby_id": m.group(1) if m else None,
            "pbandai_id": pm.group(1) if pm else None,
            "title": tit.get_text(strip=True),
            "price": (a.select_one(".p-card__price").get_text(strip=True) if a.select_one(".p-card__price") else None),
            "date": (a.select_one(".p-card_date").get_text(strip=True) if a.select_one(".p-card_date") else None),
            "tag": tag.get_text(strip=True) if tag else None,
            "thumb": src,
        })
    return {"cards": cards,
            "reissue_text_hits": sorted({t.strip()[:60] for t in soup.find_all(string=REISSUE_RX)})}


def parse_detail(html: str, fetched_at: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    t0 = epoch_of(fetched_at)
    h1 = soup.select_one("h1.p-heading__h1-product") or soup.find("h1")
    fields = {}
    for dt in soup.select("dl.pg-products__detail dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            fields[dt.get_text(strip=True)] = re.sub(r"\s+", " ", dd.get_text(" ", strip=True))
    pb = soup.select_one("a.pg-products__pblink")
    brands = []
    for a in soup.select("li.p-card__link a.p-card__flat"):
        m = re.search(r"/(brand|series)/([^/]+)/?", a.get("href", ""))
        brands.append({"type": m.group(1) if m else None, "key": m.group(2) if m else None,
                       "label": (a.select_one(".p-card__flatTit") or a).get_text(strip=True)})
    gallery = []
    for img in soup.select(".pg-products__contentLeft img"):
        u = img.get("src") or ""
        if u and u not in gallery:
            gallery.append(u)
    desc = soup.select_one(".pg-products__article")
    desc_imgs = [i.get("src") for i in (desc.select("img") if desc else []) if i.get("src")]
    main = soup.select_one("main") or soup
    text = main.get_text(" ", strip=True)
    signed = [{"url": u.split("?")[0], "ttl_s": expires_of(u) - t0}
              for u in gallery + desc_imgs if expires_of(u)]
    return {
        "title": h1.get_text(strip=True) if h1 else None,
        "fields": fields,
        "pbandai_link": pb["href"] if pb else None,
        "brands_series": brands,
        "gallery": gallery,
        "gallery_hosts": sorted({classify_host(u) for u in gallery}),
        "description_images": desc_imgs,
        "description_image_hosts": sorted({classify_host(u) for u in desc_imgs}),
        "signed_url_ttl_s": signed,
        "release_dates_in_text": DATE_RX.findall(text)[:6],
        "reissue_text_hits": sorted(set(REISSUE_RX.findall(text))),
        "og_image": (soup.find("meta", property="og:image") or {}).get("content"),
    }


def parse_filters(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out = {"series": [], "brand": [], "order_form": []}
    for cb in soup.select("input[type=checkbox]"):
        n = cb.get("name", "")
        k = re.sub(r"\[\]$", "", n)
        if k in out:
            lab = cb.find_next("label")
            out[k].append({"value": cb.get("value"), "label": lab.get_text(strip=True) if lab else None})
    return out


# ---------------------------------------------------------------- 실행
def run(b: common.Browser) -> dict:
    res: dict = {"site": SITE, "base": BASE, "errors": []}
    common.load_robots(SITE)

    # 1) 일반 HTTP(requests)로 열리는지 — CLAUDE.md의 "리다이렉트 반복" 가정 확인용 1회
    try:
        r = common.http_get(SITE, f"{BASE}/schedule/", kind="list")
        res["plain_requests"] = {k: r.get(k) for k in ("ok", "status", "final", "redirects")}
        res["plain_requests"]["has_cards"] = "p-card" in r.get("html", "")
        res["plain_requests"]["len"] = len(r.get("html", ""))
    except Blocked as e:
        res["plain_requests"] = {"blocked": str(e)}

    # 2) 월별 일정
    sched = {}
    for ym in SCHEDULE_MONTHS:
        url = f"{BASE}/schedule/" if ym == "202610" else f"{BASE}/schedule/index.php?saledate={ym}"
        try:
            d = b.goto(SITE, url)
        except Blocked as e:
            res["errors"].append(str(e)); continue
        if d.get("error"):
            sched[ym] = {"error": d["error"]}; continue
        p = parse_schedule(d["html"])
        cards = p["cards"]
        sched[ym] = {
            "url": url, "status": d["status"], "redirects": d["redirects"], "final": d["final"],
            "cards": len(cards),
            "general": sum(1 for c in cards if c["hobby_id"] and not c["tag"]),
            "online(P-반다이 링크)": sum(1 for c in cards if c["pbandai_id"]),
            "gbase": sum(1 for c in cards if c["tag"] and "ガンダムベース" in c["tag"]),
            "reissue_text_hits": p["reissue_text_hits"],
            "first": cards[0]["title"] if cards else None,
            "titles": [c["title"] for c in cards],
        }
        sched[ym]["_cards"] = cards
        if ym in FIXTURE_MONTHS:
            common.save_fixture(f"hobby-schedule-{ym}.html", clean_html(d["html"]))
    res["schedule"] = {k: {kk: vv for kk, vv in v.items() if kk not in ("_cards", "titles")} for k, v in sched.items()}

    # 3) 상세 샘플 (+ RG/PG 후보를 일정에서 동적으로 1개씩)
    picks = list(DETAIL_SAMPLES)
    all_cards = [c for v in sched.values() for c in v.get("_cards", []) if c["hobby_id"]]
    for label, rx in (("PG", r"^(PG|ＰＧ)\b|^PG "),):
        hit = next((c for c in all_cards if re.search(rx, c["title"])), None)
        if hit and hit["hobby_id"] not in {p[0] for p in picks}:
            picks.append((hit["hobby_id"], f"{label} (일정에서 동적 선택)"))
        elif not hit:
            res["errors"].append(f"{label} 후보를 캐시된 월에서 못 찾음")
    # RG는 일정 14개월에 없어서 브랜드 페이지(/brand/rg/)의 첫 상품을 쓴다 (목록 1요청)
    try:
        d = b.goto(SITE, f"{BASE}/brand/rg/")
        soup = BeautifulSoup(d["html"], "html.parser")
        rg_ids = []
        for a in soup.select("a[href*='/item/01_']"):
            m = re.search(r"/item/(01_\d+)/", a["href"])
            if m and m.group(1) not in rg_ids:
                rg_ids.append(m.group(1))
        res["brand_rg"] = {"status": d["status"], "item_links": len(rg_ids)}
        if rg_ids and rg_ids[0] not in {p[0] for p in picks}:
            picks.append((rg_ids[0], "RG (브랜드 페이지 첫 상품)"))
    except Blocked as e:
        res["errors"].append(str(e))
    details, images = [], {"akamai_gallery": {}, "cloudfront_signed": []}
    for item_id, why in picks:
        url = f"{BASE}/item/{item_id}/"
        try:
            d = b.goto(SITE, url, kind="detail")
        except Blocked as e:
            res["errors"].append(f"{item_id}: {e}"); continue
        if d.get("error") or d["status"] != 200:
            details.append({"id": item_id, "why": why, "status": d["status"], "error": d.get("error")}); continue
        p = parse_detail(d["html"], d["fetched_at"])
        p.update({"id": item_id, "why": why, "url": url, "fetched_at": d["fetched_at"]})
        details.append(p)
        ak = [u for u in p["gallery"] if "akamaihd.net" in u]
        if ak:
            images["akamai_gallery"][item_id] = ak
        for u in p["gallery"] + p["description_images"]:
            if expires_of(u):
                images["cloudfront_signed"].append({"url": u, "fetched_at": d["fetched_at"], "item": item_id})
        if item_id in FIXTURE_ITEMS:
            common.save_fixture(f"hobby-item-{item_id}.html", clean_html(d["html"]))
    res["details"] = details
    res["detail_requests_used"] = common.detail_used(SITE)

    # 3-b) 일반 HTTP(requests)로도 상세 필드가 나오는지 (이미 센 URL이라 상세 예산 추가 소모 없음)
    try:
        r = common.http_get(SITE, f"{BASE}/item/01_4257/", kind="detail")
        if r.get("ok"):
            pd_ = parse_detail(r["html"], datetime.now(common.KST).isoformat())
            res["plain_detail"] = {"status": r["status"], "title": pd_["title"], "fields": pd_["fields"],
                                   "gallery": len(pd_["gallery"]), "brands": len(pd_["brands_series"]),
                                   "pbandai_link": pd_["pbandai_link"]}
        else:
            res["plain_detail"] = {"ok": False, "status": r.get("status")}
    except Blocked as e:
        res["errors"].append(f"plain detail: {e}")

    # 3-c) 같은 제품이 여러 달에 반복되는지 (재판이 별도 카드로 올라오는지) — 캐시된 일정만 사용
    norm = lambda t: re.sub(r"[\s　（）()\[\]【】]", "", t).lower()
    seen_t: dict[str, list] = {}
    for ym, v in sched.items():
        for c in v.get("_cards", []):
            seen_t.setdefault(norm(c["title"]), []).append((ym, c["hobby_id"] or c["pbandai_id"]))
    res["repeated_titles_across_months"] = {t: m for t, m in seen_t.items() if len({x[0] for x in m}) > 1}

    # 4) 일정 썸네일도 서명 URL → 만료 측정용으로 같이 보관 (캐시된 값의 fetched_at 사용)
    for ym, v in sched.items():
        c = common.cache_get(v.get("url", ""))
        for card in v.get("_cards", [])[:2]:
            if expires_of(card["thumb"]):
                images["cloudfront_signed"].append({"url": card["thumb"], "fetched_at": c["fetched_at"],
                                                    "item": f"schedule-{ym}"})
    ttls = [expires_of(i["url"]) - epoch_of(i["fetched_at"]) for i in images["cloudfront_signed"]]
    res["signed_ttl_summary"] = {"n": len(ttls), "min_s": min(ttls) if ttls else None,
                                 "max_s": max(ttls) if ttls else None}

    # 5) 상품 검색 필터(브랜드/시리즈 키) → 걸프라 라인 분류 근거
    try:
        d = b.goto(SITE, f"{BASE}/item_all/")
        res["filters"] = parse_filters(d["html"])
        res["filters_counts"] = {k: len(v) for k, v in res["filters"].items()}
    except Blocked as e:
        res["errors"].append(str(e))

    # 6) 브랜드 페이지 1개 (30MS) — 라인 단위 열거 가능 여부
    try:
        d = b.goto(SITE, f"{BASE}/brand/30ms/")
        soup = BeautifulSoup(d["html"], "html.parser")
        items = soup.select("a[href*='/item/01_']")
        res["brand_30ms"] = {"status": d["status"], "title": d["title"], "item_links": len({a['href'] for a in items}),
                             "pager": [a.get_text(strip=True) for a in soup.select("[class*=pager] a, [class*=pagination] a")][:10]}
        common.save_fixture("hobby-brand-30ms.html", clean_html(d["html"]))
    except Blocked as e:
        res["errors"].append(str(e))

    # 산출물
    for ym, v in sched.items():
        v.pop("_cards", None)
    common.summary_write("hobby-images.json", images)
    common.summary_write("hobby-summary.json", res)
    return res


if __name__ == "__main__":
    br = common.Browser("ja-JP")
    try:
        out = run(br)
    finally:
        br.close(); common.shutdown()
    print("detail used:", out.get("detail_requests_used"), "errors:", out["errors"])
