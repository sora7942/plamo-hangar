"""audit_terms.py — 같은 가타카나 단어의 한국어 표기 갈림 점검. 합성 문서만 쓴다 (네트워크·Claude 없음)."""
import json

from crawler import audit_terms as at
from crawler import config


def docs(*rows):
    return [at.Doc(ja, ko, kind, f"k{i}") for i, (ja, ko, kind) in enumerate(rows)]


def test_skeletons_put_katakana_and_hangul_spellings_of_one_word_together():
    assert at.kata_skeleton("クアンタ") == "KNT"
    assert {at.hangul_skeleton(w) for w in ("쿠안타", "콴타", "퀀터", "퀀타")} == {"KNT"}
    assert at.kata_skeleton("ヴィダール") == at.hangul_skeleton("비다르") == "PTR"
    assert at.kata_skeleton("ストライク") == at.hangul_skeleton("스트라이크") == "STRK"
    assert at.kata_skeleton("ガンダム") == at.hangul_skeleton("건담")
    assert at.sounds_like("콴타", "クアンタ") and not at.sounds_like("건담", "クアンタ")
    assert at.same_sound("쿠안타", "콴타") and not at.same_sound("이펙트", "스트라이크")


def test_finds_words_spelled_differently_and_uses_shop_spelling_as_evidence():
    d = docs(*[("HG ダブルオークアンタ", "HG 더블오 쿠안타", "ai")] * 0)
    rows = []
    for i in range(4):
        rows.append((f"MG ダブルオークアンタ{i}型", f"MG 더블오 쿠안타 {i}형", "ai"))
    rows += [("HG ダブルオークアンタ", "HG 더블오 콴타", "ai"), ("RG ダブルオークアンタ", "RG 더블오 콴타", "shop"), ("SD クアンタ", "SD 콴타", "shop")]
    rows += [("HG ガンダム エアリアル", f"HG 건담 에어리얼 {i}", "ai") for i in range(40)]            # 어디에나 나오는 말(건담)은 점검에서 빠진다
    found = at.find_variants(docs(*rows), min_items=3)
    q = [r for r in found if "クアンタ" in r["ja"]]
    assert q and set(q[0]["variants"]) == {"쿠안타", "콴타"}
    assert q[0]["variants"]["쿠안타"] == 4 and q[0]["variants"]["콴타"] == 3 and q[0]["shop"] == {"쿠안타": 0, "콴타": 2}
    best, why = at.propose(q[0])
    assert best == "콴타" and "조이하비" in why                                                    # 국내 매장 표기를 근거로 제안
    assert not [r for r in found if "건담" in set(r["variants"])]


def test_no_shop_evidence_or_a_tie_means_no_proposal_only_display():
    row = {"ja": "クアンタ", "items": 5, "variants": {"쿠안타": 3, "콴타": 2}, "shop": {"쿠안타": 0, "콴타": 0}}
    assert at.propose(row)[0] is None and "표시만" in at.propose(row)[1]
    row["shop"] = {"쿠안타": 1, "콴타": 1}
    assert at.propose(row)[0] is None and "갈림" in at.propose(row)[1]
    assert at.retranslate_count({"variants": {"쿠안타": 9, "퀀타": 3, "콴타": 1}}, "콴타") == 12
    assert at.retranslate_count({"variants": {"쿠안타": 9, "콴타": 1}}, None) == 1                  # 제안이 없으면 다수결 기준


def test_suffix_differences_and_fragments_are_not_reported_as_spelling_variants():
    rows = [(f"HG ストライクガンダム{i}", f"HG 스트라이크 건담 {i}", "ai") for i in range(3)]
    rows += [(f"MG ストライクルージュ{i}", f"MG 스트라이크루즈 {i}", "ai") for i in range(3)]            # 다른 낱말(루즈)
    rows += [("HG タイプ", "HG 타입", "ai")] * 3 + [("HG プロトタイプ", "HG 프로토타입", "ai")] * 3       # 프로토타입은 타입을 포함 → 표기 차이가 아니다
    found = at.find_variants(docs(*rows), min_items=3)
    assert not [r for r in found if {"타입", "프로토타입"} <= set(r["variants"])]


def test_collection_only_spellings_are_listed_as_alias_candidates(tmp_path):
    cat = [("HG ダブルオークアンタ", "HG 더블오 퀀타", "ai"), ("MG ダブルオークアンタ", "MG 더블오 퀀타", "ai"), ("RG ダブルオークアンタ", "RG 더블오 퀀타", "ai")]
    (tmp_path / config.COLLECTION_FILE).write_text(json.dumps({"kits": [{"name": "퀀타 풀세이버"}, {"name": "퀀터 데저트"}, {"name": "퀀터 트란잠"}, {"name": "더블오"}]}, ensure_ascii=False), encoding="utf-8")
    out = at.collection_alias_candidates(docs(*cat), tmp_path, min_docs=2)
    assert [(r["mine"], r["mine_n"], r["catalog"]) for r in out] == [("퀀터", 2, "퀀타")]            # 카탈로그와 같은 표기(퀀타)는 후보가 아니다
    row = {"ja": "クアンタ", "variants": {"퀀타": 3}}
    assert at.collection_spellings(tmp_path, row) == ["퀀터(2)"]


def test_main_reads_only_and_writes_report_when_asked(tmp_path, capsys):
    for name in config.CATALOG_FILES.values():
        (tmp_path / name).write_text(json.dumps({"updatedAt": "x", "items": []}), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    out = tmp_path / "report" / "r.md"
    assert at.main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    assert out.exists() and "표기가 갈린 단어 0개" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before | {}          # 데이터 폴더의 파일은 그대로
