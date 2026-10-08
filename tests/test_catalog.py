"""catalog.py — 분류, 병합, 상세 확정, 밀린 상품 선택, 저장."""
import json

import pytest

from crawler import config
from crawler.catalog import (Catalog, classify_brand_keys, classify_title, extract_scale, merge_release,
                             release_key)
from conftest import FIXTURES

NOW = "2026-10-06T09:00:00+09:00"
LATER = "2026-10-07T09:00:00+09:00"


def card(num="01_7001", name="HG 1/144 テスト機", month="2026-10", date=None, channel="general", pb=False, price=1100):
    rel = {"month": month, **({"date": date} if date else {})}
    cid = f"pb-{num}" if pb else f"bh-{num}"
    url = f"https://p-bandai.jp/item/{num}/" if pb else f"https://bandai-hobby.net/item/{num}/"
    return {"id": cid, "url": url, "nameJa": name, "priceJpy": price, "channel": channel,
            "pbUrl": url if pb else None, "release": rel}


def detail(name="HG 1/144 テスト機", keys=("hg",), images=("https://bandai-a.akamaihd.net/bc/img/model/xl/9_1.jpg",), **kw):
    return {"nameJa": name, "priceJpy": 1320, "release": {"month": "2026-10", "date": "2026-10-24"},
            "brandKeys": list(keys), "seriesKey": "g-witch", "series": "水星の魔女", "pbUrl": None,
            "images": list(images), **kw}


# ---------------------------------------------------------------- 분류표
def test_brand_table_classifies_all_77_filter_keys_and_nothing_extra():
    keys = [b["value"].lower() for b in json.loads((FIXTURES / "hobby-brand-filters.json").read_text(encoding="utf-8"))["brand"]]
    assert len(keys) == 77
    assert set(keys) == set(config.BRAND_LINE), "분류표와 호비사이트 필터 키가 어긋남"


def test_brand_groups_do_not_overlap_and_girl_is_the_four_user_keys():
    groups = [config.GUNPLA_CONFIRMED, config.GUNPLA_TENTATIVE, config.GIRL, config.EXCLUDED_CANDIDATES,
              config.EXCLUDED_ACCESSORY, config.EXCLUDED_OTHER]
    assert sum(len(g) for g in groups) == len(config.BRAND_LINE) == 77
    assert set(config.GIRL) == {"30ms", "30mp", "figurerise-standard", "figurerise-standard-amp"} == set(config.GIRL_BRANDS)


@pytest.mark.parametrize("keys,expect", [
    (["hg"], ("gunpla", "HG", [])),
    (["hg", "pb_gunpla", "pb_hg"], ("gunpla", "HG", [])),
    (["pb_gunpla"], ("gunpla", None, [])),                    # 등급은 상품명 앞 토큰에서
    (["SDEX"], ("gunpla", "SDEX", [])),                       # 대소문자 무시
    (["30ms"], ("girl", "30MS", [])),
    (["figurerise-bust"], (None, None, [])),                  # 제외 (걸프라로 옮겼다가 다시 제외로 돌림)
    (["hg", "30ms"], ("girl", "30MS", [])),                   # girl 우선
    (["claymonsters"], (None, None, [])),
    (["gundam_decal", "hg"], ("gunpla", "HG", [])),           # 대상 키가 하나라도 있으면 대상
    (["brand-new-key"], (None, None, ["brand-new-key"])),     # 사전에 없는 키는 제외 + unknown
    ([], (None, None, [])),
])
def test_classify_brand_keys(keys, expect):
    assert classify_brand_keys(keys) == expect


@pytest.mark.parametrize("title,expect", [
    ("HG 1/144 ガンダムエアリアル", ("gunpla", "HG")),
    ("ＨＧ 1/144 レッドライダー", ("gunpla", "HG")),             # 전각
    ("ＭＧ 1/100 ガンダムＭｋ-Ｖ(連邦カラー)", ("gunpla", "MG")),
    ("MGSD クシャトリヤ", ("gunpla", "MGSD")),
    ("RE/100 ガンキャノン", ("gunpla", "RE/100")),
    ("SDガンダム EXスタンダード ガンダムエアリアル", ("gunpla", "SDEX")),
    ("SDW HEROES ダークグラスパードラゴン", ("gunpla", "SD")),
    ("30MS SIS-E00 ミャスティ[カラーC]", ("girl", "30MS")),
    ("30 MINUTES SISTERS フレキシブルシール", ("girl", "30MS")),
    ("Figure-rise Standard Amplified マグナガルルモン", ("girl", "Figure-rise Standard Amplified")),
    ("Figure-riseBust テストキャラ", (None, None)),             # bust는 제목으로도 걸프라로 판정하지 않는다
    ("Figure-rise Bust テストキャラ", (None, None)),
    ("Figure-rise Standard 孫悟空 (NEW SPEC Ver.)", ("girl", "Figure-rise Standard")),
    ("ドラゴンクエストねんどモンスターズ スライム", (None, None)),
    ("1/1000宇宙戦艦ヤマト3199 デラックスセット", (None, None)),
    ("30MM 1/144 エグザビークル", (None, None)),               # 30MM은 걸프라가 아니다
])
def test_classify_title(title, expect):
    assert classify_title(title) == expect


@pytest.mark.parametrize("title,expect", [("HG 1/144 ガンダム", "1/144"), ("ＨＧ 1/144 ガンダム", "1/144"),
                                          ("1/1000宇宙戦艦ヤマト3199", "1/1000"), ("RE/100 ガンキャノン", None),
                                          ("MGSD クシャトリヤ", None), ("PG 1/60 ユニコーン", "1/60")])
def test_extract_scale(title, expect):
    assert extract_scale(title) == expect


def test_merge_release_rules():
    month, day, nxt = {"month": "2026-10"}, {"month": "2026-10", "date": "2026-10-17"}, {"month": "2027-01"}
    assert merge_release(month, day, authoritative=False) == day          # 같은 달이면 날짜가 있는 쪽
    assert merge_release(day, month, authoritative=False) == day
    assert merge_release(month, nxt, authoritative=False) == nxt          # 카드가 더 늦은 달 = 연기
    assert merge_release(nxt, month, authoritative=False) == nxt          # 과거 달 카드가 덮어쓰지 않는다
    assert merge_release(nxt, month, authoritative=True) == month         # 상세는 권위가 있다
    assert merge_release(None, day, authoritative=False) == day and merge_release(day, None, authoritative=False) == day
    assert release_key({"month": "2026-10"}) == "2026-10-00" and release_key(day) == "2026-10-17" and release_key(None) == ""


# ---------------------------------------------------------------- 카드 반영
def test_new_card_becomes_provisional_item_by_title():
    cat = Catalog()
    item, is_new = cat.upsert_card(card(), NOW)
    assert is_new and item["line"] == "gunpla" and item["grade"] == "HG" and item["scale"] == "1/144"
    assert item["detailAt"] is None and item["firstSeen"] == NOW and item["nameKo"] is None and item["images"] == []
    assert item["brandKeys"] == [] and item["kr"] == []


def test_unmatched_title_is_pending_and_pb_unmatched_is_excluded():
    cat = Catalog()
    item, _ = cat.upsert_card(card("01_7002", "ドラゴンクエストねんどモンスターズ スライム"), NOW)
    assert item["line"] is None
    none_item, new = cat.upsert_card(card("item-1000253221", "ねんどろいど なにか", pb=True, channel="online"), NOW)
    assert none_item is None and not new and cat.excluded["pb-item-1000253221"] == "title-no-match"
    ok, new = cat.upsert_card(card("item-1000253222", "ＭＧ 1/100 ガンダムＭｋ-Ｖ", pb=True, channel="online"), NOW)
    assert new and ok["line"] == "gunpla" and ok["id"] == "pb-item-1000253222" and ok["pbUrl"] == ok["url"]


def test_second_sighting_is_not_new_and_keeps_first_seen():
    cat = Catalog()
    cat.upsert_card(card(month="2026-10"), NOW)
    item, is_new = cat.upsert_card(card(month="2026-10", date="2026-10-24"), LATER)
    assert not is_new and item["firstSeen"] == NOW
    assert item["release"] == {"month": "2026-10", "date": "2026-10-24"} and item["updated"] == LATER


def test_excluded_ids_are_never_recreated():
    cat = Catalog()
    cat.excluded["bh-01_7001"] = "brand:claymonsters"
    assert cat.upsert_card(card(), NOW) == (None, False) and not cat.items


def test_brand_list_card_gets_line_from_brand_key_and_title_does_not_matter():
    cat = Catalog()
    item, is_new = cat.upsert_card(card("01_7394", "スケールアトリエウエア(浴衣03)"), NOW, brand_key="30ms")
    assert is_new and item["line"] == "girl" and item["grade"] == "30MS" and item["brandKeys"] == ["30ms"]
    # 이미 임시 항목으로 있던 것에 브랜드 키가 뒤늦게 붙는 경우도 line이 확정된다
    cat.upsert_card(card("01_7395", "謎の名前"), NOW)
    item2, _ = cat.upsert_card(card("01_7395", "謎の名前"), LATER, brand_key="30mp")
    assert item2["line"] == "girl" and item2["brandKeys"] == ["30mp"]


# ---------------------------------------------------------------- 상세 확정
def test_apply_detail_confirms_and_filters_signed_urls():
    cat = Catalog()
    cat.upsert_card(card(), NOW)
    signed = "https://bandai-a.akamaihd.net/x.jpg?Expires=1&Signature=a"
    out, unknown = cat.apply_detail("bh-01_7001", detail(images=[signed, "https://bandai-hobby.net/images/153_1_s_a.jpg"]), LATER)
    it = cat.items["bh-01_7001"]
    assert (out, unknown) == ("ok", []) and it["detailAt"] == LATER and it["firstSeen"] == NOW
    assert it["series"] == "水星の魔女" and it["seriesKey"] == "g-witch" and it["priceJpy"] == 1320
    assert it["release"] == {"month": "2026-10", "date": "2026-10-24"}
    assert it["images"] == ["https://bandai-hobby.net/images/153_1_s_a.jpg"]            # 서명 URL은 버린다


def test_apply_detail_moves_line_and_uses_title_token_when_brand_has_no_grade():
    cat = Catalog()
    cat.upsert_card(card("01_7003", "RG 1/144 ナニカ"), NOW)
    cat.apply_detail("bh-01_7003", detail("RG 1/144 ナニカ", keys=["pb_gunpla"]), LATER)
    assert cat.items["bh-01_7003"]["grade"] == "RG"
    cat.upsert_card(card("01_7004", "謎の機体"), NOW)                                    # 제목으로 판정 못 함 → 보류
    assert cat.items["bh-01_7004"]["line"] is None
    cat.apply_detail("bh-01_7004", detail("謎の機体", keys=["30mp"]), LATER)
    assert cat.items["bh-01_7004"]["line"] == "girl" and cat.items["bh-01_7004"]["grade"] == "30MP"


def test_apply_detail_excludes_non_target_and_reports_unknown_keys():
    cat = Catalog()
    cat.upsert_card(card("01_7005", "HG Newクルルロボ"), NOW)
    out, unknown = cat.apply_detail("bh-01_7005", detail("HG Newクルルロボ", keys=["claymonsters", "brand-new-key"]), LATER)
    assert out == "excluded" and unknown == ["brand-new-key"]
    assert "bh-01_7005" not in cat.items and cat.excluded["bh-01_7005"] == "brand:claymonsters,brand-new-key"


def test_apply_detail_without_brand_keys_falls_back_to_title():
    cat = Catalog()
    cat.upsert_card(card("01_7006", "謎の旧キット"), NOW)
    assert cat.apply_detail("bh-01_7006", detail("謎の旧キット", keys=[]), LATER)[0] == "excluded"
    cat.upsert_card(card("01_7007", "HG 1/144 旧キット"), NOW)
    assert cat.apply_detail("bh-01_7007", detail("HG 1/144 旧キット", keys=[]), LATER)[0] == "ok"


def test_detail_failures_404_excludes_others_count_up():
    cat = Catalog()
    cat.upsert_card(card("01_7008"), NOW)
    cat.upsert_card(card("01_7009"), NOW)
    cat.record_detail_failure("bh-01_7008", 404)
    assert cat.excluded["bh-01_7008"] == "detail-404" and "bh-01_7008" not in cat.items
    for _ in range(config.DETAIL_MAX_FAILURES):
        cat.record_detail_failure("bh-01_7009", 500)
    assert cat.items["bh-01_7009"]["detailFails"] == config.DETAIL_MAX_FAILURES
    assert cat.backlog_candidates() == []                                                # 여러 번 실패한 항목은 더 시도하지 않는다


# ---------------------------------------------------------------- 밀린 상품 선택
def _fill(cat, n, start=1000, month="2026-10", name="HG 1/144 机"):
    ids = []
    for i in range(n):
        item, _ = cat.upsert_card(card(f"01_{start + i}", f"{name}{i}", month=month, date=f"{month}-{(i % 28) + 1:02d}"), NOW)
        ids.append(item["id"])
    return ids


def test_select_details_caps_new_and_backlog_separately():
    cat = Catalog()
    old = _fill(cat, 200, 1000, "2024-05")                       # 이전부터 밀려 있던 것
    new = _fill(cat, 70, 5000, "2026-10")                        # 이번에 처음 본 것
    new_sel, back_sel = cat.select_details(40, 150, set(new))
    assert len(new_sel) == 40 and set(new_sel) <= set(new)
    assert len(back_sel) == 150 and not set(back_sel) & set(new_sel)
    # 새 상품이 상한을 넘으면 남은 새 상품은 밀린 쪽으로 간다 (발매일 최신순이라 old보다 먼저)
    assert set(new) - set(new_sel) <= set(back_sel)


def test_select_details_newest_release_month_first_then_provisional_lines():
    cat = Catalog()
    cat.upsert_card(card("01_8001", "謎A", month="2026-12"), NOW)                           # line 없음
    cat.upsert_card(card("01_8002", "HG 1/144 古い", month="2024-01"), NOW)
    cat.upsert_card(card("01_8003", "HG 1/144 新しい", month="2026-11"), NOW)
    _, back = cat.select_details(0, 10, set())
    assert back == ["bh-01_8001", "bh-01_8003", "bh-01_8002"]                           # 발매월 최신순 (같은 달이면 line이 있는 항목이 먼저)
    cat.upsert_card(card("01_8004", "謎B", month="2026-11"), NOW)
    _, back = cat.select_details(0, 10, set())
    assert back[:3] == ["bh-01_8001", "bh-01_8003", "bh-01_8004"]


def test_select_details_skips_pb_cards_confirmed_items_and_respects_hard_max():
    cat = Catalog()
    cat.upsert_card(card("item-1000253222", "ＭＧ 1/100 ガンダム", pb=True, channel="online"), NOW)
    ids = _fill(cat, 3)
    cat.apply_detail(ids[0], detail(), LATER)
    new, back = cat.select_details(40, 150, set())
    assert "pb-item-1000253222" not in back and ids[0] not in back and len(back) == 2
    _fill(cat, 600, 9000)
    new, back = cat.select_details(10_000, 10_000, set(cat.items))
    assert len(new) + len(back) <= config.DETAIL_HARD_MAX


# ---------------------------------------------------------------- 저장·불러오기
def test_save_splits_files_and_roundtrips(tmp_path):
    cat = Catalog()
    cat.upsert_card(card("01_7001", "HG 1/144 A"), NOW)
    cat.upsert_card(card("01_7002", "30MS B"), NOW)
    cat.upsert_card(card("01_7003", "謎"), NOW)
    cat.excluded["bh-01_9999"] = "brand:train"
    counts = cat.save(tmp_path, NOW)
    assert counts == {"catalog-gunpla.json": 1, "catalog-girl.json": 1, "catalog-pending.json": 1}
    pend = json.loads((tmp_path / "catalog-pending.json").read_text(encoding="utf-8"))
    assert pend["excluded"] == {"bh-01_9999": "brand:train"} and pend["items"][0]["id"] == "bh-01_7003"
    again = Catalog.load(tmp_path)
    assert again.items == cat.items and again.excluded == cat.excluded and not again.was_empty
    assert Catalog.load(tmp_path / "nowhere").was_empty


def test_save_keeps_updated_at_when_nothing_changed(tmp_path):
    cat = Catalog()
    cat.upsert_card(card(), NOW)
    cat.save(tmp_path, NOW)
    again = Catalog.load(tmp_path)
    again.save(tmp_path, LATER)
    assert json.loads((tmp_path / "catalog-gunpla.json").read_text(encoding="utf-8"))["updatedAt"] == NOW
    again.upsert_card(card("01_7010", "HG 1/144 B"), LATER)
    again.save(tmp_path, LATER)
    assert json.loads((tmp_path / "catalog-gunpla.json").read_text(encoding="utf-8"))["updatedAt"] == LATER


def test_saved_json_is_utf8_unescaped_and_sorted_newest_first(tmp_path):
    cat = Catalog()
    cat.upsert_card(card("01_7001", "HG 1/144 古い", month="2024-01"), NOW)
    cat.upsert_card(card("01_7002", "HG 1/144 新しい", month="2026-11"), NOW)
    cat.save(tmp_path, NOW)
    raw = (tmp_path / "catalog-gunpla.json").read_text(encoding="utf-8")
    assert "新しい" in raw and "\\u" not in raw
    assert [i["id"] for i in json.loads(raw)["items"]] == ["bh-01_7002", "bh-01_7001"]


def test_untranslated_lists_only_target_lines_without_name_ko():
    cat = Catalog()
    cat.upsert_card(card("01_7001", "HG 1/144 A"), NOW)
    cat.upsert_card(card("01_7002", "謎"), NOW)                                              # 보류 항목은 번역하지 않는다
    cat.upsert_card(card("01_7003", "HG 1/144 C"), NOW)
    cat.items["bh-01_7003"]["nameKo"] = "이미 있음"
    assert [i["id"] for i in cat.untranslated(10)] == ["bh-01_7001"]
