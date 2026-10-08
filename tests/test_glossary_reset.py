"""용어집을 고친 뒤 기존 번역을 다시 번역 대상으로 비우는 일(한 번만), --translate-only/--translate-max. Claude는 가짜 클라이언트."""
import json
from types import SimpleNamespace

import pytest

from crawler import config, series
from crawler.catalog import Catalog
from crawler.pipeline import Options
from crawler.store import write_json
from test_pipeline import World, go, read


def item(i, ja, ko, **extra):
    return {"id": i, "line": "gunpla", "grade": "HG", "nameJa": ja, "nameKo": ko, "release": {"month": "2026-10"}, **extra}


def test_reset_blanks_only_translations_that_lack_the_new_spelling():
    cat = Catalog()
    cat.items = {i["id"]: i for i in (
        item("a", "HG 1/144 クアンタ", "HG 1/144 쿠안타"),                                            # 다른 표기 → 비운다
        item("b", "HG 1/144 ダブルオークアンタ", "HG 1/144 더블오 콴타"),                              # 이미 지정 표기 → 그대로
        item("c", "HG 1/144 ガンダム", "HG 1/144 건담"),                                              # 용어와 상관없음
        item("d", "HG 1/144 クアンタ", "HG 1/144 퀀타", nameKoSource="joyhobby"),                      # 조이하비 한글명은 건드리지 않는다
        item("e", "HG 1/144 クアンタ", None),                                                        # 이미 비어 있음
        item("f", "ＨＧ 1/144 ティターンズの旗", "HG 1/144 티탄즈의 깃발"),                              # 조사(의)가 붙어도 지정 표기가 들어 있으면 정상
        item("g", "HG 1/144 ティターンズ仕様", "HG 1/144 티탄스 사양"),
    )}
    gl = {"クアンタ": "콴타", "ティターンズ": "티탄즈", "ガンダム": "건담"}
    assert sorted(cat.reset_glossary(gl, {})) == ["a", "g"]
    assert cat.items["a"]["nameKo"] is None and cat.items["g"]["nameKo"] is None
    assert cat.items["b"]["nameKo"] == "HG 1/144 더블오 콴타" and cat.items["d"]["nameKo"] == "HG 1/144 퀀타" and cat.items["f"]["nameKo"]


def test_reset_is_once_per_entry_value_and_nfkc_aware():
    cat = Catalog()
    cat.items = {"a": item("a", "ＨＧ １/144 ｸｱﾝﾀ", "HG 1/144 쿠안타")}                                # 전각·반각도 같은 낱말로 본다
    assert cat.reset_glossary({"クアンタ": "콴타"}, {"クアンタ": "콴타"}) == []                        # 이미 적용한 용어는 다시 비우지 않는다
    assert cat.items["a"]["nameKo"] == "HG 1/144 쿠안타"
    assert cat.reset_glossary({"クアンタ": "콴타"}, {"クアンタ": "퀀타"}) == ["a"]                      # 값이 바뀌면 다시 적용한다
    assert cat.reset_glossary({}, {}) == []


def test_series_entries_are_dropped_the_same_way():
    known = {"narrative": {"ja": "機動戦士ガンダムNT[ナラティブ]", "ko": "기동전사 건담 NT[나라티브]"},
             "macross": {"ja": "マクロスシリーズ", "ko": "마크로스 시리즈"},
             "x": {"ja": "別のシリーズ", "ko": "다른 시리즈"}}
    gone = series.drop_glossary(known, {"ナラティブ": "내러티브", "クロス": "크로스"}, {})
    assert gone == ["narrative"] and set(known) == {"macross", "x"}                                  # 마크로스에는 `크로스`가 들어 있으니 그대로


def test_config_glossary_additions_are_whole_words_and_the_titans_rule_is_not_a_particle_ban():
    g = config.TRANSLATE_GLOSSARY
    assert g["クアンタ"] == "콴타" and g["アクシズ"] == "액시즈" and g["ティターンズ"] == "티탄즈"
    assert "アクシ" not in g, "`アクシ`는 アクション까지 걸린다 — 낱말 전체(アクシズ)만"
    assert not [k for k in g if len(k) <= 2 and k not in {"シャア"}], "너무 짧은 키는 낱말 일부에 걸린다"
    assert "의" not in g["ティターンズ"]


def run_with_fake(tmp_path, opts, calls, tr=None):
    def create(**kw):
        rows = json.loads(kw["messages"][0]["content"])
        calls.append([r["id"] for r in rows])
        text = json.dumps({"items": [{"id": r["id"], "ko": (tr or (lambda r: f"한글 {r['id']}"))(r)} for r in rows]}, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    return go(World(), tmp_path, opts, anthropic_client=SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_pipeline_retranslates_items_for_a_new_glossary_entry_once(tmp_path, monkeypatch):
    calls = []
    run_with_fake(tmp_path, Options(bootstrap=True, from_month="2026-09"), calls)
    meta = read(tmp_path, "meta.json")
    assert meta["crawl"]["glossaryApplied"] == config.TRANSLATE_GLOSSARY                          # 지금 용어집은 모두 적용된 것으로 기록
    f = tmp_path / "catalog-gunpla.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    for it in doc["items"]:
        if it["id"] == "bh-01_7001":
            it["nameKo"] = "HG 1/144 테스트기A"
    write_json(f, doc)

    monkeypatch.setitem(config.TRANSLATE_GLOSSARY, "テスト機", "시험기")                             # 용어집에 새 용어
    calls.clear()
    res, *_ = run_with_fake(tmp_path, Options(), calls)
    items = {i["id"]: i for i in read(tmp_path, "catalog-gunpla.json")["items"]}
    assert items["bh-01_7001"]["nameKo"] == "한글 bh-01_7001"                                     # 같은 실행에서 다시 번역됨
    assert calls == [["bh-01_7001"]] and res["meta"]["crawl"]["lastFixups"]["glossaryReset"] == 1
    assert read(tmp_path, "meta.json")["crawl"]["glossaryApplied"]["テスト機"] == "시험기"

    calls.clear()                                                                                 # 모델이 지정 표기를 안 써도 매 실행 비우지 않는다
    res, *_ = run_with_fake(tmp_path, Options(), calls)
    assert calls == [] and res["meta"]["crawl"]["lastFixups"]["glossaryReset"] == 0


def test_translate_max_limits_one_run_newest_first(tmp_path):
    calls = []
    res, *_ = run_with_fake(tmp_path, Options(bootstrap=True, from_month="2026-09", translate_max=1), calls)
    assert sum(1 for c in calls for i in c if i.startswith(('bh-', 'pb-'))) == 1 and res["meta"]["sources"]["translate"]["pending"] >= 1


def test_translate_only_runs_just_the_translate_stage_with_its_cap():
    import main as m            # 테스트 안에서 가져온다 — 모듈 맨 위에서 가져오면 conftest가 load_dotenv를 막기 전에 main이 진짜 load_dotenv를 묶어 둔다
    a = m.parse_args(["--translate-only", "--translate-max", "1500"])
    assert a.translate_only and a.translate_max == 1500
    assert m.parse_args([]).translate_max == config.TRANSLATE_MAX_PER_RUN and not m.parse_args([]).translate_only
    assert Options(only={"translate"}).stages() == {"translate"}
    for bad in (["--translate-max", "0"], ["--translate-max", str(config.TRANSLATE_MAX_HARD + 1)],
                ["--translate-only", "--only", "joyhobby"], ["--translate-only", "--bootstrap"], ["--translate-only", "--brand-backfill"],
                ["--translate-only", "--discord-test"]):
        with pytest.raises(SystemExit):
            m.parse_args(bad)


def test_workflow_has_translate_only_inputs_and_runs_translate_without_collecting():
    wf = (config.ROOT / ".github" / "workflows" / "crawl.yml").read_text(encoding="utf-8")
    assert "translate_only:" in wf and "translate_max:" in wf and "default: 600" in wf
    assert 'python main.py --translate-only --translate-max "${TRANSLATE_MAX:-600}"' in wf
    assert wf.index("TRANSLATE_ONLY\" = \"true\"") < wf.index("python main.py \"${args[@]}\"")
