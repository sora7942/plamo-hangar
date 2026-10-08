"""4단계(카탈로그 연결) 사이트 확인 — Playwright. 저장소 파일은 건드리지 않는다.

실행:  conda activate plamo;  python tests/e2e/site_catalog_check.py
- docs/ 를 로컬 서버로 띄우되 /data/collection.json 만 메모리에서 일부 프라에 catalogId 를 붙인 사본으로 바꿔 준다.
- 카탈로그 JSON 은 docs/data 의 실제 파일. 공식 이미지는 실제 호스트에서 가져온다(일반 Chrome UA — HeadlessChrome이면 호비 이미지가 막힌다).
- 소유자 모드는 tests/helpers/fake-github.js (가짜 GitHub, 실제 저장 없음).
- 스크린샷은 tests/e2e/out/ (gitignore — 공식 이미지가 찍히므로 저장소에 넣지 않는다).
"""
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_mock_check as M  # noqa: E402  (check/poll/new_context/open_page/shot ... 재사용)

DOCS = M.DOCS
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
check, section, poll, shot = M.check, M.section, M.poll, M.shot


def load(name):
    return json.loads((DOCS / "data" / name).read_text(encoding="utf-8"))


REAL = load("collection.json")
# 사용자가 실제 사이트에서 연결해 둔 값(catalogId·cover)은 이 확인과 무관하게 지운 사본으로 시험한다 (저장소 파일은 그대로)
for _k in REAL["kits"]:
    _k["catalogId"] = None
    _k["cover"] = None
UNLINKED_TEXT = json.dumps(REAL, ensure_ascii=False)
ITEMS = load("catalog-gunpla.json")["items"] + load("catalog-girl.json")["items"]
MANY = [x for x in ITEMS if len(x["images"]) >= 4][:6]
NOIMG = next(x for x in ITEMS if x.get("detailAt") and not x["images"])
UNKNOWN = "bh-99_99999"


def make_collection():
    """실제 컬렉션 사본: 앞 7개에 catalogId 를 붙인다 (원본 파일은 그대로)."""
    c = json.loads(json.dumps(REAL))
    k = c["kits"]
    for i, it in enumerate(MANY[:4]):
        k[i]["catalogId"] = it["id"]
    k[1]["cover"] = "off:2"
    k[4]["catalogId"] = NOIMG["id"]
    k[5]["catalogId"] = UNKNOWN
    return c


COLL = make_collection()
COLL_TEXT = json.dumps(COLL, ensure_ascii=False)
REQUESTS = []


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css", ".json": "application/json"}

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if self.headers.get("X-Plain") is None and path.startswith("/data/"):
            REQUESTS.append(self.path)
        if path == "/data/collection.json":
            body = (MODE.get("text") or (COLL_TEXT if MODE["linked"] else UNLINKED_TEXT)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


MODE = {"linked": True}


class UABrowser:
    def __init__(self, b):
        self.b = b

    def new_context(self, **kw):
        return self.b.new_context(user_agent=UA, **kw)


def catalog_requests():
    return [r for r in REQUESTS if "catalog-" in r or "meta.json" in r]


def M_thumb(u):
    return u.replace("bandai-a.akamaihd.net/bc/img/model/xl/", "bandai-a.akamaihd.net/bc/img/model/m/")


def card_for(page, kit_id):
    return page.locator(f'.card[data-id="{kit_id}"]')


def img_loaded(page, kit_id):
    return page.evaluate("""(id) => { const i = document.querySelector('.card[data-id="' + id + '"] .ph img'); return !!i && i.complete && i.naturalWidth > 0; }""", kit_id)


def run(browser, base):
    ids = [COLL["kits"][i]["id"] for i in range(6)]

    section("방문자 화면(토큰 없음) — 연결된 프라에 공식 사진")
    REQUESTS.clear()
    ctx = M.new_context(browser, token=False)
    page = M.open_page(ctx, base)
    check(page.locator(".card").count() == 131, "첫 화면: 컬렉션 131개 카드")
    for i in (0, 2, 3):
        poll(page, f"(() => {{ const i = document.querySelector('.card[data-id=\"{ids[i]}\"] .ph img'); return !!i; }})()", timeout=15000)
    page.wait_for_timeout(300)
    srcs = [page.evaluate("(id) => (document.querySelector('.card[data-id=\"' + id + '\"] .ph img') || {}).src || ''", ids[i]) for i in range(4)]
    exp = [M_thumb(MANY[i]["images"][2 if i == 1 else 0]) for i in range(4)]
    check(srcs == exp, f"카드는 작은 이미지: akamai는 /model/m/, 호비사이트 이미지는 원본 그대로 {[s[-34:] for s in srcs]}")
    check(sum("/bc/img/model/m/" in s for s in srcs) >= 1, "akamai 카드에 /model/m/ 사용")
    check(srcs[1] == exp[1], "cover=off:2 → 세 번째 공식 사진이 카드 대표")
    for i in range(4):  # loading=lazy 라서 화면에 들어와야 요청이 나간다
        card_for(page, ids[i]).scroll_into_view_if_needed()
        try:
            poll(page, f"(() => {{ const i = document.querySelector('.card[data-id=\"{ids[i]}\"] .ph img'); return !!i && i.complete && i.naturalWidth > 0; }})()", timeout=20000)
        except Exception:
            pass
    loaded = [img_loaded(page, ids[i]) for i in range(4)]
    check(all(loaded), f"방문자 화면에서 공식 사진이 실제로 뜬다(naturalWidth>0): {loaded}")
    check(page.locator(".card .ph img").count() == 4, "공식 사진 카드는 4개(연결 4, 사진 없음 1, 미등록 1, 나머지 미연결 → 자리표시)")
    creq = catalog_requests()
    check(len([r for r in creq if "meta.json" in r]) == 1 and len([r for r in creq if "catalog-" in r]) == 2, f"카탈로그 요청: meta 1 + catalog 2 ({len(creq)}건)")
    check(all("?v=" in r for r in creq if "catalog-" in r), "카탈로그는 ?v=<meta.updatedAt> 캐시 키로 요청")
    check(not [r for r in REQUESTS if "kr-arrivals" in r or "catalog-pending" in r or "feed.json" in r], "kr-arrivals·pending·feed 는 읽지 않는다")
    page.evaluate("window.scrollTo(0, 0)")
    shot(page, "cat-visitor-1280-light.png")

    section("상세: 공식 사진 갤러리·출처")
    card_for(page, ids[0]).click()
    page.wait_for_selector("#d-main", timeout=5000)
    main_src = page.evaluate("document.querySelector('#d-main').src")
    check(main_src == MANY[0]["images"][0], f"상세 대표는 원본 크기 공식 사진: {main_src[-40:]}")
    check(page.locator("#d-credit").is_visible() and "BANDAI SPIRITS" in page.locator("#d-credit").inner_text(), "출처 '사진: BANDAI SPIRITS' 표시")
    href = page.locator("#d-credit a").get_attribute("href")
    check(href == MANY[0]["url"] and page.locator("#d-credit a").get_attribute("rel") == "noopener noreferrer", f"원본 페이지 링크 {href}")
    n_th = page.locator(".thumbs .th").count()
    check(n_th == len(MANY[0]["images"]), f"썸네일 {n_th}개 = 공식 사진 {len(MANY[0]['images'])}장")
    page.locator(".thumbs .th").nth(2).click()
    check(page.evaluate("document.querySelector('#d-main').src") == MANY[0]["images"][2], "썸네일 클릭 → 큰 사진 교체")
    check(page.locator(".linkbox").count() == 1 and "공식 페이지" in page.locator(".linkbox").inner_text(), "상세에 '반다이 제품' 줄과 공식 페이지 링크")
    shot(page, "cat-detail-1280-light.png")
    page.keyboard.press("Escape")

    card_for(page, ids[4]).click()
    page.wait_for_selector(".official-link", timeout=5000)
    check(page.locator(".detail-photo .ghost").count() == 1, "안정 이미지가 없는 연결 제품: 등급 글자 자리표시")
    ob = page.locator(".official-link a")
    check(ob.count() == 1 and "공식 사진 보기" in ob.inner_text() and ob.get_attribute("href") == NOIMG["url"], "'공식 사진 보기' 버튼 → 호비사이트 상품 페이지")
    page.keyboard.press("Escape")

    card_for(page, ids[5]).click()
    page.wait_for_selector(".linkbox", timeout=5000)
    check("카탈로그에 아직 없는 제품" in page.locator(".linkbox").inner_text(), "카탈로그에 없는 catalogId: 다음 수집 안내")
    check(page.locator("#d-main").count() == 0 and page.locator(".official-link").count() == 1, "이 경우 사진 영역은 자리표시")
    page.keyboard.press("Escape")

    card_for(page, COLL["kits"][10]["id"]).click()
    page.wait_for_selector(".specs", timeout=5000)
    check(page.locator(".linkbox").count() == 0 and page.locator("#d-credit").count() == 0, "미연결 프라: 연결 줄·출처 없음")
    page.keyboard.press("Escape")
    check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:3]}")
    ctx.close()

    section("카탈로그 불러오기 실패 — 보유 목록은 그대로")
    ctx = M.new_context(browser, token=False)
    ctx.route("**/data/catalog-*.json*", lambda r: r.abort())
    page = ctx.new_page()
    page.goto(base)
    page.wait_for_selector(".card", timeout=15000)
    page.wait_for_timeout(1200)
    check(page.locator(".card").count() == 131, "카드 131개 그대로")
    check(page.locator(".card .ph img").count() == 0, "공식 사진 없이 자리표시")
    check("카탈로그를 불러오지 못해" in page.locator("#countline").inner_text(), "목록 위 안내: 카탈로그를 불러오지 못했어요")
    card_for(page, ids[0]).click()
    page.wait_for_selector(".linkbox", timeout=5000)
    check("불러오지 못했어요" in page.locator(".linkbox").inner_text(), "상세 안내도 같은 말")
    ctx.close()

    section("작은 이미지(/model/m/)가 안 뜨면 원본(xl)으로")
    ctx = M.new_context(browser, token=False)
    ctx.route("**/bc/img/model/m/**", lambda r: r.abort())
    page = M.open_page(ctx, base)
    card_for(page, ids[0]).scroll_into_view_if_needed()
    try:
        poll(page, f"(() => {{ const i = document.querySelector('.card[data-id=\"{ids[0]}\"] .ph img'); return !!i && i.complete && i.naturalWidth > 0; }})()", timeout=20000)
    except Exception:
        pass
    src0 = page.evaluate("(id) => (document.querySelector('.card[data-id=\"' + id + '\"] .ph img') || {}).src || ''", ids[0])
    check("/model/xl/" in src0 and img_loaded(page, ids[0]), f"m 이미지 실패 → xl로 대체되어 표시: {src0[-34:]}")
    ctx.close()

    section("연결된 프라가 없으면 카탈로그를 읽지 않는다")
    MODE["linked"] = False
    REQUESTS.clear()
    ctx = M.new_context(browser, token=False)
    page = M.open_page(ctx, base)
    page.wait_for_timeout(1000)
    check(not catalog_requests(), f"카탈로그 요청 없음 {catalog_requests()}")
    ctx.close()
    MODE["linked"] = True

    section("소유자 모드 — 설정에서 공식 사진 숨기기")
    seed = {COLL_PATH: COLL_TEXT + "\n", "docs/data/feed.json": '{"n":1}', "docs/data/meta.json": "{}"}
    ctx = M.new_context(browser, fake={"seed": seed})
    page = M.open_page(ctx, base)
    poll(page, f"!!document.querySelector('.card[data-id=\"{ids[0]}\"] .ph img')", timeout=15000)
    check(True, "소유자 화면에서도 공식 사진이 붙는다")
    page.locator('[data-act="settings"]').first.click()
    page.wait_for_selector("#s-offhide", timeout=5000)
    check(not page.locator("#s-offhide").is_checked(), "공식 사진 숨기기: 기본 꺼짐")
    before = len(M.history(page)); M.reset_log(page)
    page.locator("#s-offhide").check()
    page.locator("#s-save").click()
    M.settle(page)
    M.one_commit(page, "공식 사진 숨기기", before, msg_re=r"collection: 설정", modified=[COLL_PATH])
    saved = M.collection(page)
    check(saved["settings"]["hideOfficialPhotos"] is True, "settings.hideOfficialPhotos = true 저장")
    check(len(saved["kits"]) == 131 and saved["kits"][0]["catalogId"] == MANY[0]["id"], "kits·catalogId 는 그대로")
    check(page.locator(".card .ph img").count() == 0, "숨기기 후: 공식 사진 카드가 자리표시로")
    card_for(page, ids[0]).click()
    page.wait_for_selector(".official-link", timeout=5000)
    check("숨김 설정" in page.locator(".official-link").inner_text(), "상세: 숨김 설정 안내 + 공식 사진 보기")
    page.keyboard.press("Escape")
    ctx.close()

    section("400px · 다크 — 가로 넘침 없음")
    for scheme in ("light", "dark"):
        ctx = M.new_context(browser, w=400, h=860, scheme=scheme, token=False)
        page = M.open_page(ctx, base)
        poll(page, f"!!document.querySelector('.card[data-id=\"{ids[0]}\"] .ph img')", timeout=15000)
        page.wait_for_timeout(1500)
        check(M.no_overflow(page), f"400px {scheme}: 가로 스크롤 없음 (목록)")
        shot(page, f"cat-visitor-400-{scheme}.png")
        card_for(page, ids[0]).click()
        page.wait_for_selector("#d-main", timeout=5000)
        page.wait_for_timeout(1200)
        check(M.no_overflow(page) and page.evaluate("document.querySelector('.panel').scrollWidth <= document.querySelector('.panel').clientWidth + 1"), f"400px {scheme}: 상세 가로 넘침 없음")
        shot(page, f"cat-detail-400-{scheme}.png")
        ctx.close()


COLL_PATH = M.COLL


def gap_checks(browser, base):
    """재판 공백: 카탈로그 응답에 입고 날짜·발매일을 주입(route)해서 문구·정렬을 결정적으로 확인한다."""
    import datetime

    today = datetime.date.today()
    d = lambda n: (today + datetime.timedelta(days=n)).isoformat()
    kits = COLL["kits"]
    ids = [kits[i]["id"] for i in range(6)]
    patch = {
        MANY[0]["id"]: {"kr": [{"date": d(-7), "type": "restock"}], "release": {"month": "2023-05", "date": "2023-05-01"}},
        MANY[1]["id"]: {"kr": [{"date": d(-400), "type": "restock"}, {"date": d(-30), "type": "restock"}], "release": {"month": "2023-05", "date": "2023-05-01"}},
        MANY[2]["id"]: {"kr": [], "release": {"month": "2022-10", "date": None}},
        MANY[3]["id"]: {"kr": [], "release": {"month": "2027-03", "date": None}},
        NOIMG["id"]: {"kr": [{"date": d(5), "type": "new"}], "release": {"month": "2023-05", "date": "2023-05-01"}},
    }

    def serve(route):
        body = json.loads(route.fetch().text())
        for it in body["items"]:
            if it["id"] in patch:
                it.update(patch[it["id"]])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False))

    section("재판 공백 표시·정렬 (카탈로그에 입고 날짜 주입)")
    ctx = M.new_context(browser, token=False)
    ctx.route("**/data/catalog-*.json*", serve)
    page = M.open_page(ctx, base)
    poll(page, "document.querySelectorAll('.gapline').length >= 5", timeout=15000)
    line = lambda i: page.locator(f'.card[data-id="{ids[i]}"] .gapline').inner_text()
    check(line(0) == "마지막 입고 " + d(-7) + " · 7일 전", f"카드(최근 입고): {line(0)}")
    check("recent" in page.locator(f'.card[data-id="{ids[0]}"] .gapline').get_attribute("class"), "30일 이내 입고는 강조")
    check(line(1) == "마지막 입고 " + d(-30) + " · 30일 전", f"카드(가장 최근 입고를 씀): {line(1)}")
    check(line(2) == "입고 기록 없음 · 일본 발매 2022-10", f"카드(월만 아는 발매일은 월까지만): {line(2)}")
    check(line(3) == "일본 발매 예정 2027-03", f"카드(발매 예정): {line(3)}")
    check(line(4) == "입고 예정 " + d(5), f"카드(입고 예정): {line(4)}")
    check(page.locator(f'.card[data-id="{ids[5]}"] .gapline').count() == 0 and page.locator(f'.card[data-id="{kits[20]["id"]}"] .gapline').count() == 0, "카탈로그에 없는 연결·미연결 프라는 공백 줄 없음")
    shot(page, "cat-gap-list.png")

    card_for(page, ids[2]).click()
    page.wait_for_selector(".specs", timeout=5000)
    spec = page.locator(".specs").inner_text()
    check("국내 입고 기록 없음 (2024-01-04 이후 기준) · 일본 발매 2022-10" in spec, "상세: 기준일(joyOldest)이 들어간 문구")
    page.keyboard.press("Escape")
    card_for(page, ids[1]).click()
    page.wait_for_selector(".specs", timeout=5000)
    check("국내 마지막 입고 " + d(-30) + " · 30일 전" in page.locator(".specs").inner_text(), "상세: 국내 마지막 입고 · N일 전")
    page.keyboard.press("Escape")
    card_for(page, ids[4]).click()
    page.wait_for_selector(".specs", timeout=5000)
    check("국내 입고 예정 " + d(5) in page.locator(".specs").inner_text(), "상세: 국내 입고 예정")
    page.keyboard.press("Escape")

    page.select_option("#f-sort", "gap")
    page.wait_for_timeout(300)
    order = page.evaluate("Array.from(document.querySelectorAll('.card')).map(c => c.dataset.id)")
    exp = [ids[1], ids[0], ids[2], ids[4], ids[3]]
    check(order[:5] == exp, f"재판 공백 긴 순: 입고 오래된 순 → 기록 없음(일본 발매 오래된 순) {[ids.index(x) if x in ids else x for x in order[:5]]}")
    rest = order[5:]
    check(ids[5] in rest and len(order) == 131, "카탈로그에 없는 연결·미연결은 맨 뒤 묶음")
    ctx.close()

    section("빈 칸 모아보기: 반다이 제품 미연결 (소유자)")
    seed = {COLL_PATH: COLL_TEXT + "\n", "docs/data/feed.json": '{"n":1}', "docs/data/meta.json": "{}"}
    ctx = M.new_context(browser, fake={"seed": seed})
    ctx.route("**/data/catalog-*.json*", serve)
    page = M.open_page(ctx, base)
    opts = page.evaluate("Array.from(document.querySelectorAll('#f-gap option')).map(o => o.textContent)")
    check(any(o.startswith("반다이 제품 미연결") for o in opts), f"옵션에 '반다이 제품 미연결' {opts}")
    n_unlinked = sum(1 for k in kits if not k.get("catalogId"))
    check(any(o == f"반다이 제품 미연결 ({n_unlinked})" for o in opts), f"개수 {n_unlinked}")
    page.select_option("#f-gap", "unlinked")
    page.wait_for_timeout(300)
    check(page.locator(".card").count() == n_unlinked and page.locator(".gapline").count() == 0, f"미연결 {n_unlinked}개만 표시")
    page.click('[data-tab="wish"]')
    check(any(o.startswith("반다이 제품 미연결") for o in page.evaluate("Array.from(document.querySelectorAll('#f-gap option')).map(o => o.textContent)")), "위시리스트 탭에도 옵션이 있다")
    check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:3]}")
    ctx.close()

    section("400px · 다크: 재판 공백 줄")
    for scheme in ("light", "dark"):
        ctx = M.new_context(browser, w=400, h=860, scheme=scheme, token=False)
        ctx.route("**/data/catalog-*.json*", serve)
        page = M.open_page(ctx, base)
        poll(page, "document.querySelectorAll('.gapline').length >= 5", timeout=15000)
        page.select_option("#f-sort", "gap")
        page.wait_for_timeout(500)
        check(M.no_overflow(page), f"400px {scheme}: 가로 넘침 없음 (재판 공백 정렬)")
        shot(page, f"cat-gap-400-{scheme}.png")
        card_for(page, ids[2]).click()
        page.wait_for_selector(".specs", timeout=5000)
        page.wait_for_timeout(400)
        check(M.no_overflow(page) and page.evaluate("document.querySelector('.panel').scrollWidth <= document.querySelector('.panel').clientWidth + 1"), f"400px {scheme}: 상세 가로 넘침 없음")
        shot(page, f"cat-gap-detail-400-{scheme}.png")
        ctx.close()


def feed_checks(browser, base):
    """신제품·입고 탭: 지연 로딩, 내 프라 맨 위, 종류·라인·등급 필터, 위시리스트에 추가(연결된 채로)."""
    feed = load("feed.json")["items"]
    by_id = {x["id"]: x for x in ITEMS}
    cat_of = lambda f: by_id.get(f["catalogId"]) if f.get("catalogId") else None
    my_kr = next(f for f in feed if f["type"] == "kr-restock" and cat_of(f))
    my_new = next(f for f in feed if f["type"] == "new" and cat_of(f))
    coll = json.loads(json.dumps(REAL))
    coll["kits"][0]["catalogId"] = my_new["catalogId"]
    coll["kits"][1]["catalogId"] = my_kr["catalogId"]
    coll["kits"][1]["list"] = "wish"
    text = json.dumps(coll, ensure_ascii=False)
    n_mine = sum(1 for f in feed if f.get("catalogId") in (my_new["catalogId"], my_kr["catalogId"]))
    MODE["text"] = text

    section("신제품·입고 탭 (방문자)")
    REQUESTS.clear()
    ctx = M.new_context(browser, token=False)
    page = M.open_page(ctx, base)
    check(not [r for r in REQUESTS if "feed.json" in r], "탭을 열기 전에는 feed.json 을 읽지 않는다")
    check(page.locator('.tab[data-tab="feed"]').count() == 1, "세 번째 탭 '신제품·입고'")
    page.click('.tab[data-tab="feed"]')
    page.wait_for_selector(".fd-item", timeout=15000)
    check(len([r for r in REQUESTS if "feed.json" in r]) == 1 and all("?v=" in r for r in REQUESTS if "feed.json" in r), "feed.json 1회, ?v= 캐시 키")
    check(page.locator(".fd-item").count() == 60, f"처음 60개만 그린다 (전체 {len(feed)}개)")
    check(f"({len(feed) - 60}개 남음)" in page.locator("[data-more]").inner_text(), "더 보기 버튼")
    check(page.locator(".fd-item.mine").count() == n_mine and page.locator(".fd-item").first.get_attribute("class").endswith("mine"), f"내 프라 {n_mine}개가 맨 위·강조")
    tags = page.locator(".fd-item.mine .fd-mine").all_inner_texts()
    check(sorted(tags) == sorted(["내 프라 · 보유", "내 프라 · 위시"]) or n_mine != 2, f"내 프라 표시: {tags}")
    check(page.locator(".fd-item.mine").first.get_attribute("data-id") == my_kr["id"], "내 프라 안에서는 최근 발견 순 (국내 입고가 먼저)")
    check(page.locator("[data-wish]").count() == 0, "방문자에게는 '위시리스트에 추가' 버튼이 없다")
    hrefs = page.evaluate("Array.from(document.querySelectorAll('.fd-title[href]')).map(a => [a.href, a.rel, a.target])")
    ok = all(h.startswith("https://") and "noopener" in r and t == "_blank" and any(d in h for d in ("bandai-hobby.net", "p-bandai.jp", "joyhobby.co.kr")) for h, r, t in hrefs)
    check(ok and len(hrefs) == 60, "제목 링크: 공식·조이하비 https, noopener, 새 탭")
    n_img = page.evaluate("document.querySelectorAll('.fd-thumb img').length")
    check(n_img > 0 and page.evaluate("Array.from(document.querySelectorAll('.fd-thumb img')).every(i => i.src.startsWith('https://bandai-'))"), f"썸네일은 카탈로그의 공식 사진({n_img}개)")
    shot(page, "cat-feed-1280-light.png")

    cnt = lambda: int(page.locator(".count-line").inner_text().split("개 표시")[0])
    def click_chip(group, val):
        page.click(f'[data-fk="{group}"][data-fv="{val}"]')
        page.wait_for_timeout(150)
    click_chip("type", "kr-restock")
    exp = sum(1 for f in feed if f["type"] == "kr-restock")
    check(cnt() == exp and page.evaluate("Array.from(document.querySelectorAll('.fd-item .fd-type')).every(t => t.classList.contains('t-kr-restock'))"), f"종류 '국내 재입고' {exp}개")
    click_chip("type", "all")
    click_chip("line", "girl")
    exp = sum(1 for f in feed if cat_of(f) and cat_of(f)["line"] == "girl")
    check(cnt() == exp, f"라인 '걸프라' {exp}개 (연결 안 된 입고 글은 라인을 몰라 빠진다)")
    click_chip("line", "all")
    click_chip("grade", "MG")
    exp = sum(1 for f in feed if cat_of(f) and cat_of(f)["grade"] == "MG")
    check(cnt() == exp and exp > 0, f"등급 'MG' {exp}개")
    click_chip("type", "kr-new")
    exp2 = sum(1 for f in feed if f["type"] == "kr-new" and cat_of(f) and cat_of(f)["grade"] == "MG")
    check(cnt() == exp2, f"필터 조합(국내 신규 + MG) {exp2}개")
    click_chip("type", "all"); click_chip("grade", "all")
    click_chip("mine", "toggle")
    check(cnt() == n_mine and page.locator(".fd-item.mine").count() == n_mine, "내 프라만 보기")
    click_chip("mine", "toggle")
    page.click("[data-more]")
    check(page.locator(".fd-item").count() == min(120, len(feed)), "더 보기: 60개 더")
    check(M.no_overflow(page) and not ctx.errors, f"가로 넘침·콘솔 에러 없음 {ctx.errors[:3]}")
    # 탭을 오갔다 와도 다시 받지 않는다
    page.click('.tab[data-tab="own"]'); page.click('.tab[data-tab="feed"]')
    page.wait_for_selector(".fd-item")
    check(len([r for r in REQUESTS if "feed.json" in r]) == 1, "탭을 다시 열어도 feed.json 은 1회")
    ctx.close()

    section("신제품·입고 탭: 읽기 실패 → 다시 시도")
    ctx = M.new_context(browser, token=False)
    box = {"fail": True}
    ctx.route("**/data/feed.json*", lambda r: r.abort() if box["fail"] else r.continue_())
    page = M.open_page(ctx, base)
    page.click('.tab[data-tab="feed"]')
    page.wait_for_selector("[data-retry]", timeout=10000)
    check("불러오지 못했어요" in page.locator("#feed-root").inner_text(), "실패 안내 + 다시 시도")
    box["fail"] = False
    page.click("[data-retry]")
    page.wait_for_selector(".fd-item", timeout=10000)
    check(page.locator(".fd-item").count() > 0, "다시 시도하면 목록이 뜬다")
    ctx.close()

    section("신제품·입고 탭 (소유자): 위시리스트에 추가")
    seed = {COLL_PATH: text + "\n", "docs/data/feed.json": '{"n":1}', "docs/data/meta.json": "{}"}
    ctx = M.new_context(browser, fake={"seed": seed})
    page = M.open_page(ctx, base)
    page.click('.tab[data-tab="feed"]')
    page.wait_for_selector(".fd-item", timeout=15000)
    check(page.locator(".fd-item.mine [data-wish]").count() == 0, "내 프라에는 추가 버튼이 없다")
    target = next(f for f in feed if f["type"] == "kr-new" and cat_of(f) and f["catalogId"] not in (my_new["catalogId"], my_kr["catalogId"]))
    page.click('.tab[data-tab="feed"]')
    tcat = cat_of(target)
    # 필터로 대상을 화면에 올린다 (60개 제한)
    page.click(f'[data-fk="type"][data-fv="kr-new"]')
    page.click(f'[data-fk="grade"][data-fv="{tcat["grade"]}"]')
    before = len(M.history(page)); M.reset_log(page)
    page.locator(f'.fd-item[data-id="{target["id"]}"] [data-wish]').click()
    page.wait_for_selector("#kit-form", timeout=5000)
    check(page.input_value("#f-list") == "wish", "위시리스트로 열린다")
    check("연결됨" in page.locator("#pk-linked").inner_text(), "카탈로그에 연결된 채로 열린다")
    check(page.input_value("#f-grade") == tcat["grade"] and page.input_value("#f-name") != "", f"이름·등급이 채워진다: {page.input_value('#f-name')}")
    check(not page.locator("#pk-box").is_visible(), "연결된 항목은 찾기 영역이 접혀 있다")
    page.click("#save")
    if page.locator("#modal").count() and page.locator("#dup").is_visible():  # 같은 이름이 이미 있으면 한 번 더 눌러야 추가 (기존 중복 경고)
        page.click("#save")
    M.settle(page)
    M.one_commit(page, "위시리스트 추가", before, msg_re=r"collection: 추가 ", collection_only=True)
    saved = M.collection(page)["kits"][-1]
    check(saved["list"] == "wish" and saved["catalogId"] == target["catalogId"], f"저장: wish + catalogId {saved['catalogId']}")
    check(page.locator(f'.fd-item[data-id="{target["id"]}"]').get_attribute("class").endswith("mine") and page.locator(f'.fd-item[data-id="{target["id"]}"] [data-wish]').count() == 0, "추가 후 그 항목이 '내 프라'로 바뀐다")
    page.click('[data-fk="type"][data-fv="all"]'); page.click('[data-fk="grade"][data-fv="all"]')
    page.click('.tab[data-tab="wish"]')
    check(page.locator(".card").count() == 2, "위시리스트 탭에 2개 (기존 1 + 추가 1)")
    page.click('.tab[data-tab="feed"]')
    un = next(f for f in feed if not f.get("catalogId"))
    page.click('[data-fk="type"][data-fv="' + un["type"] + '"]')
    page.locator(f'.fd-item[data-id="{un["id"]}"] [data-wish]').click()
    page.wait_for_selector("#kit-form")
    check(page.locator("#pk-box").is_visible() and page.input_value("#f-list") == "wish" and page.input_value("#f-name") == un["titleKo"], "연결 안 된 입고 글: 이름만 채우고 찾기가 열린다")
    check("연결 안 됨" in page.locator("#pk-linked").inner_text(), "연결 없이 열린다")
    page.keyboard.press("Escape")
    page.click('[data-act="add"]')
    page.wait_for_selector("#kit-form")
    check(page.input_value("#f-list") == "own", "신제품·입고 탭에서 '+ 추가'는 보유 목록으로 열린다")
    page.keyboard.press("Escape")
    check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:3]}")
    ctx.close()

    section("신제품·입고 탭: 400px · 다크")
    for scheme in ("light", "dark"):
        ctx = M.new_context(browser, w=400, h=860, scheme=scheme, token=False)
        page = M.open_page(ctx, base)
        page.click('.tab[data-tab="feed"]')
        page.wait_for_selector(".fd-item", timeout=15000)
        page.wait_for_timeout(1500)
        check(M.no_overflow(page), f"400px {scheme}: 가로 넘침 없음 (탭 3개·필터·목록)")
        shot(page, f"cat-feed-400-{scheme}.png")
        ctx.close()
    ctx = M.new_context(browser, w=400, h=860, token=False)
    ctx.route("**/data/catalog-*.json*", lambda r: r.abort())
    page = M.open_page(ctx, base)
    page.click('.tab[data-tab="feed"]')
    page.wait_for_selector(".fd-item", timeout=15000)
    check("카탈로그를 불러오지 못해" in page.locator("#feed-root").inner_text() and page.locator(".fd-item").count() > 0, "카탈로그 없이도 소식 목록은 뜨고 안내가 나온다")
    ctx.close()
    MODE.pop("text", None)


def autolink_checks(browser, base):
    """설정 '자동 연결 후보 보기' + 시리즈 한국어 + 상세 리뷰 링크. 카탈로그 응답에 seriesKo 를 주입한다(크롤러가 만들기 전 단계)."""
    import collections
    import re
    import unicodedata

    def pynorm(s):
        return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s or "").lower())

    def pytitle(it):
        s = (it.get("nameKo") or "").strip()
        for tok in (it.get("grade"), it.get("scale")):
            if tok and s.startswith(tok + " "):
                s = s[len(tok) + 1:].strip()
        return s

    cnt = collections.Counter((pynorm(pytitle(x)), x["grade"], x["scale"] or "논스케일") for x in ITEMS if x.get("nameKo") and x["grade"] in ("HG", "MG", "RG"))
    ok = [x for x in ITEMS if x.get("nameKo") and x["grade"] in ("HG", "MG", "RG") and x["scale"] and x.get("series") and cnt[(pynorm(pytitle(x)), x["grade"], x["scale"])] == 1 and pytitle(x)]
    dup = next(x for x in ITEMS if x.get("nameKo") and x["grade"] in ("HG", "MG", "RG") and x["scale"] and cnt[(pynorm(pytitle(x)), x["grade"], x["scale"])] > 1 and pytitle(x))
    X, Y, Z = ok[0], ok[1], ok[2]
    KO = {X["id"]: "테스트 시리즈 한국어 X", Y["id"]: "테스트 시리즈 한국어 Y"}

    def serve(route):
        body = json.loads(route.fetch().text())
        for it in body["items"]:
            if it["id"] in KO:
                it["seriesKo"] = KO[it["id"]]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False))

    coll = json.loads(json.dumps(REAL))
    k = coll["kits"]
    k[0].update(name=pytitle(X), grade=X["grade"], scale=X["scale"], series="", catalogId=None)                      # 연결 후보 (빈 시리즈칸)
    k[1].update(name="시리즈 제안 대상", catalogId=Y["id"], series=Y["series"])                                       # 일본어 그대로 → 한국어 제안
    k[2].update(name="직접 적은 시리즈", catalogId=Y["id"], series="내가 직접 쓴 시리즈")                              # 제안 안 함
    k[3].update(name=pytitle(dup), grade=dup["grade"], scale=dup["scale"], catalogId=None)                          # 후보 2개 → 제안 안 함
    k[4].update(name=pytitle(X), grade="기타", scale=X["scale"], catalogId=None)                                      # 등급 기타 → 제안 안 함
    k[6].update(name="빈 칸 채우기 대상", catalogId=Z["id"], grade="기타", scale="논스케일", series="")                      # 빈 칸 채우기 후보 (등급·스케일·시리즈)
    k[7].update(name="시리즈는 직접 적음", catalogId=Z["id"], grade="기타", scale="논스케일", series="내가 직접 쓴 시리즈 Z")      # 시리즈는 건드리면 안 됨
    ids = [x["id"] for x in k[:5]]
    text = json.dumps(coll, ensure_ascii=False)
    seed = {COLL_PATH: text + "\n", "docs/data/feed.json": '{"n":1}', "docs/data/meta.json": "{}"}

    section("설정 → 자동 연결 후보 보기")
    ctx = M.new_context(browser, fake={"seed": seed})
    ctx.route("**/data/catalog-*.json*", serve)
    page = M.open_page(ctx, base)
    page.locator('[data-act="settings"]').first.click()
    page.wait_for_selector("#s-auto", timeout=5000)
    page.click("#s-auto")
    page.wait_for_selector("#al-body input[data-kind]", timeout=20000)
    link_ids = page.evaluate("Array.from(document.querySelectorAll('input[data-kind=\"link\"]')).map(i => i.dataset.id)")
    ser_ids = page.evaluate("Array.from(document.querySelectorAll('input[data-kind=\"series\"]')).map(i => i.dataset.id)")
    check(ids[0] in link_ids, "이름·등급·스케일이 같은 프라가 연결 후보에 있다")
    check(ids[3] not in link_ids and ids[4] not in link_ids, "후보가 2개인 이름·등급이 기타인 프라는 제안하지 않는다")
    check(ser_ids == [ids[1]], f"시리즈 한국어 제안은 일본어 그대로인 프라 1개만 {len(ser_ids)}개")
    row = page.locator(f'input[data-kind="link"][data-id="{ids[0]}"]').locator("xpath=ancestor::li")
    check("채워질 항목" in row.inner_text() and "시리즈" in row.inner_text(), "행에 채워질 항목 안내")
    srow = page.locator(f'input[data-kind="series"][data-id="{ids[1]}"]').locator("xpath=ancestor::li").inner_text()
    check(Y["series"] in srow and KO[Y["id"]] in srow, "일본어 → 한국어 미리보기")
    check(page.locator("#al-go").inner_text() != "적용" and not page.locator("#al-go").is_disabled(), f"적용 버튼: {page.locator('#al-go').inner_text()}")
    shot(page, "cat-autolink-1280.png")
    # 우리가 확인하려는 두 개만 남긴다
    page.click('[data-all="link"]')
    page.click('[data-all="series"]')
    page.click('[data-all="fill"]')
    page.check(f'input[data-kind="link"][data-id="{ids[0]}"]')
    page.check(f'input[data-kind="series"][data-id="{ids[1]}"]')
    check(page.locator("#al-go").inner_text() == "1개 연결 · 시리즈 1개 변경 적용", f"선택 수가 버튼에 반영: {page.locator('#al-go').inner_text()}")
    before = len(M.history(page)); M.reset_log(page)
    page.click("#al-go")
    M.settle(page)
    M.one_commit(page, "자동 연결", before, msg_re=r"collection: 반다이 제품 1개 자동 연결 · 시리즈 1개 한국어로", collection_only=True)
    after = {x["id"]: x for x in M.collection(page)["kits"]}
    check(after[ids[0]]["catalogId"] == X["id"] and after[ids[0]]["name"] == k[0]["name"], "연결됨, 내 이름은 그대로")
    check(after[ids[0]]["series"] == KO[X["id"]], f"빈 시리즈칸은 한국어 시리즈로 채움: {after[ids[0]]['series']}")
    check(after[ids[1]]["series"] == KO[Y["id"]] and after[ids[1]]["catalogId"] == Y["id"], "일본어 시리즈를 한국어로 바꿈")
    others = [i for i in after if i not in ids[:2]]
    check(all(after[i] == next(x for x in k if x["id"] == i) for i in others), f"나머지 프라 {len(others)}개는 하나도 바뀌지 않음 (직접 적은 시리즈·빈 칸 채우기 후보 포함)")

    section("빈 칸 채우기 (이미 연결된 프라)")
    z_series = Z.get("seriesKo") or Z["series"]
    page.locator('[data-act="settings"]').first.click()
    page.click("#s-auto")
    page.wait_for_selector('input[data-kind="fill"]', timeout=20000)
    fill_ids = page.evaluate("""Array.from(document.querySelectorAll('input[data-kind="fill"]')).map(i => i.dataset.id)""")
    check(k[6]["id"] in fill_ids and k[7]["id"] in fill_ids, "빈 칸이 있는 연결 프라가 후보에 있다")
    check(ids[0] not in fill_ids and ids[2] not in fill_ids and k[10]["id"] not in fill_ids, "이미 채워진·미연결 프라는 후보가 아니다")
    r6 = page.locator(f'input[data-kind="fill"][data-id="{k[6]["id"]}"]').locator("xpath=ancestor::li").inner_text()
    r7 = page.locator(f'input[data-kind="fill"][data-id="{k[7]["id"]}"]').locator("xpath=ancestor::li").inner_text()
    check("등급: 기타 → " + Z["grade"] in r6 and "스케일: 논스케일 → " + Z["scale"] in r6 and "시리즈" in r6, f"행에 바뀔 값 미리보기: {r6.splitlines()[1:4]}")
    check("시리즈" not in r7.replace("시리즈는 직접 적음", ""), "직접 적은 시리즈는 후보 항목에 없다")
    page.click('[data-all="fill"]'); page.click('[data-all="link"]') if page.locator('[data-all="link"]').count() else None
    page.check(f'input[data-kind="fill"][data-id="{k[6]["id"]}"]')
    check(page.locator("#al-go").inner_text() == "빈 칸 1개 채움 적용", f"버튼: {page.locator('#al-go').inner_text()}")
    before = len(M.history(page)); M.reset_log(page)
    page.click("#al-go")
    M.settle(page)
    M.one_commit(page, "빈 칸 채우기", before, msg_re=r"collection: 빈 칸 1개 채움", collection_only=True)
    after2 = {x["id"]: x for x in M.collection(page)["kits"]}
    a6, a7 = after2[k[6]["id"]], after2[k[7]["id"]]
    check((a6["grade"], a6["scale"], a6["series"]) == (Z["grade"], Z["scale"], z_series) and a6["name"] == "빈 칸 채우기 대상", f"등급·스케일·시리즈 채움: {a6['grade']} {a6['scale']} {a6['series'][:12]}")
    check((a7["grade"], a7["scale"], a7["series"]) == ("기타", "논스케일", "내가 직접 쓴 시리즈 Z"), "선택하지 않은 프라는 그대로(직접 적은 시리즈 포함)")
    page.keyboard.press("Escape")

    section("상세: 리뷰 찾아보기 · 시리즈 · 다시 열면 제안이 없다")
    card_for(page, ids[0]).click()
    page.wait_for_selector(".reviews", timeout=5000)
    hrefs = page.evaluate("Array.from(document.querySelectorAll('.reviews a')).map(a => [a.href, a.rel, a.target, a.textContent])")
    check(len(hrefs) == 2 and hrefs[0][0].startswith("https://www.youtube.com/results?search_query=") and hrefs[1][0].startswith("https://search.naver.com/search.naver?where=blog&query="), f"리뷰 링크: {[h[3] for h in hrefs]}")
    check(all("noopener" in h[1] and h[2] == "_blank" for h in hrefs), "새 탭 · noopener")
    q = f"{X['grade']} {k[0]['name']} 리뷰"
    check(page.evaluate("decodeURIComponent(document.querySelector('.reviews a').href.split('search_query=')[1])") == q, f"검색어 '{q}'")
    poll(page, f"document.querySelector('.linkbox') && document.querySelector('.linkbox').innerText.includes('{KO[X['id']]}')", timeout=15000)
    check(True, "연결 줄에 한국어 시리즈 표시")
    page.keyboard.press("Escape")
    page.locator('[data-act="settings"]').first.click()
    page.click("#s-auto")
    page.wait_for_selector("#al-body", timeout=5000)
    poll(page, "document.querySelector('#al-body') && !/불러오는 중/.test(document.querySelector('#al-body').innerText)", timeout=15000)
    left = page.evaluate("Array.from(document.querySelectorAll('input[data-kind]')).map(i => i.dataset.kind + ':' + i.dataset.id)")
    check(f"link:{ids[0]}" not in left and f"series:{ids[1]}" not in left, "적용한 항목은 제안에서 사라진다")
    page.keyboard.press("Escape")
    check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:3]}")
    ctx.close()

    section("자동 연결 후보: 400px · 다크")
    for scheme in ("light", "dark"):
        ctx = M.new_context(browser, w=400, h=860, scheme=scheme, fake={"seed": seed})
        ctx.route("**/data/catalog-*.json*", serve)
        page = M.open_page(ctx, base)
        page.locator('[data-act="settings"]').first.click()
        page.click("#s-auto")
        page.wait_for_selector("#al-body input[data-kind]", timeout=20000)
        page.wait_for_timeout(1000)
        check(page.evaluate("(() => { const p = document.querySelector('.panel'); return p.scrollWidth <= p.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth + 1; })()"), f"400px {scheme}: 가로 넘침 없음")
        shot(page, f"cat-autolink-400-{scheme}.png")
        ctx.close()


def owner_flows(browser, base):
    """소유자 모드: 찾기 → 연결 → 채우기 → 공식 대표 사진 → 저장(커밋 1개). 저장되는 건 catalogId·cover 뿐 (이미지 URL은 저장 안 함)."""
    import collections

    titles = collections.Counter(x["nameKo"] for x in ITEMS)
    uniq = [x for x in ITEMS if titles[x["nameKo"]] == 1 and len(x["images"]) >= 3 and x["grade"] in ("HG", "MG", "RG") and x.get("series") and x["scale"]]
    A, B = uniq[0], uniq[1]
    S72 = next(x for x in ITEMS if x["scale"] == "1/72" and x.get("nameKo"))
    seed = {COLL_PATH: json.dumps(REAL, ensure_ascii=False) + "\n", "docs/data/feed.json": '{"n":1}', "docs/data/meta.json": "{}"}
    ctx = M.new_context(browser, fake={"seed": seed})
    page = M.open_page(ctx, base)
    kits = REAL["kits"]
    gita = [x for x in kits if x["grade"] == "기타"]

    section("추가 폼: 찾기 → 선택 → 채우기 → 공식 사진 대표 → 저장")
    before = len(M.history(page)); M.reset_log(page)
    page.click("[data-act=add]")
    page.wait_for_selector("#pk-q", timeout=5000)
    check(page.locator("#pk-box").is_visible(), "새 프라: 찾기 영역이 열려 있다")
    check(page.evaluate("document.activeElement && document.activeElement.id") == "pk-q", "검색 칸에 포커스")
    page.fill("#pk-q", A["nameKo"])
    page.wait_for_selector(f'.pk-item[data-id="{A["id"]}"]', timeout=15000)
    page.keyboard.press("Enter")
    check(page.locator("#modal").count() == 1 and len(M.history(page)) == before, "검색 칸에서 Enter: 저장·닫힘 없음")
    check(page.locator(".pk-item").first.get_attribute("data-id") == A["id"], "정확한 이름이면 1순위 후보")
    page.click(f'[data-pick="{A["id"]}"]')
    check(page.input_value("#f-grade") == A["grade"], f"등급 채움 {A['grade']}")
    check(page.input_value("#f-scale") == A["scale"], f"스케일 채움 {A['scale']}")
    check(page.input_value("#f-series") == (A.get("seriesKo") or A["series"]), "시리즈 채움 (한국어 시리즈가 있으면 그것)")
    name = page.input_value("#f-name")
    check(bool(name) and not name.startswith(A["grade"] + " "), f"이름 채움(등급 머리말 없이): {name}")
    check("채운 항목" in page.locator("#pk-note").inner_text(), "채운 항목 안내")
    check("연결됨" in page.locator("#pk-linked").inner_text(), "연결됨 표시")
    n_off = page.locator(".pm-official").count()
    check(n_off == len(A["images"]), f"사진 관리에 공식 사진 {n_off}장")
    page.locator(".pm-official").nth(2).locator('[data-pm="cover"]').click()
    check(page.locator(".pm-official").nth(2).locator(".pm-badge").count() == 1, "공식 사진 3번째가 대표로 표시")
    M.save_and_wait(page)
    M.one_commit(page, "추가(연결)", before, msg_re=r"collection: 추가 ", collection_only=True)
    text = page.evaluate(f"window.__gh.fileText('{COLL_PATH}')")
    saved = json.loads(text)["kits"][-1]
    check(saved["catalogId"] == A["id"] and saved["cover"] == "off:2" and saved["photos"] == [], f"저장값: catalogId·cover만 {saved['catalogId']} {saved['cover']}")
    check("akamaihd" not in text and "bandai-hobby.net/images" not in text, "공식 이미지 URL은 collection.json에 저장되지 않는다")

    section("상세 → 반다이 제품 연결 (빈 칸만 채움, 이름은 그대로)")
    target = gita[0]
    card_for(page, target["id"]).click()
    page.wait_for_selector("#relink", timeout=5000)
    check(page.locator("#relink").inner_text() == "반다이 제품 연결" and page.locator("#unlink").count() == 0, "연결 전: '반다이 제품 연결'만")
    page.click("#relink")
    page.wait_for_selector("#pk-q", timeout=5000)
    page.fill("#pk-q", B["nameKo"])
    page.wait_for_selector(f'.pk-item[data-id="{B["id"]}"]', timeout=15000)
    check(page.locator("#pk-go").is_disabled(), "고르기 전엔 '연결' 버튼이 꺼져 있다")
    page.click(f'[data-pick="{B["id"]}"]')
    summ = page.locator("#pk-sum").inner_text()
    check("채워지는 항목" in summ and "이름" not in summ.split("채워지는 항목")[-1], f"요약: {summ}")
    before = len(M.history(page)); M.reset_log(page)
    page.click("#pk-go")
    M.settle(page)
    M.one_commit(page, "연결", before, msg_re=r"collection: 반다이 제품 연결 ", collection_only=True)
    k2 = next(x for x in M.collection(page)["kits"] if x["id"] == target["id"])
    check(k2["catalogId"] == B["id"] and k2["name"] == target["name"], "catalogId 저장, 내 이름은 그대로")
    check(k2["grade"] == B["grade"] and (not target["series"] or k2["series"] == target["series"]), f"기타였던 등급이 {k2['grade']}로 채워짐, 있던 시리즈는 유지")
    check(k2["price"] == target["price"] and k2["tags"] == target["tags"] and k2["memo"] == target["memo"], "다른 필드는 건드리지 않음")

    section("이름도 바꾸기 체크 · 연결 변경 · 연결 해제")
    t2 = gita[1]
    card_for(page, t2["id"]).click()
    page.click("#relink")
    page.fill("#pk-q", A["nameKo"])
    page.wait_for_selector(f'.pk-item[data-id="{A["id"]}"]', timeout=15000)
    check(page.locator(f'.pk-item[data-id="{A["id"]}"] .pk-used').count() == 1, "이미 다른 프라에 연결된 제품이면 알려 준다")
    page.check("#pk-rename")
    page.click(f'[data-pick="{A["id"]}"]')
    page.click("#pk-go")
    M.settle(page)
    k3 = next(x for x in M.collection(page)["kits"] if x["id"] == t2["id"])
    check(k3["name"] == name and k3["catalogId"] == A["id"], "체크하면 이름도 카탈로그 이름으로")
    card_for(page, t2["id"]).click()
    page.wait_for_selector("#unlink", timeout=5000)
    check(page.locator("#relink").inner_text() == "제품 연결 변경", "연결 후: '제품 연결 변경' + '연결 해제'")
    before = len(M.history(page)); M.reset_log(page)
    page.click("#unlink")
    M.settle(page)
    M.one_commit(page, "연결 해제", before, msg_re=r"collection: 반다이 제품 연결 해제 ", collection_only=True)
    k4 = next(x for x in M.collection(page)["kits"] if x["id"] == t2["id"])
    check(k4["catalogId"] is None and k4["name"] == name and k4["grade"] == k3["grade"], "해제해도 채운 값은 그대로, catalogId만 null")

    section("호비사이트 주소 붙여넣기")
    t3 = gita[2]
    card_for(page, t3["id"]).click()
    page.click("#relink")
    page.fill("#pk-q", A["url"])
    page.wait_for_selector(f'.pk-item[data-id="{A["id"]}"]', timeout=5000)
    check(page.locator(".pk-item").count() == 1 and "주소로 찾은 제품" in page.locator("#pk-status").inner_text(), "카탈로그에 있는 주소: 그 제품 한 개")
    page.fill("#pk-q", "https://bandai-hobby.net/item/99_99999/")
    page.wait_for_selector("[data-pick-ref]", timeout=5000)
    check("카탈로그에 없어요" in page.locator("#pk-status").inner_text(), "없는 주소: 연결만 저장 안내")
    page.click("[data-pick-ref]")
    check("연결만 저장" in page.locator("#pk-sum").inner_text(), "요약: 연결만 저장")
    page.click("#pk-go")
    M.settle(page)
    k5 = next(x for x in M.collection(page)["kits"] if x["id"] == t3["id"])
    check(k5["catalogId"] == "bh-99_99999" and k5["name"] == t3["name"] and k5["grade"] == t3["grade"], "catalogId만 저장, 나머지는 그대로")
    card_for(page, t3["id"]).click()
    page.wait_for_selector(".linkbox", timeout=5000)
    poll(page, "document.querySelector('.linkbox') && /아직 없는 제품/.test(document.querySelector('.linkbox').innerText)", timeout=15000)
    check(True, "상세: '카탈로그에 아직 없는 제품이에요'")
    page.keyboard.press("Escape")
    page.click("[data-act=add]")
    page.wait_for_selector("#pk-q")
    page.fill("#pk-q", "https://p-bandai.jp/item/item-1000000000/")
    poll(page, "/카탈로그에 있는 것만/.test(document.querySelector('#pk-status').innerText)", timeout=10000)
    check(page.locator("[data-pick-ref]").count() == 0, "없는 P-반다이 주소는 연결 버튼 없이 안내만")
    page.fill("#pk-q", "zzzz존재하지않는이름")
    poll(page, "/찾지 못했어요/.test(document.querySelector('#pk-status').innerText)", timeout=10000)
    check(True, "못 찾으면 안내 문구")
    page.keyboard.press("Escape")

    section("수정 폼: 연결 해제·스케일 보존")
    linked = next(x for x in M.collection(page)["kits"] if x["id"] == next(y["id"] for y in M.collection(page)["kits"] if y.get("catalogId") == A["id"]))
    card_for(page, linked["id"]).click()
    page.click("#edit")
    page.wait_for_selector("#pk-unlink", timeout=5000)
    check(not page.locator("#pk-box").is_visible(), "수정 폼: 찾기 영역은 접혀 있다")
    check(page.locator(".pm-official").count() == len(A["images"]), "연결된 프라의 공식 사진이 사진 관리에 보인다")
    check(page.locator('.pm-official .pm-badge').count() == 1, "대표(off:2) 표시가 유지된다")
    before = len(M.history(page)); M.reset_log(page)
    page.click("#pk-unlink")
    check(page.locator(".pm-official").count() == 0, "연결을 풀면 공식 사진 항목이 사라진다")
    M.save_and_wait(page)
    M.one_commit(page, "수정 폼에서 해제", before, collection_only=True)
    k6 = next(x for x in M.collection(page)["kits"] if x["id"] == linked["id"])
    check(k6["catalogId"] is None and k6["cover"] is None, "catalogId·공식 대표(cover) 모두 해제")

    page.click("[data-act=add]")
    page.wait_for_selector("#pk-q")
    page.fill("#pk-q", S72["nameKo"])
    page.wait_for_selector(f'.pk-item[data-id="{S72["id"]}"]', timeout=15000)
    page.click(f'[data-pick="{S72["id"]}"]')
    check(page.input_value("#f-scale") == "1/72", "목록에 없는 스케일(1/72)도 선택·보존")
    page.keyboard.press("Escape")
    check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:3]}")
    shot(page, "cat-owner-final.png")
    ctx.close()

    section("400px 모바일 · 다크: 추가 폼 찾기 영역")
    for scheme in ("light", "dark"):
        ctx = M.new_context(browser, w=400, h=860, scheme=scheme, fake={"seed": seed})
        page = M.open_page(ctx, base)
        page.click("[data-act=add]")
        page.wait_for_selector("#pk-q")
        page.fill("#pk-q", A["nameKo"])
        page.wait_for_selector(f'.pk-item[data-id="{A["id"]}"]', timeout=15000)
        page.wait_for_timeout(1200)
        ok = page.evaluate("(() => { const p = document.querySelector('.panel'); return p.scrollWidth <= p.clientWidth + 1 && document.documentElement.scrollWidth <= innerWidth + 1; })()")
        check(ok, f"400px {scheme}: 가로 넘침 없음 (찾기 결과)")
        shot(page, f"cat-form-400-{scheme}.png")
        page.click(f'[data-pick="{A["id"]}"]')
        page.wait_for_timeout(800)
        shot(page, f"cat-form-picked-400-{scheme}.png")
        ctx.close()


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(DOCS)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("서버", base)
    M.OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = UABrowser(p.chromium.launch())
        try:
            run(browser, base)
            owner_flows(browser, base)
            gap_checks(browser, base)
            feed_checks(browser, base)
            autolink_checks(browser, base)
        finally:
            browser.b.close()
            srv.shutdown()
    bad = [m for ok, m in M.results if not ok]
    print(f"\n{len(M.results) - len(bad)}/{len(M.results)} 통과")
    for m in bad:
        print("  ✗", m)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
