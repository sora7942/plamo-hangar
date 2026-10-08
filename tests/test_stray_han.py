"""번역에 원문에 없는 한자(중국어식 오번역 `비达르`)가 섞이는 문제 — 검사·재요청·기존 데이터 재번역 표시. Claude는 가짜 클라이언트."""
import json

from crawler import config, feed, series, translate
from crawler.catalog import Catalog
from crawler.pipeline import Options
from test_pipeline import World, go, read
from test_series import FakeClient as SeriesClient
from test_translate import FakeClient, cat_with, reply

NOW = "2026-10-09T09:00:00+09:00"


def test_stray_han_ignores_han_that_the_japanese_source_has():
    assert translate.stray_han("ガンダムヴィダール", "건담 비达르") == "达"
    assert translate.stray_han("ＲＥ/100 1/100 ８９式ベース・ジャバー", "RE/100 1/100 89式 베이스 재버") == ""        # 원문에도 있는 한자는 정상
    assert translate.stray_han("ＭＧ 1/100 百式改", "MG 1/100 백식改") == ""
    assert translate.stray_han("HG 1/144 昔の機体", "HG 1/144 옛 기체") == ""
    assert translate.stray_han("怪獣8号", "怪兽8号") == "兽"
    assert translate.stray_han(None, "비达르") == "达" and translate.stray_han("x", None) == ""
    assert translate.bad_translation("ヴィダール", "비达르") and translate.bad_translation("x", "ガ") and not translate.bad_translation("x", "건담")


def test_translation_with_stray_han_is_retried_once_with_prev_ko_then_accepted():
    def handler(n, kw):
        rows = json.loads(kw["messages"][0]["content"])
        if n == 1:
            return reply([{"id": r["id"], "ko": "건담 비达르"} for r in rows])
        assert rows[0]["prev_ko"] == "건담 비达르" and rows[0]["ja"] == "HG 1/144 ガンダムヴィダール"
        return reply([{"id": r["id"], "ko": "HG 1/144 건담 비다르"} for r in rows])
    cat = Catalog()
    cat.items["bh-1"] = {"id": "bh-1", "line": "gunpla", "grade": "HG", "series": None, "nameJa": "HG 1/144 ガンダムヴィダール", "nameKo": None, "release": {"month": "2026-10"}, "updated": "old"}
    fc = FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 2 and res["kanaRetried"] == 1 and res["kanaRejected"] == 0
    assert cat.items["bh-1"]["nameKo"] == "HG 1/144 건담 비다르"


def test_translation_that_keeps_stray_han_is_left_empty_for_next_run():
    cat, fc = cat_with(2), FakeClient(lambda n, kw: reply([{"id": r["id"], "ko": "机体"} for r in json.loads(kw["messages"][0]["content"])]))
    res = translate.translate_pending(cat, NOW, client=fc)
    assert res["kanaRejected"] == 2 and res["pending"] == 2 and all(i["nameKo"] is None for i in cat.items.values())


def test_system_prompt_forbids_new_han_and_glossary_fixes_vidar():
    assert "한자" in translate.SYSTEM_PROMPT and "- ヴィダール → 비다르" in translate.SYSTEM_PROMPT
    assert config.TRANSLATE_GLOSSARY["ヴィダール"] == "비다르" and "한자" in series.SYSTEM_PROMPT


def test_series_translation_with_stray_han_is_retried_then_dropped():
    def handler(n, kw):
        rows = json.loads(kw["messages"][0]["content"])
        return reply([{"id": r["id"], "ko": "怪兽8号"} for r in rows])
    cat = Catalog()
    cat.items["bh-1"] = {"id": "bh-1", "line": "gunpla", "seriesKey": "kaiju", "series": "怪獣8号", "nameKo": "x", "release": {"month": "2026-10"}}
    known = {}
    res = series.translate_pending(cat, known, client=SeriesClient(handler=handler))
    assert res["kanaRetried"] == 1 and res["kanaRejected"] == 1 and known == {}


def test_reset_stray_han_blanks_only_bad_names_and_spares_shop_names_and_legit_kanji():
    cat = Catalog()
    base = {"line": "gunpla", "release": {"month": "2026-10"}}
    cat.items["a"] = {**base, "id": "a", "nameJa": "ガンダムヴィダール", "nameKo": "건담 비达르"}
    cat.items["b"] = {**base, "id": "b", "nameJa": "ＭＧ 百式改", "nameKo": "MG 백식改"}
    cat.items["c"] = {**base, "id": "c", "nameJa": "ガンダムヴィダール", "nameKo": "조이하비 비达르", "nameKoSource": "joyhobby"}
    assert cat.reset_stray_han() == ["a"]
    assert cat.items["a"]["nameKo"] is None and cat.items["b"]["nameKo"] == "MG 백식改" and cat.items["c"]["nameKo"] == "조이하비 비达르"
    assert [i["id"] for i in cat.untranslated(10)] == ["a"]                                    # 번역 대상으로 다시 잡힌다
    assert cat.reset_stray_han() == []


def test_drop_stray_han_from_series_dictionary():
    known = {"ok": {"ja": "怪獣8号", "ko": "괴수 8号"}, "bad": {"ja": "怪獣8号", "ko": "怪兽 8호"}}
    assert series.drop_stray_han(known) == ["bad"] and list(known) == ["ok"]


def test_feed_title_ko_with_stray_han_is_reset_and_backfilled_from_catalog():
    item = {"id": "bh-new-01_1", "type": "new", "source": "bandai-hobby", "catalogId": "bh-01_1", "title": "HG ガンダムヴィダール", "titleKo": "HG 건담 비达르", "image": None, "added": "2026-10-01T00:00:00+09:00"}
    jh = {"id": "jh-1-BD0000001", "type": "kr-new", "source": "joyhobby", "catalogId": None, "title": "[HG] 건담 비达르(VIDAR)", "titleKo": "HG 건담 비达르", "image": None, "added": "2026-10-01T00:00:00+09:00"}
    assert feed.reset_stray_han([item, jh]) == 1 and item["titleKo"] is None and jh["titleKo"] == "HG 건담 비达르"      # 조이하비 글은 한글 원문이라 건드리지 않는다
    cat = Catalog()
    cat.items["bh-01_1"] = {"id": "bh-01_1", "line": "gunpla", "nameKo": "HG 건담 비다르", "images": []}
    merged, _ = feed.merge_feed([item], [], cat)
    assert merged[0]["titleKo"] == "HG 건담 비다르"


def test_pipeline_flags_bad_existing_translation_and_retranslates_it_in_the_same_run(tmp_path):
    from types import SimpleNamespace
    calls = []

    def create(**kw):
        rows = json.loads(kw["messages"][0]["content"])
        calls.append(rows)
        text = json.dumps({"items": [{"id": r["id"], "ko": f"한글 {r['id']}"} for r in rows]}, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    fake = SimpleNamespace(messages=SimpleNamespace(create=create))
    res, *_ = go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"), anthropic_client=fake)
    f = tmp_path / "catalog-gunpla.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for it in doc["items"]:
        if it["id"] == "bh-01_7001":
            it["nameKo"] = "HG 1/144 테스트 机A"                                                  # 지난 실행에서 한자가 섞여 저장된 번역
    from crawler.store import write_json
    write_json(f, doc)
    calls.clear()
    res, *_ = go(World(), tmp_path, Options(), anthropic_client=fake)
    items = {i["id"]: i for i in read(tmp_path, "catalog-gunpla.json")["items"]}
    assert items["bh-01_7001"]["nameKo"] == "한글 bh-01_7001"                                      # 같은 실행에서 다시 번역됨
    assert res["meta"]["crawl"]["lastFixups"]["strayHanReset"] == 1
    assert [r["id"] for rows in calls for r in rows] == ["bh-01_7001"]                           # 다른 항목은 다시 번역하지 않는다
