"""run() 안의 joyhobby 단계 — 가짜 조이하비(합성 HTML)로 임시 폴더에서. 네트워크·디스코드·Claude 호출 없음."""
import json
from datetime import datetime, timedelta

import pytest

from conftest import JOY_BOARD, JOY_POST, JOY_ROBOTS, joy_board_html, joy_post_html, make_client
from crawler import config
from crawler.catalog import Catalog
from crawler.pipeline import Options, run
from crawler.sources.joyhobby import board_url
from schema_check import check_dir

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=config.KST)
NOW_ISO = "2026-10-06T09:00:00+09:00"
IMG = "https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"
RED = "[HGGQX04] 1/144 붉은 건담(RED GUNDAM) - 기동전사 건담 지쿠악스(프라모델)"
PINNED = [("1", "26년 10월 무이자할부 안내"), ("2", "조이하비 불량/반품/AS 규정")]
BUG_PAGE = "<html><body>Microsoft SQL Server Native Client 11.0 오류 '80040e57' 데이터 형식 smallint에 산술 오버플로 오류가 발생했습니다.</body></html>"


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    monkeypatch.setattr(config, "JOY_BOARD_PAGE_SIZE", 3)           # 합성 게시판은 쪽당 3개


def red_item():
    return {"id": "bh-01_1", "url": "https://bandai-hobby.net/item/01_1/", "line": "gunpla", "brandKeys": ["hg"], "grade": "HG", "scale": "1/144",
            "seriesKey": None, "series": None, "nameJa": "HG 1/144 レッドガンダム", "nameKo": "HG 1/144 붉은건담", "priceJpy": 2750,
            "channel": "general", "pbUrl": None, "release": {"month": "2026-06"}, "kr": [], "images": [IMG],
            "firstSeen": NOW_ISO, "updated": NOW_ISO, "detailAt": NOW_ISO}


def seed(tmp_path, *items):
    cat = Catalog()
    for it in items or (red_item(),):
        cat.items[it["id"]] = it
    cat.save(tmp_path, NOW_ISO)


class Joy:
    """합성 조이하비: 3쪽짜리 게시판 + 글 본문."""

    def __init__(self):
        self.pages = {
            1: [("510", "2026-10-05", "10/6(화) 판매예정 반다이 제품리스트 안내"), ("509", "2026-10-04", "휴무 안내"), ("508", "2026-10-03", "프라모델 신제품 입고안내")],
            2: [("507", "2026-09-26", "9/27(토) 반다이 재입고 리스트"), ("506", "2026-09-20", "굿즈 이벤트 안내"), ("505", "2026-09-10", "9/12 반다이 입고예정 리스트")],
            3: [("504", "2026-08-01", "8/2 반다이 제품리스트"), ("503", "2026-07-30", "공지")],
        }
        self.posts = {
            "510": ("10/6(화) 판매예정 반다이 제품리스트 안내", "안녕하세요", [("BD5000001", RED, "27500원"), ("BD5000002", "[RG] 1/144 없는 기체(NONE)(프라모델)", "30,000원")]),
            "508": ("프라모델 신제품 입고안내", "입고", [("ANN26713", "브리짓", "72000원")]),                      # 반다이가 아님 → BD 행 없음
            "507": ("9/27(토) 반다이 재입고 리스트", "반다이 재입고 안내", [("BD5000003", "[HG] 1/144 다른 기체(OTHER)", "20000원")]),
            "505": ("9/12 반다이 입고예정 리스트", "소개", [("BD5000004", "[MG] 1/100 또 다른 기체", "50000원")]),
            "504": ("8/2 반다이 제품리스트", "소개", [("BD5000005", "[HG] 1/144 오래된 기체", "10000원")]),
        }
        self.fail_board: set[int] = set()
        self.fail_post: dict[str, int] = {}
        self.broken_post: set[str] = set()                # 사이트 버그(조회수 overflow)로 영구히 500인 글

    def routes(self):
        r = {"https://www.joyhobby.co.kr/robots.txt": JOY_ROBOTS}
        for page, rows in self.pages.items():
            r[board_url(page)] = (lambda u, page=page, rows=rows: (500, "boom") if page in self.fail_board else joy_board_html(rows, PINNED))
        r[board_url(4)] = lambda u: joy_board_html([self.pages[3][-1]], PINNED)         # 끝을 넘으면 마지막 행만 되풀이 (요청하면 안 된다)
        for pid, (title, intro, items) in self.posts.items():
            r[JOY_POST.format(id=pid)] = (lambda u, pid=pid, title=title, intro=intro, items=items:
                                          (500, BUG_PAGE) if pid in self.broken_post else
                                          (self.fail_post[pid], "boom") if pid in self.fail_post else joy_post_html(title, intro, items))
        return r


def go(joy, tmp_path, *, now=NOW, bootstrap=True, joy_pages=None, only=("joyhobby",), post=None, report=False, **kw):
    client, sess, _ = make_client(joy.routes())
    lines: list[str] = []
    opts = Options(only=set(only), bootstrap=bootstrap, joy_pages=joy_pages, data_dir=tmp_path, report_dir=tmp_path / "out" if report else None)
    res = run(opts, client, now=now, out=lines.append, post=post or (lambda *a, **k: None), **kw)
    return res, client, sess, lines


def read(tmp_path, name):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


def urls(sess):
    return [c["url"] for c in sess.calls]


# ---------------------------------------------------------------- 과거 글 채우기 한 번에
def test_backfill_walks_to_the_last_page_and_never_requests_beyond_it(tmp_path):
    seed(tmp_path)
    joy = Joy()
    posted = []
    res, client, sess, lines = go(joy, tmp_path, joy_pages=25, post=lambda *a, **k: posted.append(k), report=True)
    u = urls(sess)
    assert [x for x in u if "board_list" in x] == [board_url(1), board_url(2), board_url(3)]          # 마지막 쪽(3)에서 멈춘다. 4쪽은 요청하지 않음
    assert sorted(x.rsplit("=", 1)[1] for x in u if "board_view" in x) == ["504", "505", "507", "508", "510"]   # 후보 제목만 연다 (509·506·503은 열지 않음)
    assert client.detail_limit is None and posted == []                                                # --bootstrap 중에는 알림 없음

    arr = read(tmp_path, config.KR_ARRIVALS_FILE)
    assert {p: v["state"] for p, v in arr["posts"].items()} == {"510": "done", "508": "no-bd", "507": "done", "505": "done", "504": "done"}
    assert len(arr["rows"]) == 5 and {r["code"] for r in arr["rows"]} == {f"BD500000{i}" for i in range(1, 6)}
    assert arr["posts"]["510"]["sale"] == "2026-10-06" and arr["posts"]["510"]["date"] == "2026-10-05"
    assert list(arr["codeMap"]) == ["BD5000001"] and arr["codeMap"]["BD5000001"]["method"] == "fuzzy"        # 카탈로그에 있는 것만 연결

    cat = read(tmp_path, "catalog-gunpla.json")["items"][0]
    assert [(k["post"], k["date"], k["type"]) for k in cat["kr"]] == [("510", "2026-10-06", "restock")]      # 발매 2026-06 → 60일 규칙
    assert cat["nameKo"] == "HG 1/144 붉은 건담" and cat["nameKoAi"] == "HG 1/144 붉은건담" and cat["nameKoSource"] == "joyhobby"

    feed = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}
    assert set(feed) == {"jh-510-BD5000001", "jh-510-BD5000002", "jh-507-BD5000003", "jh-505-BD5000004"}      # 30일 이내 글만 (8/1 글 제외)
    assert feed["jh-510-BD5000001"]["catalogId"] == "bh-01_1" and feed["jh-510-BD5000001"]["image"] == IMG
    assert feed["jh-510-BD5000002"]["catalogId"] is None and feed["jh-510-BD5000002"]["type"] == "kr-new"    # 연결 안 된 항목도 피드에
    assert feed["jh-507-BD5000003"]["type"] == "kr-restock"                                                    # 발매일을 모르고 글에 "재입고"

    meta = read(tmp_path, "meta.json")
    assert meta["crawl"]["joyNext"] == 4 and meta["crawl"]["joyDone"] is True and meta["crawl"]["joyOldest"] == "2026-07-30"
    assert meta["since"] == "2026-07-30"                                                                       # 조이하비 기록 시작일
    s = meta["sources"]["joyhobby"]
    assert s["ok"] is True and s["error"] is None and s["posts"] == 5 and s["rows"] == 5 and s["linkedCodes"] == 1 and s["krAdded"] == 1
    assert check_dir(tmp_path) == []

    text = "\n".join(lines)
    assert "후보였지만 BD 행 없음 1건" in text and "508 2026-10-03 프라모델 신제품 입고안내" in text
    assert "codeMap 신규 연결 1건" in text and "BD5000001" in text
    report = json.loads((tmp_path / "out" / "joy-report.json").read_text(encoding="utf-8"))
    assert report["noBdPosts"][0]["post"] == "508" and report["link"]["newLinks"][0]["code"] == "BD5000001"
    links = (tmp_path / "out" / "joy-links.txt").read_text(encoding="utf-8").splitlines()
    assert links[0].startswith("점수 | 차이") and len(links) == 2 and "BD5000001" in links[1] and "HG 1/144 붉은건담 → HG 1/144 붉은 건담" in links[1]
    _, _, _, lines2 = go(joy, tmp_path, bootstrap=False, report=True)                                         # 아무 일도 없던 실행은 이전 보고서를 덮어쓰지 않는다
    assert json.loads((tmp_path / "out" / "joy-report.json").read_text(encoding="utf-8")) == report
    assert (tmp_path / "out" / "joy-links.txt").exists()


# ---------------------------------------------------------------- 쪽 수 제한과 이어하기
def test_backfill_resumes_from_the_saved_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOY_DAILY_PAGES", 1)
    seed(tmp_path)
    joy = Joy()
    _, _, sess1, _ = go(joy, tmp_path, joy_pages=1)
    assert [x for x in urls(sess1) if "board_list" in x] == [board_url(1), board_url(2)]                        # 매일 1쪽 + 과거 1쪽
    assert sorted(x.rsplit("=", 1)[1] for x in urls(sess1) if "board_view" in x) == ["505", "507", "508", "510"]
    c1 = read(tmp_path, "meta.json")["crawl"]
    assert c1["joyNext"] == 3 and not c1.get("joyDone") and c1["joyOldest"] == "2026-09-10"
    assert read(tmp_path, "meta.json")["since"] == "2026-09-10"                                                 # 훑은 만큼만 "기록 시작일"

    _, _, sess2, _ = go(joy, tmp_path, joy_pages=1)
    assert [x for x in urls(sess2) if "board_list" in x] == [board_url(1), board_url(3)]
    assert [x.rsplit("=", 1)[1] for x in urls(sess2) if "board_view" in x] == ["504"]                           # 이미 읽은 글은 다시 열지 않는다
    c2 = read(tmp_path, "meta.json")["crawl"]
    assert c2["joyNext"] == 4 and c2["joyDone"] is True and c2["joyOldest"] == "2026-07-30"

    _, _, sess3, _ = go(joy, tmp_path, joy_pages=1)                                                             # 끝까지 훑은 뒤에는 과거 쪽을 더 요청하지 않는다
    assert [x for x in urls(sess3) if "board_list" in x] == [board_url(1)] and not [x for x in urls(sess3) if "board_view" in x]


def test_without_bootstrap_only_the_daily_pages_are_scanned(tmp_path):
    seed(tmp_path)
    _, _, sess, _ = go(Joy(), tmp_path, bootstrap=False)
    assert [x for x in urls(sess) if "board_list" in x] == [board_url(1), board_url(2)]
    meta = read(tmp_path, "meta.json")
    assert meta["crawl"]["joyNext"] == 3 and meta["since"] == "2026-09-10"


# ---------------------------------------------------------------- 매일 실행
def test_daily_run_is_idempotent_and_requests_only_the_board(tmp_path):
    seed(tmp_path)
    joy = Joy()
    go(joy, tmp_path, joy_pages=25)
    names = ["catalog-gunpla.json", "catalog-girl.json", "catalog-pending.json", "feed.json", config.KR_ARRIVALS_FILE]
    before = {n: (tmp_path / n).read_bytes() for n in names}
    _, client, sess, _ = go(joy, tmp_path, bootstrap=False, now=NOW + timedelta(hours=6))
    assert not [x for x in urls(sess) if "board_view" in x] and client.stats.by_kind["list"] == 2
    assert {n: (tmp_path / n).read_bytes() for n in names} == before


def test_new_post_goes_to_feed_and_discord_but_only_recent_posts_are_notified(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook-for-test")
    seed(tmp_path)
    joy = Joy()
    go(joy, tmp_path, joy_pages=25)
    later = NOW + timedelta(days=2)                                                                              # 2026-10-08
    joy.pages[1] = [("511", "2026-10-07", "10/8(목) 반다이 제품리스트")] + joy.pages[1][:2]
    joy.pages[2] = [("512", "2026-09-29", "9/30 반다이 입고리스트")] + joy.pages[2][:2]                            # 뒤늦게 발견된 9일 전 글
    joy.posts["511"] = ("10/8(목) 반다이 제품리스트", "소개", [("BD5000006", "[HG] 1/144 새 기체(NEW)(프라모델)", "20000원")])
    joy.posts["512"] = ("9/30 반다이 입고리스트", "소개", [("BD5000007", "[HG] 1/144 지난주 기체(OLD)(프라모델)", "20000원")])
    sent = []

    class Ok:
        status_code = 204
    res, _, _, lines = go(joy, tmp_path, bootstrap=False, now=later, post=lambda url, **k: (sent.append(k["json"]), Ok())[1])
    feed = {f["id"] for f in read(tmp_path, "feed.json")["items"]}
    assert {"jh-511-BD5000006", "jh-512-BD5000007"} <= feed                                                      # 둘 다 피드(30일 이내)
    titles = [e["title"] for m in sent for e in m["embeds"]]
    assert len(sent) == 1 and len(titles) == 1 and "새 기체" in titles[0]                                         # 알림은 3일 이내 글 하나만
    assert res["notified"] == 1


# ---------------------------------------------------------------- 실패는 격리된다
def test_board_failure_is_reported_but_the_run_continues(tmp_path):
    seed(tmp_path)
    joy = Joy()
    joy.fail_board = {1}
    res, *_ = go(joy, tmp_path, bootstrap=False)
    s = read(tmp_path, "meta.json")["sources"]["joyhobby"]
    assert s["ok"] is False and "list:1" in s["error"]
    assert (tmp_path / "catalog-gunpla.json").exists() and (tmp_path / "feed.json").exists() and (tmp_path / config.KR_ARRIVALS_FILE).exists()
    assert "joyNext" not in read(tmp_path, "meta.json")["crawl"]                                                 # 한 쪽도 못 훑었으면 커서도 없다


def test_post_failures_keep_the_post_pending_then_give_up(tmp_path):
    seed(tmp_path)
    joy = Joy()
    joy.fail_post = {"510": 500, "505": 404}
    go(joy, tmp_path, joy_pages=25)
    posts = read(tmp_path, config.KR_ARRIVALS_FILE)["posts"]
    assert posts["510"]["state"] == "pending" and posts["510"]["fails"] == 1 and posts["505"]["state"] == "gone"
    s = read(tmp_path, "meta.json")["sources"]["joyhobby"]
    assert s["ok"] is False and "post:510" in s["error"] and s["pendingLeft"] == 1
    for _ in range(config.JOY_POST_MAX_FAILURES - 1):
        go(joy, tmp_path, bootstrap=False)
    assert read(tmp_path, config.KR_ARRIVALS_FILE)["posts"]["510"]["state"] == "error"
    joy.fail_post = {}
    _, _, sess, _ = go(joy, tmp_path, bootstrap=False)
    assert not [x for x in urls(sess) if "board_view" in x]                                                      # 포기한 글은 다시 시도하지 않는다


def test_later_hobby_catalog_growth_links_old_rows_and_backfills_kr(tmp_path):
    """상세가 나중에 채워지면 (조이하비 글을 다시 읽지 않고) 과거 입고도 kr에 들어간다."""
    seed(tmp_path, dict(red_item(), id="bh-01_9", nameKo="HG 1/144 완전히 무관한 물건"))
    joy = Joy()
    go(joy, tmp_path, joy_pages=25)
    assert read(tmp_path, "catalog-gunpla.json")["items"][0]["kr"] == []
    assert read(tmp_path, config.KR_ARRIVALS_FILE)["codeMap"] == {}
    seed(tmp_path, red_item())
    _, _, sess, _ = go(joy, tmp_path, bootstrap=False)
    assert not [x for x in urls(sess) if "board_view" in x]
    item = read(tmp_path, "catalog-gunpla.json")["items"][0]
    assert item["id"] == "bh-01_1" and [k["post"] for k in item["kr"]] == ["510"]
    feed = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}
    assert feed["jh-510-BD5000001"]["catalogId"] == "bh-01_1" and feed["jh-510-BD5000001"]["image"] == IMG        # 피드의 빈 칸도 채워진다


def test_other_stages_alone_do_not_touch_the_arrivals_file(tmp_path):
    seed(tmp_path)
    go(Joy(), tmp_path, only=("hobby_item",), bootstrap=False)
    assert not (tmp_path / config.KR_ARRIVALS_FILE).exists()


def test_site_bug_posts_are_marked_broken_once_and_never_block_the_rest(tmp_path):
    """조회수 overflow로 영구히 500인 글이 연속으로 여러 개여도(차단 기준 5회 초과) 중단하지 않고, 다시 시도하지도 않는다."""
    seed(tmp_path)
    joy = Joy()
    joy.pages[1] = [("515", "2026-10-05", "반다이 입고 1"), ("514", "2026-10-05", "반다이 입고 2"), ("513", "2026-10-05", "반다이 입고 3")]
    joy.pages[2] = [("512", "2026-10-04", "반다이 입고 4"), ("511", "2026-10-04", "반다이 입고 5"), ("510", "2026-10-04", "반다이 입고 6")]
    for pid in ("515", "514", "513", "512", "511", "510"):
        joy.posts[pid] = ("t", "i", [("BD5000001", RED, "1원")])
    joy.broken_post = {"515", "514", "513", "512", "511", "510"}
    joy.pages[3] = [("504", "2026-08-01", "8/2 반다이 제품리스트"), ("503", "2026-07-30", "공지")]
    _, _, sess, _ = go(joy, tmp_path, joy_pages=25)
    posts = read(tmp_path, config.KR_ARRIVALS_FILE)["posts"]
    assert {p: v["state"] for p, v in posts.items() if p in joy.broken_post} == {p: "broken" for p in joy.broken_post}
    assert posts["504"]["state"] == "done"                                                      # 그 뒤의 정상 글은 읽었다
    s = read(tmp_path, "meta.json")["sources"]["joyhobby"]
    assert s["ok"] is True and s["error"] is None and s["postsBroken"] == 6                    # 사이트 버그는 소스 실패가 아니다
    _, _, sess2, _ = go(joy, tmp_path, bootstrap=False)
    assert not [x for x in urls(sess2) if "board_view" in x]                                  # 다시 열지 않는다


def test_previously_failed_posts_wait_behind_new_ones(tmp_path):
    seed(tmp_path)
    joy = Joy()
    joy.fail_post = {"510": 500}
    go(joy, tmp_path, joy_pages=25)
    joy.fail_post = {"510": 500}
    joy.pages[1] = [("520", "2026-10-06", "10/7 반다이 제품리스트")] + joy.pages[1][:2]
    joy.posts["520"] = ("10/7 반다이 제품리스트", "i", [("BD5000008", "[HG] 1/144 새 기체", "1원")])
    _, _, sess, _ = go(joy, tmp_path, bootstrap=False)
    order = [x.rsplit("=", 1)[1] for x in urls(sess) if "board_view" in x]
    assert order == ["520", "510"]                                                              # 새 글(520)이 먼저, 실패한 적 있는 510은 뒤
