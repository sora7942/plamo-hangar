"""translate.py — mock 클라이언트로만. 실제 Claude API는 호출하지 않는다."""
import importlib
import json
from types import SimpleNamespace

import pytest

from crawler import config, translate
from crawler.catalog import Catalog

NOW = "2026-10-06T09:00:00+09:00"


def cat_with(n, *, prefilled=()):
    cat = Catalog()
    for i in range(n):
        cat.items[f"bh-01_{i}"] = {"id": f"bh-01_{i}", "line": "gunpla", "grade": "HG", "series": None,
                                   "nameJa": f"HG 1/144 機体{i}", "nameKo": None, "release": {"month": "2026-10"},
                                   "updated": "old"}
    for i in prefilled:
        cat.items[f"bh-01_{i}"]["nameKo"] = "조이하비 이름"
    return cat


def reply(rows, stop="end_turn"):
    block = SimpleNamespace(type="text", text=json.dumps({"items": rows}, ensure_ascii=False))
    return SimpleNamespace(stop_reason=stop, content=[block], usage=SimpleNamespace(input_tokens=100, output_tokens=50))


class FakeClient:
    """messages.create 호출을 기록하고, 요청 JSON의 id마다 '번역<id>'로 답한다."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.handler:
            return self.handler(len(self.calls), kw)
        rows = json.loads(kw["messages"][0]["content"])
        return reply([{"id": r["id"], "ko": f"번역 {r['id']}"} for r in rows])


def test_translates_in_batches_of_50_and_fills_name_ko():
    cat, fc = cat_with(120), FakeClient()
    res = translate.translate_pending(cat, NOW, client=fc)
    assert [len(json.loads(c["messages"][0]["content"])) for c in fc.calls] == [50, 50, 20]
    assert res["ok"] and res["done"] == 120 and res["pending"] == 0 and res["error"] is None
    it = cat.items["bh-01_7"]
    assert it["nameKo"] == "번역 bh-01_7" and it["updated"] == NOW


def test_request_shape_uses_configured_model_schema_effort_and_no_forced_tool_or_sampling():
    cat, fc = cat_with(2), FakeClient()
    translate.translate_pending(cat, NOW, client=fc)
    kw = fc.calls[0]
    assert kw["model"] == config.CLAUDE_MODEL and kw["max_tokens"] == config.TRANSLATE_MAX_TOKENS
    assert kw["system"] == translate.SYSTEM_PROMPT
    assert kw["output_config"]["effort"] == "low" and kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["format"]["schema"] == translate.OUTPUT_SCHEMA
    assert not {"tool_choice", "temperature", "top_p", "top_k", "thinking"} & set(kw)        # 5.5 계열에서 400이 나는 설정을 쓰지 않는다
    row = json.loads(kw["messages"][0]["content"])[0]
    assert row == {"id": "bh-01_1", "ja": "HG 1/144 機体1", "grade": "HG"}      # 발매일 최신순, 같으면 id 내림차순


def test_never_overwrites_existing_name_ko_and_skips_already_done_items():
    cat, fc = cat_with(3, prefilled=[1]), FakeClient()
    translate.translate_pending(cat, NOW, client=fc)
    asked = [r["id"] for r in json.loads(fc.calls[0]["messages"][0]["content"])]
    assert "bh-01_1" not in asked and cat.items["bh-01_1"]["nameKo"] == "조이하비 이름"
    assert cat.items["bh-01_1"]["updated"] == "old"


def test_no_credentials_skips_without_calling():
    cat = cat_with(5)
    res = translate.translate_pending(cat, NOW)             # client 없음 + 환경에 키 없음 (conftest가 비워 둔다)
    assert res["skipped"] == "no api key" and res["done"] == 0 and res["pending"] == 5
    assert all(i["nameKo"] is None for i in cat.items.values())


def test_nothing_to_translate_is_ok_without_credentials():
    res = translate.translate_pending(Catalog(), NOW)
    assert res["ok"] and res["skipped"] is None and res["done"] == 0


def test_partial_response_applies_only_valid_ids_and_blank_values_are_dropped():
    def handler(n, kw):
        return reply([{"id": "bh-01_0", "ko": " 정상 "}, {"id": "bh-01_1", "ko": "  "}, {"id": "bh-99", "ko": "모르는 id"}])
    cat = cat_with(3)
    res = translate.translate_pending(cat, NOW, client=FakeClient(handler))
    assert cat.items["bh-01_0"]["nameKo"] == "정상" and cat.items["bh-01_1"]["nameKo"] is None and "bh-99" not in cat.items
    assert res["done"] == 1 and res["pending"] == 2


def test_bad_json_retries_once_then_skips_that_batch_and_continues():
    def handler(n, kw):
        if n <= 2:                                          # 첫 배치: 두 번 다 깨진 응답
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="not json")],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        rows = json.loads(kw["messages"][0]["content"])
        return reply([{"id": r["id"], "ko": "ok"} for r in rows])
    cat, fc = cat_with(60), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc, batch_size=50)
    assert len(fc.calls) == 3 and res["done"] == 10 and res["pending"] == 50 and res["ok"]


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_refusal_and_truncation_are_not_applied(stop):
    cat = cat_with(2)
    res = translate.translate_pending(cat, NOW, client=FakeClient(lambda n, kw: reply([{"id": "bh-01_0", "ko": "x"}], stop)))
    assert res["done"] == 0 and all(i["nameKo"] is None for i in cat.items.values())


def test_api_error_stops_all_further_calls_and_is_reported():
    def handler(n, kw):
        raise RuntimeError("boom https://secret.example")
    cat, fc = cat_with(120), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 1 and res["ok"] is False and res["error"] == "RuntimeError"
    assert "secret" not in json.dumps(res)


def test_max_items_per_run_is_respected():
    cat, fc = cat_with(30), FakeClient()
    res = translate.translate_pending(cat, NOW, client=fc, max_items=12, batch_size=5)
    assert res["done"] == 12 and res["pending"] == 18


def test_model_name_comes_from_environment(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-test-model")
    importlib.reload(config)
    try:
        assert config.CLAUDE_MODEL == "claude-test-model"
    finally:
        monkeypatch.delenv("CLAUDE_MODEL")
        importlib.reload(config)
    assert config.CLAUDE_MODEL == config.DEFAULT_MODEL == "claude-sonnet-5-5"


def test_has_credentials_reads_environment(monkeypatch):
    assert not translate.has_credentials()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert translate.has_credentials()


def test_sample_titles_come_from_fixtures_without_network():
    rows = translate._sample_titles(20)
    assert len(rows) == 20 and all(r["grade"] for r in rows) and len({r["nameJa"] for r in rows}) == 20


def test_sample_cli_without_key_does_not_call_api(capsys):
    assert translate.main(["--sample", "20"]) == 0
    assert "ANTHROPIC_API_KEY가 없습니다" in capsys.readouterr().out
