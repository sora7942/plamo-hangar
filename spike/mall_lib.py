"""6-0 spike: 반다이남코코리아몰(bnkrmall.co.kr) 확인용 요청 도구.

- 전체 요청 30회 상한 (이미지 요청 포함, spike/out/mall-budget.json에 누적) · robots.txt 준수 · 요청 간 1.2초 이상
- 같은 URL은 spike/out/mall-cache/ 에서 읽어 재요청하지 않는다 (재요청이 필요한 시간 경과 확인만 fresh=True로 명시)
- 모든 요청은 spike/out/mall-requests.log 에 남긴다
- 본문은 spike/out/mall-cache/ 에만 저장 (저장소에 넣지 않는다 — spike/out은 .gitignore)
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler import config  # noqa: E402
from crawler.http import HttpClient, decode_body  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
CACHE = OUT / "mall-cache"
BUDGET = OUT / "mall-budget.json"
LOG = OUT / "mall-requests.log"
CAP = 30
BASE = "https://www.bnkrmall.co.kr"
CACHE.mkdir(parents=True, exist_ok=True)

_client = HttpClient(log_path=LOG)          # robots.txt 확인·1.2초 간격·기록은 크롤러와 같은 게이트를 쓴다


def used() -> int:
    return json.loads(BUDGET.read_text(encoding="utf-8"))["n"] if BUDGET.exists() else 0


def _bump(url: str, note: str = "") -> None:
    n = used() + 1
    if n > CAP:
        raise RuntimeError(f"요청 상한 {CAP}회 초과 — 중단")
    BUDGET.write_text(json.dumps({"n": n, "last": url, "at": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    print(f"[요청 {n}/{CAP}] {note}{url}")


def _path(url: str) -> Path:
    return CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")


def _ensure_robots() -> None:
    """robots.txt는 한 번만 받아 디스크에 두고(요청 1회), 다음 프로세스부터는 읽어서 쓴다."""
    from crawler.http import Robots
    if BASE in _client._robots:
        return
    rp = CACHE / "robots.txt"
    if not rp.exists():
        _bump(BASE + "/robots.txt", "robots ")
        res = _client._send(BASE + "/robots.txt", "robots")
        rp.write_text(res.text if res.ok else "", encoding="utf-8")
    _client._robots[BASE] = Robots(rp.read_text(encoding="utf-8"))


def get(url: str, *, fresh: bool = False) -> tuple[int | None, str, str]:
    """→ (status, text, final_url). 캐시에 있으면 요청하지 않는다. robots로 막힌 경로는 열지 않는다."""
    p = _path(url)
    if p.exists() and not fresh:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d["status"], d["text"], d["final"]
    _ensure_robots()
    _bump(url)
    res = _client.get(url, kind="spike")
    d = {"status": res.status, "text": res.text, "final": res.final_url}
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return res.status, res.text, res.final_url


def raw_get(url: str, headers: dict, *, stream_bytes: int = 0) -> tuple[int | None, dict, bytes]:
    """이미지 등 비HTML 확인용 (같은 간격·상한). stream_bytes>0이면 그만큼만 읽는다."""
    _client.limiter.wait()
    _bump(url, "raw ")
    r = _client.session.get(url, headers={"User-Agent": config.USER_AGENT, **headers}, timeout=config.TIMEOUT, stream=True, allow_redirects=True)
    body = next(r.iter_content(stream_bytes or 65536), b"") if stream_bytes else r.content
    r.close()
    return r.status_code, dict(r.headers), body
