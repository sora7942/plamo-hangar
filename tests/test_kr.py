"""kr.py — 재매칭으로 나중에 연결, codeMap 기억, (post, code) 중복, 60일 규칙, nameKo 교체/되돌리기, 사람이 고치는 표, 피드 N일·알림 N일."""
import copy
import json
from datetime import date

import pytest

from crawler import config, kr
from crawler.catalog import Catalog

NOW = "2026-10-06T09:00:00+09:00"
TODAY = date(2026, 10, 6)
RED = "[HGGQX04] 1/144 붉은 건담(RED GUNDAM) - 기동전사 건담 지쿠악스(프라모델)"
IMG = "https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"


def item(cid="bh-01_1", grade="HG", scale="1/144", name_ko="HG 1/144 붉은건담", release=None, line="gunpla", images=None):
    return {"id": cid, "line": line, "grade": grade, "scale": scale, "nameKo": name_ko, "nameJa": name_ko, "release": release,
            "kr": [], "images": images or [], "updated": "2026-01-01T00:00:00+09:00"}


def catalog(*items):
    c = Catalog()
    for it in items:
        c.items[it["id"]] = it
    return c


def arrivals(*posts):
    """posts: (글번호, 글 날짜, 제목, 재입고 문구, [(코드, 이름, 가격)])"""
    a = kr.Arrivals()
    for pid, d, title, restock, rows in posts:
        assert a.note_board_row({"id": pid, "date": d, "title": title})
        a.record_post(pid, {"restock": restock, "rows": [{"code": c, "name": n, "price": p} for c, n, p in rows]})
    return a


POST = ("100", "2026-10-02", "10/3(토) 판매예정 반다이 제품리스트 안내", False, [("BD5000001", RED, 27500)])


# ---------------------------------------------------------------- 재매칭으로 나중에 연결
def test_unlinked_rows_are_relinked_when_the_catalog_fills_up_later():
    a = arrivals(POST)
    cat = catalog()
    rep = kr.link_all(a, cat, NOW)
    assert rep["newLinks"] == [] and rep["unlinkedCodes"] == 1 and a.code_map == {} and rep["reasons"] == {"no-candidates": 1}

    cat.items["bh-01_1"] = item(release={"month": "2026-06"})            # 상세가 나중에 채워졌다
    rep = kr.link_all(a, cat, NOW)
    assert [n["catalogId"] for n in rep["newLinks"]] == ["bh-01_1"] and rep["krAdded"] == 1
    assert a.code_map["BD5000001"]["method"] == "fuzzy" and a.code_map["BD5000001"]["score"] == 100
    assert cat.items["bh-01_1"]["kr"] == [{"date": "2026-10-03", "type": "restock", "source": "joyhobby", "post": "100",
                                           "code": "BD5000001", "priceKrw": 27500, "seenAt": NOW}]

    before = copy.deepcopy((a.code_map, cat.items))
    rep = kr.link_all(a, cat, "2026-10-07T09:00:00+09:00")                # 다시 돌려도 달라지는 것이 없다
    assert rep["newLinks"] == [] and rep["krAdded"] == 0 and (a.code_map, cat.items) == before


def test_known_code_links_directly_to_later_posts_even_if_the_name_differs():
    a = arrivals(POST)
    cat = catalog(item(release={"month": "2026-06"}))
    kr.link_all(a, cat, NOW)
    a.note_board_row({"id": "101", "date": "2026-10-09", "title": "10/10(토) 반다이 입고리스트"})
    a.record_post("101", {"restock": False, "rows": [{"code": "BD5000001", "name": "[HG] 완전히 다른 표기 xyz", "price": 28600}]})
    rep = kr.link_all(a, cat, "2026-10-09T09:00:00+09:00")
    assert rep["newLinks"] == [] and rep["krAdded"] == 1                  # 퍼지 매칭 없이 코드로 연결
    assert [(k["post"], k["date"], k["priceKrw"]) for k in cat.items["bh-01_1"]["kr"]] == [("100", "2026-10-03", 27500), ("101", "2026-10-10", 28600)]


def test_same_post_and_code_is_recorded_once_even_if_the_post_is_recorded_twice():
    a = arrivals(POST)
    a.record_post("100", {"restock": False, "rows": [{"code": "BD5000001", "name": RED, "price": 27500}]})     # 같은 글을 두 번 반영해도
    assert len(a.rows) == 1
    cat = catalog(item(release={"month": "2026-06"}))
    kr.link_all(a, cat, NOW)
    kr.link_all(a, cat, NOW)
    assert len(cat.items["bh-01_1"]["kr"]) == 1


def test_kr_entries_are_never_removed_when_the_item_changes_or_a_row_disappears():
    a = arrivals(POST)
    cat = catalog(item(release={"month": "2026-06"}))
    kr.link_all(a, cat, NOW)
    a.rows.clear()                                                          # 원본 행이 없어져도 이미 쌓은 kr은 남는다
    kr.link_all(a, cat, NOW)
    assert len(cat.items["bh-01_1"]["kr"]) == 1


# ---------------------------------------------------------------- 60일 규칙
@pytest.mark.parametrize("release,kr_date,restock,expected", [
    ({"month": "2026-06", "date": "2026-06-20"}, "2026-08-18", True, "new"),          # 59일 뒤 (재입고 문구가 있어도 발매일이 우선)
    ({"month": "2026-06", "date": "2026-06-20"}, "2026-08-19", False, "restock"),     # 정확히 60일
    ({"month": "2026-08"}, "2026-10-29", False, "new"),                               # 월만 알면 그 달 마지막 날(8/31) 기준: 59일
    ({"month": "2026-08"}, "2026-10-30", False, "restock"),                           # 60일
    ({"month": "2026-10", "date": "2026-10-24"}, "2026-10-03", False, "new"),         # 발매 전 입고
    (None, "2026-10-03", True, "restock"),                                            # 발매일을 모르면 글의 "재입고" 문구
    (None, "2026-10-03", False, "new"),
])
def test_kr_type_rule(release, kr_date, restock, expected):
    assert kr.kr_type(release, kr_date, restock) == expected


def test_restock_flag_of_the_post_decides_when_release_is_unknown():
    a = arrivals(("100", "2026-10-02", "10/3(토) 반다이 재입고 리스트", True, [("BD5000001", RED, 1)]))
    cat = catalog(item(release=None))
    kr.link_all(a, cat, NOW)
    assert cat.items["bh-01_1"]["kr"][0]["type"] == "restock"


# ---------------------------------------------------------------- kr.date: 판매예정일 / 글 날짜
def test_kr_date_is_sale_date_from_title_with_post_date_stored_separately():
    a = arrivals(POST, ("101", "2026-01-01", "6/30(화) 반다이 입고리스트", False, [("BD5000002", "[HG] 1/144 나", 1)]),
                 ("102", "2024-07-04", "금주 반다이 입고 및 판매일정 안내", False, [("BD5000003", "[HG] 1/144 다", 1)]))
    assert a.posts["100"]["sale"] == "2026-10-03" and a.kr_date("100") == "2026-10-03"
    assert a.posts["101"]["sale"] is None and a.kr_date("101") == "2026-01-01"       # 60일 넘게 차이 → 글 날짜
    assert a.kr_date("102") == "2024-07-04"
    assert {r["post"]: r["postDate"] for r in a.rows} == {"100": "2026-10-02", "101": "2026-01-01", "102": "2024-07-04"}


# ---------------------------------------------------------------- nameKo 교체 / 되돌리기
def test_name_ko_is_replaced_only_above_the_stricter_threshold_and_ai_name_is_kept():
    a = arrivals(POST)
    cat = catalog(item())
    rep = kr.link_all(a, cat, NOW)
    it = cat.items["bh-01_1"]
    assert rep["nameChanged"] == 1 and it["nameKo"] == "HG 1/144 붉은 건담" and it["nameKoAi"] == "HG 1/144 붉은건담"
    assert it["nameKoSource"] == "joyhobby" and a.code_map["BD5000001"]["nameApplied"] is True and it["updated"] == NOW
    assert kr.link_all(a, cat, "2026-10-07T00:00:00+09:00")["nameChanged"] == 0           # 한 번만


def test_link_tier_alone_does_not_touch_name_ko(monkeypatch):
    monkeypatch.setattr(config, "MATCH_NAME_SCORE", 101)
    a = arrivals(POST)
    cat = catalog(item())
    rep = kr.link_all(a, cat, NOW)
    it = cat.items["bh-01_1"]
    assert len(rep["newLinks"]) == 1 and rep["nameChanged"] == 0
    assert it["nameKo"] == "HG 1/144 붉은건담" and "nameKoSource" not in it and "nameKoAi" not in it


def test_first_joy_name_wins_and_translation_never_overwrites_it():
    from crawler.translate import translate_pending

    a = arrivals(POST)
    cat = catalog(item(name_ko=None))                                       # 아직 번역되지 않은 항목도 연결·교체된다 (nameKoAi는 null)
    cat.items["bh-01_1"]["nameJa"] = "HG 1/144 レッドガンダム"
    kr.link_all(a, cat, NOW)
    it = cat.items["bh-01_1"]
    # nameKo가 없으면 후보에서 빠지므로 이 항목은 연결되지 않는다 (번역 후에야 후보가 된다)
    assert it["nameKo"] is None and a.code_map == {}
    it["nameKo"] = "HG 1/144 붉은건담"
    kr.link_all(a, cat, NOW)
    assert it["nameKoSource"] == "joyhobby"
    assert cat.untranslated(10) == []

    class Boom:                                                             # 번역 대상이 아니므로 호출되면 안 된다
        class messages:
            @staticmethod
            def create(**kw):
                raise AssertionError("조이하비 한글명 항목은 번역하지 않는다")
    assert translate_pending(cat, NOW, client=Boom())["done"] == 0


# ---------------------------------------------------------------- 사람이 고치는 표
def test_override_none_blocks_the_link_reverts_name_and_removes_its_kr(monkeypatch):
    a = arrivals(POST)
    cat = catalog(item(release={"month": "2026-06"}))
    kr.link_all(a, cat, NOW)
    it = cat.items["bh-01_1"]
    assert it["nameKoSource"] == "joyhobby" and len(it["kr"]) == 1

    monkeypatch.setitem(config.KR_CODE_OVERRIDES, "BD5000001", None)
    rep = kr.link_all(a, cat, "2026-10-07T09:00:00+09:00")
    assert rep["nameReverted"] == 1 and rep["krRemoved"] == 1 and a.code_map == {}
    assert it["nameKo"] == "HG 1/144 붉은건담" and "nameKoSource" not in it and "nameKoAi" not in it and it["kr"] == []
    rep = kr.link_all(a, cat, "2026-10-08T09:00:00+09:00")                  # 그 뒤로도 다시 연결되지 않는다
    assert rep["newLinks"] == [] and a.code_map == {} and it["kr"] == []


def test_override_target_forces_the_link_and_moves_it_from_a_wrong_item(monkeypatch):
    a = arrivals(POST)
    cat = catalog(item("bh-01_1", release={"month": "2026-06"}), item("bh-01_2", name_ko="HG 1/144 다른 상품", release={"month": "2026-06"}))
    kr.link_all(a, cat, NOW)
    assert a.code_map["BD5000001"]["catalogId"] == "bh-01_1" and len(cat.items["bh-01_1"]["kr"]) == 1

    monkeypatch.setitem(config.KR_CODE_OVERRIDES, "BD5000001", "bh-01_2")
    rep = kr.link_all(a, cat, "2026-10-07T09:00:00+09:00")
    e = a.code_map["BD5000001"]
    assert e["catalogId"] == "bh-01_2" and e["method"] == "override" and e["score"] is None
    assert cat.items["bh-01_1"]["kr"] == [] and cat.items["bh-01_1"]["nameKo"] == "HG 1/144 붉은건담" and "nameKoSource" not in cat.items["bh-01_1"]
    assert len(cat.items["bh-01_2"]["kr"]) == 1 and cat.items["bh-01_2"]["nameKoSource"] == "joyhobby"     # 사람이 확인한 연결은 이름 교체도 허용
    assert cat.items["bh-01_2"]["nameKoAi"] == "HG 1/144 다른 상품" and rep["overrides"] == 1


def test_override_to_a_missing_catalog_item_is_ignored_until_it_exists(monkeypatch):
    monkeypatch.setitem(config.KR_CODE_OVERRIDES, "BD5000001", "bh-01_9")
    a = arrivals(POST)
    cat = catalog()
    kr.link_all(a, cat, NOW)
    assert a.code_map == {}


def test_link_to_an_item_that_left_the_catalog_is_dropped_and_rematched():
    a = arrivals(POST)
    cat = catalog(item("bh-01_1"))
    kr.link_all(a, cat, NOW)
    del cat.items["bh-01_1"]                                                # 재분류로 제외 목록으로 옮겨졌다
    cat.items["bh-01_5"] = item("bh-01_5", name_ko="HG 1/144 붉은 건담")
    rep = kr.link_all(a, cat, NOW)
    assert rep["staleDropped"] == 1 and a.code_map["BD5000001"]["catalogId"] == "bh-01_5"


# ---------------------------------------------------------------- 피드
def test_feed_items_cover_only_the_last_30_days_and_notify_only_the_last_3():
    a = arrivals(("300", "2026-10-05", "10/6(화) 반다이 제품리스트", False, [("BD5000001", RED, 27500), ("BD5000009", "[MG] 1/100 어딘가 없는 기체", 1)]),
                 ("200", "2026-09-26", "9/27(토) 반다이 재입고 리스트", True, [("BD5000002", "[RG] 1/144 없는 기체", 2)]),
                 ("100", "2026-08-27", "8/28(금) 반다이 입고리스트", False, [("BD5000003", "[HG] 1/144 옛날 기체", 3)]))
    cat = catalog(item(images=[IMG], release={"month": "2026-01"}))
    kr.link_all(a, cat, NOW)
    items, notify = kr.feed_items(a, cat, TODAY, NOW)
    by_id = {i["id"]: i for i in items}
    assert set(by_id) == {"jh-300-BD5000001", "jh-300-BD5000009", "jh-200-BD5000002"}          # 40일 전 글은 피드에 오지 않는다
    assert notify == {"jh-300-BD5000001", "jh-300-BD5000009"}                                  # 5일 전 글은 알림 대상이 아니다
    linked, unlinked, old = by_id["jh-300-BD5000001"], by_id["jh-300-BD5000009"], by_id["jh-200-BD5000002"]
    assert linked == {"id": "jh-300-BD5000001", "type": "kr-restock", "date": "2026-10-06", "added": NOW, "catalogId": "bh-01_1",
                      "title": RED, "titleKo": "HG 1/144 붉은 건담",
                      "url": "https://www.joyhobby.co.kr/mall/board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID=300",
                      "image": IMG, "source": "joyhobby"}
    assert unlinked["catalogId"] is None and unlinked["image"] is None and unlinked["type"] == "kr-new"     # 연결 안 된 항목도 피드에 들어간다
    assert old["type"] == "kr-restock" and old["titleKo"] == "RG 1/144 없는 기체" and old["date"] == "2026-09-27"


def test_feed_window_and_notify_window_come_from_config(monkeypatch):
    monkeypatch.setattr(config, "KR_FEED_DAYS", 5)
    monkeypatch.setattr(config, "KR_NOTIFY_DAYS", 0)
    a = arrivals(("300", "2026-10-06", "10/6 반다이", False, [("BD5000001", RED, 1)]), ("200", "2026-10-01", "10/1 반다이", False, [("BD5000002", RED + "2", 1)]),
                 ("100", "2026-09-30", "9/30 반다이", False, [("BD5000003", RED + "3", 1)]))
    items, notify = kr.feed_items(a, catalog(), TODAY, NOW)
    assert {i["id"] for i in items} == {"jh-300-BD5000001", "jh-200-BD5000002"} and notify == {"jh-300-BD5000001"}


def test_refresh_feed_fills_link_image_and_type_later_without_touching_added():
    a = arrivals(POST)
    cat = catalog()
    kr.link_all(a, cat, NOW)
    items, _ = kr.feed_items(a, cat, TODAY, "2026-10-06T09:00:00+09:00")
    feed = [dict(i, added="2026-10-02T21:00:00+09:00") for i in items]
    assert feed[0]["catalogId"] is None and feed[0]["image"] is None and feed[0]["type"] == "kr-new"
    assert kr.refresh_feed(feed, a, cat) == 0

    cat.items["bh-01_1"] = item(images=[IMG], release={"month": "2026-06"})
    kr.link_all(a, cat, "2026-10-07T09:00:00+09:00")
    assert kr.refresh_feed(feed, a, cat) == 1
    assert (feed[0]["catalogId"], feed[0]["image"], feed[0]["type"], feed[0]["added"]) == ("bh-01_1", IMG, "kr-restock", "2026-10-02T21:00:00+09:00")
    assert kr.refresh_feed(feed, a, cat) == 0


# ---------------------------------------------------------------- 상태 파일
def test_arrivals_file_roundtrip_and_updated_at_is_kept_when_nothing_changed(tmp_path):
    a = arrivals(POST)
    kr.link_all(a, catalog(item()), NOW)
    a.save(tmp_path, NOW)
    first = (tmp_path / config.KR_ARRIVALS_FILE).read_bytes()
    b = kr.Arrivals.load(tmp_path)
    assert (b.posts, b.rows, b.code_map) == (a.posts, a.rows, a.code_map)
    b.save(tmp_path, "2026-10-09T09:00:00+09:00")
    assert (tmp_path / config.KR_ARRIVALS_FILE).read_bytes() == first               # 바뀐 게 없으면 파일이 그대로
    b.note_board_row({"id": "101", "date": "2026-10-09", "title": "반다이 입고"})
    b.save(tmp_path, "2026-10-09T09:00:00+09:00")
    assert json.loads((tmp_path / config.KR_ARRIVALS_FILE).read_text(encoding="utf-8"))["updatedAt"] == "2026-10-09T09:00:00+09:00"


def test_note_board_row_ignores_non_candidates_known_posts_and_rows_without_date():
    a = kr.Arrivals()
    assert not a.note_board_row({"id": "1", "date": "2026-10-01", "title": "26년 10월 무이자할부 안내"})
    assert not a.note_board_row({"id": "2", "date": None, "title": "반다이 제품리스트"})
    assert a.note_board_row({"id": "3", "date": "2026-10-01", "title": "프라모델 신제품 입고안내"})
    assert not a.note_board_row({"id": "3", "date": "2026-10-01", "title": "프라모델 신제품 입고안내"})
    assert list(a.posts) == ["3"] and a.posts["3"]["state"] == "pending"


def test_post_failures_pending_order_and_give_up():
    a = kr.Arrivals()
    for pid, d in (("1", "2026-09-01"), ("3", "2026-10-01"), ("2", "2026-10-01")):
        a.note_board_row({"id": pid, "date": d, "title": "반다이 입고"})
    assert a.pending(10) == ["3", "2", "1"] and a.pending(2) == ["3", "2"]             # 최신 글 먼저, 같은 날은 번호 큰 것 먼저
    a.record_failure("1", 404)
    assert a.posts["1"]["state"] == "gone"
    for _ in range(config.JOY_POST_MAX_FAILURES - 1):
        a.record_failure("2", 500)
    assert a.posts["2"]["state"] == "pending" and a.posts["2"]["fails"] == 2
    a.record_failure("2", None)
    assert a.posts["2"]["state"] == "error" and a.pending(10) == ["3"]
    a.record_post("3", {"restock": False, "rows": []})
    assert a.posts["3"]["state"] == "no-bd" and a.posts["3"]["rows"] == 0 and a.rows == []


def test_name_replacement_keeps_the_sub_line_prefix_of_the_existing_translation():
    """HGUC·HGBD 같은 하위 라인 표기는 grade(HG)로 뭉개지지 않는다. 이름이 이미 등급 낱말로 시작하면 앞에 또 붙이지 않는다."""
    rows = [("BD5000001", "[HGUC206] 1/144 MS-08TX/S 이프리트 슈나이드(EFREET SCHNEID) - 기동전사 건담 UC(프라모델)", 1),
            ("BD5000002", "[HGBD014] 건담 더블오 스카이(Gundam OO Sky) - 건담 빌드 다이버즈(프라모델)", 1),
            ("BD5000003", "[SDCS] SD건담 크로스실루엣 크로스본 건담 X1(프라모델)", 1),
            ("BD5000004", "[BB172] BB전사 호검 건담(프라모델)", 1)]
    a = arrivals(("100", "2026-10-02", "10/3 반다이 제품리스트", False, rows))
    cat = catalog(item("e", "HG", "1/144", "HGUC 1/144 이프리트 슈나이드"), item("s", "HG", "1/144", "HGBD 1/144 건담 더블오 스카이"),
                  item("c", "SDCS", None, "SD건담 크로스 실루엣 크로스본 건담 X1"), item("b", "BB", None, "BB전사 호검 건담"))
    kr.link_all(a, cat, NOW)
    assert cat.items["e"]["nameKo"] == "HGUC 1/144 MS-08TX/S 이프리트 슈나이드"
    assert cat.items["s"]["nameKo"] == "HGBD 1/144 건담 더블오 스카이"
    assert cat.items["c"]["nameKo"] == "SD건담 크로스실루엣 크로스본 건담 X1"
    assert cat.items["b"]["nameKo"] == "BB전사 호검 건담"
    assert cat.items["e"]["nameKoAi"] == "HGUC 1/144 이프리트 슈나이드"


# ---------------------------------------------------------------- nameKo 교체는 gunpla만
GIRL_ROW = ("100", "2026-10-02", "10/3(토) 판매예정 반다이 제품리스트 안내", False,
            [("BD5000011", "[30MS] 옵션 파츠 세트17 에이더 코스튬 컬러A - 아이돌마스터 샤이니 컬러즈(프라모델)", 5500)])


def girl_item():
    return item("g1", "30MS", None, "30MS 옵션 파츠 세트17(에이더 코스튬)[컬러A]", line="girl", release={"month": "2024-03"})


def test_girl_items_are_linked_and_get_kr_but_keep_their_translation():
    a = arrivals(GIRL_ROW)
    cat = catalog(girl_item())
    rep = kr.link_all(a, cat, NOW)
    it = cat.items["g1"]
    assert a.code_map["BD5000011"]["catalogId"] == "g1" and a.code_map["BD5000011"]["nameOk"] is True       # 연결되고 이름 기준도 넘었지만
    assert rep["nameChanged"] == 0 and it["nameKo"] == "30MS 옵션 파츠 세트17(에이더 코스튬)[컬러A]"           # 번역은 그대로
    assert "nameKoSource" not in it and "nameKoAi" not in it and a.code_map["BD5000011"]["nameApplied"] is False
    assert [(k["post"], k["code"], k["type"]) for k in it["kr"]] == [("100", "BD5000011", "restock")]        # kr은 쌓인다
    items, _ = kr.feed_items(a, cat, TODAY, NOW)
    assert items[0]["catalogId"] == "g1"                                                                    # 피드 연결도 그대로


def test_girl_names_already_replaced_are_reverted_to_the_ai_translation():
    a = arrivals(GIRL_ROW)
    cat = catalog(dict(girl_item(), nameKo="30MS 옵션 파츠 세트17 에이더 코스튬 컬러A", nameKoAi="30MS 옵션 파츠 세트17(에이더 코스튬)[컬러A]", nameKoSource="joyhobby"))
    a.code_map["BD5000011"] = {"catalogId": "g1", "method": "fuzzy", "score": 100.0, "margin": 100.0, "nameOk": True, "nameApplied": True,
                               "post": "100", "at": NOW}
    rep = kr.link_all(a, cat, "2026-10-07T09:00:00+09:00")
    it = cat.items["g1"]
    assert rep["nameReverted"] == 1 and it["nameKo"] == "30MS 옵션 파츠 세트17(에이더 코스튬)[컬러A]"
    assert "nameKoSource" not in it and "nameKoAi" not in it and a.code_map["BD5000011"]["nameApplied"] is False
    assert len(it["kr"]) == 1                                                                                # 연결·kr은 유지
    assert kr.link_all(a, cat, "2026-10-08T09:00:00+09:00")["nameReverted"] == 0 and it["nameKo"].endswith("[컬러A]")   # 다시 바뀌지 않는다


def test_override_does_not_force_name_replacement_on_girl_items(monkeypatch):
    monkeypatch.setitem(config.KR_CODE_OVERRIDES, "BD5000011", "g1")
    a = arrivals(GIRL_ROW)
    cat = catalog(girl_item())
    kr.link_all(a, cat, NOW)
    assert a.code_map["BD5000011"]["method"] == "override" and cat.items["g1"]["nameKo"].endswith("[컬러A]") and len(cat.items["g1"]["kr"]) == 1
