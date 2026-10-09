"""반다이남코코리아몰 상품 ↔ 카탈로그 연결, 가격·한국 공식 이름 반영 (7a) — mall.json, 카탈로그 priceKrw·mallGno·nameKo·seriesKo.

mall.json
  goods: {gno: {name, series, price, soldOut, cate, first(YYYY-MM-DD), seen(YYYY-MM-DD)}}   몰 목록에서 읽은 상품. 연결 안 된 상품은 이번 스캔에 나온 것만 남긴다
  links: {gno: {catalogId, method(fuzzy|override), score, margin, nameOk, nameApplied, at}}  한 번 확실히 연결된 gno ↔ catalogId (다음 실행부터는 이름을 다시 비교하지 않는다)
  scan:  {at(PC가 몰을 읽은 시각), complete, requests, count}                                    마지막 스냅샷 요약 (스캔은 PC가 mall-scan.json으로 올린다 — crawler/mall_scan.py)

매 실행(link_all)
  1. MALL_OVERRIDES 적용 (강제 연결 / 연결 금지: 굳은 연결을 풀고 이름·시리즈·가격 필드를 되돌린다)
  2. 연결 안 된 상품을 지금의 카탈로그로 (다시) 매칭 — 등급 낱말로 후보를 좁히고 match.best_match(보호 규칙·점수 차이)로 판정. 애매하면 연결하지 않는다
     추가 보호: 가격 비율(원 ÷ 엔)이 MALL_PRICE_RATIO 밖이면 연결하지 않는다(세트·분류 불일치), 한 카탈로그 항목에 몰 상품이 둘 이상 붙으면 점수 높은 쪽만
  3. 연결된 상품(이번 스캔에 있음)의 가격·품절·mallGno를 카탈로그에 쓴다. 확실한 연결(nameOk)이면 nameKo·seriesKo를 몰 표기로 바꾼다
     (nameKoSource="bnkrmall", 이전 이름은 nameKoAi / 조이하비 이름은 nameKoJoy에 보존. 우선순위: 몰 > 조이하비 > AI)
  4. 스캔이 정상으로 끝났을 때만, 몰에서 사라진 연결 상품에 mallEnded=True (가격·확인 시각은 마지막 값 그대로)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from . import config, match
from .store import read_json, write_json

log = logging.getLogger("plamo.mall")

NAME_SOURCE = "bnkrmall"
_ENTRY_RX = re.compile(r"^ENTRY\s+GRADE\b", re.I)
_FR_STD_RX = re.compile(r"^(?:Figure-rise\s+Standard|피규어라이즈\s*스탠다드)(?![가-힣A-Za-z])", re.I)
_HGBDR_RX = re.compile(r"^HGBD:R(?![A-Za-z])", re.I)


# ---------------------------------------------------------------- 상태 파일
class MallState:
    def __init__(self) -> None:
        self.goods: dict[str, dict] = {}
        self.links: dict[str, dict] = {}
        self.scan: dict = {}
        self.updated_at: str | None = None
        self._prev: dict | None = None

    @classmethod
    def load(cls, data_dir: Path) -> "MallState":
        s = cls()
        d = read_json(Path(data_dir) / config.MALL_FILE, None)
        if isinstance(d, dict):
            s._prev = d
            s.updated_at = d.get("updatedAt")
            s.goods = {k: dict(v) for k, v in (d.get("goods") or {}).items()}
            s.links = {k: dict(v) for k, v in (d.get("links") or {}).items()}
            s.scan = dict(d.get("scan") or {})
        return s

    def save(self, data_dir: Path, now_iso: str) -> None:
        doc = {"updatedAt": now_iso, "scan": self.scan,
               "links": dict(sorted(self.links.items(), key=lambda kv: int(kv[0]))),
               "goods": dict(sorted(self.goods.items(), key=lambda kv: int(kv[0])))}
        if self._prev and all(self._prev.get(k) == doc[k] for k in ("goods", "links")) and (self._prev.get("scan") or {}).get("complete") == self.scan.get("complete"):
            doc["updatedAt"] = self._prev.get("updatedAt", now_iso)       # 바뀐 게 없으면 시각도 그대로
            doc["scan"] = self._prev.get("scan", self.scan)
        write_json(Path(data_dir) / config.MALL_FILE, doc)

    def absorb(self, scan: dict, now_iso: str) -> tuple[set[str], bool]:
        """이번 스캔의 상품을 반영한다 → (이번에 본 gno 집합, 스캔을 믿어도 되는가).
        믿을 수 있는 스캔 = 모든 쪽을 정상으로 읽었고 상품 수가 이전 스캔의 MALL_ENDED_MIN_RATIO 이상. 이때만 "사라짐"을 판정하고,
        연결 안 된 채 사라진 상품을 버린다(연결된 상품은 남긴다)."""
        today = now_iso[:10]
        seen = set(scan["goods"])
        prev_n = int(self.scan.get("count") or 0)
        healthy = bool(scan["complete"]) and bool(seen) and len(seen) >= config.MALL_ENDED_MIN_RATIO * prev_n
        for gno, g in scan["goods"].items():
            prev = self.goods.get(gno) or {}
            self.goods[gno] = {"name": g["name"], "series": g["series"], "price": g["price"], "soldOut": g["soldOut"],
                               "cate": g["cate"], "first": prev.get("first") or today, "seen": today}
        if healthy:
            for gno in [k for k in self.goods if k not in seen and k not in self.links]:
                del self.goods[gno]
        if healthy or not self.scan:       # 믿을 수 없는 스캔은 이전 "마지막 정상 스캔"의 상품 수(count)를 덮어쓰지 않는다
            self.scan = {"at": now_iso, "complete": healthy, "requests": scan["requests"], "count": len(seen)}
        else:
            self.scan = {**self.scan, "lastTry": now_iso, "lastTryComplete": False}
        return seen, healthy


# ---------------------------------------------------------------- 몰 상품명
@dataclass(frozen=True)
class MallName:
    raw: str
    grade_words: str           # 이름 맨 앞의 등급 낱말들 (`HG`, `ENTRY GRADE` …) — 없으면 ""
    grade: str | None          # 카탈로그 등급 (모르면 None → 매칭하지 않음)
    scale: str | None
    core: str                  # 등급 낱말·스케일을 뗀 이름 (몰 표기 그대로 — 괄호 부가 설명도 남긴다)
    joy: match.JoyName         # best_match에 넘기는 이름 (grade·scale·text 포함)


def _grade_of(words: str, first_token: str) -> str | None:
    if _ENTRY_RX.match(words):
        return "EG"
    if _FR_STD_RX.match(words):
        return "Figure-rise Standard"
    return match.bracket_grade(first_token) if words else None


def _leading_words(text: str) -> tuple[str, int]:
    """→ (이름 맨 앞의 등급 낱말들, 그 부분의 원문 길이). 몰 표기의 예외: `HGBD:R`(콜론), 한글 `피규어라이즈 스탠다드`(영문 `Figure-rise Standard`로 정리)."""
    m = _FR_STD_RX.match(text)
    if m:
        return "Figure-rise Standard", m.end()
    m = _HGBDR_RX.match(text)
    if m:
        return "HGBD:R", m.end()
    words = match.leading_grade_words(text)
    return words, len(words)


def parse_mall_name(raw: str) -> MallName:
    text = re.sub(r"\s+", " ", match.nfkc(raw)).strip()
    sm = match._SCALE_RX.search(text)
    scale = sm.group(0) if sm else None
    if sm:
        text = re.sub(r"\s+", " ", text[:sm.start()] + " " + text[sm.end():]).strip()
    words, n = _leading_words(text)
    core = text[n:].strip() if words else text
    grade = _grade_of(words, words.split()[0] if words else "")
    ko = core
    for old, new in config.NAME_KO_REPLACEMENTS.items():
        ko = ko.replace(old, new)
    joy = match.JoyName(raw=raw, bracket=None, grade=grade, scale=scale, ko=ko, models=match.model_tokens(ko),
                        text=match.strip_grade_words(match.strip_models(ko)))
    return MallName(raw=raw, grade_words=words, grade=grade, scale=scale, core=core, joy=joy)


def mall_name_ko(mn: MallName, item: dict) -> str:
    """카탈로그 nameKo 형식(`등급 스케일 이름`)으로 정리한 몰 이름. 등급·스케일은 몰 이름에 있으면 그것, 없으면 카탈로그 값."""
    grade = mn.grade_words or match.leading_grade_words(item.get("nameKo")) or item.get("grade") or ""
    scale = mn.scale or item.get("scale") or ""
    core = mn.core
    for old, new in config.NAME_KO_REPLACEMENTS.items():
        core = core.replace(old, new)
    if grade and core.lower().startswith(grade.lower()):
        grade = ""
    return " ".join(p for p in (grade, scale, core) if p)


# ---------------------------------------------------------------- 이름·시리즈·가격 반영/되돌리기
def _apply_name(item: dict, new: str, now_iso: str) -> bool:
    if item.get("nameKoSource") == NAME_SOURCE:
        if item.get("nameKo") == new:
            return False
        item["nameKo"] = new
        item["updated"] = now_iso
        return True
    if item.get("nameKoSource") == "joyhobby":
        item["nameKoJoy"] = item.get("nameKo")            # 몰을 걷어내면 조이하비 이름으로 돌아간다
    else:
        item["nameKoAi"] = item.get("nameKo")             # 몰을 걷어내면 AI 번역으로 돌아간다 (번역 전이었으면 None)
    item["nameKo"] = new
    item["nameKoSource"] = NAME_SOURCE
    item["updated"] = now_iso
    return True


def _revert_name(item: dict, now_iso: str) -> bool:
    if item.get("nameKoSource") != NAME_SOURCE:
        return False
    if "nameKoJoy" in item:
        item["nameKo"] = item.pop("nameKoJoy")
        item["nameKoSource"] = "joyhobby"
    else:
        item["nameKo"] = item.pop("nameKoAi", None)
        item.pop("nameKoSource", None)
    item["updated"] = now_iso
    return True


def _clear_mall_fields(item: dict, now_iso: str) -> bool:
    changed = _revert_name(item, now_iso)
    if item.get("seriesKoSource") == NAME_SOURCE:
        item.pop("seriesKo", None)
        item.pop("seriesKoSource", None)            # seriesKey가 있으면 series.apply가 사전 값으로 다시 채운다
        changed = True
    for k in ("priceKrw", "priceKrwAt", "mallGno", "mallSoldOut", "mallEnded"):
        if k in item:
            del item[k]
            changed = True
    if changed:
        item["updated"] = now_iso
    return changed


def _price_ok(good: dict, item: dict) -> bool:
    """몰 판매가(원) ÷ 호비 정가(엔)이 정상 범위인가. 엔 가격을 모르면 판단하지 않는다(통과)."""
    jpy = item.get("priceJpy")
    if not jpy:
        return True
    lo, hi = config.MALL_PRICE_RATIO
    return lo <= good["price"] / jpy <= hi


def _write_price(item: dict, good: dict, now_iso: str, price_at: str | None = None) -> bool:
    """가격·품절 표시·mallGno. 값이 바뀐 것만 `updated`를 올린다. 확인 시각 priceKrwAt은 `price_at`(= PC가 몰을 읽은 스냅샷 시각, 없으면 now_iso)."""
    changed = item.get("priceKrw") != good["price"] or item.get("mallGno") != good["gno"] or bool(item.get("mallSoldOut")) != good["soldOut"] or bool(item.get("mallEnded"))
    item["priceKrw"], item["priceKrwAt"], item["mallGno"] = good["price"], price_at or now_iso, good["gno"]
    if good["soldOut"]:
        item["mallSoldOut"] = True
    else:
        item.pop("mallSoldOut", None)
    item.pop("mallEnded", None)
    if changed:
        item["updated"] = now_iso
    return changed


def _apply_series(item: dict, series: str | None, now_iso: str) -> bool:
    if not series or (item.get("seriesKo") == series and item.get("seriesKoSource") == NAME_SOURCE):
        return False
    item["seriesKo"], item["seriesKoSource"] = series, NAME_SOURCE
    item["updated"] = now_iso
    return True


# ---------------------------------------------------------------- 연결
def link_all(state: MallState, catalog, seen: set[str], scan_complete: bool, now_iso: str, *, report_limit: int = 40, price_at: str | None = None) -> dict:
    """`scan_complete`: "몰에서 사라짐"을 판정해도 되는 스냅샷인가(정상으로 끝났고 너무 오래되지 않음). `price_at`: priceKrwAt에 쓸 스냅샷 시각 — 같은 스냅샷을 다시 적용해도 카탈로그가 바뀌지 않는다."""
    rep: dict = {"goods": len(state.goods), "seen": len(seen), "newLinks": [], "unlinked": [], "overrides": 0, "staleDropped": 0,
                 "nameChanged": [], "nameReverted": 0, "priceUpdated": 0, "ended": 0, "reasons": {}, "noName": 0}
    overrides = config.MALL_OVERRIDES

    # 1. 사람이 고친 표
    for gno, target in overrides.items():
        cur = state.links.get(gno)
        if target is None:
            if cur:
                old = catalog.items.get(cur["catalogId"])
                if old:
                    rep["nameReverted"] += _clear_mall_fields(old, now_iso)
                del state.links[gno]
            rep["overrides"] += 1
        elif target in catalog.items:
            if cur and cur["catalogId"] != target:
                old = catalog.items.get(cur["catalogId"])
                if old:
                    rep["nameReverted"] += _clear_mall_fields(old, now_iso)
            if not cur or cur["catalogId"] != target:
                state.links[gno] = {"catalogId": target, "method": "override", "score": None, "margin": None, "nameOk": True,
                                    "nameApplied": False, "at": now_iso}
            for other, e in list(state.links.items()):        # 한 카탈로그 항목에는 몰 상품 하나만 — 같은 항목을 가리키던 다른(자동) 연결은 푼다
                if other != gno and e["catalogId"] == target and overrides.get(other) != target:
                    del state.links[other]
            rep["overrides"] += 1

    # 카탈로그에서 사라진(제외로 옮겨진) 상품을 가리키는 연결은 버린다 → 다시 매칭 대상이 된다
    for gno, e in list(state.links.items()):
        if e["catalogId"] not in catalog.items:
            del state.links[gno]
            rep["staleDropped"] += 1

    # 2. 연결 안 된 상품(이번 스캔에 나온 것)을 지금의 카탈로그로 매칭
    blocked = {g for g, t in overrides.items() if t is None}
    claimed = {e["catalogId"]: g for g, e in state.links.items()}
    index = match.CatalogIndex(catalog.items.values())
    cands = []
    for gno in sorted(seen, key=int):
        if gno in state.links or gno in blocked or gno not in state.goods:
            continue
        g = state.goods[gno]
        mn = parse_mall_name(g["name"])
        m = match.best_match(mn.joy, index)
        row = {"gno": gno, "mall": g["name"], "series": g["series"], "price": g["price"], "reason": m.reason, "score": round(m.score, 1),
               "margin": round(m.margin, 1), "top": [(s, i, catalog.items[i].get("nameKo")) for s, i in m.top]}
        if m.linked and not _price_ok({**g, "gno": gno}, catalog.items[m.catalog_id]):
            row["reason"], m.linked = "price-mismatch", False
        if m.linked:
            cands.append((m, mn, row))
        else:
            rep["reasons"][row["reason"]] = rep["reasons"].get(row["reason"], 0) + 1
            rep["unlinked"].append(row)
    for m, mn, row in sorted(cands, key=lambda t: (-t[0].score, int(t[2]["gno"]))):       # 점수 높은 쪽이 카탈로그 항목을 가져간다
        if m.catalog_id in claimed:
            row["reason"] = "duplicate"
            rep["reasons"]["duplicate"] = rep["reasons"].get("duplicate", 0) + 1
            rep["unlinked"].append(row)
            continue
        claimed[m.catalog_id] = row["gno"]
        state.links[row["gno"]] = {"catalogId": m.catalog_id, "method": "fuzzy", "score": row["score"], "margin": row["margin"],
                                   "nameOk": m.name_ok, "nameApplied": False, "at": now_iso}
        rep["newLinks"].append({**row, "catalogId": m.catalog_id, "nameOk": m.name_ok, "catalogNameKo": catalog.items[m.catalog_id].get("nameKo")})

    # 3. 이번 스캔에 있는 연결 상품: 가격·품절·mallGno, 확실한 연결이면 이름·시리즈
    for gno, e in state.links.items():
        item = catalog.items[e["catalogId"]]
        if gno in seen and gno in state.goods:
            g = {**state.goods[gno], "gno": gno}
            rep["priceUpdated"] += _write_price(item, g, now_iso, price_at)
            if e.get("nameOk"):
                mn = parse_mall_name(g["name"])
                if not mn.core:
                    rep["noName"] += 1
                else:
                    before, was = item.get("nameKo"), item.get("nameKoSource") or "ai"
                    new = mall_name_ko(mn, item)
                    if _apply_name(item, new, now_iso):
                        e["nameApplied"] = True
                        rep["nameChanged"].append({"gno": gno, "id": item["id"], "before": before, "after": new, "was": was})
                if _apply_series(item, g.get("series"), now_iso):
                    e["seriesApplied"] = True

    # 4. 정상 스캔이 끝났을 때만 — 몰에서 사라진 연결 상품
    if scan_complete and seen:
        for gno, e in state.links.items():
            if gno not in seen and gno in state.goods:
                item = catalog.items[e["catalogId"]]
                if not item.get("mallEnded"):
                    item["mallEnded"] = True
                    item["updated"] = now_iso
                    rep["ended"] += 1
    return rep
