"""series.py — 시리즈 한국어(seriesKo). mock 클라이언트로만, 실제 Claude API는 호출하지 않는다."""
import json
from types import SimpleNamespace

from crawler import config, series
from crawler.catalog import Catalog

NOW = "2026-10-08T09:00:00+09:00"
JA = {"g-witch": "機動戦士ガンダム 水星の魔女", "seed-d": "機動戦士ガンダムSEED DESTINY", "macross": "マクロスシリーズ"}


def cat_with(spec):
    """spec: [(id, seriesKey|None)] — series 일본어는 JA에서."""
    cat = Catalog()
    for cid, key in spec:
        cat.items[cid] = {"id": cid, "line": "gunpla", "grade": "HG", "seriesKey": key, "series": JA.get(key) if key else None,
                          "nameJa": "HG 1/144 テスト", "nameKo": "테스트", "release": {"month": "2026-10"}, "updated": "old"}
    return cat


def reply(rows):
    block = SimpleNamespace(type="text", text=json.dumps({"items": rows}, ensure_ascii=False))
    return SimpleNamespace(stop_reason="end_turn", content=[block], usage=SimpleNamespace(input_tokens=10, output_tokens=5))


class FakeClient:
    def __init__(self, answers=None, handler=None):
        self.calls, self.answers, self.handler = [], answers or {}, handler
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.handler:
            return self.handler(len(self.calls), kw)
        rows = json.loads(kw["messages"][0]["content"])
        return reply([{"id": r["id"], "ko": self.answers.get(r["id"], f"한국어 {r['id']}")} for r in rows])


SPEC = [("bh-1", "g-witch"), ("bh-2", "g-witch"), ("bh-3", "seed-d"), ("bh-4", None), ("bh-5", "g-witch")]


def test_pending_lists_unique_series_most_used_first_and_skips_known_and_overrides():
    cat = cat_with(SPEC)
    assert series.pending(cat, {}, {}) == [{"id": "g-witch", "ja": JA["g-witch"]}, {"id": "seed-d", "ja": JA["seed-d"]}]
    known = {"g-witch": {"ja": JA["g-witch"], "ko": "수성의 마녀"}}
    assert series.pending(cat, known, {}) == [{"id": "seed-d", "ja": JA["seed-d"]}]
    assert series.pending(cat, known, {"seed-d": "시드 데스티니"}) == []
    stale = {"g-witch": {"ja": "옛 일본어 이름", "ko": "수성의 마녀"}}       # 호비사이트가 시리즈 이름을 바꾸면 다시 번역한다
    assert [p["id"] for p in series.pending(cat, stale, {})] == ["g-witch", "seed-d"]


def test_translate_pending_calls_api_once_for_unique_series_and_fills_dictionary():
    cat, fc, known = cat_with(SPEC), FakeClient({"g-witch": "기동전사 건담 수성의 마녀", "seed-d": "기동전사 건담 SEED DESTINY"}), {}
    res = series.translate_pending(cat, known, client=fc)
    assert len(fc.calls) == 1 and json.loads(fc.calls[0]["messages"][0]["content"]) == [{"id": "g-witch", "ja": JA["g-witch"]}, {"id": "seed-d", "ja": JA["seed-d"]}]
    assert res["ok"] and res["done"] == 2 and res["pending"] == 0 and res["error"] is None
    assert known["seed-d"] == {"ja": JA["seed-d"], "ko": "기동전사 건담 SEED DESTINY"}
    assert series.apply(cat, known, {}) == 4                       # 시리즈가 있는 4개 항목에 채워진다
    assert cat.items["bh-1"]["seriesKo"] == "기동전사 건담 수성의 마녀" and cat.items["bh-3"]["seriesKo"] == "기동전사 건담 SEED DESTINY"
    assert "seriesKo" not in cat.items["bh-4"]
    assert cat.items["bh-1"]["updated"] == "old"                    # 다른 필드(updated)는 건드리지 않는다


def test_second_run_translates_only_new_series():
    cat, known = cat_with(SPEC), {}
    series.translate_pending(cat, known, client=FakeClient())
    cat.items["bh-9"] = {**cat.items["bh-1"], "id": "bh-9", "seriesKey": "macross", "series": JA["macross"]}
    fc = FakeClient({"macross": "마크로스 시리즈"})
    res = series.translate_pending(cat, known, client=fc)
    assert json.loads(fc.calls[0]["messages"][0]["content"]) == [{"id": "macross", "ja": JA["macross"]}]
    assert res["done"] == 1 and known["macross"]["ko"] == "마크로스 시리즈"
    fc2 = FakeClient()
    assert series.translate_pending(cat, known, client=fc2)["done"] == 0 and fc2.calls == []      # 새 시리즈가 없으면 API를 부르지 않는다


def test_overrides_win_and_need_no_api_call():
    cat, known = cat_with(SPEC), {"g-witch": {"ja": JA["g-witch"], "ko": "번역된 이름"}}
    fc = FakeClient()
    res = series.translate_pending(cat, known, client=fc)
    assert [json.loads(c["messages"][0]["content"])[0]["id"] for c in fc.calls] == ["seed-d"]
    series.apply(cat, known, {"g-witch": "사람이 고친 이름", "seed-d": "사람이 정한 이름"})
    assert cat.items["bh-1"]["seriesKo"] == "사람이 고친 이름" and cat.items["bh-3"]["seriesKo"] == "사람이 정한 이름"
    assert res["ok"]


def test_apply_is_idempotent_and_drops_seriesko_when_japanese_label_changed():
    cat = cat_with(SPEC)
    known = {"g-witch": {"ja": JA["g-witch"], "ko": "수성의 마녀"}, "seed-d": {"ja": JA["seed-d"], "ko": "시드 데스티니"}}
    assert series.apply(cat, known, {}) == 4 and series.apply(cat, known, {}) == 0
    cat.items["bh-1"]["series"] = "名前が変わった"
    assert series.apply(cat, known, {}) == 1 and "seriesKo" not in cat.items["bh-1"]


def test_no_api_key_skips_but_known_series_are_still_applied():
    cat, known = cat_with(SPEC), {"g-witch": {"ja": JA["g-witch"], "ko": "수성의 마녀"}}
    res = series.translate_pending(cat, known)                     # conftest가 키를 비워 둔다
    assert res["skipped"] == "no api key" and res["ok"] and res["pending"] == 1 and "seed-d" not in known
    series.apply(cat, known, {})
    assert cat.items["bh-1"]["seriesKo"] == "수성의 마녀" and "seriesKo" not in cat.items["bh-3"]


def test_kana_in_translation_is_retried_once_then_dropped_until_next_run():
    def handler(n, kw):
        rows = json.loads(kw["messages"][0]["content"])
        if n == 1:
            return reply([{"id": r["id"], "ko": "건담 シリーズ" if r["id"] == "seed-d" else "수성의 마녀"} for r in rows])
        assert rows == [{"id": "seed-d", "ja": JA["seed-d"], "prev_ko": "건담 シリーズ"}]     # 가나가 남은 항목만, 앞선 번역과 함께
        return reply([{"id": "seed-d", "ko": "아직 シ"}])
    cat, known = cat_with(SPEC), {}
    res = series.translate_pending(cat, known, client=FakeClient(handler=handler))
    assert res["kanaRetried"] == 1 and res["kanaRejected"] == 1 and res["done"] == 1
    assert "seed-d" not in known and known["g-witch"]["ko"] == "수성의 마녀" and res["pending"] == 1


def test_api_failure_stops_and_keeps_earlier_results():
    class Boom(Exception):
        pass

    def handler(n, kw):
        if n == 2:
            raise Boom()
        return reply([{"id": r["id"], "ko": f"한국어 {r['id']}"} for r in json.loads(kw["messages"][0]["content"])])
    cat = cat_with([(f"bh-{i}", f"k{i}") for i in range(5)])
    for it in cat.items.values():
        it["series"] = f"日本語{it['seriesKey']}"
    known = {}
    res = series.translate_pending(cat, known, client=FakeClient(handler=handler), batch_size=2)
    assert res["ok"] is False and res["error"] == "Boom" and res["done"] == 2 and len(known) == 2 and res["pending"] == 3


def test_request_shape_uses_series_prompt_with_glossary_model_and_schema():
    fc = FakeClient()
    series.translate_pending(cat_with(SPEC), {}, client=fc)
    kw = fc.calls[0]
    assert kw["model"] == config.CLAUDE_MODEL and kw["system"] == series.SYSTEM_PROMPT
    assert "기동전사 건담 SEED DESTINY" in kw["system"]                              # 예시
    for ja, ko in config.TRANSLATE_GLOSSARY.items():                                # 용어집 적용
        assert f"- {ja} → {ko}" in kw["system"]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert not {"tool_choice", "temperature", "top_p", "top_k", "thinking"} & set(kw)


def test_overrides_values_have_no_kana():
    for k, v in config.SERIES_KO_OVERRIDES.items():
        assert v and not series.has_kana(v), k


def test_dictionary_file_roundtrip_and_no_rewrite_when_unchanged(tmp_path):
    assert series.load(tmp_path) == {}
    assert series.save(tmp_path, {}, NOW) is False and not (tmp_path / config.SERIES_FILE).exists()    # 비어 있으면 만들지 않는다
    known = {"seed-d": {"ja": JA["seed-d"], "ko": "시드 데스티니"}}
    assert series.save(tmp_path, known, NOW) is True
    assert series.load(tmp_path) == known
    assert series.save(tmp_path, known, "2026-12-01T00:00:00+09:00") is False                         # 바뀐 게 없으면 updatedAt도 그대로
    assert json.loads((tmp_path / config.SERIES_FILE).read_text(encoding="utf-8"))["updatedAt"] == NOW
    (tmp_path / config.SERIES_FILE).write_text("{깨진 JSON", encoding="utf-8")
    assert series.load(tmp_path) == {}
    (tmp_path / config.SERIES_FILE).write_text(json.dumps({"items": {"a": {"ja": "x"}, "b": "bad", "c": {"ja": "x", "ko": ""}}}), encoding="utf-8")
    assert series.load(tmp_path) == {}
