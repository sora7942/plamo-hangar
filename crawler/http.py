"""외부 HTTP 요청 게이트 — spike/common.py의 요청 간격·robots·로그를 정리해 옮긴 것.

- 모든 요청은 RateLimiter(요청 시작~시작 간격 >= MIN_INTERVAL)를 통과한다
- robots.txt를 먼저 받아 허용 여부를 확인하고, 막힌 경로는 열지 않는다
- timeout, 브라우저형 User-Agent를 항상 붙인다
- requests.log에 탭 구분으로 남긴다 (시작 시각, method, kind, status, redirects, url, final, note)
- 403/429나 연속 실패가 이어지면 그 소스를 중단한다 (SourceAborted)
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config
from .store import now_kst

log = logging.getLogger("plamo.http")


_CHARSET_HEADER_RX = re.compile(r"charset\s*=\s*[\"']?([\w.:-]+)", re.I)
_CHARSET_META_RX = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([\w.:-]+)", re.I)
_CHARSET_ALIASES = {"euc-kr": "cp949", "euckr": "cp949", "ks_c_5601-1987": "cp949", "ksc5601": "cp949"}   # cp949가 euc-kr의 상위 집합


def decode_body(content: bytes, content_type: str | None = None) -> str:
    """응답 바이트 → 문자열. 문자 집합은 Content-Type 헤더 → HTML `<meta charset>` → UTF-8 순으로 정한다.

    조이하비는 EUC-KR이라 UTF-8로 읽으면 한글이 전부 깨진다(r.text는 charset이 없으면 latin-1로 읽어 이것도 깨진다).
    알 수 없는 이름이면 UTF-8. 디코딩 오류는 치환 문자로 두고 멈추지 않는다.
    """
    name = None
    m = _CHARSET_HEADER_RX.search(content_type or "")
    if m:
        name = m.group(1)
    else:
        m = _CHARSET_META_RX.search(content[:4096])
        if m:
            name = m.group(1).decode("ascii", "ignore")
    name = _CHARSET_ALIASES.get((name or "utf-8").lower(), (name or "utf-8"))
    try:
        return content.decode(name, "replace")
    except LookupError:
        return content.decode("utf-8", "replace")


class Blocked(Exception):
    """robots.txt 차단 또는 상세 상한 초과로 요청하지 않음."""


class SourceAborted(Exception):
    """429 또는 연속 실패 — 이 소스는 더 두드리지 않는다."""


class RateLimiter:
    """요청 시작 시각끼리 min_interval 이상 떨어지게 한다. 시계·sleep을 주입할 수 있어 테스트에서 가짜로 바꾼다."""

    def __init__(self, min_interval: float = config.MIN_INTERVAL, clock=time.perf_counter, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def now(self) -> float:
        return self._clock()

    def wait(self) -> None:
        # sleep이 조금 일찍 깨는 환경(Windows 시계 해상도 ~15ms)에서도 간격이 모자라지 않게, 시계로 확인될 때까지 반복한다
        while self._last is not None:
            gap = self._clock() - self._last
            if gap >= self.min_interval:
                break
            self._sleep(self.min_interval - gap)
        self._last = self._clock()


class Robots:
    """Google 방식(와일드카드 *, $, 가장 긴 규칙 우선, 동률이면 Allow) 최소 구현 — UA '*' 그룹만 본다.

    urllib.robotparser는 * / $ 를 못 읽어서 직접 구현했다 (spike/common.py의 Robots와 같다).
    """

    def __init__(self, text: str):
        self.rules: list[tuple[str, str]] = []
        group_agents: list[str] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, v = (s.strip() for s in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if in_rules:
                    group_agents, in_rules = [], False
                group_agents.append(v.lower())
            elif k in ("allow", "disallow"):
                in_rules = True
                if "*" in group_agents and v:
                    self.rules.append((k, v))

    @staticmethod
    def _match(pattern: str, path: str) -> int:
        end = pattern.endswith("$")
        pat = pattern[:-1] if end else pattern
        rx = "^" + "".join(".*" if c == "*" else re.escape(c) for c in pat) + ("$" if end else "")
        return len(pattern) if re.match(rx, path) else -1

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        path = (u.path or "/") + (("?" + u.query) if u.query else "")
        best, verdict = -1, True
        for kind, pat in self.rules:
            n = self._match(pat, path)
            if n > best or (n == best and kind == "allow"):
                best, verdict = n, (kind == "allow")
        return verdict


@dataclass
class Fetched:
    url: str
    status: int | None = None
    text: str = ""
    final_url: str = ""
    redirects: int = 0
    error: str | None = None
    size: int = 0                  # 응답 본문 바이트 수 (진단용)
    content_type: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


@dataclass
class Stats:
    started: float = field(default_factory=time.monotonic)
    by_kind: Counter = field(default_factory=Counter)
    failures: int = 0
    min_gap: float | None = None   # 실제 요청 시작 간격 중 최소(초) — 간격 준수 확인용
    _last_start: float | None = None

    @property
    def requests(self) -> int:
        return sum(self.by_kind.values())

    def note_start(self, mono: float) -> None:
        if self._last_start is not None:
            gap = mono - self._last_start
            self.min_gap = gap if self.min_gap is None else min(self.min_gap, gap)
        self._last_start = mono

    def as_dict(self) -> dict:
        return {"requests": self.requests, "byKind": dict(self.by_kind), "failures": self.failures,
                "elapsedSec": round(time.monotonic() - self.started, 1)}


class HttpClient:
    def __init__(self, *, session=None, limiter: RateLimiter | None = None, log_path: Path | None = None,
                 detail_limit: int | None = None, timeout: int = config.TIMEOUT, user_agent: str = config.USER_AGENT):
        self.session = session or requests.Session()
        self.limiter = limiter or RateLimiter()
        self.log_path = Path(log_path) if log_path else None
        self.detail_limit = detail_limit          # kind="detail" 요청 상한 (안전장치)
        self.timeout = timeout
        self.user_agent = user_agent
        self.stats = Stats()
        self._robots: dict[str, Robots] = {}
        self.robots_info: dict[str, dict] = {}      # origin → robots.txt 요청 결과 요약 (진단용: HTTP 상태, 크기, 앞부분)
        self._consecutive_failures = 0
        self._start_wall: datetime | None = None   # 마지막 요청의 "시작" 시각 — 로그의 간격 = 시작~시작 간격 (spike와 같은 방식)

    # ------------------------------------------------------------ 로그
    def _log(self, method: str, kind: str, status, url: str, final: str = "", redirects: int = 0, note: str = "") -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        when = now_kst() if method == "SKIP" or self._start_wall is None else self._start_wall
        line = "\t".join([when.isoformat(timespec="milliseconds"), method, kind, str(status), str(redirects),
                          url, final if final != url else "", note])
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------ 실제 전송 (게이트 통과 후)
    def _send(self, url: str, kind: str) -> Fetched:
        self.limiter.wait()
        self._start_wall = now_kst()
        self.stats.note_start(self.limiter.now())      # 간격 통계도 제한기와 같은 시계를 쓴다
        self.stats.by_kind[kind] += 1
        try:
            r = self.session.get(url, headers={"User-Agent": self.user_agent, "Accept-Language": "ja,en;q=0.5"},
                                 timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as e:
            self.stats.failures += 1
            self._log("GET", kind, "ERR", url, note=type(e).__name__)
            return Fetched(url=url, error=type(e).__name__)
        headers = getattr(r, "headers", None) or {}
        text = decode_body(r.content, headers.get("Content-Type"))
        self._log("GET", kind, r.status_code, url, r.url, len(r.history))
        return Fetched(url=url, status=r.status_code, text=text, final_url=r.url, redirects=len(r.history),
                       size=len(r.content or b""), content_type=str(headers.get("Content-Type") or ""))

    # ------------------------------------------------------------ robots
    def _robots_for(self, url: str) -> Robots:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}"
        if origin not in self._robots:
            res = self._send(origin + "/robots.txt", "robots")
            ctype_html = res.text.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
            self.robots_info[origin] = {"status": res.status, "error": res.error, "bytes": res.size, "html": ctype_html,
                                        "head": re.sub(r"\s+", " ", res.text)[:200]}
            # 호비사이트는 robots.txt 자리에 HTML을 돌려준다 = 규칙 없음. 실패해도 규칙 없음으로 본다(spike와 동일).
            self._robots[origin] = Robots("" if (not res.ok or ctype_html) else res.text)
        return self._robots[origin]

    # ------------------------------------------------------------ 공개
    def get(self, url: str, kind: str = "list") -> Fetched:
        if not self._robots_for(url).allowed(url):
            self._log("SKIP", kind, "-", url, note="disallowed by robots.txt")
            raise Blocked(f"robots.txt disallows {url}")
        if kind == "detail" and self.detail_limit is not None and self.stats.by_kind["detail"] >= self.detail_limit:
            raise Blocked(f"detail limit {self.detail_limit} reached")
        res = self._send(url, kind)
        self._note_result(res)
        return res

    def _note_result(self, res: Fetched) -> None:
        if res.status == 429:
            raise SourceAborted("429 Too Many Requests")
        if res.ok or res.status == 404:     # 404는 그 상품만의 문제, 사이트 장애가 아니다
            self._consecutive_failures = 0
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= config.MAX_CONSECUTIVE_FAILURES:
            raise SourceAborted(f"{self._consecutive_failures} consecutive failures (last: {res.status or res.error})")

    def reset_breaker(self) -> None:
        """소스를 바꿀 때 호출 — 앞 소스의 연속 실패가 다음 소스를 막지 않게."""
        self._consecutive_failures = 0
