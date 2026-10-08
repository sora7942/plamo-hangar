"""docs/ 사이트를 Playwright로 확인한다 (가짜 GitHub — 실제 네트워크 저장·실제 토큰 없음).

실행:  conda activate plamo;  python tests/e2e/site_mock_check.py
- 앱 코드에는 mock 모드가 없다. add_init_script로 tests/helpers/fake-github.js 를 주입해 window.fetch 의
  https://api.github.com/ 요청만 메모리 저장소로 응답한다. 요청 로그는 window.__gh.log.
- 스크린샷은 tests/e2e/out/ (gitignore).
- Google Fonts·cdnjs(SheetJS)는 실제 네트워크를 쓴다(엑셀 백업 확인). 오프라인이면 그 단계만 건너뛴다.
"""
import base64
import json
import re
import struct
import sys
import threading
import time
import zlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
OUT = ROOT / "tests" / "e2e" / "out"
FAKE_JS = (ROOT / "tests" / "helpers" / "fake-github.js").read_text(encoding="utf-8")
TOKEN = "mock-token"
COLL = "docs/data/collection.json"
FEED = "docs/data/feed.json"

results = []


def check(cond, msg):
    results.append((bool(cond), msg))
    print(("  ✓ " if cond else "  ✗ ") + msg, flush=True)
    return bool(cond)


def section(title):
    print(f"\n== {title}", flush=True)


# ---------- 로컬 서버 (docs/ 만) ----------
# 이 확인은 "빈 컬렉션에서 시작"을 전제로 한다. 저장소의 실제 collection.json(사용자 데이터)은 쓰지 않고 빈 컬렉션을 제공한다.
EMPTY_COLL = '{"version":3,"settings":{"name":"프라 격납고","hidePurchase":true,"hideOfficialPhotos":false},\n"kits":[]}\n'


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css",
                      ".webp": "image/webp", ".svg": "image/svg+xml", ".json": "application/json"}

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/data/collection.json":
            body = EMPTY_COLL.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(DOCS)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


# ---------- 테스트용 PNG (외부 라이브러리 없이) ----------
def make_png(w, h, seed=0):
    base = bytes(((i * 7 + seed * 53) % 256) for i in range(3 * w))
    rows = []
    for y in range(h):
        k = (y * 3) % (3 * w)
        rows.append(b"\x00" + base[k:] + base[:k])

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def png_file(name, w, h, seed=0):
    return {"name": name, "mimeType": "image/png", "buffer": make_png(w, h, seed)}


# ---------- 컨텍스트·페이지 ----------
def new_context(browser, *, w=1280, h=900, scheme="light", fake=None, snapshot=None, token=True):
    ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, accept_downloads=True, locale="ko-KR")
    opts = {"token": TOKEN, "seed": {COLL: EMPTY_COLL, FEED: '{"n":1}', "docs/data/meta.json": "{}"}}
    if snapshot:
        opts["restore"] = snapshot
    opts.update(fake or {})
    ctx.add_init_script(script=FAKE_JS + "\nFakeGitHub.install(window," + json.dumps(opts) + ");")
    if token:
        ctx.add_init_script(script=f"try{{if(!localStorage.getItem('plamo-token'))localStorage.setItem('plamo-token','{TOKEN}')}}catch(e){{}}")
    ctx.leaked = []
    ctx.route("https://api.github.com/**", lambda r: (ctx.leaked.append(r.request.url), r.abort()))
    ctx.errors = []
    return ctx


def watch(ctx, page):
    def on_console(m):
        if m.type == "error" and "fonts.g" not in (m.location.get("url", "") if m.location else ""):
            ctx.errors.append(m.text)
    page.on("console", on_console)
    page.on("pageerror", lambda e: ctx.errors.append("pageerror: " + str(e)))


def open_page(ctx, base):
    page = ctx.new_page()
    watch(ctx, page)
    page.goto(base)
    page.wait_for_selector(".card, .empty", timeout=15000)
    return page


def poll(page, expr, timeout=30000, interval=100):
    """page.evaluate 를 폴링한다. (CSP 아래에서 wait_for_function 은 eval 이 막혀 못 쓴다)"""
    end = time.time() + timeout / 1000
    while time.time() < end:
        try:
            if page.evaluate(expr):
                return True
        except Exception:
            pass
        page.wait_for_timeout(interval)
    raise PWTimeout(f"poll timeout: {expr[:90]}")


def gh(page, expr):
    return page.evaluate(expr)


def history(page):
    return gh(page, "window.__gh.clientHistory().map(c=>({sha:c.sha,message:c.message,parents:c.parents,changes:c.changes}))")


def collection(page):
    return json.loads(gh(page, f"window.__gh.fileText('{COLL}')"))


def write_calls(page):
    return gh(page, "window.__gh.writeCalls().map(e=>e.method+' '+e.path.replace(/^\\/repos\\/[^/]+\\/[^/]+/,''))")


def one_commit(page, label, before, *, msg_re=None, modified=None, added=None, deleted=None, collection_only=False):
    """한 동작 = 커밋 1개인지: 새 커밋 1개, 커밋 POST 1·ref PATCH 1, 메시지·변경 경로."""
    h = history(page)
    ok = check(len(h) == before + 1, f"{label}: 커밋이 정확히 1개 늘었다 ({before}→{len(h)})")
    w = write_calls(page)
    check(w.count("POST /git/commits") == 1 and w.count("PATCH /git/refs/heads/main") == 1, f"{label}: 커밋 POST 1회 + ref PATCH 1회")
    if not ok or len(h) <= before:
        return None
    c = h[-1]
    if msg_re:
        check(re.search(msg_re, c["message"]), f"{label}: 메시지 {c['message']!r}")
    ch = c["changes"]
    if collection_only:
        check(ch["modified"] == [COLL] and not ch["added"] and not ch["deleted"], f"{label}: collection.json만 변경")
    if modified is not None:
        check(sorted(ch["modified"]) == sorted(modified), f"{label}: 수정 {ch['modified']}")
    if added is not None:
        check(sorted(ch["added"]) == sorted(added) if isinstance(added, list) else len(ch["added"]) == added, f"{label}: 추가 파일 {len(ch['added'])}개")
    if deleted is not None:
        check(sorted(ch["deleted"]) == sorted(deleted) if isinstance(deleted, list) else len(ch["deleted"]) == deleted, f"{label}: 삭제 파일 {len(ch['deleted'])}개")
    return c


def settle(page):
    page.wait_for_selector("#saving", state="hidden", timeout=30000)
    page.wait_for_selector("#modal", state="detached", timeout=30000)


def reset_log(page):
    gh(page, "window.__gh.resetLog()")


def save_and_wait(page, selector="#save"):
    page.click(selector)
    settle(page)


def add_kit(page, name, *, grade="HG", photos=None, price=None, shop=None, status=None, series=None):
    page.click('[data-act=add]')
    page.fill("#f-name", name)
    page.select_option("#f-grade", grade)
    if status:
        page.select_option("#k-status", status)
    if price:
        page.fill("#f-price", str(price))
    if shop:
        page.fill("#f-shop", shop)
    if series:
        page.fill("#f-series", series)
    if photos:
        page.set_input_files("#f-photo", photos)
        poll(page, f"document.querySelectorAll('.pm-item').length=={len(photos)}", timeout=60000)


def open_kit(page, name):
    page.click(f'.card[aria-label^="{name}"]')
    page.wait_for_selector("#modal")


def webp_info(page, path):
    return page.evaluate("""async (p) => { const b = window.__gh.fileBytes(p); if (!b) return null;
      const bmp = await createImageBitmap(new Blob([b], {type:'image/webp'}));
      return {w: bmp.width, h: bmp.height, riff: String.fromCharCode(...b.slice(0,4)), webp: String.fromCharCode(...b.slice(8,12)), size: b.length}; }""", path)


def shot(page, name, full=False):
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.screenshot(path=str(OUT / name), full_page=full)


def no_overflow(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


# =====================================================================
def scenarios(browser, base):
    ctx = new_context(browser, token=False)
    page = open_page(ctx, base)

    section("1. 방문자 (토큰 없음)")
    check(page.locator(".banner").count() == 1 and "예시" in page.inner_text(".banner"), "예시 데이터 배너")
    check(page.locator(".card").count() == 4, "예시 카드 4장(보유 탭)")
    check(page.locator("[data-act=add]").count() == 0 and page.locator("[data-act=import]").count() == 0, "소유자 버튼 없음")
    check(page.locator(".linkbtn").count() == 1, "푸터 '소유자 설정' 링크")
    check(page.title() == "프라 격납고", "title")

    section("2. 토큰 연결 → 소유자 모드")
    page.click(".linkbtn")
    page.wait_for_selector("#s-token")
    check(page.get_attribute("#s-token", "type") == "password", "토큰 입력칸은 password")
    page.fill("#s-token", TOKEN)
    page.click("#s-connect")
    page.wait_for_selector("[data-act=add]", timeout=15000)
    check(True, "연결 후 '+ 추가' 버튼 노출")
    check(TOKEN not in page.content(), "화면(DOM)에 토큰 값 없음")
    page.click("[data-act=settings]")
    page.wait_for_selector("#s-token")
    check(page.input_value("#s-token") == "" and TOKEN not in page.inner_text("#modal"), "설정을 다시 열어도 토큰 값 비노출")
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal", state="detached")

    section("3. 추가 (사진 없음) → 1커밋")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "B 건담 바르바토스", grade="HG", price=17000, shop="테스트샵")
    save_and_wait(page)
    one_commit(page, "추가", n0, msg_re=r"^collection: 추가 B 건담 바르바토스$", collection_only=True)
    check(page.locator(".banner").count() == 0 and page.locator('.card[aria-label^="B 건담"]').count() == 1, "목록에 새 프라 표시(예시 배너 사라짐)")
    check("1~2분" in page.inner_text("#toast"), "저장 토스트에 사이트 반영 지연(1~2분) 안내")

    section("4. 추가 (사진 2장) → 한 커밋에 collection.json + 사진 4파일")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "A 건담 에어리얼", grade="HG", photos=[png_file("big.png", 2400, 1800, 1), png_file("small.png", 800, 600, 2)])
    save_and_wait(page)
    c = one_commit(page, "사진 2장 추가", n0, msg_re=r"^collection: 추가 A 건담 에어리얼 · 사진 \+2$", modified=[COLL], added=4, deleted=[])
    kitA = next(k for k in collection(page)["kits"] if k["name"].startswith("A "))
    check(len(kitA["photos"]) == 2 and kitA["cover"] is None and kitA["catalogId"] is None, "photos 2개, cover null, catalogId null")
    paths = sorted(c["changes"]["added"]) if c else []
    check(all(re.fullmatch(rf"docs/photos/{kitA['id']}/p[0-9a-z]+(_t)?\.webp", p) for p in paths) and len(paths) == 4, "경로 docs/photos/<kitId>/<photoId>.webp(+_t)")
    p1, p2 = kitA["photos"]
    i1f, i1t, i2f, i2t = (webp_info(page, "docs/" + x) for x in (p1["src"], p1["thumb"], p2["src"], p2["thumb"]))
    check(i1f and (i1f["w"], i1f["h"]) == (1600, 1200), f"큰 사진 2400x1800 → 긴 변 1600 ({i1f and (i1f['w'], i1f['h'])})")
    check(i1t and (i1t["w"], i1t["h"]) == (480, 360), f"큰 사진 썸네일 480 ({i1t and (i1t['w'], i1t['h'])})")
    check(i2f and (i2f["w"], i2f["h"]) == (800, 600), f"작은 사진은 키우지 않음 ({i2f and (i2f['w'], i2f['h'])})")
    check(i2t and (i2t["w"], i2t["h"]) == (480, 360), "작은 사진 썸네일 480")
    check(all(i and i["riff"] == "RIFF" and i["webp"] == "WEBP" for i in (i1f, i1t, i2f, i2t)), "저장된 파일은 RIFF…WEBP")
    check(page.locator('.card[aria-label^="A 건담"] .ph img').count() == 1, "카드에 대표 썸네일(img)")

    section("5. 수정 → 1커밋 (collection.json만)")
    reset_log(page)
    n0 = len(history(page))
    open_kit(page, "B 건담")
    page.click("#edit")
    page.fill("#f-name", "B2 건담 바르바토스")
    save_and_wait(page)
    one_commit(page, "수정", n0, msg_re=r"^collection: 수정 B2 건담 바르바토스$", collection_only=True)

    section("6. 사진 순서 변경 + 대표 지정 → 1커밋 (파일 변화 없음)")
    reset_log(page)
    n0 = len(history(page))
    open_kit(page, "A 건담")
    page.click("#edit")
    page.wait_for_selector(".pm-item")
    second_id = page.locator(".pm-item").nth(1).get_attribute("data-pid")
    page.locator(".pm-item").nth(1).locator('[data-pm=cover]').click()
    page.locator(".pm-item").nth(1).locator('[data-pm=up]').click()
    check(page.locator(".pm-item").nth(0).get_attribute("data-pid") == second_id, "↑로 순서가 바뀜")
    check(page.locator(".pm-item").nth(0).locator(".pm-badge").count() == 1, "대표 배지가 붙음")
    save_and_wait(page)
    one_commit(page, "순서·대표", n0, msg_re=r"^collection: 수정 A 건담 에어리얼$", collection_only=True)
    kitA = next(k for k in collection(page)["kits"] if k["name"].startswith("A "))
    check(kitA["photos"][0]["id"] == second_id and kitA["cover"] == "my:" + second_id, f"photos 순서 변경, cover=my:{second_id}")

    section("7. 대표 사진 삭제 → 파일 2개 삭제 + cover 초기화 (한 커밋)")
    reset_log(page)
    n0 = len(history(page))
    open_kit(page, "A 건담")
    page.click("#edit")
    page.wait_for_selector(".pm-item")
    gone = kitA["photos"][0]
    page.locator(".pm-item").nth(0).locator('[data-pm=del]').click()
    save_and_wait(page)
    one_commit(page, "사진 삭제", n0, msg_re=r"^collection: 수정 A 건담 에어리얼 · 사진 -1$", modified=[COLL], added=[],
               deleted=["docs/" + gone["src"], "docs/" + gone["thumb"]])
    kitA = next(k for k in collection(page)["kits"] if k["name"].startswith("A "))
    check(len(kitA["photos"]) == 1 and kitA["cover"] is None, "photos 1개, cover null")

    section("8. 프라 삭제 → 남은 사진 파일도 같은 커밋에서 삭제")
    reset_log(page)
    n0 = len(history(page))
    left = kitA["photos"][0]
    open_kit(page, "A 건담")
    page.click("#del")
    page.click("#del")
    settle(page)
    one_commit(page, "프라 삭제", n0, msg_re=r"^collection: 삭제 A 건담 에어리얼 · 사진 -1$", modified=[COLL], added=[],
               deleted=["docs/" + left["src"], "docs/" + left["thumb"]])
    check(not any(f.startswith(f"docs/photos/{kitA['id']}/") for f in gh(page, "window.__gh.listFiles()")), "저장소에 그 프라의 사진 폴더가 남지 않음")

    section("9. 일괄 수정 / 일괄 삭제 → 각 1커밋")
    add_kit(page, "C 건담 데스티니", grade="MG")
    save_and_wait(page)
    reset_log(page)
    n0 = len(history(page))
    page.click("[data-act=select]")
    page.click('.card[aria-label^="B2"]')
    page.click('.card[aria-label^="C 건담"]')
    page.click("[data-s=edit]")
    page.select_option("#b-status", "built")
    page.fill("#b-shop", "일괄샵")
    save_and_wait(page, "#b-apply")
    one_commit(page, "일괄 수정", n0, msg_re=r"^collection: 2개 일괄 수정$", collection_only=True)
    ks = {k["name"][:2]: k for k in collection(page)["kits"]}
    check(ks["B2"]["status"] == "built" and ks["C "]["status"] == "built" and ks["C "]["shop"] == "일괄샵" and ks["B2"]["shop"] == "테스트샵", "상태 일괄 변경, 비어 있는 구매처에만 채움")
    reset_log(page)
    n0 = len(history(page))
    page.click("[data-act=select]")
    page.click('.card[aria-label^="C 건담"]')
    page.click("[data-s=edit]")
    page.click("#b-del")
    page.click("#b-del")
    settle(page)
    one_commit(page, "일괄 삭제", n0, msg_re=r"^collection: 1개 일괄 삭제$", collection_only=True)
    check([k["name"][:2] for k in collection(page)["kits"]] == ["B2"], "C만 삭제됨")

    section("9b. 위시리스트 추가 → '샀어요 · 보유로 옮기기' → 각 1커밋")
    page.click("[data-tab=wish]")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "위시 건담 칼리번", grade="HG", price=22000)
    save_and_wait(page)
    one_commit(page, "위시 추가", n0, msg_re=r"^collection: 추가 위시 건담 칼리번$", collection_only=True)
    check(next(k for k in collection(page)["kits"] if k["name"].startswith("위시"))["list"] == "wish", "list=wish로 저장")
    reset_log(page)
    n0 = len(history(page))
    open_kit(page, "위시 건담")
    page.click("#move")
    save_and_wait(page)
    one_commit(page, "보유로 이동", n0, msg_re=r"^collection: 보유로 이동 위시 건담 칼리번$", collection_only=True)
    check(next(k for k in collection(page)["kits"] if k["name"].startswith("위시"))["list"] == "own", "list=own으로 이동")
    page.click("[data-tab=own]")

    section("10. 가져오기: CSV 붙여넣기 / v2 JSON(사진 data URI) / 엑셀 백업")
    reset_log(page)
    n0 = len(history(page))
    page.click("[data-act=import]")
    page.fill("#i-text", "이름\t등급\t상태\n건담 데스티니\tHG\t완성\nB2 건담 바르바토스\tHG\t\n프리덤 건담\tMG\t미개봉")
    page.wait_for_selector("#i-skip")
    check(page.inner_text("#i-go") == "2개 가져오기", "중복 1개는 건너뛰기 기본값 → 2개")
    save_and_wait(page, "#i-go")
    one_commit(page, "CSV 가져오기", n0, msg_re=r"^collection: 2개 가져오기$", collection_only=True)
    reset_log(page)
    n0 = len(history(page))
    uri = "data:image/png;base64," + base64.b64encode(make_png(64, 48, 3)).decode()
    v2 = json.dumps({"settings": {"name": "v2"}, "kits": [{"id": "kold", "name": "v2 건담", "grade": "RG", "photo": uri, "tags": ["옛"]}]}, ensure_ascii=False)
    page.click("[data-act=import]")
    page.fill("#i-text", v2)
    poll(page, "document.querySelector('#i-go') && !document.querySelector('#i-go').disabled")
    check("사진 1장" in page.inner_text("#i-prev"), "미리보기에 사진 1장 안내")
    save_and_wait(page, "#i-go")
    c = one_commit(page, "v2 JSON 가져오기", n0, msg_re=r"^collection: 1개 가져오기 · 사진 \+1$", modified=[COLL], added=2, deleted=[])
    kv = next(k for k in collection(page)["kits"] if k["name"] == "v2 건담")
    check(len(kv["photos"]) == 1 and "photo" not in kv and kv["id"] != "kold" and webp_info(page, "docs/" + kv["photos"][0]["src"])["riff"] == "RIFF", "data URI → WebP 파일 photos[0], 새 id")
    try:
        with page.expect_download(timeout=20000) as dl:
            page.click("[data-act=export]")
        p = Path(dl.value.path())
        check(dl.value.suggested_filename.startswith("프라격납고_") and dl.value.suggested_filename.endswith(".xlsx") and p.stat().st_size > 1000, f"엑셀 백업 일반 다운로드 ({dl.value.suggested_filename}, {p.stat().st_size}B)")
    except PWTimeout:
        print("  - 엑셀 백업: cdnjs를 못 불러와 건너뜀 (오프라인?)")

    section("11. 설정 저장 → 1커밋")
    reset_log(page)
    n0 = len(history(page))
    page.click("[data-act=settings]")
    page.fill("#s-name", "내 격납고")
    page.uncheck("#s-hide")
    save_and_wait(page, "#s-save")
    one_commit(page, "설정", n0, msg_re=r"^collection: 설정$", collection_only=True)
    check(page.inner_text("h1") == "내 격납고" and collection(page)["settings"]["hidePurchase"] is False, "이름·구매정보 표시 설정 반영")
    page.click("[data-act=settings]")
    page.fill("#s-name", "프라 격납고")
    page.check("#s-hide")
    save_and_wait(page, "#s-save")

    section("12a. 다른 파일만 바뀜(크롤러 커밋) → 대화상자 없이 1커밋, 그 파일 보존")
    adv = gh(page, f"window.__gh.advanceHead({{files:{{'{FEED}':'{{\"n\":2}}','docs/data/catalog-gunpla.json':'[]'}}, message:'data: crawl'}})")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "D 건담 루브리스")
    save_and_wait(page)
    check(page.locator("#alert").count() == 0, "충돌 대화상자 없음")
    c = one_commit(page, "크롤러 커밋 뒤 저장", n0, msg_re=r"^collection: 추가 D 건담 루브리스$", collection_only=True)
    check(c and c["parents"] == [adv], "부모 = 크롤러가 전진시킨 head")
    check(gh(page, f"window.__gh.fileText('{FEED}')") == '{"n":2}' and gh(page, "window.__gh.fileText('docs/data/catalog-gunpla.json')") == "[]", "크롤러 파일 변경 보존")
    section("12a'. GET ref~PATCH 사이에 다른 파일 커밋 → 422 → 조용히 재시도")
    gh(page, "window.__gh.hooks.beforePatchRef.push(api => api.advanceHead({files:{'docs/data/meta.json':'{\"at\":1}'}, message:'data: crawl 2'}))")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "E 건담 캘리번")
    save_and_wait(page)
    check(page.locator("#alert").count() == 0, "대화상자 없음")
    h = history(page)
    check(len(h) == n0 + 1, f"head 위에 내 커밋 1개만 ({n0}→{len(h)})")
    w = write_calls(page)
    check(w.count("PATCH /git/refs/heads/main") == 2, "ref PATCH 2회(첫 시도 422 → 재시도)")
    check(gh(page, "window.__gh.fileText('docs/data/meta.json')") == '{"at":1}', "끼어든 파일 변경 보존")

    section("12b. collection.json이 바뀜 → 대화상자: 취소 / 다시 적용")
    remote_kit = "{id:'kremote',name:'원격에서 추가한 프라',grade:'HG',list:'own'}"
    gh(page, f"""(() => {{ const t = JSON.parse(window.__gh.fileText('{COLL}')); t.kits.push({remote_kit}); window.__gh.advanceHead({{files:{{'{COLL}': JSON.stringify(t)}}, message:'다른 기기에서 추가'}}); }})()""")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "F 건담 헤어리")
    page.click("#save")
    page.wait_for_selector("#alert", timeout=15000)
    check("먼저 저장된 변경" in page.inner_text("#alert"), "충돌 안내 대화상자")
    page.click('#alert .btn[data-i="0"]')
    page.wait_for_selector("#alert", state="detached")
    check(len(history(page)) == n0, "취소하면 커밋 0")
    check(page.locator('.card[aria-label^="원격에서 추가한 프라"]').count() == 1, "화면이 최신(원격 변경 포함)으로 갱신됨")
    page.locator("#modal [data-close]").first.click()
    page.wait_for_selector("#modal", state="detached")
    # 다시 원격이 앞서간 상태에서 '다시 적용'
    adv = gh(page, f"""(() => {{ const t = JSON.parse(window.__gh.fileText('{COLL}')); t.kits.push({{id:'kremote2',name:'원격 두번째 프라',grade:'RG',list:'own'}}); return window.__gh.advanceHead({{files:{{'{COLL}': JSON.stringify(t)}}, message:'다른 기기에서 또 추가'}}); }})()""")
    reset_log(page)
    n0 = len(history(page))
    add_kit(page, "G 건담 에피온")
    page.click("#save")
    page.wait_for_selector("#alert", timeout=15000)
    page.click("#alert .btn.primary")
    settle(page)
    c = one_commit(page, "다시 적용", n0, msg_re=r"^collection: 추가 G 건담 에피온$", collection_only=True)
    names = [k["name"] for k in collection(page)["kits"]]
    check("원격에서 추가한 프라" in names and "원격 두번째 프라" in names and "G 건담 에피온" in names and "F 건담 헤어리" not in names, "원격 변경 + 내 변경 모두 반영")
    check(c and c["parents"] == [adv], "부모 = 최신 head")

    section("14. 전체 점검")
    all_log = gh(page, "JSON.stringify(window.__gh.log)")
    check(TOKEN not in all_log, "요청 URL·본문에 토큰 없음 (헤더에만)")
    check(gh(page, "window.__gh.log.every(e => e.auth)"), "모든 요청에 Authorization 헤더")
    check(TOKEN not in page.content(), "화면에 토큰 없음")
    check(no_overflow(page), "가로 스크롤 없음(1280)")

    check(not ctx.errors, f"1~14 구간 콘솔 에러 없음 {ctx.errors[:2] if ctx.errors else ''}")
    check(not ctx.leaked, "실제 api.github.com 요청이 새지 않음")
    snap = gh(page, "window.__gh.snapshot()")
    ctx.close()

    section("15. 새로고침(새 페이지) → API에서 읽기 + 배포 후 방문자 화면")
    ctx2 = new_context(browser, snapshot=snap)
    serve_deployed_from_snapshot(ctx2, snap)
    owner = open_page(ctx2, base)
    check(owner.locator(".banner").count() == 0 and owner.locator(".card").count() >= 4, f"새로고침 후 소유자 목록 (카드 {owner.locator('.card').count()}장)")
    poll(owner, "(() => { const i = document.querySelector('.card[aria-label^=\"v2 건담\"] .ph img'); return i && i.complete && i.naturalWidth > 0 })()", timeout=15000)
    check(True, "새로고침 후 사진 썸네일이 (배포된 photos/ 경로로) 보임")
    check(all(owner.evaluate("[...document.images].map(i => i.referrerPolicy === 'no-referrer')")), "모든 <img>에 referrerpolicy=no-referrer")
    visitor_ctx = new_context(browser, token=False)
    visitor_ctx.add_init_script(script="try{localStorage.removeItem('plamo-token')}catch(e){}")
    serve_deployed_from_snapshot(visitor_ctx, snap)
    v = open_page(visitor_ctx, base)
    check(v.locator("[data-act=add]").count() == 0, "방문자: 소유자 버튼 없음")
    check(v.locator(".stat .k", has_text="총 구매액").count() == 0, "방문자: 구매정보(총 구매액) 숨김")
    v.click('.card[aria-label^="v2 건담"]')
    v.wait_for_selector("#modal")
    check("구매처" not in v.inner_text("#modal") and "가격" not in v.inner_text("#modal"), "방문자 상세: 구매일·구매처·가격 숨김")
    check(v.locator("#d-main").count() == 1, "방문자 상세에 사진")
    for c_ in (ctx2, visitor_ctx):
        check(not c_.errors, f"콘솔 에러 없음 {c_.errors[:2] if c_.errors else ''}")
        check(not c_.leaked, "실제 api.github.com 요청이 새지 않음")
    ctx2.close()
    visitor_ctx.close()
    return snap


def serve_deployed_from_snapshot(ctx, snap):
    """snapshot(fake 상태)에서 방문자가 읽을 collection.json·photos 를 만들어 라우트로 서빙."""
    blobs = {k: base64.b64decode(v) for k, v in snap["blobs"].items()}
    head = snap["refs"]["main"]
    files = {}
    # tree 파일 맵(path→blob sha)은 snapshot.trees 에 있다
    tree = snap["trees"][snap["commits"][head]["tree"]]["files"]
    for p, sha in tree.items():
        files[p] = blobs[sha]

    def data_route(route):
        route.fulfill(status=200, body=files[COLL], content_type="application/json")

    def photo_route(route):
        key = "docs/" + re.sub(r"^https?://[^/]+/", "", route.request.url).split("?")[0]
        if key in files:
            route.fulfill(status=200, body=files[key], content_type="image/webp")
        else:
            route.fulfill(status=404, body="")

    ctx.route(re.compile(r".*/data/collection\.json.*"), data_route)
    ctx.route(re.compile(r".*/photos/.*"), photo_route)


def owner_check_fails(browser, base):
    """소유자 판정 단계 실패: 계정에 쓰기 권한 없음 / 토큰 거부(401)."""
    for label, fake, want in (("계정 쓰기 권한 없음", {"accountPush": False}, "쓸 권한"), ("토큰 거부(401)", {"token": "other-token"}, "토큰")):
        section(f"2b. 소유자 판정 실패: {label}")
        ctx = new_context(browser, fake=fake)
        page = ctx.new_page()
        watch(ctx, page)
        page.goto(base)
        page.wait_for_selector(".card", timeout=15000)
        page.wait_for_selector("#toast:not([hidden])", timeout=15000)
        check(want in page.inner_text("#toast"), f"안내 토스트: {page.inner_text('#toast')}")
        check(page.locator("[data-act=add]").count() == 0 and page.locator(".linkbtn").count() == 1, "방문자 모드로 열림(소유자 버튼 없음)")
        check(TOKEN not in page.content() and TOKEN not in page.inner_text("#toast"), "화면·토스트에 토큰 값 없음")
        check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:2] if ctx.errors else ''}")
        ctx.close()


def denied(browser, base):
    for status, ratelimit in ((403, False), (404, False), (403, True)):
        label = f"쓰기 {status}" + (" + rate limit" if ratelimit else "")
        section(f"13. 권한 오류: {label}")
        ctx = new_context(browser, fake={"deny": {"status": status, "ratelimit": ratelimit}})
        page = open_page(ctx, base)
        page.wait_for_selector("[data-act=add]", timeout=15000)
        add_kit(page, "권한 없는 프라")
        page.click("#save")
        if ratelimit:
            page.wait_for_selector("#toast:not([hidden])", timeout=15000)
            check("한도" in page.inner_text("#toast"), "요청 한도 안내(권한 오류와 구분)")
        else:
            page.wait_for_selector("#alert", timeout=15000)
            msg = page.inner_text("#a-msg")
            check("Contents: Read and write" in msg and "확인해 주세요" in msg, f"권한 안내 문구: {msg}")
            check(TOKEN not in msg, "안내에 토큰 값 없음")
            page.click('#alert .btn[data-i="0"]')
        check(len(history(page)) == 0, "커밋 0")
        check(page.locator("#modal").count() == 1 and page.input_value("#f-name") == "권한 없는 프라", "폼 내용이 그대로 남음(입력 손실 없음)")
        page.locator("#modal [data-close]").first.click()
        page.wait_for_selector("#modal", state="detached")
        check(page.locator(".banner").count() == 1 and page.locator('.card[aria-label^="권한 없는"]').count() == 0, "낙관적으로 목록에 추가되지 않음")
        check(TOKEN not in page.content() and TOKEN not in gh(page, "JSON.stringify(window.__gh.log)"), "화면·요청 로그에 토큰 값 없음")
        check(not ctx.errors, f"콘솔 에러 없음 {ctx.errors[:2] if ctx.errors else ''}")
        ctx.close()


def screens(browser, base, snap_seed):
    """색상 모드·폭별 스크린샷. 먼저 사진 3장짜리 프라가 있는 상태를 UI로 만든다."""
    section("스크린샷 준비: 사진 3장 프라 추가")
    ctx = new_context(browser)
    page = open_page(ctx, base)
    page.wait_for_selector("[data-act=add]", timeout=15000)
    add_kit(page, "HG 건담 에어리얼", grade="HG", series="기동전사 건담 수성의 마녀", price=17000, shop="건담베이스", status="built",
            photos=[png_file("a.png", 2400, 1800, 1), png_file("b.png", 1000, 1000, 2), png_file("c.png", 800, 600, 3)])
    save_and_wait(page)
    add_kit(page, "RG 뉴건담", grade="RG", series="역습의 샤아", price=45000, status="building", photos=[png_file("d.png", 1200, 900, 4)])
    save_and_wait(page)
    add_kit(page, "MG RX-78-2 건담 Ver.3.0", grade="MG", series="기동전사 건담")
    save_and_wait(page)
    snap = gh(page, "window.__gh.snapshot()")
    ctx.close()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    for w, h, tag in ((1280, 900, "desktop"), (400, 800, "mobile")):
        for scheme in ("light", "dark"):
            section(f"스크린샷 {tag}-{scheme}")
            ctx = new_context(browser, w=w, h=h, scheme=scheme, snapshot=snap)
            serve_deployed_from_snapshot(ctx, snap)
            page = open_page(ctx, base)
            page.wait_for_selector("[data-act=add]", timeout=15000)
            poll(page, "[...document.querySelectorAll('.card .ph img')].every(i => i.complete && i.naturalWidth > 0)", timeout=15000)
            check(no_overflow(page), f"{tag}-{scheme} 목록: 가로 스크롤 없음")
            shot(page, f"{tag}-{scheme}-1-list-owner.png", full=True)
            open_kit(page, "HG 건담")
            poll(page, "(() => { const i = document.querySelector('#d-main'); return i && i.complete && i.naturalWidth > 0 })()", timeout=15000)
            check(no_overflow(page), f"{tag}-{scheme} 상세: 가로 스크롤 없음")
            shot(page, f"{tag}-{scheme}-2-detail.png")
            page.locator(".th").nth(1).click()
            check(page.locator("#d-count").inner_text() == "2 / 3", "썸네일 클릭으로 큰 사진 전환 (2 / 3)")
            page.click("#edit")
            page.wait_for_selector(".pm-item")
            page.locator("#pm").scroll_into_view_if_needed()
            check(page.locator(".pm-item").count() == 3, "폼에 사진 3장 관리 UI")
            check(no_overflow(page), f"{tag}-{scheme} 폼: 가로 스크롤 없음")
            shot(page, f"{tag}-{scheme}-3-form-photos.png")
            page.keyboard.press("Escape")
            page.click("[data-act=settings]")
            page.wait_for_selector("#s-token")
            shot(page, f"{tag}-{scheme}-4-settings.png")
            page.keyboard.press("Escape")
            ctx.close()
            vctx = new_context(browser, w=w, h=h, scheme=scheme, token=False)
            vctx.add_init_script(script="try{localStorage.removeItem('plamo-token')}catch(e){}")
            serve_deployed_from_snapshot(vctx, snap)
            vpage = open_page(vctx, base)
            poll(vpage, "[...document.querySelectorAll('.card .ph img')].every(i => i.complete && i.naturalWidth > 0)", timeout=15000)
            check(no_overflow(vpage), f"{tag}-{scheme} 방문자: 가로 스크롤 없음")
            shot(vpage, f"{tag}-{scheme}-5-list-visitor.png", full=True)
            check(not vctx.errors and not ctx.errors, f"{tag}-{scheme} 콘솔 에러 없음 {(vctx.errors + ctx.errors)[:2]}")
            vctx.close()
    print(f"\n스크린샷: {OUT}")


def main():
    srv, base = start_server()
    print("서버", base)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            snap = scenarios(browser, base)
            owner_check_fails(browser, base)
            denied(browser, base)
            screens(browser, base, snap)
        finally:
            browser.close()
            srv.shutdown()
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} 통과")
    for m in bad:
        print("  ✗", m)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
