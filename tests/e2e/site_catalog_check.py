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
        if path == "/data/collection.json" and MODE["linked"]:
            body = COLL_TEXT.encode("utf-8")
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
    before = len(M.history(page))
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
