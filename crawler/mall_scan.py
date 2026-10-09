"""반다이남코코리아몰 목록 스냅샷 `docs/data/mall-scan.json` — 사용자 PC가 쓰고 Actions는 읽기만 한다. (7a 후속)

왜: 몰의 웹 방화벽이 GitHub Actions(클라우드 IP)에는 "Request Rejected / Your support ID is …"(HTTP 200, 247바이트)만 돌려준다 (2026-10 진단).
그래서 몰 목록은 한국 IP인 사용자 PC에서 평소처럼 받는다(`python main.py --only mall --mall-local`, 작업 스케줄러 하루 1회).
VPN·프록시·헤더 위장 같은 우회는 하지 않는다. PC에서도 차단 응답이 오면 `blocked:true`로 기록하고 그 자리에서 멈춘다.

파일 작성자 분리: PC는 이 파일만, Actions는 `mall.json`(연결 상태)·카탈로그만 쓴다. 그래서 push 충돌이 없다.

mall-scan.json
  updatedAt  마지막 시도 시각
  blocked    마지막 시도가 방화벽 차단이었는가
  lastTry    마지막 시도: {at, ok, blocked, complete, requests, pages, results:[{where,status,ok,bytes}], errors, diag}
  scan       goods를 읽은 스캔: {at, complete, requests, count} — 시도가 상품을 하나도 못 읽었으면(차단·구조 변경) 이전 값을 그대로 둔다
  goods      {gno: {name, series, price, soldOut, cate}} — 마지막으로 읽은 상품 (시도가 실패하면 이전 값 그대로)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from . import config
from .http import Blocked, HttpClient, SourceAborted
from .sources import mall
from .store import iso, now_kst, read_json, write_json

log = logging.getLogger("plamo.mall_scan")


def load(data_dir: Path) -> dict | None:
    d = read_json(Path(data_dir) / config.MALL_SCAN_FILE, None)
    return d if isinstance(d, dict) else None


def run_local(http: HttpClient, data_dir: Path, *, dump_dir: Path | None = None, dry_run: bool = False,
              now: datetime | None = None, out=print) -> dict:
    """몰 목록을 읽어 mall-scan.json을 쓴다(카탈로그·mall.json·meta는 건드리지 않는다). → 쓴(또는 dry-run이면 쓸) 문서."""
    now_iso = iso(now or now_kst())
    prev = load(data_dir) or {}
    try:
        res = mall.scan(http, dump_dir=dump_dir)
    except SourceAborted as e:        # 429는 차단, 연속 실패는 장애
        res = {"goods": {}, "requests": http.stats.by_kind["mall"], "complete": False, "pages": {}, "diag": [], "results": [],
               "blocked": str(e).startswith("429"), "errors": [f"중단: {e}"]}
    except Blocked as e:              # robots.txt가 막은 경로
        res = {"goods": {}, "requests": http.stats.by_kind["mall"], "complete": False, "pages": {}, "diag": [], "results": [],
               "blocked": False, "errors": [f"중단: {e}"]}
    blocked = bool(res["blocked"])
    got = bool(res["goods"]) and not blocked
    doc = {
        "updatedAt": now_iso,
        "blocked": blocked,
        "lastTry": {"at": now_iso, "ok": got and res["complete"], "blocked": blocked, "complete": bool(res["complete"]) and got,
                    "requests": res["requests"], "pages": res["pages"], "results": res["results"], "errors": res["errors"], "diag": res["diag"]},
        "scan": prev.get("scan") or {},
        "goods": prev.get("goods") or {},
    }
    if got:      # 일부만 읽은 스캔도 상품이 있으면 스냅샷으로 삼는다(complete:false라 Actions가 "판매 종료"는 판정하지 않는다)
        doc["scan"] = {"at": now_iso, "complete": bool(res["complete"]), "requests": res["requests"], "count": len(res["goods"])}
        doc["goods"] = dict(sorted(res["goods"].items(), key=lambda kv: int(kv[0])))
    if not dry_run:
        write_json(Path(data_dir) / config.MALL_SCAN_FILE, doc)
    status = "차단됨" if blocked else ("완료" if got and res["complete"] else ("일부만 읽음" if got else "실패"))
    out(f"[몰 수집·PC] {status}: 상품 {len(res['goods'])}개 · 요청 {res['requests']}회 {res['pages']}"
        + (f" · 오류 {res['errors']}" if res["errors"] else "") + (" · (dry-run: 파일을 쓰지 않음)" if dry_run else f" → {config.MALL_SCAN_FILE}"))
    if blocked:
        out("[몰 수집·PC] 방화벽 차단 응답입니다. 재시도하거나 우회하지 않습니다 — 기록(blocked:true)만 남기고 끝냅니다.")
    return doc


def snapshot_age_days(scan_at: str | None, now: datetime) -> int | None:
    """스냅샷 시각 → 오늘(KST)까지 지난 날짜 수. 시각을 모르면 None."""
    try:
        d = date.fromisoformat(str(scan_at)[:10])
    except ValueError:
        return None
    return (now.astimezone(config.KST).date() - d).days


def to_scan(doc: dict, now: datetime) -> tuple[dict | None, list[str]]:
    """mall-scan.json → (`MallState.absorb`에 줄 스캔, meta에 남길 경고들). 읽을 스냅샷이 없으면 (None, 경고).
    scan: {goods, complete, requests, pages, errors, diag, at, blocked, stale, ageDays}"""
    warns: list[str] = []
    last = doc.get("lastTry") or {}
    if doc.get("blocked"):
        warns.append("PC 수집이 몰 방화벽에 차단됨(blocked) — 가격은 마지막 스냅샷 그대로입니다. 차단이 풀릴 때까지 기다리고 우회하지 않습니다")
    elif last and not last.get("ok") and not last.get("complete"):
        warns.append("PC 수집이 일부만 읽었거나 실패함: " + "; ".join(last.get("errors") or ["오류 내용 없음"])[:200])
    snap = doc.get("scan") or {}
    goods = doc.get("goods") or {}
    if not goods or not snap.get("at"):
        warns.append("읽을 몰 스냅샷이 없음 — PC에서 python main.py --only mall --mall-local 실행 필요")
        return None, warns
    age = snapshot_age_days(snap["at"], now)
    stale = age is None or age > config.MALL_STALE_DAYS
    if stale:
        warns.append(f"몰 스냅샷이 {age}일 지남(기준 {config.MALL_STALE_DAYS}일) — '판매 종료' 판정은 하지 않습니다. PC 작업 스케줄러를 확인하세요")
    scan = {"goods": goods, "complete": bool(snap.get("complete")), "requests": int(snap.get("requests") or 0), "pages": last.get("pages") or {},
            "errors": list(last.get("errors") or []), "diag": list(last.get("diag") or []), "at": snap["at"],
            "blocked": bool(doc.get("blocked")), "stale": stale, "ageDays": age}
    return scan, warns
