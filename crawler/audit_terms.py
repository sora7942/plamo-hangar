"""번역 용어 일관성 점검 (6-8) — 같은 가타카나 단어(기체명·작품 고유명)가 한국어로 여러 가지로 번역된 경우를 찾는다.

    python -m crawler.audit_terms [--top 50] [--min-items 3] [--out crawler/out/term-audit.md]

읽기만 한다 (docs/data의 카탈로그·series-ko·kr-arrivals·collection을 읽고 아무것도 쓰지 않는다. --out은 로컬 보고서 파일).

방법 (일본어 ↔ 한국어 단어 정렬을 사전 없이 통계로):
 1. 문서 = 카탈로그 항목의 (nameJa, nameKo) + series-ko.json의 (ja, ko) + 조이하비 입고 행(kr-arrivals rows·codeMap으로 카탈로그 nameJa에 이어 붙인 **국내 매장 표기**).
 2. 일본어 쪽: 가타카나 연속열(중점·공백에서 끊김)의 길이 3~12 부분 문자열 s. 같은 문서 집합을 가진 부분 문자열은 가장 긴 것만 남긴다(닫힌 단어 —
    `ンダム`이 아니라 `ガンダム`). 한국어 쪽: 한글 낱말 t(2글자 이상).
 3. s가 든 문서들에서 거의 s와 함께만 나오는 한글 낱말(정밀도 ≥ 0.85 — "건담" 같은 흔한 말은 걸러진다) 중 **발음이 s와 맞는 것**만 번역 후보로 본다.
    발음 비교는 가타카나→로마자, 한글→자모로 바꿔 자음 골격(K·T·P·S·R·N·M·H)으로 줄여 s 골격의 어느 부분과 비슷한지 본다(쿠안타·콴타·퀀터 ↔ クアンタ는 모두 KNT).
 4. 가장 많이 쓰인 후보와 발음이 비슷하고, 한 문서에 같이 나오지 않으며(서로 대체되는 표기), 한쪽이 다른 쪽을 포함하지 않는(건담/건담용 같은 접미 차이 제외) 후보가 둘 이상이면 "표기가 갈린" 단어.
 5. 근거: 조이하비(국내 매장) 표기에서 어느 쪽이 쓰였는지. 근거가 없으면 제안 없이 "표시만".
번역 단어가 일본어 단어에 정확히 대응하는지는 통계 추정이라 **사람이 확인하는 용도**다 (자동으로 용어집에 넣지 않는다).
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .store import read_json

_KATA = re.compile("[ァ-ヺー]+")
_HANGUL = re.compile("[가-힣]{2,}")
MIN_SUB, MAX_SUB, MAX_RUN = 3, 12, 40
PRECISION = 0.85
SIMILAR = 0.6
COMMON = 300             # 한 낱말이 이보다 많은 문서에 나오면 점검에서 뺀다
EXCLUSIVE = 0.2          # 같은 문서에 같이 나오는 비율이 이보다 크면 대체 표기가 아니라 다른 낱말로 본다


def jamo(s: str) -> str:
    return unicodedata.normalize("NFD", s)


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, jamo(a), jamo(b)).ratio()


# ---- 발음 골격: 가타카나·한글을 같은 자음 부류 문자열로 줄인다 (모음·반모음은 버린다)
_KANA = dict(zip("アイウエオカキクケコガギグゲゴサシスセソザジズゼゾタチツテトダヂヅデドナニヌネノハヒフヘホバビブベボパピプペポマミムメモヤユヨラリルレロワヲンヴ",
                 "a i u e o ka ki ku ke ko ga gi gu ge go sa shi su se so za ji zu ze zo ta chi tsu te to da ji zu de do na ni nu ne no ha hi fu he ho ba bi bu be bo pa pi pu pe po ma mi mu me mo ya yu yo ra ri ru re ro wa o n vu".split()))
_CLS = {**dict.fromkeys("kgqc", "K"), **dict.fromkeys("td", "T"), **dict.fromkeys("pbvf", "P"), **dict.fromkeys("szjx", "S"), **dict.fromkeys("rl", "R"),
        "n": "N", "m": "M", "h": "H"}
_INIT = dict(zip("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ", "K K N T T R M P P S S - S S S K T P H".split()))
_FINAL = ["", "K", "K", "K", "N", "N", "N", "T", "R", "K", "M", "P", "S", "T", "P", "H", "M", "P", "P", "T", "T", "N", "S", "S", "K", "T", "P", "H"]


def kata_skeleton(w: str) -> str:
    """가타카나 단어 → 자음 골격 (ッ·ー·모음은 버리고, ヴ→P, ン→N, ファ·ティ 같은 작은 모음 결합도 자음으로 환산)."""
    out = []
    for ch in unicodedata.normalize("NFKC", w):
        if ch in "ッー・" or ch in "ァィゥェォャュョ":
            continue
        r = _KANA.get(ch)
        if r:
            c = _CLS.get(r[0]) if r[0] not in "aiueo" else None
            if r.startswith(("sh", "ch", "ts")):
                c = "S"
            if c and (not out or out[-1] != c):
                out.append(c)
    return "".join(out)


def hangul_skeleton(w: str) -> str:
    out = []
    for ch in w:
        cp = ord(ch) - 0xAC00
        if not 0 <= cp < 11172:
            continue
        for c in (_INIT.get("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"[cp // 588], "-"), _FINAL[cp % 28]):
            if c and c != "-" and (not out or out[-1] != c):
                out.append(c)
    return "".join(out)


def sounds_like(token: str, word: str, threshold: float = 0.8) -> bool:
    """한글 낱말이 가타카나 단어 **전체**와 발음이 맞는가 — 두 자음 골격의 길이가 같고(하나쯤 어긋나는 것까지) 비슷도 ≥ threshold.
    (단어 일부만 맞는 경우는 합성어의 다른 낱말일 수 있어 버린다: フェクト ↔ 퍼펙트(PPKT))"""
    a, b = hangul_skeleton(token), kata_skeleton(word)
    if len(a) < 2 or len(a) != len(b):
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def same_sound(a: str, b: str) -> bool:
    """두 한글 표기가 같은 소리인가 (자음 골격이 같거나 한 글자만 다름)."""
    x, y = hangul_skeleton(a), hangul_skeleton(b)
    return len(x) >= 2 and len(x) == len(y) and difflib.SequenceMatcher(None, x, y).ratio() >= 0.8


def kata_substrings(ja: str) -> set[str]:
    out: set[str] = set()
    for run in _KATA.findall(unicodedata.normalize("NFKC", ja or "")):
        run = run[:MAX_RUN]
        for i in range(len(run)):
            for j in range(i + MIN_SUB, min(len(run), i + MAX_SUB) + 1):
                out.add(run[i:j])
    return out


def hangul_tokens(ko: str) -> set[str]:
    return set(_HANGUL.findall(ko or ""))


class Doc:
    __slots__ = ("ja", "ko", "kind", "key")

    def __init__(self, ja: str, ko: str, kind: str, key: str):
        self.ja, self.ko, self.kind, self.key = ja, ko, kind, key


def load_docs(data_dir: Path) -> list[Doc]:
    docs: list[Doc] = []
    for name in (*config.CATALOG_FILES.values(),):
        for it in (read_json(data_dir / name, {}) or {}).get("items", []):
            if it.get("nameJa") and it.get("nameKo"):
                docs.append(Doc(it["nameJa"], it["nameKo"], "shop" if it.get("nameKoSource") == "joyhobby" else "ai", it["id"]))
    for key, e in (read_json(data_dir / config.SERIES_FILE, {}) or {}).get("items", {}).items():
        docs.append(Doc(e["ja"], e["ko"], "series", "series:" + key))
    # 조이하비 입고 행: 연결된 카탈로그 항목의 일본어 이름에 국내 매장 한글명을 이어 붙인다 (국내에서 실제로 쓰는 표기)
    arr = read_json(data_dir / config.KR_ARRIVALS_FILE, {}) or {}
    ja_of = {}
    for name in config.CATALOG_FILES.values():
        for it in (read_json(data_dir / name, {}) or {}).get("items", []):
            ja_of[it["id"]] = it.get("nameJa")
    seen = set()
    for r in arr.get("rows", []):
        link = (arr.get("codeMap") or {}).get(r.get("code"))
        cid = link.get("catalogId") if link else None
        if cid and ja_of.get(cid) and (cid, r["name"]) not in seen:
            seen.add((cid, r["name"]))
            docs.append(Doc(ja_of[cid], re.sub(r"\([^)]*\)", " ", r["name"]), "shop", cid))
    return docs


def find_variants(docs: list[Doc], min_items: int = 3) -> list[dict]:
    """표기가 갈린 일본어 단어 목록 (문서 수 많은 순). 각 항목: {ja, items, variants:{한글:문서수}, shop:{한글:문서수}}."""
    J: dict[str, set[int]] = defaultdict(set)
    K: dict[str, set[int]] = defaultdict(set)
    toks: list[set[str]] = []
    for i, d in enumerate(docs):
        t = hangul_tokens(d.ko)
        toks.append(t)
        for tok in t:
            K[tok].add(i)
        for s in kata_substrings(d.ja):
            J[s].add(i)
    # 닫힌 단어만: 같은 문서 집합을 가진 부분 문자열은 가장 긴 것 하나만 (ンダム → ガンダム)
    closed: dict[frozenset, str] = {}
    for s, ds in J.items():
        if len(ds) >= min_items:
            key = frozenset(ds)
            if key not in closed or (len(s), s) > (len(closed[key]), closed[key]):
                closed[key] = s
    found: dict[frozenset, dict] = {}
    for dset, s in closed.items():
        ds = set(dset)
        n: Counter = Counter()
        for i in ds:
            n.update(toks[i])
        cands = {t: c for t, c in n.items() if c / len(K[t]) >= PRECISION and sounds_like(t, s)}
        if len(cands) < 2:
            continue
        t0 = max(cands, key=lambda t: (cands[t], len(t)))
        if len(K[t0]) > COMMON:                       # 건담·옵션처럼 어디에나 나오는 말은 표기가 갈린 게 아니라 다른 낱말이 섞인 것
            continue
        var = {t0}
        for t, c in cands.items():
            if t == t0 or t in t0 or t0 in t or similar(t, t0) < SIMILAR or not same_sound(t, t0):
                continue
            both = len(K[t] & K[t0])
            if both / max(1, min(len(K[t]), len(K[t0]))) <= EXCLUSIVE:
                var.add(t)
        if len(var) < 2:
            continue
        key = frozenset(var)
        row = {"ja": s, "items": len({docs[i].key for i in ds}), "variants": {t: len({docs[i].key for i in ds if t in toks[i]}) for t in var}}
        row["shop"] = {t: len({docs[i].key for i in ds if docs[i].kind == "shop" and t in toks[i]}) for t in var}
        old = found.get(key)
        if old is None or (row["items"], len(s)) > (old["items"], len(old["ja"])):
            found[key] = row
    rows = list(found.values())
    # 변형 집합이 다른 집합의 부분집합이면 큰 쪽만
    big = [r for r in rows if not any(set(r["variants"]) < set(o["variants"]) for o in rows)]
    big.sort(key=lambda r: (-r["items"], r["ja"]))
    return big


def propose(row: dict) -> tuple[str | None, str]:
    """(제안 표기 | None, 근거 설명). 조이하비(국내 매장) 표기에서 가장 많이 쓰인 쪽."""
    shop = {t: c for t, c in row["shop"].items() if c}
    if not shop:
        return None, "근거 없음 — 표시만"
    best = max(shop, key=lambda t: (shop[t], row["variants"][t]))
    tied = [t for t, c in shop.items() if c == shop[best]]
    if len(tied) > 1:
        return None, "조이하비 표기가 갈림 — 표시만"
    return best, "조이하비 " + ", ".join(f"{t} {c}" for t, c in sorted(shop.items(), key=lambda x: -x[1]))


def collection_spellings(data_dir: Path, row: dict) -> list[str]:
    """내 컬렉션 이름에 쓰인 낱말 중 이 단어와 **같은 소리**(자음 골격이 같음)인데 갈린 표기 목록에는 없는 것 (예: 퀀터).
    → 검색 별칭(aliases.js)에 정식 표기와 묶어 둘 후보."""
    kits = (read_json(data_dir / config.COLLECTION_FILE, {}) or {}).get("kits", [])
    toks: Counter = Counter()
    for k in kits:
        toks.update(hangul_tokens(k.get("name", "")))
    return [f"{t}({c})" for t, c in toks.items() if t not in row["variants"] and sounds_like(t, row["ja"])]


def collection_alias_candidates(docs: list[Doc], data_dir: Path, min_docs: int = 2) -> list[dict]:
    """카탈로그 번역은 한 가지로 일관되지만 **내 컬렉션 이름만 다르게 쓴** 낱말(발바토스↔바르바토스 같은 것) — 검색 별칭(aliases.js) 후보.
    컬렉션 낱말 t가 카탈로그 한글 낱말 어디에도 없고, 카탈로그에서 min_docs개 이상 문서에 나오는 낱말 u와 같은 소리(자음 골격 같음·자모 유사도 ≥ 0.6)이면 (t, u)."""
    cat_count: Counter = Counter()
    for d in docs:
        if d.kind != "series":
            cat_count.update(hangul_tokens(d.ko))
    kits = (read_json(data_dir / config.COLLECTION_FILE, {}) or {}).get("kits", [])
    mine: Counter = Counter()
    for k in kits:
        mine.update(hangul_tokens(k.get("name", "")))
    out = []
    for t, c in mine.items():
        if cat_count.get(t):
            continue
        pairs = [(u, n) for u, n in cat_count.items() if n >= min_docs and u != t and abs(len(u) - len(t)) <= 1 and similar(t, u) >= 0.6 and same_sound(t, u)]
        if pairs:
            u, n = max(pairs, key=lambda x: x[1])
            out.append({"mine": t, "mine_n": c, "catalog": u, "catalog_n": n})
    out.sort(key=lambda r: (-r["mine_n"], -r["catalog_n"], r["mine"]))
    return out


def retranslate_count(row: dict, canonical: str | None) -> int:
    """제안 표기를 쓰기로 하면 다시 번역될 문서 수 (제안 표기가 아닌 표기가 든 카탈로그·시리즈 문서)."""
    keep = canonical or max(row["variants"], key=row["variants"].get)
    return sum(c for t, c in row["variants"].items() if t != keep)


def render(rows: list[dict], data_dir: Path, top: int) -> str:
    out = ["| # | 일본어 | 문서 | 갈린 표기 (문서 수) | 다수결 | 조이하비(국내 매장) 근거 | 정식 표기 제안 | 제안대로 하면 재번역 | 내 컬렉션의 같은 소리 표기 |", "|---|---|---|---|---|---|---|---|---|"]
    for n, r in enumerate(rows[:top], 1):
        best, why = propose(r)
        v = " / ".join(f"{t} {c}" for t, c in sorted(r["variants"].items(), key=lambda x: -x[1]))
        major = max(r["variants"], key=r["variants"].get)
        mine = ", ".join(collection_spellings(data_dir, r)) or "-"
        out.append(f"| {n} | {r['ja']} | {r['items']} | {v} | {major} | {why} | {best or '—'} | {retranslate_count(r, best)}건 | {mine} |")
    return chr(10).join(out)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="같은 가타카나 단어가 여러 한국어로 번역된 경우를 찾는다 (읽기만 한다)")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--min-items", type=int, default=3)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    docs = load_docs(a.data_dir)
    rows = find_variants(docs, a.min_items)
    alias = collection_alias_candidates(docs, a.data_dir)
    nl = "\n"
    text = (f"문서 {len(docs)}개 (카탈로그·시리즈·조이하비 입고) → 표기가 갈린 단어 {len(rows)}개, 상위 {min(a.top, len(rows))}개{nl}{nl}" + render(rows, a.data_dir, a.top) +
            f"{nl}{nl}내 컬렉션에서만 다르게 쓴 낱말 {len(alias)}개 (카탈로그 표기와 소리가 같음 → 검색 별칭 후보){nl}{nl}| 내 컬렉션 표기 (프라 수) | 카탈로그 표기 (문서 수) |{nl}|---|---|{nl}" +
            nl.join(f"| {r['mine']} ({r['mine_n']}) | {r['catalog']} ({r['catalog_n']}) |" for r in alias))
    print(text)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
