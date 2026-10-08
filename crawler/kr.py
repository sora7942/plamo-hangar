"""국내 입고(조이하비) 상태와 연결 — kr-arrivals.json, 카탈로그 kr, nameKo 교체, 피드 항목.

kr-arrivals.json (SPEC 4장)
  posts:   {글번호: {date(글 날짜), title, state(pending|done|no-bd|gone|broken|error), sale(판매예정일|null), restock, rows, fails?}}
  rows:    [{post, postDate, code, name, price}]   조이하비 원본 행. (post, code)는 한 번만
  codeMap: {BD코드: {catalogId, method(fuzzy|override), score, margin, nameOk, nameApplied, post, at}}
           한 번 확실히 연결된 코드 ↔ 카탈로그 id. 다음 글부터는 코드로 바로 연결한다 (코드가 같으면 같은 상품)

매 실행(link_all)
  1. KR_CODE_OVERRIDES 적용 (강제 연결 / 연결 금지: 굳은 연결을 풀고 nameKo를 nameKoAi로 되돌리고 그 코드의 kr을 뺀다)
  2. 연결 안 된 코드를 지금의 카탈로그로 다시 매칭 → 카탈로그가 나중에 채워지면 과거 입고도 연결된다
  3. 높은 기준을 넘은 연결만, **line이 gunpla인 항목만** nameKo를 조이하비 한글명으로 교체 (원래 번역은 nameKoAi에 보존, nameKoSource="joyhobby").
     gunpla가 아닌 항목에 이미 바뀐 이름이 있으면 nameKoAi로 되돌린다
  4. 연결된 모든 행에 대해 카탈로그 kr 항목 추가 — (post, code) 한 번만, 지우지 않는다 (override 금지 외에는)
"""
from __future__ import annotations

import calendar
import logging
import re
from datetime import date
from pathlib import Path

from . import config, match
from .sources import joyhobby
from .store import read_json, write_json

log = logging.getLogger("plamo.kr")

_FEED_ID_RX = re.compile(r"^jh-(\d+)-(.+)$")
NAME_REPLACE_LINE = "gunpla"      # nameKo를 조이하비 한글명으로 바꾸는 것은 이 line만. 걸프라는 연결·kr만 하고 번역을 유지한다


# ---------------------------------------------------------------- 상태 파일
class Arrivals:
    def __init__(self) -> None:
        self.updated_at: str | None = None
        self.posts: dict[str, dict] = {}
        self.rows: list[dict] = []
        self.code_map: dict[str, dict] = {}
        self._prev: dict | None = None

    @classmethod
    def load(cls, data_dir: Path) -> "Arrivals":
        a = cls()
        d = read_json(Path(data_dir) / config.KR_ARRIVALS_FILE, None)
        if isinstance(d, dict):
            a._prev = d
            a.updated_at = d.get("updatedAt")
            a.posts = {k: dict(v) for k, v in (d.get("posts") or {}).items()}
            a.rows = [dict(r) for r in d.get("rows") or []]
            a.code_map = {k: dict(v) for k, v in (d.get("codeMap") or {}).items()}
        return a

    def payload(self, updated_at: str) -> dict:
        rows = sorted(self.rows, key=lambda r: -int(r["post"]))             # 안정 정렬: 같은 글 안에서는 들어온 순서
        return {"updatedAt": updated_at,
                "posts": dict(sorted(self.posts.items(), key=lambda kv: -int(kv[0]))),
                "codeMap": dict(sorted(self.code_map.items())),
                "rows": rows}

    def save(self, data_dir: Path, now_iso: str) -> None:
        doc = self.payload(now_iso)
        if self._prev and all(self._prev.get(k) == doc[k] for k in ("posts", "codeMap", "rows")):
            doc["updatedAt"] = self._prev.get("updatedAt", now_iso)          # 바뀐 게 없으면 시각도 그대로
        write_json(Path(data_dir) / config.KR_ARRIVALS_FILE, doc)

    # ------------------------------------------------------------ 목록·본문 반영
    def note_board_row(self, row: dict) -> bool:
        """목록 행을 본다. 후보 제목이고 처음 보는 글이면 pending으로 올린다 → 새로 올렸는가."""
        pid = row["id"]
        if pid in self.posts or not row.get("date") or not joyhobby.is_candidate_title(row["title"]):
            return False
        self.posts[pid] = {"date": row["date"], "title": row["title"], "state": "pending"}
        return True

    def pending(self, limit: int) -> list[str]:
        ids = [pid for pid, p in self.posts.items() if p["state"] == "pending"]
        ids.sort(key=lambda i: (self.posts[i]["date"], int(i)), reverse=True)     # 최신 글부터
        ids.sort(key=lambda i: self.posts[i].get("fails", 0))                      # 안정 정렬: 실패한 적 있는 글은 뒤로 (새 글이 먼저)
        return ids[:limit]

    def record_post(self, pid: str, parsed: dict) -> None:
        post = self.posts[pid]
        post_date = date.fromisoformat(post["date"])
        sale = joyhobby.parse_sale_date(post["title"], post_date)
        post.pop("fails", None)
        post.update({"sale": sale.isoformat() if sale else None, "restock": bool(parsed["restock"]),
                     "rows": len(parsed["rows"]), "state": "done" if parsed["rows"] else "no-bd"})
        have = {(r["post"], r["code"]) for r in self.rows}
        for r in parsed["rows"]:
            if (pid, r["code"]) not in have:
                self.rows.append({"post": pid, "postDate": post["date"], "code": r["code"], "name": r["name"], "price": r["price"]})

    def record_failure(self, pid: str, status: int | None, *, site_bug: bool = False) -> None:
        post = self.posts[pid]
        if status == 404:
            post["state"] = "gone"
            return
        if site_bug:                                  # 조이하비 서버 버그(조회수 overflow)로 누가 열어도 500 — 다시 시도하지 않는다
            post["state"] = "broken"
            return
        post["fails"] = post.get("fails", 0) + 1
        if post["fails"] >= config.JOY_POST_MAX_FAILURES:
            post["state"] = "error"

    # ------------------------------------------------------------ 조회
    def kr_date(self, pid: str) -> str:
        p = self.posts[pid]
        return p.get("sale") or p["date"]

    def latest_rows(self) -> dict[str, dict]:
        """코드 → 가장 최근 글의 행."""
        out: dict[str, dict] = {}
        for r in self.rows:
            cur = out.get(r["code"])
            if cur is None or (r["postDate"], int(r["post"])) > (cur["postDate"], int(cur["post"])):
                out[r["code"]] = r
        return out

    def stats(self) -> dict:
        states: dict[str, int] = {}
        for p in self.posts.values():
            states[p["state"]] = states.get(p["state"], 0) + 1
        codes = {r["code"] for r in self.rows}
        return {"posts": len(self.posts), "postStates": states, "rows": len(self.rows), "codes": len(codes),
                "linkedCodes": len(codes & self.code_map.keys())}


# ---------------------------------------------------------------- kr 규칙
def kr_type(release: dict | None, kr_date: str, post_restock: bool) -> str:
    """일본 발매일 + KR_RESTOCK_AFTER_DAYS 이상 뒤면 restock, 아니면 new. 발매일이 없으면 글의 "재입고" 문구로.
    발매일이 월만 알려져 있으면 그 달의 마지막 날을 발매일로 본다 (애매하면 restock이 아닌 new 쪽)."""
    d = date.fromisoformat(kr_date)
    ref: date | None = None
    if release:
        if release.get("date"):
            ref = date.fromisoformat(release["date"])
        elif release.get("month"):
            y, m = (int(x) for x in release["month"].split("-"))
            ref = date(y, m, calendar.monthrange(y, m)[1])
    if ref is None:
        return "restock" if post_restock else "new"
    return "restock" if (d - ref).days >= config.KR_RESTOCK_AFTER_DAYS else "new"


# ---------------------------------------------------------------- 연결
def _revert_name(item: dict, now_iso: str) -> bool:
    if item.get("nameKoSource") != "joyhobby":
        return False
    item["nameKo"] = item.pop("nameKoAi", None)
    item.pop("nameKoSource", None)
    item["updated"] = now_iso
    return True


def _drop_kr_code(catalog, code: str, keep_id: str | None, now_iso: str) -> int:
    n = 0
    for it in catalog.items.values():
        if it["id"] == keep_id or not it.get("kr"):
            continue
        kept = [k for k in it["kr"] if k.get("code") != code]
        if len(kept) != len(it["kr"]):
            n += len(it["kr"]) - len(kept)
            it["kr"] = kept
            it["updated"] = now_iso
    return n


def link_all(arr: Arrivals, catalog, now_iso: str, *, near_miss_limit: int = 40) -> dict:
    """연결·nameKo·kr을 한 번에 갱신한다. → 보고용 dict."""
    rep: dict = {"newLinks": [], "nearMiss": [], "overrides": 0, "staleDropped": 0, "nameChanged": 0, "nameReverted": 0,
                 "krAdded": 0, "krRemoved": 0, "unlinkedCodes": 0, "reasons": {}}
    overrides = config.KR_CODE_OVERRIDES
    latest = arr.latest_rows()

    # 1. 사람이 고친 표
    for code, target in overrides.items():
        cur = arr.code_map.get(code)
        if target is None:
            if cur:
                old = catalog.items.get(cur["catalogId"])
                if old and cur.get("nameApplied") and _revert_name(old, now_iso):
                    rep["nameReverted"] += 1
                del arr.code_map[code]
            rep["krRemoved"] += _drop_kr_code(catalog, code, None, now_iso)
            rep["overrides"] += 1
        elif target in catalog.items:
            if cur and cur["catalogId"] != target:
                old = catalog.items.get(cur["catalogId"])
                if old and cur.get("nameApplied") and _revert_name(old, now_iso):
                    rep["nameReverted"] += 1
            if not cur or cur["catalogId"] != target:
                arr.code_map[code] = {"catalogId": target, "method": "override", "score": None, "margin": None,
                                      "nameOk": True, "nameApplied": False, "post": (latest.get(code) or {}).get("post"), "at": now_iso}
            rep["krRemoved"] += _drop_kr_code(catalog, code, target, now_iso)
            rep["overrides"] += 1

    # 카탈로그에서 사라진(제외로 옮겨진) 상품을 가리키는 연결은 버린다 → 다시 매칭 대상이 된다
    for code, e in list(arr.code_map.items()):
        if e["catalogId"] not in catalog.items:
            del arr.code_map[code]
            rep["staleDropped"] += 1

    # 2. 연결 안 된 코드를 지금의 카탈로그로 다시 매칭
    blocked = {c for c, t in overrides.items() if t is None}
    todo = [r for c, r in latest.items() if c not in arr.code_map and c not in blocked]
    index = match.CatalogIndex(catalog.items.values())
    for r in sorted(todo, key=lambda r: r["code"]):
        jn = match.parse_name(r["name"])
        m = match.best_match(jn, index)
        if m.linked:
            arr.code_map[r["code"]] = {"catalogId": m.catalog_id, "method": "fuzzy", "score": round(m.score, 1),
                                       "margin": round(m.margin, 1), "nameOk": m.name_ok, "nameApplied": False,
                                       "post": r["post"], "at": now_iso}
            rep["newLinks"].append({"code": r["code"], "catalogId": m.catalog_id, "score": round(m.score, 1),
                                    "margin": round(m.margin, 1), "nameOk": m.name_ok, "joy": r["name"],
                                    "catalogNameKo": catalog.items[m.catalog_id].get("nameKo")})
        else:
            rep["reasons"][m.reason] = rep["reasons"].get(m.reason, 0) + 1
            if m.reason in ("low-score", "ambiguous", "model-conflict", "guard") and len(rep["nearMiss"]) < near_miss_limit:
                rep["nearMiss"].append({"code": r["code"], "joy": r["name"], "reason": m.reason, "guarded": m.guarded, "score": round(m.score, 1),
                                        "margin": round(m.margin, 1), "top": [(s, i, catalog.items[i].get("nameKo")) for s, i in m.top]})
    rep["unlinkedCodes"] = len([c for c in latest if c not in arr.code_map])

    # 3-a. 건프라(gunpla)가 아닌 항목(걸프라 등)은 nameKo를 바꾸지 않는다 — 이미 바뀐 것은 nameKoAi로 되돌린다 (연결·kr은 그대로)
    for it in catalog.items.values():
        if it.get("nameKoSource") == "joyhobby" and it.get("line") != NAME_REPLACE_LINE and _revert_name(it, now_iso):
            for e in arr.code_map.values():
                if e["catalogId"] == it["id"]:
                    e["nameApplied"] = False
            rep["nameReverted"] += 1
    # 3-b. 높은 기준을 넘은(또는 사람이 확인한) 연결만 nameKo를 조이하비 한글명으로 교체
    for code, e in arr.code_map.items():
        if e.get("nameApplied") or not e.get("nameOk") or code not in latest:
            continue
        item = catalog.items[e["catalogId"]]
        if item.get("nameKoSource") or item.get("line") != NAME_REPLACE_LINE:      # 이미 조이하비·몰 이름이면 건드리지 않는다 (몰 > 조이하비 > AI)
            continue
        jn = match.parse_name(latest[code]["name"])
        if not jn.text:
            continue
        item["nameKoAi"] = item.get("nameKo")                       # 바꾸기 전 번역 보존 (되돌릴 때 쓴다)
        # 앞의 등급 낱말은 기존 번역의 것을 보존한다 (HGUC·HGBD처럼 하위 라인을 구별하는 표기가 `grade`(HG)로 뭉개지지 않게)
        item["nameKo"] = match.display_name(jn, grade=match.leading_grade_words(item.get("nameKo")) or item.get("grade"),
                                            scale=item.get("scale"))
        item["nameKoSource"] = "joyhobby"
        item["updated"] = now_iso
        e["nameApplied"] = True
        rep["nameChanged"] += 1

    # 4. 연결된 행마다 카탈로그 kr 항목 — (post, code) 한 번만
    have: dict[str, set[tuple[str, str]]] = {}
    touched: set[str] = set()
    for r in arr.rows:
        e = arr.code_map.get(r["code"])
        if not e or r["post"] not in arr.posts:
            continue
        item = catalog.items[e["catalogId"]]
        keys = have.setdefault(item["id"], {(k.get("post"), k.get("code")) for k in item.get("kr") or []})
        if (r["post"], r["code"]) in keys:
            continue
        kd = arr.kr_date(r["post"])
        item.setdefault("kr", []).append({
            "date": kd, "type": kr_type(item.get("release"), kd, bool(arr.posts[r["post"]].get("restock"))),
            "source": "joyhobby", "post": r["post"], "code": r["code"], "priceKrw": r["price"], "seenAt": now_iso})
        keys.add((r["post"], r["code"]))
        touched.add(item["id"])
        rep["krAdded"] += 1
    for cid in touched:
        item = catalog.items[cid]
        item["kr"].sort(key=lambda k: (k["date"], k["post"], k["code"]))
        item["updated"] = now_iso
    return rep


# ---------------------------------------------------------------- 피드
def _row_type(arr: Arrivals, catalog, row: dict) -> tuple[str, str | None]:
    """→ (kr-restock|kr-new, 연결된 catalogId | None)."""
    e = arr.code_map.get(row["code"])
    item = catalog.items.get(e["catalogId"]) if e else None
    kd = arr.kr_date(row["post"])
    release = item.get("release") if item else None
    t = kr_type(release, kd, bool(arr.posts[row["post"]].get("restock")))
    return f"kr-{t}", item["id"] if item else None


def feed_items(arr: Arrivals, catalog, today: date, now_iso: str) -> tuple[list[dict], set[str]]:
    """글 날짜가 최근 KR_FEED_DAYS일 이내인 행의 피드 항목. → (항목들, 그중 디스코드 알림 대상 id: 글 날짜 KR_NOTIFY_DAYS일 이내).
    이미 피드에 있는 id는 merge_feed가 무시한다. 과거 글은 kr 이력·원본 행에만 들어가고 피드에는 오지 않는다."""
    out, notify = [], set()
    for r in arr.rows:
        post = arr.posts.get(r["post"])
        if not post:
            continue
        age = (today - date.fromisoformat(post["date"])).days
        if age > config.KR_FEED_DAYS:
            continue
        ftype, cid = _row_type(arr, catalog, r)
        item = catalog.items.get(cid) if cid else None
        jn = match.parse_name(r["name"])
        fid = f"jh-{r['post']}-{r['code']}"
        out.append({
            "id": fid, "type": ftype, "date": arr.kr_date(r["post"]), "added": now_iso, "catalogId": cid,
            "title": r["name"], "titleKo": match.display_name(jn, scale=(item or {}).get("scale")) or None,
            "url": joyhobby.post_url(r["post"]), "image": (item.get("images") or [None])[0] if item else None,
            "source": "joyhobby"})
        if age <= config.KR_NOTIFY_DAYS:
            notify.add(fid)
    return out, notify


def refresh_feed(items: list[dict], arr: Arrivals, catalog) -> int:
    """이미 피드에 있는 조이하비 항목 중 나중에 카탈로그와 연결된 것의 catalogId·image를 채우고, type을 60일 규칙으로 고친다.
    `added`와 나머지는 그대로. → 바뀐 항목 수."""
    changed = 0
    rows = {(r["post"], r["code"]): r for r in arr.rows}
    for it in items:
        m = _FEED_ID_RX.match(it["id"])
        row = rows.get((m.group(1), m.group(2))) if m else None
        if not row or row["post"] not in arr.posts:
            continue
        ftype, cid = _row_type(arr, catalog, row)
        before = (it.get("catalogId"), it.get("image"), it.get("type"))
        if cid:
            it["catalogId"] = cid
            if not it.get("image"):
                it["image"] = (catalog.items[cid].get("images") or [None])[0]
            it["type"] = ftype
        if (it.get("catalogId"), it.get("image"), it.get("type")) != before:
            changed += 1
    return changed
