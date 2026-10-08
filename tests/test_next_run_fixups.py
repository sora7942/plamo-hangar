"""첫 crawl 결과를 본 뒤의 수정이 '다음 실행'에서 기존 데이터에 반영되는지 — 분류표 재적용(bust 제외), nameKo 부분 치환, 용어집.

docs/data를 직접 고치지 않고 크롤러 코드만 고쳐서 다음 실행 때 반영한다는 요구를 임시 폴더에서 재현한다.
"""
import json
from datetime import timedelta
from types import SimpleNamespace

from crawler import config, translate
from crawler.pipeline import Options
from test_pipeline import DATA_FILES, NOW, World, go, kinds, read
from test_catalog_brandkey import stored
from schema_check import check_dir

HOBBY = "https://bandai-hobby.net"
BUST_IDS = ["bh-01_1096", "bh-01_581", "pb-item-1000133317"]


def first_crawl(tmp_path):
    """이전(첫) crawl 결과를 만든다: 정상 수집 + 그때의 분류표(bust=girl)가 만든 bust 항목 3개, 옛 번역 표기."""
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    girl = read(tmp_path, "catalog-girl.json")
    for cid in BUST_IDS:
        girl["items"].append(stored(cid, ["figurerise-bust"], "girl", "Figure-rise Bust", nameJa=f"Figure-riseBust {cid}"))
    target = next(i for i in girl["items"] if i["id"] == "bh-01_7101")
    target["nameKo"] = "30MS 미야스티 앰플리파이드 [컬러C]"
    (tmp_path / "catalog-girl.json").write_text(json.dumps(girl, ensure_ascii=False), encoding="utf-8")
    feed = read(tmp_path, "feed.json")
    fi = next(f for f in feed["items"] if f["catalogId"] == "bh-01_7101")
    fi["titleKo"] = "30MS 미야스티 앰플리파이드 [컬러C]"
    (tmp_path / "feed.json").write_text(json.dumps(feed, ensure_ascii=False), encoding="utf-8")
    meta = read(tmp_path, "meta.json")
    meta["crawl"]["girlBrandsDone"].append("figurerise-bust")
    (tmp_path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return w


def test_next_run_moves_bust_items_to_excluded_and_fixes_amplified(tmp_path):
    w = first_crawl(tmp_path)
    before_girl = {i["id"]: i for i in read(tmp_path, "catalog-girl.json")["items"]}
    assert set(BUST_IDS) <= set(before_girl)                                        # 전제: 첫 crawl에는 bust가 girl에 들어 있었다
    before_feed = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}

    res, _, sess, _ = go(w, tmp_path, Options(), now=NOW + timedelta(days=1))

    girl = {i["id"]: i for i in read(tmp_path, "catalog-girl.json")["items"]}
    pend = read(tmp_path, "catalog-pending.json")
    assert not set(BUST_IDS) & set(girl)                                            # catalog-girl에서 빠졌다
    assert all(pend["excluded"][c] == "brand:figurerise-bust" for c in BUST_IDS)    # 제외 목록으로 이동
    assert not any("figurerise-bust" in i["brandKeys"] for f in ("catalog-girl.json", "catalog-gunpla.json", "catalog-pending.json")
                   for i in read(tmp_path, f)["items"])
    # 나머지 걸프라 항목은 그대로
    assert {k: v for k, v in girl.items() if k != "bh-01_7101"} == {k: v for k, v in before_girl.items() if k not in BUST_IDS and k != "bh-01_7101"}

    # nameKo: 그 부분 문자열만 바뀌고 다른 필드·다른 글자는 그대로 (updated도 그대로)
    after = girl["bh-01_7101"]
    assert after["nameKo"] == "30MS 미야스티 Amplified [컬러C]"
    assert {k: v for k, v in after.items() if k != "nameKo"} == {k: v for k, v in before_girl["bh-01_7101"].items() if k != "nameKo"}
    feed = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}
    assert feed["bh-new-01_7101"]["titleKo"] == "30MS 미야스티 Amplified [컬러C]"
    assert {k: v for k, v in feed["bh-new-01_7101"].items() if k != "titleKo"} == {k: v for k, v in before_feed["bh-new-01_7101"].items() if k != "titleKo"}

    meta = res["meta"]["crawl"]
    assert meta["lastFixups"] == {"toExcluded": 3, "lineChanged": 0, "nameKoReplaced": 1, "feedTitleKoReplaced": 1, "seriesKoApplied": 0}
    assert meta["girlBrandsDone"] == config.GIRL_BRANDS                              # 더 이상 걸프라가 아닌 브랜드는 커서에서도 정리
    assert f"{HOBBY}/brand/figurerise-bust/" not in kinds(sess)                      # bust 브랜드 목록은 더 이상 요청하지 않는다
    assert meta["counts"]["excluded"] >= 3 and check_dir(tmp_path) == []


def test_fixups_are_idempotent_third_run_changes_nothing(tmp_path):
    w = first_crawl(tmp_path)
    go(w, tmp_path, Options(), now=NOW + timedelta(days=1))
    snapshot = {n: (tmp_path / n).read_bytes() for n in DATA_FILES - {"meta.json"}}
    res, *_ = go(w, tmp_path, Options(), now=NOW + timedelta(days=2))
    assert res["meta"]["crawl"]["lastFixups"] == {"toExcluded": 0, "lineChanged": 0, "nameKoReplaced": 0, "feedTitleKoReplaced": 0, "seriesKoApplied": 0}
    assert {n: (tmp_path / n).read_bytes() for n in snapshot} == snapshot


def test_fixups_run_even_when_only_one_stage_is_selected(tmp_path):
    w = first_crawl(tmp_path)
    translate_entry_before = read(tmp_path, "meta.json")["sources"]["translate"]
    res, *_ = go(w, tmp_path, Options(only={"hobby_item"}, max_new=0, max_backlog=0), now=NOW + timedelta(days=1))
    assert res["meta"]["sources"]["translate"] == translate_entry_before            # --only hobby_item이라 이번 실행에서 번역 단계는 돌지 않았다
    assert not set(BUST_IDS) & {i["id"] for i in read(tmp_path, "catalog-girl.json")["items"]}
    assert read(tmp_path, "catalog-pending.json")["excluded"]["bh-01_1096"] == "brand:figurerise-bust"
    # 번역 단계가 돌지 않는 경로에서도 nameKo·피드 titleKo 치환은 시작 시점에 적용된다
    girl = {i["id"]: i for i in read(tmp_path, "catalog-girl.json")["items"]}
    assert girl["bh-01_7101"]["nameKo"] == "30MS 미야스티 Amplified [컬러C]"
    assert {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}["bh-new-01_7101"]["titleKo"] == "30MS 미야스티 Amplified [컬러C]"
    assert res["meta"]["crawl"]["lastFixups"]["nameKoReplaced"] == 1
    assert res["meta"]["crawl"]["girlBrandsDone"] == config.GIRL_BRANDS             # 브랜드 단계를 건너뛰어도 커서가 정리된다


def test_bust_cards_from_schedule_never_enter_the_catalog_again(tmp_path):
    w = first_crawl(tmp_path)
    w.schedule["2026-10"].append({"num": "01_1096", "title": "Figure-riseBust 初音ミク", "date": "2026年10月24日 (土)"})
    w.details["01_1096"] = __import__("conftest").detail_html("Figure-riseBust 初音ミク", ["figurerise-bust"])
    go(w, tmp_path, Options(), now=NOW + timedelta(days=1))
    ids = {i["id"] for f in ("catalog-girl.json", "catalog-gunpla.json", "catalog-pending.json") for i in read(tmp_path, f)["items"]}
    assert "bh-01_1096" not in ids and f"{HOBBY}/item/01_1096/" not in kinds(go(w, tmp_path, Options(), now=NOW + timedelta(days=2))[2])


def test_new_bust_item_discovered_via_schedule_is_excluded_after_detail(tmp_path):
    """제목 규칙이 없어도(판정 불가 → 보류) 상세의 브랜드 키로 제외된다."""
    w = World()
    w.schedule["2026-10"].append({"num": "01_9001", "title": "Figure-riseBust テスト", "date": "2026年10月24日 (土)"})
    w.details["01_9001"] = __import__("conftest").detail_html("Figure-riseBust テスト", ["figurerise-bust"])
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    assert "bh-01_9001" not in {i["id"] for f in ("catalog-girl.json", "catalog-gunpla.json", "catalog-pending.json")
                                for i in read(tmp_path, f)["items"]}
    assert read(tmp_path, "catalog-pending.json")["excluded"]["bh-01_9001"] == "brand:figurerise-bust"
    assert all(f["catalogId"] != "bh-01_9001" for f in read(tmp_path, "feed.json")["items"])      # 피드에도 없다


def test_translate_stage_output_with_old_spelling_is_normalized(tmp_path):
    """모델이 용어집을 어기고 옛 표기를 써도 번역 직후 같은 치환이 적용된다."""
    def create(**kw):
        rows = json.loads(kw["messages"][0]["content"])
        text = json.dumps({"items": [{"id": r["id"], "ko": f"앰플리파이드 {r['id']}"} for r in rows]}, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    fake = SimpleNamespace(messages=SimpleNamespace(create=create))
    res, *_ = go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"), anthropic_client=fake)
    items = [i for f in ("catalog-girl.json", "catalog-gunpla.json") for i in read(tmp_path, f)["items"]]
    assert items and all(i["nameKo"].startswith("Amplified ") and "앰플리파이드" not in i["nameKo"] for i in items)
    assert res["meta"]["crawl"]["lastFixups"]["nameKoReplaced"] == len(items)
    assert all(f["titleKo"] and "앰플리파이드" not in f["titleKo"] for f in read(tmp_path, "feed.json")["items"])


# ---------------------------------------------------------------- 용어집
def test_glossary_amplified_stays_english_and_paliton_is_added_once():
    g = config.TRANSLATE_GLOSSARY
    assert g["アンプリファイド"] == "Amplified" and g["パリトン"] == "파리톤" and g["マグナガルルモン"] == "매그너가루몬"
    assert "マグナガルルァイド" not in g and "앰플리파이드" not in g.values()
    p = translate.SYSTEM_PROMPT
    assert "- アンプリファイド → Amplified" in p and "- パリトン → 파리톤" in p
    assert p.count("- マグナガルルモン → 매그너가루몬") == 1 and "マグナガルルァイド" not in p      # 두 줄로 분리, 합쳐진 줄 없음
    assert "앰플리파이드" not in p                                                                  # 옛 표기는 프롬프트 어디에도 없다


def test_prompt_tells_the_model_to_keep_amplified_in_english():
    p = translate.SYSTEM_PROMPT
    assert "영문 `Amplified` 그대로" in p and "표기가 영문이면 영문 그대로" in p


def test_existing_user_glossary_entries_are_unchanged():
    g = config.TRANSLATE_GLOSSARY
    assert (g["ディランザ"], g["グエル"], g["スレッタ"], g["ミオリネ"], g["カラー"]) == ("딜란자", "구엘", "슬레타", "미오리네", "컬러")
