"""브랜드 키가 제목 임시 판정보다 항상 우선하는지, 기존 항목 재분류, nameKo 부분 치환 — catalog.py."""
import json

from crawler import config
from crawler.catalog import Catalog
from test_catalog import LATER, NOW, card, detail


# ---------------------------------------------------------------- 분류표
def test_bust_is_excluded_by_table_and_not_in_girl_brands():
    assert config.BRAND_LINE["figurerise-bust"] == (None, None)
    assert "figurerise-bust" not in config.GIRL_BRANDS and "figurerise-bust" not in config.GIRL


# ---------------------------------------------------------------- 브랜드 키가 제목 판정보다 우선
def test_excluded_brand_key_beats_a_title_that_looks_like_a_target():
    """회귀: 브랜드 키가 제외로 분류돼도 제목이 대상처럼 보이면 제목 판정이 항목을 살리던 구멍."""
    cat = Catalog()
    item, is_new = cat.upsert_card(card("01_1096", "Figure-rise Standard 初音ミク"), NOW, brand_key="figurerise-bust")
    assert item is None and not is_new and not cat.items
    assert cat.excluded["bh-01_1096"] == "brand:figurerise-bust"
    # 제외 목록에 올랐으니 같은 카드가 다시 와도 만들지 않는다
    assert cat.upsert_card(card("01_1096", "Figure-rise Standard 初音ミク"), LATER, brand_key="figurerise-bust") == (None, False)
    # P-반다이 카드(상세 없음)도 마찬가지
    item, _ = cat.upsert_card(card("item-1000133317", "HG 1/144 テスト", pb=True, channel="online"), NOW,
                              brand_key="figurerise-bust")
    assert item is None and cat.excluded["pb-item-1000133317"] == "brand:figurerise-bust"


def test_unknown_brand_key_is_excluded_not_rescued_by_title():
    cat = Catalog()
    item, _ = cat.upsert_card(card("01_7500", "HG 1/144 テスト"), NOW, brand_key="brand-new-key")
    assert item is None and cat.excluded["bh-01_7500"] == "brand:brand-new-key"


def test_provisional_item_is_excluded_when_an_excluded_brand_key_arrives_later():
    cat = Catalog()
    cat.upsert_card(card("01_7501", "Figure-rise Standard 仮名"), NOW)              # 일정 카드: 제목으로 임시 판정 → girl
    assert cat.items["bh-01_7501"]["line"] == "girl"
    item, is_new = cat.upsert_card(card("01_7501", "Figure-rise Standard 仮名"), LATER, brand_key="figurerise-bust")
    assert (item, is_new) == (None, False) and "bh-01_7501" not in cat.items
    assert cat.excluded["bh-01_7501"] == "brand:figurerise-bust"


def test_title_is_used_only_when_there_is_no_brand_key():
    cat = Catalog()
    item, _ = cat.upsert_card(card("01_7502", "HG 1/144 キー無し"), NOW)                  # 브랜드 키 없음 → 제목 판정
    assert item["line"] == "gunpla"
    item2, _ = cat.upsert_card(card("01_7503", "HG 1/144 キー有り"), NOW, brand_key="30ms")   # 키가 제목(HG)보다 우선
    assert item2["line"] == "girl" and item2["grade"] == "30MS"


def test_apply_detail_prefers_brand_keys_over_title():
    cat = Catalog()
    cat.upsert_card(card("01_7504", "HG 1/144 제목은 건프라"), NOW)
    cat.apply_detail("bh-01_7504", detail("HG 1/144 제목은 건프라", keys=["figurerise-bust"]), LATER)
    assert "bh-01_7504" not in cat.items and cat.excluded["bh-01_7504"] == "brand:figurerise-bust"


# ---------------------------------------------------------------- 기존 항목 재분류
def stored(cid, keys, line, grade, **kw):
    """이전 실행이 저장해 둔 항목 (분류표가 달랐을 때의 결과)."""
    it = {"id": cid, "url": "u", "line": line, "brandKeys": list(keys), "grade": grade, "scale": None, "seriesKey": None,
          "series": None, "nameJa": f"名前{cid}", "nameKo": None, "priceJpy": 1, "channel": "general", "pbUrl": None,
          "release": {"month": "2020-01"}, "kr": [], "images": [], "firstSeen": NOW, "updated": NOW, "detailAt": None}
    it.update(kw)
    return it


def test_reclassify_moves_excluded_brand_items_to_excluded_list_and_keeps_the_rest():
    cat = Catalog()
    for it in (stored("bh-01_1096", ["figurerise-bust"], "girl", "Figure-rise Bust"),
               stored("bh-01_581", ["figurerise-bust"], "girl", "Figure-rise Bust", detailAt=NOW),
               stored("pb-item-1000133317", ["figurerise-bust"], "girl", "Figure-rise Bust"),
               stored("bh-01_7001", ["30ms"], "girl", "30MS"),
               stored("bh-01_7002", ["hg", "pb_hg"], "gunpla", "HG"),
               stored("bh-01_7003", [], "girl", "Figure-rise Standard"),          # 브랜드 키 없음: 제목 임시 판정 유지
               stored("bh-01_7004", [], None, None)):
        cat.items[it["id"]] = it
    out = cat.reclassify(LATER)
    assert out == {"toExcluded": 3, "lineChanged": 0}
    assert set(cat.items) == {"bh-01_7001", "bh-01_7002", "bh-01_7003", "bh-01_7004"}
    assert cat.excluded == {"bh-01_1096": "brand:figurerise-bust", "bh-01_581": "brand:figurerise-bust",
                            "pb-item-1000133317": "brand:figurerise-bust"}
    assert cat.items["bh-01_7001"]["updated"] == NOW                                # 바뀌지 않은 항목은 그대로


def test_reclassify_updates_line_and_grade_and_is_idempotent():
    cat = Catalog()
    cat.items["bh-01_8001"] = stored("bh-01_8001", ["rg"], "girl", "OLD")              # 분류표가 바뀌어 line·등급이 달라진 경우
    cat.items["bh-01_8002"] = stored("bh-01_8002", ["pb_gunpla"], "gunpla", "RG")       # 키에 등급이 없으면 기존 등급 유지
    assert cat.reclassify(LATER) == {"toExcluded": 0, "lineChanged": 1}
    changed = cat.items["bh-01_8001"]
    assert (changed["line"], changed["grade"], changed["updated"]) == ("gunpla", "RG", LATER)
    assert cat.items["bh-01_8002"]["grade"] == "RG" and cat.items["bh-01_8002"]["updated"] == NOW
    assert cat.reclassify(LATER) == {"toExcluded": 0, "lineChanged": 0}                 # 두 번째는 변화 없음


def test_reclassified_excluded_items_are_not_recreated_by_later_cards():
    cat = Catalog()
    cat.items["bh-01_1096"] = stored("bh-01_1096", ["figurerise-bust"], "girl", "Figure-rise Bust")
    cat.reclassify(LATER)
    assert cat.upsert_card(card("01_1096", "Figure-riseBust 初音ミク"), LATER) == (None, False)


def test_reclassified_state_roundtrips_through_save_and_load(tmp_path):
    cat = Catalog()
    cat.items["bh-01_1096"] = stored("bh-01_1096", ["figurerise-bust"], "girl", "Figure-rise Bust")
    cat.items["bh-01_7001"] = stored("bh-01_7001", ["30ms"], "girl", "30MS")
    cat.reclassify(LATER)
    cat.save(tmp_path, LATER)
    girl = json.loads((tmp_path / "catalog-girl.json").read_text(encoding="utf-8"))
    pend = json.loads((tmp_path / "catalog-pending.json").read_text(encoding="utf-8"))
    assert [i["id"] for i in girl["items"]] == ["bh-01_7001"]
    assert pend["excluded"] == {"bh-01_1096": "brand:figurerise-bust"}


# ---------------------------------------------------------------- nameKo 부분 치환
def test_name_ko_replacement_changes_only_that_substring():
    cat = Catalog()
    cat.items["a"] = stored("a", ["30ms"], "girl", "x", updated="OLD",
                            nameKo="Figure-rise Standard 앰플리파이드 임페리얼드라몬 [리미티드 컬러]")
    cat.items["b"] = stored("b", ["30ms"], "girl", "x", nameKo="Figure-rise Standard Amplified 매그너가루몬")
    cat.items["c"] = stored("c", ["30ms"], "girl", "x", nameKo=None)
    cat.items["d"] = stored("d", ["30ms"], "girl", "x", nameKo="앰플리파이드 앰플리파이드")
    assert cat.apply_name_ko_replacements({"앰플리파이드": "Amplified"}) == 2
    assert cat.items["a"]["nameKo"] == "Figure-rise Standard Amplified 임페리얼드라몬 [리미티드 컬러]"
    assert cat.items["b"]["nameKo"] == "Figure-rise Standard Amplified 매그너가루몬" and cat.items["c"]["nameKo"] is None
    assert cat.items["d"]["nameKo"] == "Amplified Amplified"                          # 같은 말이 여러 번 나오면 모두
    assert cat.items["a"]["updated"] == "OLD" and cat.items["a"]["nameJa"] == "名前a"   # 다른 필드는 건드리지 않는다
    assert cat.apply_name_ko_replacements({"앰플리파이드": "Amplified"}) == 0           # 다시 돌려도 변화 없음


def test_config_replacements_cover_the_amplified_case():
    assert config.NAME_KO_REPLACEMENTS == {"앰플리파이드": "Amplified"}
    assert not any("぀" <= c <= "ヿ" for v in config.NAME_KO_REPLACEMENTS.values() for c in v)
