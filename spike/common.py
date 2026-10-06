"""0단계 spike 공용 유틸.

- 모든 요청(requests / Playwright 이동)은 RateLimiter(>= MIN_INTERVAL 초)를 통과한다
- robots.txt를 먼저 받아 허용 여부를 확인하고, 막힌 경로는 열지 않는다
- 같은 URL은 캐시에서 읽어 재요청하지 않는다
- 상세 페이지는 사이트별 상한 + 전체 30개 상한을 지킨다 (budget.json)
- 모든 요청은 requests.log에 남긴다 (간격·상태코드·리다이렉트 증빙)
- 이미지·미디어·폰트는 내려받지 않는다 (Playwright route로 차단)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / os.environ.get("SPIKE_OUT", "spike/out")
ENV = os.environ.get("SPIKE_ENV", "local")  # local | actions
# local이면 tests/fixtures에 저장, actions이면 artifact 폴더 안에만 저장
FIXTURES = ROOT / "tests" / "fixtures" if ENV == "local" else OUT / "fixtures"
CACHE = OUT / "cache"
for _d in (OUT, FIXTURES, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

KST = timezone(timedelta(hours=9))
MIN_INTERVAL = 1.2          # 요청 간 최소 간격(초). 지시사항은 1초 이상
TIMEOUT_S = 20              # SPEC 5장: timeout 20초
DETAIL_TOTAL_CAP = 30       # 실행당 상세 페이지 총 상한 (지시사항)
# 합계 30: 호비 18 / P-반다이 JP 3 (지역 차단 확인용) / P-반다이 해외 3 (대안 검증) / 조이하비 6
DETAIL_CAPS = {"hobby": 18, "pbandai": 3, "pbandai_global": 3, "joyhobby": 6}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

SITES = {
    "hobby": "https://bandai-hobby.net",
    "pbandai": "https://p-bandai.jp",
    "pbandai_global": "https://p-bandai.com",   # 해외 P-반다이 (JP 차단 시 대안 후보)
    "joyhobby": "https://www.joyhobby.co.kr",
}
ROBOTS_NAMES = {"hobby": "bandai-hobby", "pbandai": "pbandai", "pbandai_global": "pbandai-global",
                "joyhobby": "joyhobby"}

LOG = OUT / "requests.log"
BUDGET = OUT / "budget.json"


class Blocked(Exception):
    """robots.txt 차단 또는 예산 초과로 요청하지 않음."""


# ---------------------------------------------------------------- 로그/간격
_last = 0.0
_start_wall: datetime | None = None   # 마지막 요청의 "시작" 시각 (로그 간격 증빙용)


def _wait():
    global _last, _start_wall
    gap = time.monotonic() - _last
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last = time.monotonic()
    _start_wall = datetime.now(KST)


def log_request(method: str, url: str, status, final_url: str = "", redirects: int = 0,
                kind: str = "", note: str = ""):
    # SKIP(요청 안 함)은 현재 시각, 나머지는 요청 시작 시각을 기록 → 로그의 간격 = 시작~시작 간격
    when = datetime.now(KST) if method == "SKIP" or _start_wall is None else _start_wall
    ts = when.isoformat(timespec="milliseconds")
    line = "\t".join([ts, method, kind, str(status), str(redirects), url, final_url or "", note])
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"[req] {status} {kind:8} {url}" + (f" -> {final_url}" if final_url and final_url != url else ""))


# ---------------------------------------------------------------- 예산
def _budget() -> dict:
    if BUDGET.exists():
        return json.loads(BUDGET.read_text(encoding="utf-8"))
    return {"detail": {}, "urls": []}


def _save_budget(b: dict):
    BUDGET.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")


def detail_used(site: str | None = None) -> int:
    d = _budget()["detail"]
    return sum(d.values()) if site is None else d.get(site, 0)


def _spend_detail(site: str, url: str):
    b = _budget()
    if url in b["urls"]:
        return
    if sum(b["detail"].values()) >= DETAIL_TOTAL_CAP:
        raise Blocked(f"detail total cap {DETAIL_TOTAL_CAP} reached")
    if b["detail"].get(site, 0) >= DETAIL_CAPS[site]:
        raise Blocked(f"detail cap for {site} ({DETAIL_CAPS[site]}) reached")
    b["detail"][site] = b["detail"].get(site, 0) + 1
    b["urls"].append(url)
    _save_budget(b)


# ---------------------------------------------------------------- robots.txt
class Robots:
    """Google 방식(와일드카드 *, $, 가장 긴 규칙 우선, 동률이면 Allow) 최소 구현.

    urllib.robotparser는 * / $ 를 못 읽어서 직접 구현했다. 원문 Disallow 줄은
    사람이 같이 대조한다 (report.md에 원문 파일명을 적는다).
    """

    def __init__(self, text: str):
        self.rules: list[tuple[str, str]] = []   # (allow|disallow, pattern) for UA '*'
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
        """매칭되면 패턴 길이(우선순위), 아니면 -1."""
        end = pattern.endswith("$")
        pat = pattern[:-1] if end else pattern
        rx = "".join(".*" if c == "*" else re.escape(c) for c in pat)
        rx = "^" + rx + ("$" if end else "")
        return len(pattern) if re.match(rx, path) else -1

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        path = u.path or "/"
        if u.query:
            path += "?" + u.query
        best, verdict = -1, True
        for kind, pat in self.rules:
            n = self._match(pat, path)
            if n > best or (n == best and kind == "allow"):
                best, verdict = n, (kind == "allow")
        return verdict


_robots: dict[str, Robots] = {}


def load_robots(site: str) -> Robots:
    """robots.txt 원문을 받아 out/ 과 fixtures/ 에 저장하고 판정기를 돌려준다."""
    if site in _robots:
        return _robots[site]
    name = ROBOTS_NAMES[site]
    out_f = OUT / f"robots-{name}.txt"
    if out_f.exists():
        text = out_f.read_text(encoding="utf-8")
    else:
        url = SITES[site] + "/robots.txt"
        _wait()
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_S, allow_redirects=True)
            log_request("GET", url, r.status_code, r.url, len(r.history), "robots")
            ctype = r.headers.get("content-type", "")
            if r.status_code == 200 and "html" not in ctype.lower():
                text = r.content.decode("utf-8", "replace")   # r.text는 charset 없을 때 latin-1로 깨짐
            else:
                text = f"# (spike) robots.txt 없음 또는 비정상: status={r.status_code} content-type={ctype} final={r.url}\n"
        except requests.RequestException as e:
            log_request("GET", url, "ERR", "", 0, "robots", repr(e)[:120])
            text = f"# (spike) robots.txt 요청 실패: {e!r}\n"
        out_f.write_text(text, encoding="utf-8")
        (FIXTURES / f"robots-{name}.txt").write_text(text, encoding="utf-8")
    rb = Robots(text)
    _robots[site] = rb
    return rb


def check_allowed(site: str, url: str):
    if not load_robots(site).allowed(url):
        log_request("SKIP", url, "-", "", 0, "robots", "disallowed by robots.txt")
        raise Blocked(f"robots.txt disallows {url}")


# ---------------------------------------------------------------- 캐시
def _key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def cache_get(url: str):
    f = CACHE / f"{_key(url)}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return None


def cache_put(url: str, data: dict):
    (CACHE / f"{_key(url)}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- requests
def http_get(site: str, url: str, kind: str = "list", max_redirects: int = 8) -> dict:
    """requests 한 번 (참고용: 일반 HTTP로 열리는지 확인)."""
    check_allowed(site, url)
    if kind == "detail":
        _spend_detail(site, url)
    s = requests.Session()
    s.max_redirects = max_redirects
    s.headers["User-Agent"] = UA
    _wait()
    try:
        r = s.get(url, timeout=TIMEOUT_S, allow_redirects=True)
        log_request("GET", url, r.status_code, r.url, len(r.history), f"req-{kind}")
        return {"ok": True, "status": r.status_code, "final": r.url, "redirects": len(r.history),
                "html": r.text, "ctype": r.headers.get("content-type", "")}
    except requests.TooManyRedirects:
        log_request("GET", url, "LOOP", "", max_redirects, f"req-{kind}", f"TooManyRedirects>{max_redirects}")
        return {"ok": False, "status": "redirect-loop", "final": "", "redirects": max_redirects, "html": ""}
    except requests.RequestException as e:
        log_request("GET", url, "ERR", "", 0, f"req-{kind}", repr(e)[:120])
        return {"ok": False, "status": "error", "final": "", "redirects": 0, "html": "", "error": repr(e)}


# ---------------------------------------------------------------- Playwright
_PW: dict = {"pw": None, "br": None}


def _launch():
    """Sync API는 프로세스당 하나만 가능 → 브라우저는 공유하고 Browser마다 컨텍스트만 따로 만든다."""
    if _PW["pw"] is None:
        from playwright.sync_api import sync_playwright
        _PW["pw"] = sync_playwright().start()
        _PW["br"] = _PW["pw"].chromium.launch(headless=True)
    return _PW["br"]


def shutdown():
    if _PW["pw"] is not None:
        try:
            _PW["br"].close()
        finally:
            _PW["pw"].stop()
            _PW["pw"] = _PW["br"] = None


class Browser:
    """Playwright 컨텍스트 래퍼. 이미지·미디어·폰트는 차단하고 DOM만 받는다."""

    def __init__(self, locale: str = "ja-JP", block_assets: bool = True):
        self._b = _launch()
        self.ctx = self._b.new_context(
            user_agent=UA, locale=locale, viewport={"width": 1280, "height": 900},
            extra_http_headers={"Accept-Language": f"{locale},{locale.split('-')[0]};q=0.9,en;q=0.5"})
        if block_assets:
            self.ctx.route("**/*", lambda route: route.abort()
                           if route.request.resource_type in ("image", "media", "font")
                           else route.continue_())
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(TIMEOUT_S * 1000)
        self.xhr: list[dict] = []
        self.json_bodies: dict[str, str] = {}
        self.page.on("response", self._on_response)

    def _on_response(self, resp):
        try:
            rt = resp.request.resource_type
            if rt in ("xhr", "fetch"):
                ctype = resp.headers.get("content-type", "")
                self.xhr.append({"url": resp.url, "status": resp.status, "ctype": ctype})
                if "json" in ctype and resp.status == 200:
                    body = resp.text()
                    if len(body) < 600_000:
                        self.json_bodies[resp.url] = body
        except Exception:
            pass

    def goto(self, site: str, url: str, kind: str = "list", wait_ms: int = 1500,
             use_cache: bool = True) -> dict:
        """페이지 이동 + 렌더링된 DOM 반환. 캐시 hit면 요청하지 않는다."""
        if use_cache:
            c = cache_get(url)
            if c:
                print(f"[cache] {url}")
                return c
        check_allowed(site, url)
        if kind == "detail":
            _spend_detail(site, url)
        self.xhr, self.json_bodies = [], {}
        _wait()
        status, redirects, final = "ERR", 0, ""
        try:
            resp = self.page.goto(url, wait_until="domcontentloaded")
            self.page.wait_for_timeout(wait_ms)
            status = resp.status if resp else "none"
            redirects = 0
            req = resp.request if resp else None
            while req is not None and req.redirected_from is not None:
                redirects += 1
                req = req.redirected_from
            final = self.page.url
            html = self.page.content()
            title = self.page.title()
            err = ""
        except Exception as e:  # timeout 등
            html, title, err = "", "", repr(e)[:200]
        log_request("GET", url, status, final, redirects, f"pw-{kind}", err)
        data = {"url": url, "final": final, "status": status, "redirects": redirects,
                "title": title, "html": html, "xhr": list(self.xhr), "error": err,
                "fetched_at": datetime.now(KST).isoformat(timespec="seconds")}
        if not err:
            cache_put(url, data)
        return data

    def close(self):
        self.ctx.close()


# ---------------------------------------------------------------- fixture
def save_fixture(name: str, content: str) -> Path:
    p = FIXTURES / name
    p.write_text(content, encoding="utf-8")
    print(f"[fixture] {p.relative_to(ROOT)} ({len(content):,} bytes)")
    return p


def summary_write(name: str, data) -> Path:
    p = OUT / name
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
