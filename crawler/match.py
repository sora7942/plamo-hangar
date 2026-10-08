"""조이하비 상품명 ↔ 카탈로그 매칭 (SPEC 5장 "매칭").

조이하비 상품명: `[등급코드] 스케일 모델번호 한글명(영문명) - 작품(프라모델)`
카탈로그에는 영문명이 없고 번역된 `nameKo`만 있어서, 영문명 대신 다음을 쓴다.
  1. 등급(대괄호 코드 → config.JOY_BRACKET_GRADES)과 스케일로 후보를 좁힌다. 등급을 모르면 매칭하지 않는다
  2. 한글명 유사도(rapidfuzz). 모델번호·작품 꼬리·영문 괄호는 이름에서 뗀다
  3. 모델번호(MS-09F, GF13-017NJ …)가 양쪽에 있으면 같을 때 가산, 서로 다르면 연결하지 않는다
  4. **보호 규칙(guard)**: 점수가 높아도 한 글자·숫자·로마숫자·덧붙은 단어가 다르면 다른 상품으로 본다
     (델타↔제타, 자쿠 III↔자쿠 II, 짐 스나이퍼 K9↔짐 스나이퍼, 에어마스터↔에어마스터 버스트)
애매하면 연결하지 않는다 (틀린 연결 < 연결 없음): 보호 규칙을 통과한 1등이 MATCH_LINK_SCORE 이상이고
2등과 MATCH_MARGIN 이상 벌어져야 한다. nameKo를 조이하비 한글명으로 바꾸는 것은 더 엄격한 MATCH_NAME_SCORE를 넘을 때만 한다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from . import config

LINES = ("gunpla", "girl")
_BRACKET_RX = re.compile(r"^\s*\[([^\]]*)\]\s*")
_LEADING_BRACKETS_RX = re.compile(r"^(?:\s*\[[^\]]*\])+\s*")                  # 등급 코드 뒤의 [드래곤볼] 같은 말머리
_BRACKET_KEY_RX = re.compile(r"^(\d*[A-Za-z가-힣]+)")
_SCALE_RX = re.compile(r"(?<![\d/])1/\d{1,4}(?!\d)")
_SIZE_NOTE_RX = re.compile(r"\s*\((?:전고|전장|사이즈|높이)[^()]*\)")
_PLAMO_TAG_RX = re.compile(r"\s*\(프라모델\)\s*$")
_EN_PAREN_RX = re.compile(r"\s*\((?=[^()]*[A-Za-z])(?![^()]*[가-힣])[^()]*\)")       # (SHINING GUNDAM) 같은 영문 괄호만
_TAIL_SPLIT_RX = re.compile(r"\s+-\s+")                                                   # " - " (앞뒤 공백 여러 개 허용)
_MODEL_RX = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{1,5}\d{0,3}(?:-[A-Za-z])?-\d[A-Za-z0-9\-/]*")
_PUNCT_RX = re.compile(r"[\s\-_·・.,:;'\"!?/+()\[\]~&]+")
_RUN_RX = re.compile(r"[a-z0-9]+")
_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
_GRADE_WORD_RX = re.compile(
    r"^(?:HG\w*|RG|MG\w*|PG\w*|EG|SD\w*|BB|RE/100|30MS|30MP|FULL|MECHANICS|Figure-rise|Standard|Amplified|MEGA|SIZE|"
    r"Hi-Resolution|Model|Entry|Grade|HEROES)$", re.I)
_GREEK = {"ν": "뉴", "Ν": "뉴", "ξ": "크시", "Ξ": "크시", "ζ": "제타", "Ζ": "제타", "α": "알파", "Α": "알파", "β": "베타", "Β": "베타",
          "γ": "감마", "δ": "델타", "Δ": "델타", "π": "파이", "Π": "파이", "σ": "시그마", "Σ": "시그마", "ω": "오메가", "Ω": "오메가",
          "μ": "뮤", "Μ": "뮤", "φ": "파이", "Φ": "파이"}


def nfkc(s: str | None) -> str:
    return unicodedata.normalize("NFKC", s or "")


def fold(s: str | None) -> str:
    """비교용 정규화: NFKC + 그리스 문자를 한글 읽기로 (ν건담 = 뉴건담)."""
    s = nfkc(s)
    for k, v in _GREEK.items():
        s = s.replace(k, v)
    return s


def squash(s: str) -> str:
    """비교용: 정규화·소문자·공백/구두점 제거."""
    return _PUNCT_RX.sub("", fold(s).lower())


def spaced(s: str) -> str:
    return _PUNCT_RX.sub(" ", fold(s).lower()).strip()


def model_tokens(*texts: str | None) -> frozenset[str]:
    """모델번호 토큰. 영숫자만 남기고 숫자 앞의 0을 뗀다 (RX-78-02 == RX-78-2)."""
    out = set()
    for t in texts:
        for m in _MODEL_RX.findall(nfkc(t)):
            out.add(re.sub(r"[^A-Z0-9]", "", re.sub(r"(?<![0-9])0+(?=[0-9])", "", m.upper())))
    return frozenset(out)


def strip_models(s: str) -> str:
    return re.sub(r"\s+", " ", _MODEL_RX.sub(" ", s)).strip()


def significant_runs(text: str) -> tuple[str, ...]:
    """이름 속 영문·숫자 덩어리 중 상품을 가르는 것: 숫자가 들어간 것(K9, F91, 2), 로마숫자(II, III), 3글자 이하(EW, XN, Ka, SD).
    띄어쓰기와 무관하게 비교하려고 정렬한 튜플로 돌려준다."""
    runs = _RUN_RX.findall(fold(text).lower())
    return tuple(sorted(r for r in runs if any(c.isdigit() for c in r) or r in _ROMAN or len(r) <= 3))


# ---------------------------------------------------------------- 조이하비 상품명
@dataclass(frozen=True)
class JoyName:
    raw: str
    bracket: str | None
    grade: str | None          # 카탈로그 등급 (모르면 None → 매칭하지 않음)
    scale: str | None
    ko: str                    # 대괄호 코드·스케일·영문 괄호·(프라모델)·작품 꼬리를 뗀 이름
    models: frozenset = field(default_factory=frozenset)
    text: str = ""             # ko에서 모델번호까지 뺀 것 — 유사도는 이걸로 잰다


def bracket_grade(bracket: str | None) -> str | None:
    if not bracket:
        return None
    m = _BRACKET_KEY_RX.match(nfkc(bracket).strip())
    if not m:
        return None
    key = m.group(1).upper()
    for pattern, grade in config.JOY_BRACKET_GRADES:
        if re.search(pattern, key):
            return grade
    return None


def _clean_rest(raw: str) -> tuple[str | None, str]:
    """→ (대괄호 코드, 대괄호·(프라모델)·크기 표기를 뗀 나머지)."""
    text = nfkc(raw).strip()
    bm = _BRACKET_RX.match(text)
    bracket = bm.group(1) if bm else None
    rest = text[bm.end():] if bm else text
    rest = _LEADING_BRACKETS_RX.sub("", rest)
    rest = _PLAMO_TAG_RX.sub("", rest)
    rest = _SIZE_NOTE_RX.sub("", rest)
    return bracket, rest


def has_variant_marker(tail: str) -> bool:
    """꼬리에 변형 표시어(config.JOY_VARIANT_MARKERS)가 낱말로 들어 있는가. config.JOY_TAIL_EXEMPT에 있는 작품명은 제외."""
    t = nfkc(tail)
    if any(ex in t for ex in config.JOY_TAIL_EXEMPT):
        return False
    for m in config.JOY_VARIANT_MARKERS:
        if m.isascii():
            pat = r"(?<![A-Za-z])" + re.escape(m) + r"(?![A-Za-z])"
        else:
            pat = re.escape(m) + r"(?![가-힣])"
        if re.search(pat, t, re.I):
            return True
    return False


def strip_series_tail(rest: str) -> str:
    """이름 끝의 ` - <작품명>` 꼬리를 뗀다 (마지막 ` - ` 뒤 하나). 단 꼬리에 변형 표시어가 있으면(`- 플 전용기`) 변형 이름이라 떼지 않는다."""
    parts = _TAIL_SPLIT_RX.split(rest)
    if len(parts) < 2 or has_variant_marker(parts[-1]):
        return rest
    return " - ".join(parts[:-1])


def parse_name(raw: str) -> JoyName:
    bracket, rest = _clean_rest(raw)
    rest = strip_series_tail(rest)                   # "…(Dom Tropen) - 기동전사 건담 0083" → "…(Dom Tropen)"; 영문 괄호는 아래에서 뗀다
    rest = _EN_PAREN_RX.sub("", rest)
    sm = _SCALE_RX.search(rest)
    scale = sm.group(0) if sm else None
    if sm:
        rest = rest[:sm.start()] + " " + rest[sm.end():]
    ko = re.sub(r"\s+", " ", rest).strip(" -")
    for old, new in config.NAME_KO_REPLACEMENTS.items():       # 카탈로그 nameKo와 같은 표기로 (앰플리파이드 → Amplified)
        ko = ko.replace(old, new)
    return JoyName(raw=raw, bracket=bracket, grade=bracket_grade(bracket), scale=scale, ko=ko,
                   models=model_tokens(ko), text=strip_grade_words(strip_models(ko)))


def leading_grade_words(name_ko: str | None) -> str:
    """nameKo 맨 앞의 등급 낱말들 (`HGUC`, `HGBD`, `Figure-rise Standard Amplified`, `ENTRY GRADE` …). 하위 라인 표기를 보존하는 데 쓴다."""
    out = []
    for t in nfkc(name_ko).split():
        if not _GRADE_WORD_RX.match(t):
            break
        out.append(t)
    return " ".join(out)


def display_name(jn: JoyName, grade: str | None = None, scale: str | None = None) -> str:
    """`HG 1/144 큐베레이 마크2 - 플 전용기 …` 꼴. 카탈로그 nameKo와 같은 순서(등급 스케일 이름).
    이름이 이미 그 등급 낱말로 시작하면(`SD건담 …`, `BB전사 …`) 앞에 또 붙이지 않는다."""
    prefix = grade or jn.grade or ""
    if prefix and jn.ko.lower().startswith(prefix.lower()):
        prefix = ""
    return " ".join(p for p in (prefix, jn.scale or scale, jn.ko) if p)


# ---------------------------------------------------------------- 카탈로그 색인
def strip_grade_words(name: str) -> str:
    """이름 맨 앞의 등급 낱말(HG, SD건담, Figure-rise Standard …)을 뗀다. 카탈로그 nameKo와 조이하비 이름에 똑같이 적용한다."""
    toks = name.split()
    while toks and _GRADE_WORD_RX.match(toks[0]):
        toks.pop(0)
    return " ".join(toks)


def catalog_core(item: dict) -> str:
    """카탈로그 nameKo에서 앞의 등급·스케일을 뗀 이름. (영문 괄호는 이름의 일부일 수 있어 — `자쿠(GQ)`, `(NEW SPEC Ver.)` — 남긴다)"""
    return strip_grade_words(_SCALE_RX.sub(" ", nfkc(item.get("nameKo"))))


@dataclass(frozen=True)
class Cand:
    id: str
    grade: str | None
    scale: str | None
    core: str
    text: str                  # core에서 모델번호를 뺀 것
    sq: str
    sp: str
    models: frozenset
    runs: tuple
    toks: tuple


NAME_FIELDS = ("nameKo", "nameKoAi", "nameKoJoy")      # 같은 상품의 한국어 이름들 (현재 이름·AI 번역·조이하비 이름). 몰 이름으로 바뀌어도 앞의 이름들로 비교한다


def name_variants(item: dict) -> list[str]:
    """비교에 쓰는 한국어 이름들 (중복 제거, 현재 nameKo가 첫째)."""
    out: list[str] = []
    for f in NAME_FIELDS:
        v = item.get(f)
        if v and v not in out:
            out.append(v)
    return out


class CatalogIndex:
    """등급별 후보 목록. 한국어 이름이 있는 gunpla·girl 항목만 들어간다. 한 항목은 이름마다(nameKo·nameKoAi·nameKoJoy) 후보를 하나씩 갖고,
    모델번호 토큰은 모든 이름과 nameJa에서 모아 쓴다 — 몰 이름으로 바뀌며 모델번호가 빠져도 보호 규칙(MSN-04 ≠ MSN-04FF)이 계속 작동한다."""

    def __init__(self, items) -> None:
        self.by_grade: dict[str | None, list[Cand]] = {}
        for it in items:
            names = name_variants(it)
            if it.get("line") not in LINES or not names:
                continue
            models = model_tokens(*names, it.get("nameJa"))
            seen_text: set[str] = set()
            for nm in names:
                core = catalog_core({**it, "nameKo": nm})
                text = strip_models(core)
                if not text or squash(text) in seen_text:
                    continue
                seen_text.add(squash(text))
                sp = spaced(text)
                c = Cand(it["id"], it.get("grade"), it.get("scale"), core, text, squash(text), sp,
                         models, significant_runs(text), tuple(sp.split()))
                self.by_grade.setdefault(c.grade, []).append(c)

    def pool(self, grade: str | None, scale: str | None) -> list[Cand]:
        grades = config.JOY_GRADE_FAMILIES.get(grade or "", {grade})
        out = [c for g in grades for c in self.by_grade.get(g, [])]
        if scale:
            out = [c for c in out if not c.scale or c.scale == scale]       # 양쪽에 있고 다르면 제외
        return out


# ---------------------------------------------------------------- 보호 규칙
def guard(jtext: str, c: Cand) -> str | None:
    """이름이 비슷해도 다른 상품일 가능성이 큰 차이를 잡는다. → 사유(거절) | None(통과).
    띄어쓰기·구두점만 다른 이름은 통과한다."""
    if squash(jtext) == c.sq:
        return None
    if significant_runs(jtext) != c.runs:
        return "alnum"                                         # K9·F91·II/III·EW·Ver.Ka 같은 영문·숫자가 다르다
    jt = tuple(spaced(jtext).split())
    for toks, other in ((jt, c.toks), (c.toks, jt)):
        for t in toks:
            if t in other:
                continue
            best = max(other, key=lambda o: fuzz.ratio(t, o), default="")
            # 정확히 같은 낱말이 없으면 철자 변형(디스트로이/데스트로이)만 허용: 4글자 이상이고 MATCH_TOKEN_RATIO% 이상 같은 낱말이 맞은편에 있을 때
            if len(t) < 4 or len(best) < 4 or fuzz.ratio(t, best) < config.MATCH_TOKEN_RATIO:
                return "token"                                 # 델타↔제타, 바우↔리바우, 덧붙은 낱말(버스트·인버전)
    return None


# ---------------------------------------------------------------- 매칭
@dataclass
class Match:
    catalog_id: str | None
    score: float
    runner_up: float
    margin: float
    conflict: bool = False        # 모델번호가 서로 다름
    linked: bool = False
    name_ok: bool = False
    reason: str = ""
    top: list = field(default_factory=list)   # [(score, id)] 보호 규칙을 통과한 상위 3 (보고용)
    guarded: str | None = None    # 점수는 높았지만 보호 규칙으로 거절된 1등의 사유 (alnum|token)


def _score(jn: JoyName, jsq: str, jsp: str, c: Cand) -> tuple[float, bool]:
    s = max(fuzz.ratio(jsq, c.sq), fuzz.token_sort_ratio(jsp, c.sp))
    conflict = False
    if jn.models and c.models:
        if jn.models <= c.models or c.models <= jn.models:
            s += config.MATCH_MODEL_BONUS
        else:
            s -= config.MATCH_MODEL_CONFLICT
            conflict = True
    return max(0.0, min(100.0, s)), conflict


def best_match(jn: JoyName, index: CatalogIndex) -> Match:
    if not jn.grade:
        return Match(None, 0, 0, 0, reason="no-grade")
    if not jn.text:
        return Match(None, 0, 0, 0, reason="no-name")
    pool = index.pool(jn.grade, jn.scale)
    if not pool:
        return Match(None, 0, 0, 0, reason="no-candidates")
    jsq, jsp = squash(jn.text), spaced(jn.text)
    # 전체를 파이썬으로 채점하지 않고, 두 척도의 상위 후보만 모아 다시 채점한다
    picks = {i for _, _, i in process.extract(jsq, [c.sq for c in pool], scorer=fuzz.ratio, limit=12)}
    picks |= {i for _, _, i in process.extract(jsp, [c.sp for c in pool], scorer=fuzz.token_sort_ratio, limit=12)}
    scored = sorted(((*_score(jn, jsq, jsp, pool[i]), pool[i]) for i in picks), key=lambda t: (-t[0], t[2].id))
    passing, first_guard, pass_ids = [], None, set()
    for s, conflict, c in scored:
        why = guard(jn.text, c)
        if why is None:
            if c.id not in pass_ids:                       # 같은 상품의 다른 이름 후보는 가장 높은 점수 하나만 (2등과의 차이를 자기 자신과 재지 않는다)
                pass_ids.add(c.id)
                passing.append((s, conflict, c))
        elif first_guard is None and s >= config.MATCH_LINK_SCORE:
            first_guard = why
    if not passing:
        s1, conflict, c = scored[0]
        return Match(c.id, s1, 0.0, s1, conflict=conflict, reason="guard" if first_guard else "low-score", guarded=first_guard,
                     top=[(round(s, 1), x.id) for s, _, x in scored[:3]])
    s1, conflict, c1 = passing[0]
    s2 = passing[1][0] if len(passing) > 1 else 0.0
    m = Match(c1.id, s1, s2, s1 - s2, conflict=conflict, top=[(round(s, 1), x.id) for s, _, x in passing[:3]], guarded=first_guard)
    if s1 < config.MATCH_LINK_SCORE:
        m.reason = "guard" if first_guard else "low-score"
    elif conflict:
        m.reason = "model-conflict"          # 모델번호가 서로 다르면 이름이 비슷해도 다른 상품으로 본다 (MSN-04 ≠ MSN-04FF)
    elif m.margin < config.MATCH_MARGIN:
        m.reason = "ambiguous"
    else:
        m.linked = True
        m.name_ok = s1 >= config.MATCH_NAME_SCORE
    return m
