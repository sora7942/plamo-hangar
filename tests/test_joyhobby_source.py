"""조이하비 — EUC-KR 디코딩, 목록(고정 공지·마지막 쪽), 글 본문(BD 행), 판매예정일. 네트워크 없이 응답 원본 바이트 fixture로."""
from datetime import date

import pytest

from conftest import JOY_BOARD, JOY_POST, JOY_ROBOTS, FakeResponse, fixture_bytes, fixture_text, joy_board_html, joy_post_html, make_client
from crawler import config
from crawler.http import decode_body
from crawler.sources import joyhobby as J

EUCKR = "text/html; Charset=euc-kr"          # 실제 응답 헤더 그대로 (대문자 C)
JOY = "https://www.joyhobby.co.kr"


def raw(name: str) -> str:
    return decode_body(fixture_bytes(name), EUCKR)


# ---------------------------------------------------------------- 인코딩
def test_real_euckr_bytes_are_not_valid_utf8_but_decode_to_korean_with_header():
    data = fixture_bytes("joyhobby-raw-board-p1.html")
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")                                   # 원본 바이트는 UTF-8이 아니다 (Playwright 저장본이 아님)
    text = decode_body(data, EUCKR)
    assert "판매예정 반다이 제품리스트" in text and "�" not in text


def test_charset_falls_back_to_meta_tag_then_utf8():
    data = fixture_bytes("joyhobby-raw-board-p1.html")
    assert "판매예정 반다이 제품리스트" in decode_body(data, "text/html")        # 헤더에 charset이 없으면 <meta>
    assert "판매예정 반다이 제품리스트" in decode_body(data, None)
    assert decode_body("안녕 호비".encode("utf-8"), "text/html; charset=UTF-8") == "안녕 호비"   # 호비사이트(UTF-8)는 그대로
    assert decode_body("안녕".encode("utf-8"), None) == "안녕"                        # 아무 표시도 없으면 UTF-8
    assert decode_body("안녕".encode("utf-8"), "text/html; charset=nonsense-xx") == "안녕"   # 모르는 이름이어도 멈추지 않는다


def test_http_client_decodes_euckr_response_by_header_and_hobby_utf8_is_unchanged():
    page = FakeResponse(J.board_url(1), fixture_bytes("joyhobby-raw-board-p1.html"), headers={"Content-Type": EUCKR})
    client, sess, _ = make_client({f"{JOY}/robots.txt": JOY_ROBOTS, J.board_url(1): page,
                                   "https://bandai-hobby.net/robots.txt": "<html>x</html>",
                                   "https://bandai-hobby.net/a": FakeResponse("https://bandai-hobby.net/a", "일본어 ガンダム 한글",
                                                                              headers={"Content-Type": "text/html; charset=UTF-8"})})
    assert "판매예정 반다이 제품리스트" in client.get(J.board_url(1), "list").text
    assert client.get("https://bandai-hobby.net/a", "list").text == "일본어 ガンダム 한글"


# ---------------------------------------------------------------- 목록
def test_board_page1_drops_the_seven_pinned_notices_and_has_twenty_dated_rows():
    rows = J.parse_board_list(raw("joyhobby-raw-board-p1.html"))
    ids = [r["id"] for r in rows]
    assert len(rows) == config.JOY_BOARD_PAGE_SIZE == 20 and len(set(ids)) == 20
    assert all(r["date"] for r in rows) and ids[0] == "139506" and rows[0]["date"] == "2026-10-02"
    # 쪽마다 반복되는 고정 공지(오래된 글 4개는 일반 목록에 없다)가 섞이지 않는다
    assert not {"137658", "137474", "133641", "132529"} & set(ids)
    assert rows[0]["title"] == "10/3(토) 판매예정 반다이 제품리스트 안내" and rows[0]["category"] == "프라모델"


def test_board_last_page_has_fewer_rows_and_oldest_date():
    rows = J.parse_board_list(raw("joyhobby-raw-board-p20.html"))
    assert len(rows) == 16 < config.JOY_BOARD_PAGE_SIZE                       # 마지막 쪽은 쪽당 수보다 적다
    assert rows[-1]["date"] == "2024-01-04"


def test_candidate_title_rule_is_banda_or_ipgo():
    cands = {r["id"]: r["title"] for r in J.parse_board_list(raw("joyhobby-raw-board-p1.html")) if J.is_candidate_title(r["title"])}
    assert "139506" in cands and "139459" in cands and len(cands) == 14
    for t in ("9/6 반다이 입고예정 리스트", "금주 반다이 입고 및 판매일정 안내", "프라모델 신제품 입고안내", "[긴급공지] 12/13(토) 판매예정 반다이 제품리스트 및 판매방침 안내",
              "８/２(토) 판매예정 반다이 리스트"):
        assert J.is_candidate_title(t), t
    for t in ("(오프라인전용)구매금액대별 신도림 테크노마트 상품권 증정앵사 안내", "26년 10월 무이자할부 안내", "추석 배송일정 안내", ""):
        assert not J.is_candidate_title(t), t


def test_fetch_board_page_failure_and_empty_page_are_none():
    client, *_ = make_client({f"{JOY}/robots.txt": JOY_ROBOTS, J.board_url(1): (500, "boom"),
                              J.board_url(2): joy_board_html([]), J.board_url(3): joy_board_html([("1", "2026-10-01", "x")])})
    assert J.fetch_board_page(client, 1) is None
    assert J.fetch_board_page(client, 2) is None            # 200인데 글이 하나도 안 보이면 차단·구조 변경으로 본다
    assert [r["id"] for r in J.fetch_board_page(client, 3)] == ["1"]
    assert J.board_url(2).endswith("&nowPage=2") and "nowPage" not in J.board_url(1)


# ---------------------------------------------------------------- 글 본문
def test_post_rows_from_raw_bytes_new_format():
    p = J.parse_post(raw("joyhobby-raw-post-139506.html"))
    assert [r["code"] for r in p["rows"]] == ["BD5068558", "BD5074303", "BD5072559", "BD5074255", "BD5074276"]
    assert p["rows"][0] == {"code": "BD5068558", "price": 38500,
                            "name": "[RG42] 1/144 GF13-017NJ 샤이닝 건담(SHINING GUNDAM) - 기동무투전 G건담(프라모델)"}
    assert p["restock"] is False and "10/3(토)" in p["title"]


def test_post_older_format_price_without_comma():
    p = J.parse_post(raw("joyhobby-raw-post-135093.html"))
    assert len(p["rows"]) == 10 and p["rows"][0]["price"] == 22000 and p["rows"][0]["name"].startswith("[HGGQX02]")
    assert all(r["code"].startswith("BD") for r in p["rows"])


def test_only_bd_codes_are_kept_and_other_makers_are_ignored():
    p = J.parse_post(fixture_text("joyhobby-post-139432.html"))      # 프라모델 신제품 입고안내: ANN·PLM·AO·TMT… 반다이가 아님
    assert p["rows"] == [] and p["title"]
    mixed = J.parse_post(joy_post_html("9/1(월) 반다이 입고", "안녕하세요", [
        ("BD5000001", "[HG] 1/144 가", "19,800원"), ("KB1234567", "[X] 코토부키야", "1,000원"), ("BD5000002", "[RG] 1/144 나", "5500원")]))
    assert [(r["code"], r["price"]) for r in mixed["rows"]] == [("BD5000001", 19800), ("BD5000002", 5500)]


def test_post_parsing_is_robust_to_broken_rows_and_duplicates():
    html = joy_post_html("t", "소개", [("BD5000001", "[HG] 1/144 가", "100원"), ("BD5000001", "[HG] 1/144 가 (중복)", "100원"),
                                       ("BD5000002", "[HG] 1/144 나", "가격 미정"),      # 가격이 없는 행: 이름만 남기고 다음 행으로
                                       ("BD5000003", "BD5000004", "100원"),               # 이름 자리에 코드가 온 깨진 행은 버린다
                                       ("BD5000004", "[HG] 1/144 라", "300원")])
    rows = {r["code"]: r for r in J.parse_post(html)["rows"]}
    assert set(rows) == {"BD5000001", "BD5000002", "BD5000004"} and rows["BD5000001"]["name"] == "[HG] 1/144 가"
    assert rows["BD5000002"]["price"] is None and rows["BD5000004"]["price"] == 300


def test_restock_word_in_title_or_intro():
    assert J.parse_post(fixture_text("joyhobby-post-139459.html"))["restock"] is True       # 소개글: "반다이 재입고 제품리스트"
    assert J.parse_post(joy_post_html("재입고 안내", "소개", [("BD5000001", "a", "1원")]))["restock"] is True
    assert J.parse_post(joy_post_html("신제품", "소개", [("BD5000001", "a", "1원")]))["restock"] is False


def test_fetch_post_status_and_blocked_page():
    client, *_ = make_client({f"{JOY}/robots.txt": JOY_ROBOTS, JOY_POST.format(id="1"): joy_post_html("t", "i", [("BD5000001", "a", "1원")]),
                              JOY_POST.format(id="2"): (200, "<html>차단됨</html>")})
    assert J.fetch_post(client, "1")[0]["rows"][0]["code"] == "BD5000001"
    assert J.fetch_post(client, "2") == (None, 200, False)    # 제목을 못 찾으면 실패
    assert J.fetch_post(client, "3") == (None, 404, False)


def test_site_bug_page_is_recognised_as_permanent():
    """조회수가 smallint 범위를 넘은 글: HTTP 500 + SQL 오버플로 메시지가 든 일반 페이지 (2026-10 실제 응답에서 확인)."""
    bug = "<html><body><p>Microsoft SQL Server Native Client 11.0 오류 '80040e57' 데이터 형식 smallint에 산술 오버플로 오류가 발생했습니다.</p></body></html>"
    client, *_ = make_client({f"{JOY}/robots.txt": JOY_ROBOTS, JOY_POST.format(id="1"): (500, bug), JOY_POST.format(id="2"): (500, "<html>잠시 후 다시</html>")})
    assert J.fetch_post(client, "1") == (None, 500, True)
    assert J.fetch_post(client, "2") == (None, 500, False)    # 그냥 500은 일시 오류일 수 있어 재시도 대상


# ---------------------------------------------------------------- 판매예정일
@pytest.mark.parametrize("title,post,expected", [
    ("10/3(토) 판매예정 반다이 제품리스트 안내", date(2026, 10, 2), date(2026, 10, 3)),
    ("9/6 반다이 입고예정 리스트", date(2024, 9, 5), date(2024, 9, 6)),                       # 요일이 없어도
    ("[긴급공지] 12/13(토) 판매예정 반다이 제품리스트", date(2025, 12, 12), date(2025, 12, 13)),   # 앞의 [말머리]는 건너뜀
    ("1/3(토) 판매예정 반다이 제품리스트 안내", date(2025, 12, 30), date(2026, 1, 3)),            # 12월 글의 1월 판매는 다음 해
    ("12/28(토) 판매예정 반다이 입고리스트", date(2026, 1, 2), date(2025, 12, 28)),               # 1월 글의 12월은 지난해
    ("3/30 반다이 신제품 입고안내", date(2024, 4, 1), date(2024, 3, 30)),                        # 판매일이 글 날짜보다 앞서도
    ("6/30 반다이 입고", date(2026, 1, 1), None),                                              # 글 날짜와 60일 넘게 차이 → 글 날짜 사용
    ("2/30 반다이 입고", date(2026, 2, 28), None),                                             # 없는 날짜
    ("1/144 건담 반다이 입고", date(2026, 1, 1), None),                                         # 스케일은 날짜가 아니다
    ("금주 반다이 입고 및 판매일정 안내", date(2024, 7, 4), None),
    ("", date(2024, 7, 4), None),
])
def test_sale_date_from_title(title, post, expected):
    assert J.parse_sale_date(title, post) == expected
