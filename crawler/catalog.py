"""카탈로그 — 병합·분류·밀린 상품 선택·저장.

항목은 세 가지 상태 중 하나다.
- 확정/임시 항목: `line`이 gunpla|girl → catalog-gunpla.json / catalog-girl.json
  (`detailAt`이 null이면 일정·브랜드 카드와 제목 앞 토큰으로 만든 임시 항목. 상세를 받으면 채워진다)
- 보류: `line`이 None (제목으로 판정 못 함, 상세 대기) → catalog-pending.json 의 items
- 제외: 비대상으로 확인된 상품 → catalog-pending.json 의 excluded {id: 사유}  (같은 상품의 상세를 다시 받지 않는다)

병합 우선순위: 상세 > 브랜드 목록 > 일정 카드 > 제목 임시값. `firstSeen`·`kr`는 절대 바꾸지 않는다(kr은 3단계).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from . import config
from .sources.hobby_item import is_stable_image
from .store import read_json, write_json

log = logging.getLogger("plamo.catalog")

LINES = ("gunpla", "girl")
_RULES = [(re.compile(p), line, grade) for p, line, grade in config.TITLE_PREFIX_RULES]
_SCALE_RX = re.compile(r"(?<![\d/])1/\d{1,4}(?!\d)")


# ---------------------------------------------------------------- 분류
def nfkc(s: str | None) -> str:
    return unicodedata.normalize("NFKC", s or "")


def classify_title(title: str | None) -> tuple[str | None, str | None]:
    """상세 전 임시 판정: 제목 앞 토큰 → (line, grade). 전각 `ＨＧ` 같은 표기는 NFKC로 맞춘다."""
    t = nfkc(title).upper().strip()
    for rx, line, grade in _RULES:
        if rx.search(t):
            return line, grade
    return None, None


def classify_brand_keys(keys: list[str]) -> tuple[str | None, str | None, list[str]]:
    """브랜드 키들 → (line, grade, 사전에 없는 키). girl 키가 하나라도 있으면 girl, 아니면 gunpla 키가 있으면 gunpla,
    둘 다 없으면 line=None(제외). 사전에 없는 키는 제외로 취급하고 unknown으로 돌려준다."""
    entries, unknown = [], []
    for k in keys:
        e = config.BRAND_LINE.get(k.lower())
        if e is None:
            unknown.append(k)
        else:
            entries.append(e)
    if any(line == "girl" for line, _ in entries):
        line = "girl"
    elif any(line == "gunpla" for line, _ in entries):
        line = "gunpla"
    else:
        return None, None, unknown
    grade = next((g for ln, g in entries if ln == line and g), None)
    return line, grade, unknown


def extract_scale(title: str | None) -> str | None:
    m = _SCALE_RX.search(nfkc(title))
    return m.group(0) if m else None


# ---------------------------------------------------------------- 발매일
def release_key(rel: dict | None) -> str:
    """정렬용 문자열: 날짜가 있으면 날짜, 월만 있으면 'YYYY-MM-00'."""
    if not rel:
        return ""
    return rel.get("date") or (rel["month"] + "-00" if rel.get("month") else "")


def merge_release(old: dict | None, new: dict | None, *, authoritative: bool) -> dict | None:
    """같은 달이면 날짜가 있는 쪽을, 달이 다르면 authoritative(상세)일 때만 새 값을, 카드는 더 늦은 달로 미뤄진 경우만 따른다."""
    if not new:
        return old
    if not old:
        return new
    if old.get("month") == new.get("month"):
        return new if new.get("date") else old
    if authoritative or new["month"] > old["month"]:
        return new
    return old


# ---------------------------------------------------------------- 카탈로그
class Catalog:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.excluded: dict[str, str] = {}
        self.was_empty = True
        self._prev_files: dict[str, dict] = {}     # 파일 이름 → 불러온 내용 (바뀐 게 없으면 updatedAt을 유지)

    # ------------------------------------------------------------ 입출력
    @classmethod
    def load(cls, data_dir: Path) -> "Catalog":
        cat = cls()
        data_dir = Path(data_dir)
        names = [*config.CATALOG_FILES.values(), config.PENDING_FILE]
        for name in names:
            d = read_json(data_dir / name, None)
            if not isinstance(d, dict):
                continue
            cat._prev_files[name] = d
            for it in d.get("items", []):
                cat.items[it["id"]] = it
            if name == config.PENDING_FILE:
                cat.excluded.update(d.get("excluded", {}))
        cat.was_empty = not cat.items and not cat.excluded
        return cat

    def save(self, data_dir: Path, updated_at: str) -> dict[str, int]:
        data_dir = Path(data_dir)
        by_file: dict[str, list[dict]] = {name: [] for name in [*config.CATALOG_FILES.values(), config.PENDING_FILE]}
        for it in self.items.values():
            line = it.get("line")
            by_file[config.CATALOG_FILES[line] if line in LINES else config.PENDING_FILE].append(it)
        counts = {}
        for name, items in by_file.items():
            items.sort(key=lambda i: (release_key(i.get("release")), i["id"]), reverse=True)
            payload: dict = {"updatedAt": updated_at, "items": items}
            if name == config.PENDING_FILE:
                payload["excluded"] = dict(sorted(self.excluded.items()))
            prev = self._prev_files.get(name)
            if prev and prev.get("items") == items and prev.get("excluded") == payload.get("excluded"):
                payload["updatedAt"] = prev.get("updatedAt", updated_at)   # 바뀐 게 없으면 시각도 그대로
            write_json(data_dir / name, payload)
            counts[name] = len(items)
        return counts

    def counts(self) -> dict[str, int]:
        c = {"gunpla": 0, "girl": 0, "pending": 0}
        for it in self.items.values():
            c[it["line"] if it.get("line") in LINES else "pending"] += 1
        c["excluded"] = len(self.excluded)
        return c

    # ------------------------------------------------------------ 카드 → 항목
    def _build(self, card: dict, now: str, brand_key: str | None) -> dict | None:
        line = grade = None
        brand_keys: list[str] = []
        if brand_key:
            brand_keys = [brand_key]
            line, grade, _ = classify_brand_keys(brand_keys)
        if line is None:
            line, grade = classify_title(card["nameJa"])
        if line is None and card["id"].startswith("pb-"):
            self.excluded[card["id"]] = "title-no-match"    # 호비 상세가 없어 제목으로만 판정 가능
            return None
        return {
            "id": card["id"], "url": card["url"], "line": line, "brandKeys": brand_keys, "grade": grade,
            "scale": extract_scale(card["nameJa"]), "seriesKey": None, "series": None,
            "nameJa": card["nameJa"], "nameKo": None, "priceJpy": card.get("priceJpy"),
            "channel": card.get("channel"), "pbUrl": card.get("pbUrl"), "release": card.get("release"),
            "kr": [], "images": [], "firstSeen": now, "updated": now, "detailAt": None,
        }

    def upsert_card(self, card: dict, now: str, brand_key: str | None = None) -> tuple[dict | None, bool]:
        """일정·브랜드 카드를 반영한다. (항목 | None(제외·판정불가), 이번에 처음 만든 항목인가)."""
        cid = card["id"]
        if cid in self.excluded:
            return None, False
        item = self.items.get(cid)
        if item is None:
            item = self._build(card, now, brand_key)
            if item is None:
                return None, False
            self.items[cid] = item
            return item, True

        changed = False
        rel = merge_release(item.get("release"), card.get("release"), authoritative=False)
        if rel != item.get("release"):
            item["release"], changed = rel, True
        if item.get("priceJpy") is None and card.get("priceJpy") is not None:
            item["priceJpy"], changed = card["priceJpy"], True
        if item["detailAt"] is None:                      # 임시 항목만 카드로 보강한다 (상세 확정값은 건드리지 않음)
            if brand_key and brand_key not in item["brandKeys"]:
                item["brandKeys"].append(brand_key)
                line, grade, _ = classify_brand_keys(item["brandKeys"])
                if line:
                    item["line"], item["grade"] = line, grade or item.get("grade")
                changed = True
            if not item.get("channel") and card.get("channel"):
                item["channel"], changed = card["channel"], True
            if not item.get("pbUrl") and card.get("pbUrl"):
                item["pbUrl"], changed = card["pbUrl"], True
        if changed:
            item["updated"] = now
        return item, False

    # ------------------------------------------------------------ 상세 반영
    def _exclude(self, cid: str, reason: str) -> None:
        self.items.pop(cid, None)
        self.excluded[cid] = reason

    def apply_detail(self, cid: str, detail: dict, now: str) -> tuple[str, list[str]]:
        """상세로 확정한다. → ("ok" | "excluded", 사전에 없는 브랜드 키)."""
        item = self.items[cid]
        name = detail.get("nameJa") or item["nameJa"]
        brand_keys = detail.get("brandKeys") or []
        unknown: list[str] = []
        if brand_keys:
            line, grade, unknown = classify_brand_keys(brand_keys)
            if line is None:
                self._exclude(cid, "brand:" + ",".join(brand_keys))
                return "excluded", unknown
        else:                                              # 구형 상품처럼 브랜드 링크가 없는 경우는 제목으로만 판정
            line, grade = classify_title(name)
            if line is None:
                self._exclude(cid, "no-brand-key")
                return "excluded", []
        if not grade:                                      # pb_gunpla 등 등급 없는 키는 상품명 앞 토큰으로
            t_line, t_grade = classify_title(name)
            grade = t_grade if t_line == line else None
        item.update({
            "line": line, "brandKeys": brand_keys or item["brandKeys"], "grade": grade,
            "scale": extract_scale(name), "seriesKey": detail.get("seriesKey"), "series": detail.get("series"),
            "nameJa": name, "priceJpy": detail.get("priceJpy") if detail.get("priceJpy") is not None else item.get("priceJpy"),
            "pbUrl": detail.get("pbUrl") or item.get("pbUrl"),
            "release": merge_release(item.get("release"), detail.get("release"), authoritative=True),
            "images": [u for u in detail.get("images", []) if is_stable_image(u)],   # 서명 URL은 여기서도 한 번 더 거른다
            "updated": now, "detailAt": now,
        })
        item.pop("detailFails", None)
        return "ok", unknown

    def record_detail_failure(self, cid: str, status: int | None) -> None:
        if status == 404:
            self._exclude(cid, "detail-404")
            return
        item = self.items.get(cid)
        if item is not None:
            item["detailFails"] = item.get("detailFails", 0) + 1

    # ------------------------------------------------------------ 밀린 상품 선택
    def backlog_candidates(self) -> list[dict]:
        """상세가 필요한 항목(호비 상세가 있는 bh- 만). 임시 판정된 것 먼저, 발매일 최신순."""
        cands = [i for i in self.items.values()
                 if i["id"].startswith("bh-") and i["detailAt"] is None
                 and i.get("detailFails", 0) < config.DETAIL_MAX_FAILURES]
        cands.sort(key=lambda i: (release_key(i.get("release")), i["id"]), reverse=True)
        cands.sort(key=lambda i: i.get("line") is None)     # 안정 정렬: 임시 판정된 항목이 앞
        return cands

    def select_details(self, max_new: int, max_backlog: int, new_ids: set[str] | list[str]) -> tuple[list[str], list[str]]:
        """(새 상품 id들, 밀린 상품 id들). 합계는 DETAIL_HARD_MAX를 넘지 않는다."""
        new_ids = set(new_ids)
        max_new = max(0, min(max_new, config.DETAIL_HARD_MAX))
        max_backlog = max(0, min(max_backlog, config.DETAIL_HARD_MAX - max_new))
        cands = self.backlog_candidates()
        new = [i["id"] for i in cands if i["id"] in new_ids][:max_new]
        picked = set(new)
        # 새 상품이 상한을 넘으면 남은 새 상품도 밀린 슬롯에서 같은 기준(임시 판정 → 발매일 최신순)으로 경쟁한다.
        # (첫 실행은 전부 "새 상품"이라, 이렇게 해야 새 40 + 밀린 150이 모두 쓰인다)
        rest = [i["id"] for i in cands if i["id"] not in picked][:max_backlog]
        return new, rest

    def backlog_count(self) -> int:
        return len(self.backlog_candidates())

    # ------------------------------------------------------------ 번역 대상
    def untranslated(self, limit: int) -> list[dict]:
        out = [i for i in self.items.values() if i.get("line") in LINES and not i.get("nameKo")]
        out.sort(key=lambda i: (release_key(i.get("release")), i["id"]), reverse=True)
        return out[:limit]
