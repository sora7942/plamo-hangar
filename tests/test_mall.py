"""반다이남코코리아몰(7a): 목록 파서·스캔·이름 정리·연결·가격/이름/시리즈 반영·판매 종료·파이프라인. 네트워크·디스코드·Claude 호출 없음 (가짜 세션)."""
import json
from datetime import datetime, timedelta

import pytest

from conftest import ROBOTS_HTML, FIXTURES, make_client
from crawler import config, kr, mall_link, mall_scan, series, translate
from crawler.catalog import Catalog
from crawler.http import Blocked
from crawler.pipeline import Options, run
from crawler.sources import mall
from schema_check import check_dir
from test_pipeline import NOW as PIPE_NOW, World, go, read

NOW = "2026-10-09T10:00:00+09:00"
LATER = "2026-10-10T10:00:00+09:00"
ROBOTS = "User-agent: *\nAllow: /\nDisallow: /nmanager/\n"


# ---------------------------------------------------------------- 합성 목록 페이지
def li(gno, name, price, series_name=None, badge="", dim=""):
    cap = f'<p class="font-13 caption">{series_name}</p>' if series_name else ""
    dim_html = f'<div class="thumb-dim"><p class="font-esamanru font-bold dim-text">{dim}</p></div>' if dim else ""
    return (f'<li data-childno="1"><a class="thumb" href="../goods/detail.do?gno={gno}"><div class="thumb-img"><div class="img_box" style="background-image:none"></div>{dim_html}</div>'
            f'{cap}<h5 class="font-15">{name}</h5><div class="font-15 price"><p class="price_result"><span class="num font-20">\n {price:,}</span>원</p></div></a>'
            f'<div class="badge">{badge}</div></li>')


def page_html(rows, pages=1):
    pager = "".join(f"<button onclick=\"javascript:pageLink('{p}');\">{p}</button>" for p in range(1, pages + 1))
    return f'<html><body><ul>{"".join(li(*r) if isinstance(r, tuple) else r for r in rows)}</ul><div class="paging_box"><div class="page_list">{pager}</div></div></body></html>'


def routes_for(pages_by_cate: dict, *, fail=()):
    """{cate키: [페이지1 rows, 페이지2 rows, …]} → 라우트. 쪽수는 pager로 알린다."""
    r = {config.MALL_BASE + "/robots.txt": ROBOTS}
    for cat in config.MALL_CATEGORIES:
        pages = pages_by_cate.get(cat["key"], [[("1", "HG 더미", 1000)]])
        for n, rows in enumerate(pages, 1):
            url = mall.list_url(cat["params"], n)
            if (cat["key"], n) in fail:
                r[url] = (lambda u: (500, "boom"))
            else:
                r[url] = page_html(rows, len(pages))
    return r


# ---------------------------------------------------------------- 파서
def test_parse_list_fixture_from_real_page():
    p = mall.parse_list((FIXTURES / "mall-category-p1.html").read_text(encoding="utf-8"))
    assert p["pages"] == 8 and p["skipped"] == 0
    assert [(i["gno"], i["name"], i["series"], i["price"]) for i in p["items"]] == [
        ("8745495", "1/100 건담 에어마스터", "기동신세기 건담 X", 22800), ("64138890", "HG 건담 레오파드", "기동신세기 건담 X", 26400),
        ("16323756", "MG 백식 + 밸류트 시스템", "기동전사 Z 건담", 54000), ("18718357", "옵션파츠 세트 건프라20 [라이드 온 세트]", None, 21600),
        ("21670735", "HG 건담 X 마오", "건담 빌드 파이터즈", 21600)]
    assert all(i["soldOut"] is False for i in p["items"])
    assert "cdn.bnkrmall" not in (FIXTURES / "mall-category-p1.html").read_text(encoding="utf-8"), "몰 이미지 URL은 fixture에도 넣지 않는다"


def test_parse_list_sold_out_badge_and_price_commas():
    p = mall.parse_list(page_html([("11", "HG 품절 상품", 1234567, "시리즈", '<span class="sale">품절</span>'), ("12", "HG 판매 상품", 9900)]))
    assert [(i["gno"], i["price"], i["soldOut"]) for i in p["items"]] == [("11", 1234567, True), ("12", 9900, False)]


def test_parse_list_sold_out_is_read_from_thumb_dim_not_from_promo_badges_or_reservation_dim():
    """실제 목록(2026-10): 품절은 `.thumb-dim`의 `SOLD OUT`. `.badge`는 `MD PICK` 같은 홍보 문구, 예약 상품의 dim은 `예약상품`이다."""
    p = mall.parse_list(page_html([("1", "MGSD 윙 건담 제로EW", 54000, "신기동전기 건담 W", "", "SOLD OUT"), ("2", "RG 샤이닝 건담", 42000, None, "MD PICK", ""),
                                   ("3", "예약 상품", 30000, None, "", "예약상품"), ("4", "품절 아님", 100, None, "", "")]))
    assert {i["gno"]: i["soldOut"] for i in p["items"]} == {"1": True, "2": False, "3": False, "4": False}


def test_parse_list_structure_change_raises():
    for html in ("<html><body>점검 중입니다</body></html>", "<ul></ul>"):
        with pytest.raises(mall.MallStructureError):
            mall.parse_list(html)
    broken = page_html([("1", "HG 하나", 1000), '<li data-childno="1"><a class="thumb" href="x">가격 없음</a></li>', '<li data-childno="1"><span>?</span></li>'])
    with pytest.raises(mall.MallStructureError):                                  # 읽은 줄이 절반 미만
        mall.parse_list(broken)
    ok = mall.parse_list(page_html([("1", "HG 하나", 1000), ("2", "HG 둘", 2000), '<li data-childno="1"><span>?</span></li>']))
    assert len(ok["items"]) == 2 and ok["skipped"] == 1                           # 한두 줄만 못 읽으면 건너뛰고 계속


def test_list_urls_include_sold_out_goods_and_scan_budget_covers_the_full_lists():
    """`soldout=Y`는 품절 상품을 뺀다 → 빈 값이어야 한다 (2026-10: 건프라 40쪽·30MM 5쪽·Figure-rise 4쪽 = 49요청, 1.2초 간격으로 22쪽에서 연결이 끊겨 3초로 늦춤)."""
    for c in config.MALL_CATEGORIES:
        assert "soldout=&" in mall.list_url(c["params"], 1) and "soldout=Y" not in mall.list_url(c["params"], 1)
    assert config.MALL_MAX_REQUESTS >= 49 + 5 and config.MALL_MAX_PAGES >= 40
    assert config.MALL_MIN_INTERVAL >= 2 * config.MIN_INTERVAL, "몰은 1.2초보다 훨씬 느리게 (속도 제한)"


def test_urls_are_list_pages_only():
    u = mall.list_url({"cate": "1577", "cateName": "애니프라", "brandIdx": "202,203,407,386"}, 3)
    assert u.startswith("https://www.bnkrmall.co.kr/goods/category.do?cate=1577&page=3&cateName=") and "brandIdx=202,203,407,386" in u and "soldout=&endGoods=Y" in u and "soldout=Y" not in u
    assert mall.goods_url("58992") == "https://www.bnkrmall.co.kr/goods/detail.do?gno=58992"
    assert all("detail.do" not in mall.list_url(c["params"], 1) for c in config.MALL_CATEGORIES)


# ---------------------------------------------------------------- 스캔
def test_scan_reads_every_page_of_every_category_within_cap():
    pages = {"gunpla": [[("1", "HG 가", 1100), ("2", "HG 나", 2200)], [("3", "MG 다", 3300)]], "girl-30mm": [[("4", "30MS 라", 400)]], "girl-figurerise": [[("5", "피규어라이즈 스탠다드 마", 500)]]}
    client, sess, _ = make_client(routes_for(pages))
    res = mall.scan(client)
    assert res["complete"] and res["errors"] == [] and res["requests"] == 4 and res["pages"] == {"gunpla": 2, "girl-30mm": 1, "girl-figurerise": 1}
    assert {g: v["cate"] for g, v in res["goods"].items()} == {"1": "gunpla", "2": "gunpla", "3": "gunpla", "4": "girl-30mm", "5": "girl-figurerise"}
    urls = [c["url"] for c in sess.calls]
    assert all(("robots.txt" in u) or "category.do" in u for u in urls), "목록 페이지 외에는 요청하지 않는다(상세·이미지 없음)"
    assert not any("cdn.bnkrmall" in u or "detail.do" in u for u in urls)


def test_scan_stops_at_request_cap_and_reports_incomplete():
    pages = {"gunpla": [[("1", "HG 가", 1)], [("2", "HG 나", 1)], [("3", "HG 다", 1)]]}
    client, sess, _ = make_client(routes_for(pages))
    res = mall.scan(client, max_requests=2)
    assert res["requests"] == 2 and res["complete"] is False and "요청 상한" in res["errors"][0] and sorted(res["goods"]) == ["1", "2"]


def test_scan_page_failure_or_structure_change_marks_incomplete_but_continues():
    pages = {"gunpla": [[("1", "HG 가", 1)], [("2", "HG 나", 1)]], "girl-30mm": [[("4", "30MS 라", 1)]]}
    client, _, _ = make_client(routes_for(pages, fail={("gunpla", 2)}))
    res = mall.scan(client)
    assert res["complete"] is False and "HTTP 500" in res["errors"][0] and "1" in res["goods"] and "4" in res["goods"] and "2" not in res["goods"]
    r2 = routes_for(pages)
    r2[mall.list_url(config.MALL_CATEGORIES[1]["params"], 1)] = "<html><body>개편</body></html>"
    client2, _, _ = make_client(r2)
    res2 = mall.scan(client2)
    assert res2["complete"] is False and any("구조" in e for e in res2["errors"]) and "1" in res2["goods"] and "2" in res2["goods"]


# ---------------------------------------------------------------- 실패 진단 (Actions에서만 실패할 때 원인을 가르려고)
ERROR_PAGE = ("<html><head><title>서버 오류</title><style>.x{}</style><script>var a=1;</script></head>"
              "<body><h1>서버 오류</h1><p>잠시 후 다시 시도해 주세요.</p></body></html>")
# Actions(클라우드 IP)에서 실제로 받은 웹 방화벽 차단 응답 (HTTP 200, 짧은 본문 — 2026-10 진단)
REJECTED = ("<html><head><title>Request Rejected</title></head><body>The requested URL was rejected. Please consult with your administrator.<br><br>"
            "Your support ID is: 1234567890123456789<br><br><a href='javascript:history.back();'>[Go Back]</a></body></html>")


def test_scan_records_diag_for_http_error_and_structure_change():
    r = routes_for({})
    r[mall.list_url(config.MALL_CATEGORIES[0]["params"], 1)] = lambda u: (500, ERROR_PAGE)
    r[mall.list_url(config.MALL_CATEGORIES[1]["params"], 1)] = "<html><head><title>점검 중</title></head><body>잠시 후 다시 <b>이용</b>해 주세요</body></html>"
    client, _, _ = make_client(r)
    res = mall.scan(client)
    assert res["complete"] is False and len(res["diag"]) == 2
    d500, dstruct = res["diag"]
    assert (d500["where"], d500["status"], d500["title"]) == ("gunpla 1쪽", 500, "서버 오류")
    assert d500["head"].startswith("서버 오류 잠시 후 다시") and "var a" not in d500["head"] and ".x{}" not in d500["head"], "script·style·title은 본문 앞부분에서 뺀다"
    assert d500["finalUrl"] == mall.list_url(config.MALL_CATEGORIES[0]["params"], 1) and d500["redirects"] == 0 and d500["bytes"] == len(ERROR_PAGE.encode())
    assert (dstruct["where"], dstruct["status"], dstruct["title"], dstruct["head"]) == ("girl-30mm 1쪽", 200, "점검 중", "잠시 후 다시 이용 해 주세요")


def test_diag_head_is_limited_and_redirect_is_visible():
    long_page = "<html><head><title>" + "T" * 300 + "</title></head><body>" + "가" * 1000 + "</body></html>"
    start = mall.list_url(config.MALL_CATEGORIES[0]["params"], 1)
    sess_routes = {config.MALL_BASE + "/robots.txt": ROBOTS, start: lambda u: (200, long_page)}
    client, _, _ = make_client(sess_routes)
    res = mall.scan(client, categories=config.MALL_CATEGORIES[:1])
    d = res["diag"][0]
    assert len(d["head"]) == 200 and len(d["title"]) == 100
    fetched = type("F", (), dict(text="", status=200, error=None, final_url="https://www.bnkrmall.co.kr/login.do", url=start, redirects=2, size=0, content_type="text/html"))()
    dd = mall.describe(fetched, "gunpla 1쪽")
    assert dd["finalUrl"].endswith("/login.do") and dd["redirects"] == 2 and dd["head"] == "" and dd["title"] == ""


def test_scan_without_failures_has_empty_diag_and_no_dump(tmp_path):
    client, _, _ = make_client(routes_for({}))
    res = mall.scan(client)
    assert res["complete"] and res["diag"] == []
    assert not list(tmp_path.iterdir())


def test_scan_dump_dir_saves_every_response_and_summary(tmp_path):
    r = routes_for({"gunpla": [[("1", "HG 가", 1100)], [("2", "HG 나", 1)]]})
    r[mall.list_url(config.MALL_CATEGORIES[1]["params"], 1)] = lambda u: (500, ERROR_PAGE)
    client, _, _ = make_client(r)
    out = tmp_path / "mall-debug"
    res = mall.scan(client, dump_dir=out)
    names = sorted(p.name for p in out.iterdir())
    assert names == ["girl-30mm-p1.html", "girl-figurerise-p1.html", "gunpla-p1.html", "gunpla-p2.html", "summary.json"]
    assert (out / "girl-30mm-p1.html").read_text(encoding="utf-8") == ERROR_PAGE
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["requests"] == res["requests"] == 4 and len(summary["responses"]) == 4
    assert [x["status"] for x in summary["responses"]] == [200, 200, 500, 200]
    assert summary["robots"][config.MALL_BASE]["status"] == 200 and "Allow" in summary["robots"][config.MALL_BASE]["head"]


# ---------------------------------------------------------------- 방화벽 차단 감지 (PC에서도 차단되면 기록하고 멈춘다)
def test_scan_stops_at_first_firewall_rejection_without_retry_or_other_categories():
    r = routes_for({})
    for cat in config.MALL_CATEGORIES:
        r[mall.list_url(cat["params"], 1)] = REJECTED          # HTTP 200 + 짧은 차단 문구
    client, sess, _ = make_client(r)
    res = mall.scan(client)
    assert res["blocked"] is True and res["complete"] is False and res["goods"] == {} and res["requests"] == 1
    assert len([c for c in sess.calls if "category.do" in c["url"]]) == 1, "차단 응답이면 재시도도, 다른 카테고리 요청도 없다"
    assert res["results"] == [{"where": "gunpla 1쪽", "status": 200, "ok": True, "bytes": len(REJECTED.encode())}]
    assert "차단" in res["errors"][0] and res["diag"][0]["title"] == "Request Rejected" and "support ID" in res["diag"][0]["head"]


def test_looks_blocked_distinguishes_rejection_from_normal_and_error_pages():
    ok = page_html([("1", "HG 가", 1000)])
    mk = lambda status, text: type("F", (), dict(status=status, text=text))()
    assert mall.looks_blocked(mk(200, REJECTED)) and mall.looks_blocked(mk(403, "x")) and mall.looks_blocked(mk(429, ""))
    assert not mall.looks_blocked(mk(200, ok)) and not mall.looks_blocked(mk(500, ERROR_PAGE)) and not mall.looks_blocked(mk(200, "<html>개편</html>"))
    assert not mall.looks_blocked(mk(200, ok + "Access Denied" * 300)), "상품 줄이 있는 정상 목록은 본문에 문구가 있어도 차단이 아니다"


# ---------------------------------------------------------------- PC 스냅샷 mall-scan.json (--mall-local)
SNAP = "2026-10-06T06:30:00+09:00"            # test_pipeline.NOW(2026-10-06 09:00) 직전
KST_NOW = datetime(2026, 10, 6, 6, 30, tzinfo=config.KST)


def local_scan(tmp_path, routes, *, now=KST_NOW, dry_run=False, dump=None):
    client, sess, _ = make_client(routes)
    lines = []
    doc = mall_scan.run_local(client, tmp_path, dry_run=dry_run, now=now, out=lines.append, dump_dir=dump)
    return doc, sess, lines


def snap_doc(goods, *, at=SNAP, complete=True, blocked=False, errors=()):
    return {"updatedAt": at, "blocked": blocked,
            "lastTry": {"at": at, "ok": complete and not blocked and bool(goods), "blocked": blocked, "complete": complete, "requests": 3, "pages": {"gunpla": 1}, "results": [], "errors": list(errors), "diag": []},
            "scan": {"at": at, "complete": complete, "requests": 3, "count": len(goods)} if goods else {}, "goods": goods}


def write_snap(tmp_path, doc):
    (tmp_path / config.MALL_SCAN_FILE).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_run_local_writes_only_mall_scan_json_with_snapshot_time_results_and_goods(tmp_path):
    for name in ("mall.json", "catalog-gunpla.json", "meta.json"):          # 다른 파일은 건드리지 않는다
        (tmp_path / name).write_text('{"keep":true}', encoding="utf-8")
    pages = {"gunpla": [[("1", "HG 가", 1100, "시리즈 A"), ("2", "HG 나", 2200)], [("3", "MG 다", 3300)]], "girl-30mm": [[("4", "30MS 라", 400)]], "girl-figurerise": [[("5", "피규어라이즈 스탠다드 마", 500)]]}
    doc, sess, _ = local_scan(tmp_path, routes_for(pages))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["catalog-gunpla.json", "mall-scan.json", "mall.json", "meta.json"]
    assert all((tmp_path / n).read_text(encoding="utf-8") == '{"keep":true}' for n in ("mall.json", "catalog-gunpla.json", "meta.json"))
    saved = json.loads((tmp_path / config.MALL_SCAN_FILE).read_text(encoding="utf-8"))
    assert saved == doc and saved["blocked"] is False and saved["updatedAt"] == SNAP
    assert saved["scan"] == {"at": SNAP, "complete": True, "requests": 4, "count": 5}
    assert saved["lastTry"]["ok"] is True and saved["lastTry"]["pages"] == {"gunpla": 2, "girl-30mm": 1, "girl-figurerise": 1}
    assert [r["where"] for r in saved["lastTry"]["results"]] == ["gunpla 1쪽", "gunpla 2쪽", "girl-30mm 1쪽", "girl-figurerise 1쪽"] and all(r["status"] == 200 for r in saved["lastTry"]["results"])
    assert saved["goods"]["1"] == {"name": "HG 가", "series": "시리즈 A", "price": 1100, "soldOut": False, "cate": "gunpla"} and list(saved["goods"]) == ["1", "2", "3", "4", "5"]
    assert not any("detail.do" in c["url"] or "cdn." in c["url"] for c in sess.calls)


def test_run_local_blocked_records_flag_keeps_previous_goods_and_does_not_retry(tmp_path):
    write_snap(tmp_path, snap_doc({"7": {"name": "HG 이전", "series": None, "price": 5000, "soldOut": False, "cate": "gunpla"}}, at="2026-10-04T06:30:00+09:00"))
    r = routes_for({})
    r[mall.list_url(config.MALL_CATEGORIES[0]["params"], 1)] = REJECTED
    doc, sess, lines = local_scan(tmp_path, r)
    assert doc["blocked"] is True and doc["lastTry"]["blocked"] is True and doc["lastTry"]["ok"] is False and doc["lastTry"]["requests"] == 1
    assert doc["scan"]["at"] == "2026-10-04T06:30:00+09:00" and list(doc["goods"]) == ["7"], "차단된 날은 이전 스냅샷을 지우지 않는다"
    assert len([c for c in sess.calls if "category.do" in c["url"]]) == 1 and any("재시도하거나 우회하지 않습니다" in l for l in lines)
    assert json.loads((tmp_path / config.MALL_SCAN_FILE).read_text(encoding="utf-8"))["blocked"] is True
    # 다음 날 정상 응답이면 차단 표시가 사라지고 스냅샷이 새로 바뀐다
    doc2, _, _ = local_scan(tmp_path, routes_for({"gunpla": [[("1", "HG 가", 1100)]]}), now=datetime(2026, 10, 7, 6, 30, tzinfo=config.KST))
    assert doc2["blocked"] is False and doc2["scan"]["at"] == "2026-10-07T06:30:00+09:00" and "7" not in doc2["goods"]


def test_run_local_first_ever_block_writes_empty_snapshot_and_dry_run_writes_nothing(tmp_path):
    r = routes_for({})
    for cat in config.MALL_CATEGORIES:
        r[mall.list_url(cat["params"], 1)] = REJECTED
    doc, _, _ = local_scan(tmp_path, r, dry_run=True)
    assert doc["blocked"] is True and doc["goods"] == {} and doc["scan"] == {} and not (tmp_path / config.MALL_SCAN_FILE).exists(), "--dry-run은 파일을 쓰지 않는다"
    local_scan(tmp_path, r)
    assert json.loads((tmp_path / config.MALL_SCAN_FILE).read_text(encoding="utf-8"))["blocked"] is True


def test_run_local_partial_scan_is_kept_but_marked_incomplete_and_http_failure_keeps_old(tmp_path):
    pages = {"gunpla": [[("1", "HG 가", 1)], [("2", "HG 나", 1)]], "girl-30mm": [[("4", "30MS 라", 1)]], "girl-figurerise": [[("5", "피규어라이즈 스탠다드 마", 1)]]}
    doc, _, _ = local_scan(tmp_path, routes_for(pages, fail={("gunpla", 2)}))
    assert doc["scan"]["complete"] is False and doc["lastTry"]["ok"] is False and sorted(doc["goods"]) == ["1", "4", "5"] and doc["blocked"] is False
    # 아무것도 못 읽은 날(전부 500)은 이전 스냅샷 유지
    r = routes_for({}, fail={(c["key"], 1) for c in config.MALL_CATEGORIES})
    doc2, _, _ = local_scan(tmp_path, r, now=datetime(2026, 10, 7, 6, 30, tzinfo=config.KST))
    assert doc2["goods"] == doc["goods"] and doc2["scan"] == doc["scan"] and doc2["lastTry"]["at"] == "2026-10-07T06:30:00+09:00" and doc2["lastTry"]["ok"] is False


def test_run_local_robots_disallow_and_429_are_recorded_not_raised(tmp_path):
    client, _, _ = make_client({config.MALL_BASE + "/robots.txt": "User-agent: *\nDisallow: /goods/\n"})
    doc = mall_scan.run_local(client, tmp_path, now=KST_NOW, out=lambda *_: None)
    assert doc["blocked"] is False and "robots" in doc["lastTry"]["errors"][0]
    r = routes_for({})
    r[mall.list_url(config.MALL_CATEGORIES[0]["params"], 1)] = lambda u: (429, "slow down")
    doc2, _, _ = local_scan(tmp_path, r)
    assert doc2["blocked"] is True, "429도 차단으로 기록하고 멈춘다"


def test_mall_scan_file_passes_the_schema_check(tmp_path):
    from schema_check import check_mall_scan
    pages = {"gunpla": [[("1", "HG 가", 1100, "시리즈 A")]], "girl-30mm": [[("4", "30MS 라", 400)]], "girl-figurerise": [[("5", "피규어라이즈 스탠다드 마", 500)]]}
    doc, _, _ = local_scan(tmp_path, routes_for(pages))
    assert check_mall_scan(doc) == []
    r = routes_for({})
    r[mall.list_url(config.MALL_CATEGORIES[0]["params"], 1)] = REJECTED
    blocked, _, _ = local_scan(tmp_path, r)
    assert check_mall_scan(blocked) == [] and blocked["blocked"] is True
    assert check_mall_scan({**doc, "blocked": "yes"}) != [] and check_mall_scan({**doc, "scan": {**doc["scan"], "count": 99}}) != []


def test_to_scan_reports_blocked_stale_and_missing_snapshot():
    goods = {"1": {"name": "HG 가", "series": None, "price": 1000, "soldOut": False, "cate": "gunpla"}}
    now = datetime(2026, 10, 6, 9, 0, tzinfo=config.KST)
    scan, warns = mall_scan.to_scan(snap_doc(goods), now)
    assert warns == [] and scan["at"] == SNAP and scan["stale"] is False and scan["ageDays"] == 0 and scan["complete"] is True
    scan, warns = mall_scan.to_scan(snap_doc(goods, at="2026-09-28T06:30:00+09:00"), now)          # 8일
    assert scan["stale"] is True and scan["ageDays"] == 8 and "8일 지남" in warns[0]
    assert mall_scan.to_scan(snap_doc(goods, at="2026-09-29T06:30:00+09:00"), now)[0]["stale"] is False        # 정확히 7일은 아직 최신
    scan, warns = mall_scan.to_scan(snap_doc(goods, blocked=True), now)
    assert scan["blocked"] is True and "차단" in warns[0] and scan["goods"] == goods, "차단된 날도 마지막 스냅샷은 쓴다"
    assert mall_scan.to_scan(snap_doc({}), now)[0] is None and "스냅샷이 없음" in mall_scan.to_scan(snap_doc({}), now)[1][-1]


def test_cli_mall_local_flag_rules():
    import main as cli
    assert cli.parse_args(["--only", "mall", "--mall-local"]).mall_local is True
    for bad in (["--mall-local"], ["--only", "mall,joyhobby", "--mall-local"], ["--only", "mall", "--mall-local", "--bootstrap"], ["--mall-dump", "x"]):
        with pytest.raises(SystemExit):
            cli.parse_args(bad)


# ---------------------------------------------------------------- 이름 정리
def test_parse_mall_name_grade_scale_and_core():
    n = mall_link.parse_mall_name("HG 건담 레오파드")
    assert (n.grade_words, n.grade, n.scale, n.core) == ("HG", "HG", None, "건담 레오파드")
    n = mall_link.parse_mall_name("RG 1/48 AV-98Plus (잉그램 플러스)")
    assert (n.grade, n.scale, n.core) == ("RG", "1/48", "AV-98Plus (잉그램 플러스)")
    assert mall_link.parse_mall_name("HGBD:R 머큐원 웨폰").grade == "HG" and mall_link.parse_mall_name("HGBD:R 머큐원 웨폰").grade_words == "HGBD:R"
    n = mall_link.parse_mall_name("피규어라이즈 스탠다드 티파 아딜")
    assert (n.grade, n.grade_words, n.core) == ("Figure-rise Standard", "Figure-rise Standard", "티파 아딜")
    assert mall_link.parse_mall_name("ENTRY GRADE 윙 건담").grade == "EG"
    assert mall_link.parse_mall_name("1/100 건담 에어마스터").grade is None and mall_link.parse_mall_name("옵션파츠 세트 건프라20").grade is None
    assert mall_link.parse_mall_name("30MM 시엘노바 [그린]").grade is None, "30MM은 카탈로그에 없는 라인 — 연결하지 않는다"


def test_mall_name_ko_uses_mall_wording_with_catalog_scale_and_grade_fallback():
    item = {"grade": "HG", "scale": "1/144", "nameKo": "HGUC 1/144 NRX-055 바운드 독"}
    assert mall_link.mall_name_ko(mall_link.parse_mall_name("HGUC 바운드 독"), item) == "HGUC 1/144 바운드 독"        # 몰 이름에 스케일이 없으면 카탈로그 값
    assert mall_link.mall_name_ko(mall_link.parse_mall_name("RG 1/48 AV-98Plus (잉그램 플러스)"), {"grade": "RG", "scale": "1/48"}) == "RG 1/48 AV-98Plus (잉그램 플러스)"
    assert mall_link.mall_name_ko(mall_link.parse_mall_name("건담 에어리얼"), item) == "HGUC 1/144 건담 에어리얼"      # 몰 이름에 등급이 없으면 카탈로그의 등급 낱말
    assert mall_link.mall_name_ko(mall_link.parse_mall_name("HG 함브라비(GQ)"), item) == "HG 1/144 함브라비(GQ)"     # 괄호 부가 설명은 몰 표기 그대로


# ---------------------------------------------------------------- 연결·반영
def item(i, name_ko, *, grade="HG", scale="1/144", jpy=2400, line="gunpla", **extra):
    return {"id": i, "line": line, "grade": grade, "scale": scale, "nameJa": "x " + i, "nameKo": name_ko, "priceJpy": jpy, "release": {"month": "2026-10"},
            "kr": [], "images": [], "updated": "old", **extra}


def cat_of(*items):
    c = Catalog()
    c.items = {i["id"]: i for i in items}
    return c


def good(name, price=26400, series_name=None, sold=False):
    return {"name": name, "series": series_name, "price": price, "soldOut": sold, "cate": "gunpla"}


def run_link(cat, goods, state=None, *, complete=True, now=NOW):
    st = state or mall_link.MallState()
    scan = {"goods": goods, "complete": complete, "requests": 3}
    seen, healthy = st.absorb(scan, now)
    return st, mall_link.link_all(st, cat, seen, healthy, now)


def test_confident_link_sets_price_name_and_series_and_keeps_old_names():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"), item("bh-2", "HG 1/144 건담 에어리얼", nameKoSource="joyhobby", nameKoAi="HG 1/144 건담 에어리얼 AI"))
    st, rep = run_link(cat, {"100": good("HG 건담 레오파드", 26400, "기동신세기 건담 X"), "200": good("HG 건담 에어리얼 (SEED Ver.)", 26400, None)})
    a = cat.items["bh-1"]
    assert st.links["100"]["catalogId"] == "bh-1" and st.links["100"]["nameOk"] is True
    assert (a["priceKrw"], a["priceKrwAt"], a["mallGno"]) == (26400, NOW, "100") and "mallSoldOut" not in a and "mallEnded" not in a
    assert a["nameKo"] == "HG 1/144 건담 레오파드" and a["nameKoSource"] == "bnkrmall" and a["nameKoAi"] == "HG 1/144 건담 레오파드"
    assert a["seriesKo"] == "기동신세기 건담 X" and a["seriesKoSource"] == "bnkrmall" and a["updated"] == NOW
    assert "200" not in st.links, "이름이 다르면(보호 규칙) 연결하지 않는다"
    assert rep["reasons"].get("guard") == 1 or rep["reasons"].get("low-score") == 1
    assert rep["nameChanged"][0]["was"] == "ai"


def test_mall_name_beats_joyhobby_and_override_restores_it():
    j = item("bh-1", "HG 1/144 붉은 건담", nameKoSource="joyhobby", nameKoAi="HG 1/144 붉은건담")
    cat = cat_of(j)
    st, rep = run_link(cat, {"100": good("HG 붉은 건담", 26400, "시리즈")})
    assert j["nameKo"] == "HG 1/144 붉은 건담" and j["nameKoSource"] == "bnkrmall" and j["nameKoJoy"] == "HG 1/144 붉은 건담" and j["nameKoAi"] == "HG 1/144 붉은건담"
    assert rep["nameChanged"] and rep["nameChanged"][0]["was"] == "joyhobby"
    # 이후 조이하비 연결이 몰 이름을 덮어쓰지 않는다
    arr = kr.Arrivals()
    arr.posts["1"] = {"date": "2026-10-02", "title": "반다이 입고", "state": "done", "sale": "2026-10-03", "restock": False, "rows": 1}
    arr.rows.append({"post": "1", "postDate": "2026-10-02", "code": "BD0000001", "name": "[HG] 1/144 붉은 건담(RED) - 시리즈(프라모델)", "price": 1000})
    kr.link_all(arr, cat, NOW)
    assert j["nameKoSource"] == "bnkrmall"
    # 몰 연결 금지(override None) → 조이하비 이름, seriesKo·가격 필드 제거
    import crawler.mall_link as ml
    old = dict(config.MALL_OVERRIDES)
    config.MALL_OVERRIDES["100"] = None
    try:
        _, rep2 = run_link(cat, {"100": good("HG 붉은 건담", 26400, "시리즈")}, st, now=LATER)
    finally:
        config.MALL_OVERRIDES.clear(); config.MALL_OVERRIDES.update(old)
    assert "100" not in st.links and rep2["nameReverted"] == 1
    assert j["nameKo"] == "HG 1/144 붉은 건담" and j["nameKoSource"] == "joyhobby" and "nameKoJoy" not in j and j["nameKoAi"] == "HG 1/144 붉은건담"
    assert not any(k in j for k in ("priceKrw", "mallGno", "seriesKo", "seriesKoSource"))
    assert ml.NAME_SOURCE == "bnkrmall"


def test_override_forces_link_and_ai_name_returns_on_revert():
    cat = cat_of(item("bh-9", "HG 1/144 완전히 다른 이름"))
    config.MALL_OVERRIDES["300"] = "bh-9"
    try:
        st, rep = run_link(cat, {"300": good("HG 몰이 부르는 이름")})
        assert st.links["300"]["method"] == "override" and cat.items["bh-9"]["nameKo"] == "HG 1/144 몰이 부르는 이름" and cat.items["bh-9"]["nameKoAi"] == "HG 1/144 완전히 다른 이름"
        config.MALL_OVERRIDES["300"] = None
        run_link(cat, {"300": good("HG 몰이 부르는 이름")}, st, now=LATER)
    finally:
        config.MALL_OVERRIDES.pop("300", None)
    assert cat.items["bh-9"]["nameKo"] == "HG 1/144 완전히 다른 이름" and "nameKoSource" not in cat.items["bh-9"] and "nameKoAi" not in cat.items["bh-9"]


def test_ambiguous_nograde_lowscore_and_price_mismatch_are_not_linked():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"), item("bh-2", "HG 1/144 건담 레오파드", jpy=2400),            # 같은 이름 둘 → 애매
                 item("bh-3", "HG 1/144 건담 바이킹", jpy=2400), item("bh-4", "RG 1/144 건담 세트", grade="RG", jpy=2400))
    st, rep = run_link(cat, {"1": good("HG 건담 레오파드"), "2": good("1/100 건담 에어마스터"), "3": good("HG 완전 다른 기체"),
                             "4": good("HG 건담 바이킹", 90000),                      # 이름은 같지만 가격이 정가의 37배
                             "5": good("30MM 시엘노바 [그린]")})
    assert st.links == {} and cat.items["bh-1"].get("nameKoSource") is None
    assert rep["reasons"] == {"ambiguous": 1, "no-grade": 2, "low-score": 1, "price-mismatch": 1}
    assert {u["gno"]: u["reason"] for u in rep["unlinked"]}["4"] == "price-mismatch"


def test_one_catalog_item_gets_only_the_best_mall_good():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, rep = run_link(cat, {"10": good("HG 건담 레오파드"), "11": good("HG 건담 레오파드 (리뉴얼)")})
    assert list(st.links) == ["10"] and rep["reasons"].get("duplicate", 0) + rep["reasons"].get("guard", 0) + rep["reasons"].get("low-score", 0) == 1


def test_price_and_sold_out_refresh_and_updated_only_on_change():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, _ = run_link(cat, {"100": good("HG 건담 레오파드")})
    it = cat.items["bh-1"]
    it["updated"] = "keep"
    st, rep = run_link(cat, {"100": good("HG 건담 레오파드")}, st, now=LATER)
    assert it["priceKrwAt"] == LATER and it["updated"] == "keep" and rep["priceUpdated"] == 0         # 확인 시각만 갱신, 값이 같으면 updated는 그대로
    st, rep = run_link(cat, {"100": good("HG 건담 레오파드", 28800, sold=True)}, st, now="2026-10-11T10:00:00+09:00")
    assert it["priceKrw"] == 28800 and it["mallSoldOut"] is True and it["updated"] == "2026-10-11T10:00:00+09:00" and rep["priceUpdated"] == 1
    run_link(cat, {"100": good("HG 건담 레오파드", 28800)}, st, now="2026-10-12T10:00:00+09:00")
    assert "mallSoldOut" not in it


def test_ended_only_after_a_healthy_complete_scan_and_cleared_when_back():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"), item("bh-2", "HG 1/144 건담 바이킹"))
    st, _ = run_link(cat, {"1": good("HG 건담 레오파드"), "2": good("HG 건담 바이킹")})
    a = cat.items["bh-1"]
    # 일부 쪽만 읽은 스캔(complete=False)에서는 사라져 보여도 판정하지 않는다
    st, rep = run_link(cat, {"2": good("HG 건담 바이킹")}, st, complete=False, now=LATER)
    assert rep["ended"] == 0 and "mallEnded" not in a and st.links["1"] and "1" in st.goods
    # 정상 스캔인데 1번이 없다 → 판매 종료: 가격·확인 시각은 마지막 값 그대로
    st, rep = run_link(cat, {"2": good("HG 건담 바이킹")}, st, now="2026-10-12T10:00:00+09:00")
    assert rep["ended"] == 1 and a["mallEnded"] is True and a["priceKrw"] == 26400 and a["priceKrwAt"] == NOW and a["nameKoSource"] == "bnkrmall"
    assert "mallEnded" not in cat.items["bh-2"]
    # 다시 나타나면 해제
    st, rep = run_link(cat, {"1": good("HG 건담 레오파드", 27600), "2": good("HG 건담 바이킹")}, st, now="2026-10-13T10:00:00+09:00")
    assert "mallEnded" not in a and a["priceKrw"] == 27600 and a["priceKrwAt"] == "2026-10-13T10:00:00+09:00"


def test_scan_far_smaller_than_before_is_not_trusted_for_ended():
    cat = cat_of(*[item(f"bh-{i}", f"HG 1/144 건담 모델{chr(65 + i)}{chr(75 + i)}") for i in range(4)])
    goods = {str(i): good(f"HG 건담 모델{chr(65 + i)}{chr(75 + i)}") for i in range(4)}
    st, _ = run_link(cat, goods)
    assert len(st.links) == 4
    st, rep = run_link(cat, {"0": goods["0"]}, st, now=LATER)                                          # 4개 → 1개: 목록이 비정상으로 보고 판정하지 않는다
    assert rep["ended"] == 0 and not any(i.get("mallEnded") for i in cat.items.values()) and st.scan["count"] == 4
    st, rep = run_link(cat, {k: goods[k] for k in ("0", "1", "2")}, st, now="2026-10-12T10:00:00+09:00")  # 4개 → 3개는 정상
    assert rep["ended"] == 1


def test_unlinked_goods_that_vanish_are_dropped_but_linked_ones_stay():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, _ = run_link(cat, {"1": good("HG 건담 레오파드"), "9": good("30MM 시엘노바"), "8": good("HG 건담 레오파드 보조")})
    st, _ = run_link(cat, {"1": good("HG 건담 레오파드"), "6": good("30MM 새 상품"), "7": good("30MM 어딘가")}, st, now=LATER)
    assert set(st.goods) == {"1", "6", "7"} and set(st.links) == {"1"}


def test_stale_link_to_removed_catalog_item_is_dropped_and_relinked():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, _ = run_link(cat, {"1": good("HG 건담 레오파드")})
    cat2 = cat_of(item("bh-5", "HG 1/144 건담 레오파드"))
    st, rep = run_link(cat2, {"1": good("HG 건담 레오파드")}, st, now=LATER)
    assert rep["staleDropped"] == 1 and st.links["1"]["catalogId"] == "bh-5"


def test_other_modules_leave_mall_names_alone(monkeypatch):
    it = item("bh-1", "HG 1/144 몰 이름", nameKoSource="bnkrmall", nameKoAi="AI 이름", seriesKey="g-witch", seriesKo="몰 시리즈", seriesKoSource="bnkrmall", series="水星の魔女")
    cat = cat_of(it, item("bh-2", "HG 1/144 번역 대기", nameKo=None))
    # 번역 단계: 몰 이름 항목은 건드리지 않는다 (nameKo가 있어 대상도 아니지만, 비워져도 덮어쓰지 않는다)
    it["nameKo"] = None
    calls = []

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kw):
                raise AssertionError("몰 이름 항목 때문에 API를 부르면 안 된다")
    it["nameKo"] = "HG 1/144 몰 이름"
    assert cat.reset_stray_han() == [] and cat.reset_glossary({"몰": "다른"}, {}) == [] and calls == []
    # 시리즈: 몰 시리즈명이 사전·번역보다 우선
    assert series.apply(cat, {"g-witch": {"ja": "水星の魔女", "ko": "수성의 마녀"}}) == 0 and it["seriesKo"] == "몰 시리즈"
    del it["seriesKoSource"]
    assert series.apply(cat, {"g-witch": {"ja": "水星の魔女", "ko": "수성의 마녀"}}) == 1 and it["seriesKo"] == "수성의 마녀"
    assert translate.has_credentials() is False


# ---------------------------------------------------------------- 상태 파일·파이프라인
def test_state_file_roundtrip_is_stable_and_valid(tmp_path):
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, _ = run_link(cat, {"100": good("HG 건담 레오파드", 26400, "시리즈"), "200": good("30MM 시엘노바 [그린]", 16600)})
    st.save(tmp_path, NOW)
    doc = json.loads((tmp_path / config.MALL_FILE).read_text(encoding="utf-8"))
    assert doc["updatedAt"] == NOW and doc["links"]["100"]["catalogId"] == "bh-1" and doc["goods"]["200"]["price"] == 16600
    from schema_check import check_mall
    assert check_mall(doc) == []
    st2 = mall_link.MallState.load(tmp_path)
    st2.absorb({"goods": {"100": good("HG 건담 레오파드", 26400, "시리즈"), "200": good("30MM 시엘노바 [그린]", 16600)}, "complete": True, "requests": 3}, NOW)
    st2.save(tmp_path, LATER)
    assert json.loads((tmp_path / config.MALL_FILE).read_text(encoding="utf-8"))["updatedAt"] == NOW, "바뀐 게 없으면 시각도 그대로"


def seed_linkable(tmp_path):
    """가짜 호비사이트 항목(01_7001 HG 1/144 テスト機A)에 한국어 이름·엔 정가를 줘서(번역은 API 키가 없어 안 돈다) 몰 이름 `HG 테스트기A`(₩14,300 = ¥1,300 × 11)와 연결되게 한다."""
    p = tmp_path / "catalog-gunpla.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    it = next(i for i in doc["items"] if i["id"] == "bh-01_7001")
    it.update(nameKo="HG 1/144 테스트기A", priceJpy=1300)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return it["id"]


def all_items(tmp_path):
    return {i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json") for i in read(tmp_path, f)["items"]}


def test_pipeline_applies_snapshot_without_any_mall_request_and_same_snapshot_changes_nothing(tmp_path):
    w = World()
    goods = {"100": good("HG 테스트기A", 14300, "수성의 마녀 테스트"), "200": good("30MS 다른 상품", 4000)}
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=5, max_backlog=5))          # 카탈로그를 먼저 만든다 (이때는 스냅샷이 없다)
    cid = seed_linkable(tmp_path)
    write_snap(tmp_path, snap_doc(goods))
    res, client, sess, lines = go(w, tmp_path, Options(max_new=5, max_backlog=5))
    assert check_dir(tmp_path) == []
    src = res["meta"]["sources"]["mall"]
    assert src["ok"] is True and src["goods"] == 2 and src["complete"] is True and src["snapshotAt"] == SNAP and src["snapshotAgeDays"] == 0 and src["stale"] is False and src["blocked"] is False
    assert not [c for c in sess.calls if "bnkrmall" in c["url"]], "Actions는 몰에 요청하지 않는다 (방화벽이 클라우드 IP를 막는다)"
    assert (tmp_path / config.MALL_FILE).exists() and any(l.startswith("[몰]") for l in lines)
    it = all_items(tmp_path)[cid]
    assert (it["priceKrw"], it["priceKrwAt"], it["mallGno"]) == (14300, SNAP, "100"), "확인 시각은 실행 시각이 아니라 PC가 몰을 읽은 스냅샷 시각"
    names = ("mall.json", "catalog-gunpla.json", "catalog-girl.json")
    before = {n: (tmp_path / n).read_bytes() for n in names}
    res2, _, sess2, _ = go(w, tmp_path, Options(max_new=5, max_backlog=5), now=PIPE_NOW + timedelta(hours=3))        # 같은 스냅샷으로 다시 실행
    assert {n: (tmp_path / n).read_bytes() for n in names} == before, "같은 스냅샷이면 mall.json·카탈로그가 바뀌지 않는다"
    assert res2["meta"]["sources"]["mall"]["ok"] is True and not [c for c in sess2.calls if "bnkrmall" in c["url"]]


def test_pipeline_without_snapshot_blocked_or_stale_warns_and_does_not_end_goods(tmp_path):
    w = World()
    res, *_ = go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=5, max_backlog=5))
    m = res["meta"]["sources"]["mall"]
    assert m["ok"] is False and "mall-scan.json 없음" in m["error"] and res["meta"]["sources"]["hobby_schedule"]["ok"] is True
    goods = {"100": good("HG 테스트기A", 14300), "200": good("30MS 다른 상품", 4000)}
    target = seed_linkable(tmp_path)
    write_snap(tmp_path, snap_doc(goods))
    go(w, tmp_path, Options(max_new=5, max_backlog=5))
    assert all_items(tmp_path)[target].get("mallGno") == "100", "스냅샷이 연결되어야 아래 판정을 볼 수 있다"
    rest = {k: v for k, v in goods.items() if k != "100"}
    # PC가 차단된 날: 마지막 스냅샷을 그대로 쓰고, 경고가 meta에 남는다
    write_snap(tmp_path, snap_doc(goods, blocked=True))
    res2, *_ = go(w, tmp_path, Options(max_new=5, max_backlog=5), now=PIPE_NOW + timedelta(days=1))
    m2 = res2["meta"]["sources"]["mall"]
    assert m2["ok"] is False and m2["blocked"] is True and "차단" in m2["error"] and "mallEnded" not in all_items(tmp_path)[target]
    # 스냅샷에서 연결된 상품이 빠졌어도 8일 지난 스냅샷이면 판매 종료로 판정하지 않는다 (경고 + 가격은 그대로, 사이트가 "가격 확인 날짜"를 보인다)
    write_snap(tmp_path, snap_doc(rest, at="2026-09-28T06:30:00+09:00"))
    res3, *_ = go(w, tmp_path, Options(max_new=5, max_backlog=5))
    m3 = res3["meta"]["sources"]["mall"]
    assert m3["ok"] is False and m3["stale"] is True and m3["snapshotAgeDays"] == 8 and "8일 지남" in m3["error"]
    it = all_items(tmp_path)[target]
    assert "mallEnded" not in it and it["priceKrw"] == 14300
    # 대조: 같은 내용이 최신 스냅샷이면 판매 종료로 표시된다
    write_snap(tmp_path, snap_doc(rest | {"300": good("HG 다른 새 상품", 100)}, at=SNAP))
    go(w, tmp_path, Options(max_new=5, max_backlog=5))
    assert all_items(tmp_path)[target].get("mallEnded") is True


def test_only_mall_runs_just_the_mall_stage_and_robots_blocked_paths_are_not_requested():
    assert Options(only={"mall"}).stages() == {"mall"} and "mall" in Options().stages()
    client, sess, _ = make_client({config.MALL_BASE + "/robots.txt": "User-agent: *\nDisallow: /goods/\n"})
    with pytest.raises(Blocked):                      # robots.txt가 막은 경로는 열지 않는다 (파이프라인은 이 소스만 "중단"으로 기록하고 계속한다)
        mall.scan(client)
    assert not [c for c in sess.calls if "category.do" in c["url"]]


def test_user_confirmed_overrides_exist_and_point_at_real_catalog_items():
    cat = {i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json") for i in json.loads((config.DATA_DIR / f).read_text(encoding="utf-8"))["items"]}
    ov = {g: t for g, t in config.MALL_OVERRIDES.items() if t}
    assert {"7223664", "56457", "59201", "68326863", "48650462", "33247684"} <= set(ov)
    for gno, cid in ov.items():
        assert gno.isdigit() and cid in cat, (gno, cid)
    assert len(set(ov.values())) == len(ov), "한 카탈로그 항목에 몰 상품 하나"


def test_override_replaces_an_automatic_link_to_the_same_catalog_item():
    cat = cat_of(item("bh-1", "HG 1/144 건담 레오파드"))
    st, _ = run_link(cat, {"100": good("HG 건담 레오파드")})
    assert st.links["100"]["method"] == "fuzzy"
    config.MALL_OVERRIDES["200"] = "bh-1"
    try:
        st, rep = run_link(cat, {"100": good("HG 건담 레오파드"), "200": good("HG 건담 레오파드 다른 표기")}, st, now=LATER)
    finally:
        config.MALL_OVERRIDES.pop("200", None)
    assert list(st.links) == ["200"] and st.links["200"]["method"] == "override" and cat.items["bh-1"]["mallGno"] == "200"
