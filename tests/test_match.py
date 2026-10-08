"""match.py — 대괄호 코드 → 등급, 이름 정리, 후보 좁히기, 애매하면 연결하지 않기. 0단계 표본 상품명(tests/fixtures/joyhobby-post-*.html)을 쓴다."""
import pytest

from crawler import config, match as M


def cat(cid, grade, scale, name_ko, name_ja="", line="gunpla"):
    return {"id": cid, "line": line, "grade": grade, "scale": scale, "nameKo": name_ko, "nameJa": name_ja or name_ko}


def best(name, items):
    return M.best_match(M.parse_name(name), M.CatalogIndex(items))


@pytest.mark.parametrize("bracket,grade", [
    ("HGUC011", "HG"), ("HGAW270", "HG"), ("HGWFM02", "HG"), ("HGGQX04", "HG"), ("HGCE", "HG"),
    ("RG42", "RG"), ("RG", "RG"), ("MG", "MG"), ("MGSD04", "MGSD"), ("RE009", "RE/100"),
    ("BB172", "BB"), ("SDBF030", "SD"), ("피규어라이즈스탠다드", "Figure-rise Standard"),
    ("30MM_EXM_80", None), ("30MF_ITS_05", None),        # 카탈로그 대상이 아닌 브랜드
    ("원피스", None), ("PP274", None), ("", None), (None, None),
])
def test_bracket_code_to_grade(bracket, grade):
    assert M.bracket_grade(bracket) == grade


def test_parse_name_cleans_tags_english_parens_series_tail_and_scale():
    jn = M.parse_name("[RG42] 1/144 GF13-017NJ 샤이닝 건담(SHINING GUNDAM) - 기동무투전 G건담(프라모델)")
    assert (jn.grade, jn.scale, jn.ko, jn.text) == ("RG", "1/144", "GF13-017NJ 샤이닝 건담", "샤이닝 건담")
    assert jn.models == {"GF1317NJ"}
    assert M.parse_name("[RE009] 1/100 비기나 기나(Vigina-Ghina) - 기동전사 건담 F91(프라모델)").ko == "비기나 기나"
    assert M.parse_name("[MGSD04] XVX-016 건담 에어리얼(GUNDAM AERIAL) - 기동전사 건담 수성의 마녀(프라모델)").scale is None
    assert M.parse_name("[BP027] 1/1 칭찬돼지 로봇(오다테부타)  - 타임보칸 시리즈 얏타맨(전고:약390mm)(프라모델)").ko.startswith("칭찬돼지 로봇(오다테부타)")  # 한글 괄호는 이름의 일부
    assert M.parse_name("[PP274] 프라피아 카후우 치노 - 주문은 토끼입니까?(전고:약135mm)(프라모델)").ko == "프라피아 카후우 치노"


def test_series_tail_is_cut_regardless_of_english_paren_or_repetition():
    """이름 끝의 ` - <작품명>`(+ `(프라모델)`)은 영문 괄호 유무·반복 횟수와 관계없이 뗀다 (마지막 ` - ` 뒤). 변형 표시어가 든 꼬리만 예외."""
    assert M.parse_name("[MG] 1/100 MS-14S 샤아 전용 겔구그 Ver.2.0 - 기동전사 건담(프라모델)").ko == "MS-14S 샤아 전용 겔구그 Ver.2.0"
    assert M.parse_name("[MG] 1/100 건담 F91 Ver.2.0 - 기동전사 건담 F91(프라모델)").ko == "건담 F91 Ver.2.0"
    assert M.parse_name("[30MS] 옵션 바디 파츠 알파 시스터즈 판타즘2 컬러C - 아이돌마스터 샤이니 컬러즈(프라모델)").ko == "옵션 바디 파츠 알파 시스터즈 판타즘2 컬러C"
    assert M.parse_name("[HGUC011] 1/144 큐베레이 마크2 - 플 전용기 Qubeley Mk.II").ko == "큐베레이 마크2 - 플 전용기 Qubeley Mk.II"   # 변형 표시어 → 안 뗀다
    assert M.parse_name("[BP027] 1/1 칭찬돼지 로봇(오다테부타)  - 얏타맨 - 타임보칸(프라모델)").ko == "칭찬돼지 로봇(오다테부타) - 얏타맨"   # 마지막 꼬리 하나만
    assert M.parse_name("[HG] 1/144 건담-X 에어리얼(프라모델)").ko == "건담-X 에어리얼"                                            # 붙은 하이픈은 꼬리가 아니다


def test_f91_ver2_links_now_that_the_series_tail_is_cut():
    """첫 보고에서 점수 70으로 놓쳤던 사례: 조이하비 `건담 F91 Ver.2.0 - 기동전사 건담 F91` ↔ 카탈로그 `건담 F91 Ver.2.0`."""
    items = [cat("f91", "MG", "1/100", "MG 1/100 건담 F91 Ver.2.0"), cat("m91", "MG", "1/100", "MG 1/100 건담 M91 Ver.2.0")]
    m = best("[MG] 1/100 건담 F91 Ver.2.0 - 기동전사 건담 F91(프라모델)", items)
    assert m.linked and m.catalog_id == "f91" and m.score == 100 and m.name_ok


def test_replacements_apply_to_joy_name_like_catalog_names():
    jn = M.parse_name("[피규어라이즈스탠다드] 매그너가루몬 앰플리파이드(MagnaGarurumon Amplified) - 디지몬 프론티어(프라모델)")
    assert jn.grade == "Figure-rise Standard" and jn.ko == "매그너가루몬 Amplified"


def test_display_name_uses_grade_scale_then_name():
    jn = M.parse_name("[HGUC011] 1/144 큐베레이 마크2 - 플 전용기 Qubeley Mk.II")
    assert M.display_name(jn) == "HG 1/144 큐베레이 마크2 - 플 전용기 Qubeley Mk.II"
    assert M.display_name(M.parse_name("[MGSD06] 크샤트리아(KSHATRIYA)"), grade="MGSD", scale=None) == "MGSD 크샤트리아"
    assert M.display_name(M.parse_name("[MGSD06] 크샤트리아"), scale="1/60") == "MGSD 1/60 크샤트리아"      # 이름에 스케일이 없으면 카탈로그 값


def test_model_tokens_normalize_leading_zeros_and_ignore_plain_words():
    assert M.model_tokens("RX-78-02") == M.model_tokens("RX-78-2 건담")
    assert M.model_tokens("MS-09F 돔", "MSN-04 사자비") == {"MS9F", "MSN4"}
    assert M.model_tokens("Ver.2.0 Mk-II 건담 DX") == frozenset()


# ---------------------------------------------------------------- 매칭
def test_exact_name_links_and_replaces_name():
    items = [cat("a", "RG", "1/144", "RG 1/144 샤이닝 건담"), cat("b", "RG", "1/144", "RG 1/144 지옹"), cat("c", "MG", "1/100", "MG 1/100 샤이닝 건담")]
    m = best("[RG42] 1/144 GF13-017NJ 샤이닝 건담(SHINING GUNDAM) - 기동무투전 G건담(프라모델)", items)
    assert m.linked and m.catalog_id == "a" and m.name_ok and m.score == 100 and m.margin >= config.MATCH_MARGIN


def test_model_number_is_ignored_for_similarity_but_conflict_blocks_the_link():
    items = [cat("ff", "RG", "1/144", "RG 1/144 MSN-04FF 사자비")]
    m = best("[RG29] 1/144 MSN-04 사자비(SAZABI) - 기동전사 건담 역습의 샤아(프라모델)", items)
    assert not m.linked and m.reason == "model-conflict"           # 이름은 같아도 모델번호가 다르면 다른 상품 (MSN-04 ≠ MSN-04FF)
    both = items + [cat("plain", "RG", "1/144", "RG 1/144 사자비")]
    m2 = best("[RG29] 1/144 MSN-04 사자비(SAZABI)", both)
    assert m2.linked and m2.catalog_id == "plain"                   # 모델번호가 없는 쪽은 충돌이 아니다
    same = [cat("x", "RG", "1/144", "RG 1/144 MSN-04 사자비")]
    assert best("[RG29] 1/144 MSN-04 사자비", same).linked


def test_ambiguous_two_equal_candidates_are_not_linked():
    items = [cat("a1", "HG", "1/144", "HG 1/144 건담 에어리얼"), cat("a2", "HG", "1/144", "HG 1/144 건담 에어리얼")]
    m = best("[HGWFM01] 1/144 건담 에어리얼(GUNDAM AERIAL)", items)
    assert not m.linked and m.reason == "ambiguous" and m.margin == 0


def test_similar_but_different_names_are_not_linked_low_score():
    items = [cat("a", "HG", "1/144", "HG 1/144 돔 트로펜 (유니콘 Ver.)")]
    m = best("[HGUC017] 1/144 MS-09F 돔 트로펜 (Dom Tropen) - 기동전사 건담 0083 스타더스트 메모리(프라모델)", items)
    assert not m.linked and m.reason == "low-score"


def test_grade_scale_and_family_filter_candidates():
    items = [cat("mg", "MG", "1/100", "MG 1/100 건담 에어리얼"), cat("hg144", "HG", "1/144", "HG 1/144 건담 에어리얼"),
             cat("hg72", "HG", "1/72", "HG 1/72 건담 에어리얼")]
    assert best("[HG] 1/144 건담 에어리얼", items).catalog_id == "hg144"              # 등급·스케일이 같은 것만
    assert best("[HG] 1/100 건담 에어리얼", items).reason == "no-candidates"          # 스케일이 둘 다 있고 다르면 제외
    assert best("[HG] 건담 에어리얼", items).reason == "ambiguous"                   # 스케일을 모르면 후보가 둘 → 연결하지 않음
    assert best("[SDBF030] SD 스타 위닝 건담", [cat("sd", "SD", None, "SD 스타 위닝 건담")]).linked
    assert best("[BB172] SD 호검 건담", [cat("sd", "SD", None, "SD 호검 건담")]).linked        # BB ↔ SD 계열 허용
    fr = [cat("fa", "Figure-rise Standard Amplified", None, "Figure-rise Standard Amplified 매그너가루몬 Amplified", line="girl")]
    assert best("[피규어라이즈스탠다드] 매그너가루몬 앰플리파이드(MagnaGarurumon Amplified)", fr).linked


def test_unknown_grade_or_missing_names_never_match():
    items = [cat("a", "HG", "1/144", "HG 1/144 고잉 메리호")]
    assert best("[원피스] 고잉 메리호 (GOING MERRY)(프라모델)", items).reason == "no-grade"
    assert best("[30MM_EXM_80] 1/144 xEXM-000 제노발트(XENOVALT)(프라모델)", items).reason == "no-grade"
    assert best("브리짓 가동 플라스틱 모델", items).reason == "no-grade"
    assert best("[HG] 1/144 MS-09F", items).reason == "no-name"
    assert M.best_match(M.parse_name("[HG] 1/144 건담"), M.CatalogIndex([])).reason == "no-candidates"


def test_catalog_items_without_name_ko_or_in_pending_line_are_not_candidates():
    items = [dict(cat("a", "HG", "1/144", ""), nameKo=None), cat("p", "HG", "1/144", "HG 1/144 건담", line=None)]
    assert M.CatalogIndex(items).by_grade == {}


def test_name_tier_is_stricter_than_link_tier(monkeypatch):
    items = [cat("a", "HG", "1/144", "HG 1/144 건담 아스타로트 리나시멘토")]
    name = "[HGGT] 1/144 건담 아스타로트 리나시멘트(리나시멘토)(GUNDAM ASTAROTH RINASCIMENTO)"
    m = best(name, items)                                              # 철자 한 글자 차이: 연결은 되지만 이름 교체 기준에는 못 미친다
    assert m.linked and not m.name_ok and config.MATCH_LINK_SCORE <= m.score < config.MATCH_NAME_SCORE
    monkeypatch.setattr(config, "MATCH_NAME_SCORE", 82)
    assert best(name, items).name_ok


# ---------------------------------------------------------------- 보호 규칙 (실제 첫 실행에서 점수 80~92로 잘못 연결됐던 사례들)
@pytest.mark.parametrize("joy,catalog_name,reason", [
    ("[HGUC] 1/144 MSN-001 델타 건담(DELTA GUNDAM)", "HGUC 1/144 제타 건담", "token"),
    ("[HGUC] 1/144 RX-105 크시 건담(XI GUNDAM)", "HGUC 1/144 건담 픽시", "token"),
    ("[RE] 1/100 AMX-107 바우(BAWOO)", "RE/100 리바우", "token"),
    ("[HG] 1/144 GW-9800 건담 에어마스터(GUNDAM AIRMASTER)", "HG 1/144 건담 에어마스터 버스트", "token"),
    ("[HGUC] 1/144 AMX-011 자쿠 III(ZAKU III)", "HGUC 1/144 자쿠 II", "alnum"),
    ("[HGBF] 1/144 건담 F91(GUNDAM F91)", "HGBF 1/144 건담 M91", "alnum"),
    ("[HGBF] 1/144 짐 스나이퍼 K9(GM SNIPER K9)", "HGUC 1/144 짐 스나이퍼", "alnum"),
    ("[HGUC] 1/144 짐스나이퍼2(GM Sniper II)", "HGUC 1/144 짐 스나이퍼", "alnum"),
    ("[HG] 1/144 건담 아스트레이 레드프레임(ASTRAY RED FRAME)", "HG 1/144 건담 아스트레이 레드 프레임 인버전", "token"),
    ("[RG] 1/144 XXXG-00W0 윙건담 제로 EW(WING GUNDAM ZERO EW)", "RG 1/144 윙 건담 제로", "alnum"),
    ("[MG] 1/100 유니콘건담 2호기 밴시(BANSHEE)", "MG 1/100 유니콘 건담 2호기 밴시 Ver.Ka", "alnum"),
    ("[HG] 1/144 GN-003 건담 큐리오스(KYRIOS)", "HG 1/144 건담 헬리오스", "token"),                      # 낱말 유사도 75%: 철자 변형으로 보기엔 너무 멀다
])
def test_guard_rejects_near_names_that_are_different_products(joy, catalog_name, reason):
    grade = joy[1:].split("]")[0]
    m = best(joy, [cat("x", {"HGUC": "HG", "HGBF": "HG", "RE": "RE/100"}.get(grade, grade), None, catalog_name)])
    assert not m.linked and m.reason == "guard" and m.guarded == reason, (m.score, m.reason, m.guarded)


@pytest.mark.parametrize("joy,catalog_name", [
    ("[HG] 1/144 베귀르펜테", "HG 1/144 베귀르펜데"),                                                # 철자 변형(4글자 이상 낱말, 80% 이상)은 통과
    ("[HG] 1/144 ASW-G-66 건담 키마리스 비다르(GUNDAM KIMARIS VIDAR)", "HG 1/144 건담 키마리스 비다르"),   # 하이픈 사이에 영문자가 낀 모델번호
    ("[HG] 1/144 자쿠 GQ", "HG 1/144 자쿠(GQ)"),                                                    # 카탈로그 이름 속 영문 괄호도 이름의 일부
    ("[MG] 1/100 베지터 NEW SPEC Ver.", "MG 1/100 베지터 (NEW SPEC Ver.)"),
    ("[HG] 1/144 디스트로이 건담", "HG 1/144 데스트로이 건담"),
    ("[HG] 1/144 건담 아스타로트 리나시멘트(리나시멘토)", "HG 1/144 건담 아스타로트 리나시멘토"),
    ("[SDCS] SD건담 크로스실루엣 크로스본 건담 X1", "SD건담 크로스 실루엣 크로스본 건담 X1"),           # 띄어쓰기만 다르면 통과
    ("[30MS] 옵션 바디 파츠 알파 시스터즈 판타즘2 컬러C", "30MS 옵션 바디 파츠 알파 시스터즈 판타즘2[컬러C]"),
    ("[RG] 1/144 RX-93 뉴건담", "RG 1/144 ν건담"),                                                   # ν = 뉴
    ("[SDBF030] SD 스타 위닝 건담", "SD 스타 위닝 건담"),                                              # 이름 앞의 SD는 등급 낱말이라 양쪽에서 뗀다
])
def test_guard_still_allows_spelling_and_spacing_variants(joy, catalog_name):
    grade = joy[1:].split("]")[0]
    grade = {"HGBF": "HG", "SDBF030": "SD"}.get(grade, grade)
    m = best(joy, [cat("x", grade, None, catalog_name)])
    assert m.linked, (m.score, m.reason, m.guarded)


def test_guard_filters_candidates_before_ranking_so_a_decoy_does_not_block_the_real_match():
    items = [cat("real", "HG", "1/144", "HG 1/144 건담 에어마스터"), cat("burst", "HG", "1/144", "HG 1/144 건담 에어마스터 버스트")]
    m = best("[HG] 1/144 GW-9800 건담 에어마스터(GUNDAM AIRMASTER)", items)
    assert m.linked and m.catalog_id == "real"
    only_burst = best("[HG] 1/144 GW-9800 건담 에어마스터(GUNDAM AIRMASTER)", items[1:])
    assert not only_burst.linked and only_burst.guarded == "token"


def test_model_numbers_conflict_unless_one_side_contains_the_other():
    items = [cat("a", "MG", "1/100", "MG 1/100 GN-0000+GNR-010/XN 더블오 잔라이저")]
    m = best("[MG] 1/100 GN-0000+GNR-010 더블오라이저(00 RAISER)", items)
    assert not m.linked                                              # {GN0000, GNR010} vs {GN0000, GNR010XN}: 서로 포함하지 않는다


# ---------------------------------------------------------------- 말머리, 그리스 문자
def test_leading_secondary_bracket_and_greek_letters():
    jn = M.parse_name("[피규어라이즈스탠다드] [드래곤볼] 얼티밋 손오반(프라모델)")
    assert jn.grade == "Figure-rise Standard" and jn.ko == "얼티밋 손오반"
    assert M.squash("ν건담") == M.squash("뉴건담") and M.squash("Ξ건담") == M.squash("크시 건담")


@pytest.mark.parametrize("joy,catalog_name", [
    ("[HGBF] 1/144 스트라이커 징크스(STRIKER JINX)", "HGBF 1/144 스트라이커 진크스"),                 # 3글자 낱말의 철자 차이는 델타/제타와 구조가 같다
    ("[HG] 1/144 건담 어메이징 발바토스 루프스", "HG 1/144 건담 어메이징 바르바토스 루프스"),             # 낱말 유사도 67% < 80%
    ("[HG] 1/144 건담 르브리스", "HG 1/144 건담 루브리스"),                                          # 75%: 큐리오스/헬리오스와 구별할 수 없다
])
def test_ambiguous_spelling_variants_are_rejected_on_purpose(joy, catalog_name):
    """철자 변형인지 다른 상품인지 구별할 수 없는 차이는 연결하지 않는다 (알려진 재현율 손실 — 맞는 쌍은 KR_CODE_OVERRIDES로 지정)."""
    m = best(joy, [cat("x", "HG", None, catalog_name)])
    assert not m.linked and m.guarded == "token"


# ---------------------------------------------------------------- 변형 표시어가 든 꼬리는 떼지 않는다
@pytest.mark.parametrize("tail", ["플 전용기 Qubeley Mk.II", "플 전용기", "윙 건담 제로 커스텀", "특별 사양", "한정사양(1차)", "타입 B", "타입-B", "TYPE-A",
                                  "Type B", "컬러 B", "Ver.Ka", "VER. 2.0", "Version 2", "버전 업", "오오와시 장비", "플라이트 유닛", "프리미엄 에디션", "Limited Edition"])
def test_tail_with_a_variant_marker_is_kept(tail):
    assert M.parse_name(f"[HG] 1/144 기체 - {tail}(프라모델)").ko == f"기체 - {tail}"


@pytest.mark.parametrize("tail", ["기동전사 건담 F91", "아이돌마스터 샤이니 컬러즈", "기동전사 건담 수성의 마녀", "원피스", "마크로스7", "Gundam Verse Origin"])
def test_series_names_are_cut_even_when_they_look_close_to_a_marker(tail):
    """컬러즈는 컬러가 아니고, Verse는 Ver가 아니다 (낱말 경계)."""
    assert M.parse_name(f"[HG] 1/144 기체 - {tail}(프라모델)").ko == "기체"


def test_exempt_series_name_with_a_marker_is_cut(monkeypatch):
    name = "[HG] 1/144 기체 - 기동전사 건담 특별 사양(프라모델)"
    assert M.parse_name(name).ko == "기체 - 기동전사 건담 특별 사양"          # 목록에 없으면 표시어 때문에 남는다
    monkeypatch.setattr(config, "JOY_TAIL_EXEMPT", ("기동전사 건담 특별 사양",))
    assert M.parse_name(name).ko == "기체"


def test_variant_named_with_a_subtitle_is_not_linked_to_the_base_kit():
    """`큐베레이 마크2 - 플 전용기`는 기본형만 있는 카탈로그에서 연결되지 않아야 한다 (틀린 연결 < 연결 없음)."""
    base_only = [cat("base", "HG", "1/144", "HGUC 1/144 큐베레이 마크2")]
    for name in ("[HGUC011] 1/144 큐베레이 마크2 - 플 전용기 Qubeley Mk.II", "[HGUC011] 1/144 큐베레이 마크2 - 플 전용기(프라모델)"):
        m = best(name, base_only)
        assert not m.linked and m.reason in ("guard", "low-score"), (name, m.score, m.reason, m.guarded)     # 점수가 낮든 보호 규칙이 막든 연결은 안 된다
    # 기본형 이름 그대로 올라온 상품은 여전히 연결된다 (꼬리가 작품명이면 떼므로)
    assert best("[HGUC011] 1/144 큐베레이 마크2 - 기동전사 Z건담(프라모델)", base_only).linked
