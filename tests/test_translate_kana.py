"""translate.py — 가나(히라가나·가타카나) 잔존 재요청, 용어집 프롬프트, 실제 Claude 호출 차단 가드. mock 클라이언트로만."""
import json
from types import SimpleNamespace

import pytest

from crawler import config, translate
from test_translate import FakeClient, NOW, cat_with, reply


def rows_of(kw):
    return json.loads(kw["messages"][0]["content"])


# ---------------------------------------------------------------- 안전장치: 테스트가 실제 Claude를 부를 수 없다
def test_guard_blocks_real_claude_client_and_dotenv(tmp_path, monkeypatch):
    """.env에 진짜 키가 있어도 테스트는 그것을 읽지 못하고, SDK 클라이언트도 만들 수 없다 (실제 호출 방지)."""
    import anthropic
    import dotenv
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-should-not-load\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    dotenv.load_dotenv()
    assert not translate.has_credentials()
    with pytest.raises(AssertionError, match="실제 Claude 클라이언트"):
        anthropic.Anthropic()
    with pytest.raises(AssertionError, match="실제 Claude 클라이언트"):
        translate.make_client()


# ---------------------------------------------------------------- 가나 검사
@pytest.mark.parametrize("text,expect", [
    ("30MS 스케일 아틀리에 웨어 [カラーC]", True),      # 가타카나
    ("HG 1/144 건담 えありある", True),                   # 히라가나
    ("건담ー", True),                                     # 장음 기호
    ("ｶﾗｰ", True),                                       # 반각 가타카나
    ("30MS 미야스티 [컬러C]", False),
    ("HG 1/144 건담 에어리얼 Ver.Ka", False),
    ("돔・트로펜", False),                                 # 중점(U+30FB)은 구두점 — 가나가 아님
    ("", False),
    (None, False),
])
def test_has_kana(text, expect):
    assert translate.has_kana(text) is expect


# ---------------------------------------------------------------- 가나 재요청
def test_kana_left_items_are_requested_again_alone_with_prev_ko():
    def handler(n, kw):
        rows = rows_of(kw)
        if n == 1:   # 첫 응답: 0번만 가나가 남음
            return reply([{"id": r["id"], "ko": "컬러C 남음ー" if r["id"] == "bh-01_0" else f"번역 {r['id']}"} for r in rows])
        return reply([{"id": r["id"], "ko": "[컬러C] 고침"} for r in rows])
    cat, fc = cat_with(3), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 2
    second = rows_of(fc.calls[1])
    assert [r["id"] for r in second] == ["bh-01_0"]                          # 그 항목만 다시 묻는다
    assert second[0]["prev_ko"] == "컬러C 남음ー" and second[0]["ja"] == "HG 1/144 機体0"
    assert all("prev_ko" not in r for r in rows_of(fc.calls[0]))
    assert cat.items["bh-01_0"]["nameKo"] == "[컬러C] 고침"
    assert cat.items["bh-01_1"]["nameKo"] == "번역 bh-01_1"
    assert res["done"] == 3 and res["pending"] == 0 and res["kanaRetried"] == 1 and res["kanaRejected"] == 0 and res["ok"]


def test_kana_still_left_after_retry_leaves_name_ko_empty_and_is_retried_next_run():
    def handler(n, kw):
        return reply([{"id": r["id"], "ko": "여전히 カラー" if r["id"] == "bh-01_1" else f"번역 {r['id']}"} for r in rows_of(kw)])
    cat, fc = cat_with(3), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 2                                                  # 재요청은 딱 한 번
    assert cat.items["bh-01_1"]["nameKo"] is None and cat.items["bh-01_1"]["updated"] == "old"
    assert cat.items["bh-01_0"]["nameKo"] == "번역 bh-01_0" and cat.items["bh-01_2"]["nameKo"] == "번역 bh-01_2"
    assert res["done"] == 2 and res["pending"] == 1 and res["kanaRetried"] == 1 and res["kanaRejected"] == 1
    # 다음 실행: 비어 있는 항목만 다시 대상이 된다
    fc2 = FakeClient()
    res2 = translate.translate_pending(cat, NOW, client=fc2)
    assert [r["id"] for r in rows_of(fc2.calls[0])] == ["bh-01_1"] and cat.items["bh-01_1"]["nameKo"] == "번역 bh-01_1"
    assert res2["pending"] == 0


def test_no_retry_request_when_nothing_has_kana():
    cat, fc = cat_with(5), FakeClient()
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 1 and res["kanaRetried"] == 0 and res["kanaRejected"] == 0


def test_kana_retry_with_malformed_response_is_not_asked_a_third_time():
    def handler(n, kw):
        if n == 1:
            return reply([{"id": r["id"], "ko": "カラー"} for r in rows_of(kw)])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="not json")],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    cat, fc = cat_with(2), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc)
    assert len(fc.calls) == 2 and res["done"] == 0 and res["kanaRejected"] == 2 and res["pending"] == 2 and res["ok"]


def test_api_error_during_kana_retry_keeps_clean_translations_and_stops():
    def handler(n, kw):
        rows = rows_of(kw)
        if n == 1:   # 첫 배치 50개 중 한 개만 가나가 남는다 (어떤 id가 첫 배치인지는 정렬에 맡기고 첫 행을 고른다)
            return reply([{"id": r["id"], "ko": "カラー" if r["id"] == rows[0]["id"] else f"번역 {r['id']}"} for r in rows])
        raise RuntimeError("boom https://secret.example")
    cat, fc = cat_with(60), FakeClient(handler)
    res = translate.translate_pending(cat, NOW, client=fc, batch_size=50)
    first_batch = [r["id"] for r in rows_of(fc.calls[0])]
    kana_id = first_batch[0]
    assert len(fc.calls) == 2                                                  # 두 번째 배치는 요청하지 않는다
    assert res["ok"] is False and res["error"] == "RuntimeError" and "secret" not in json.dumps(res)
    assert cat.items[kana_id]["nameKo"] is None                                # 재요청이 실패한 항목은 비어 있다
    assert all(cat.items[i]["nameKo"] == f"번역 {i}" for i in first_batch[1:])   # 같은 배치의 깨끗한 번역은 그대로 반영
    assert all(it["nameKo"] is None for i, it in cat.items.items() if i not in first_batch)   # 둘째 배치는 요청 안 함
    assert res["done"] == 49 and res["pending"] == 11                          # 못 한 11개는 다음 실행에서


def test_kana_retry_stays_within_its_own_batch():
    calls = []

    def handler(n, kw):
        rows = rows_of(kw)
        calls.append([r["id"] for r in rows])
        bad = {rows[0]["id"]} if n == 1 else set()                             # 첫 배치의 첫 항목만 가나가 남음
        return reply([{"id": r["id"], "ko": "カラー" if r["id"] in bad else "ok"} for r in rows])
    cat = cat_with(7)
    res = translate.translate_pending(cat, NOW, client=FakeClient(handler), batch_size=5)
    # 최신순: 첫 배치 6,5,4,3,2 → 재요청 6 → 둘째 배치 1,0
    assert calls == [["bh-01_6", "bh-01_5", "bh-01_4", "bh-01_3", "bh-01_2"], ["bh-01_6"], ["bh-01_1", "bh-01_0"]]
    assert res["done"] == 7 and res["pending"] == 0 and res["kanaRetried"] == 1


# ---------------------------------------------------------------- 시스템 프롬프트·용어집
def test_system_prompt_contains_user_glossary_and_kana_rules():
    p = translate.SYSTEM_PROMPT
    for ja, ko in {"ディランザ": "딜란자", "グエル": "구엘", "スレッタ": "슬레타", "ミオリネ": "미오리네", "カラー": "컬러"}.items():
        assert f"- {ja} → {ko}" in p
    assert "[カラーC]` → `[컬러C]" in p and "히라가나·가타카나" in p and "prev_ko" in p
    assert "`[カラーB]` 같은 색상 기호" not in p                 # 예전 지시("색상 기호는 그대로 둔다")는 사라졌다


def test_glossary_comes_from_config_and_can_be_extended():
    assert translate.build_system_prompt({"テスト": "테스트"}).endswith("- テスト → 테스트")
    assert "용어집" not in translate.build_system_prompt({})
    p = translate.build_system_prompt({**config.TRANSLATE_GLOSSARY, "新語": "신어"})
    assert "- 新語 → 신어" in p and all(f"- {ja} → {ko}" in p for ja, ko in config.TRANSLATE_GLOSSARY.items())


def test_glossary_entries_are_well_formed():
    assert len(config.TRANSLATE_GLOSSARY) >= 5
    for ja, ko in config.TRANSLATE_GLOSSARY.items():
        assert ja and ko and ja.strip() == ja and ko.strip() == ko
        assert translate.has_kana(ja) or any("一" <= c <= "鿿" for c in ja), f"일본어 용어가 아님: {ja}"
        assert not translate.has_kana(ko), f"용어집 값에 가나가 있음: {ja} → {ko}"     # 값에 가나가 있으면 가나 검사와 충돌한다


def test_sent_system_prompt_is_the_glossary_prompt():
    cat, fc = cat_with(1), FakeClient()
    translate.translate_pending(cat, NOW, client=fc)
    assert "- ディランザ → 딜란자" in fc.calls[0]["system"] and fc.calls[0]["system"] == translate.SYSTEM_PROMPT


# ---------------------------------------------------------------- 샘플 CLI는 파이프라인과 같은 경로
def test_sample_cli_uses_kana_retry_and_marks_results(monkeypatch, capsys):
    def handler(n, kw):
        rows = rows_of(kw)
        bad = {rows[0]["id"], rows[1]["id"]} if n == 1 else {rows[0]["id"]}
        return reply([{"id": r["id"], "ko": "남음 カラー" if r["id"] in bad else f"번역 {r['id']}"} for r in rows])
    fc = FakeClient(handler)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(translate, "make_client", lambda: fc)
    assert translate.main(["--sample", "6"]) == 0
    out = capsys.readouterr().out
    assert len(fc.calls) == 2 and "가나 재요청 2개" in out and "비움 1개" in out and "용어집 " in out
    assert out.count("[가나가 남아 재요청함]") == 1 and out.count("[가나가 남아 nameKo 비움") == 1
    assert "(비어 있음)" in out
