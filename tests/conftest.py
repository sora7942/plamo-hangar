"""공용 테스트 도구.

- 실제 네트워크 전송을 막는다 (CLAUDE.md Critical: 테스트에서 실제 네트워크·디스코드·Claude API 호출 금지)
- fixture 읽기, 가짜 requests 세션, 가짜 시계(요청 간격 검증), 합성 상세 페이지 생성기
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.http import HttpClient, RateLimiter  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """requests의 실제 전송을 막는다. 네트워크를 쓰는 테스트는 여기서 바로 실패한다."""
    def boom(*a, **k):
        raise AssertionError("테스트에서 실제 네트워크 요청이 시도되었습니다")
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", boom)

    # Anthropic SDK는 requests가 아니라 httpx로 나가서 위 차단에 걸리지 않는다 → 클라이언트 생성 자체를 막는다.
    # (테스트는 가짜 client를 주입해서 쓴다.)
    import anthropic

    def no_claude(*a, **k):
        raise AssertionError("테스트에서 실제 Claude 클라이언트를 만들려고 했습니다 (가짜 client를 주입하세요)")
    monkeypatch.setattr(anthropic.Anthropic, "__init__", no_claude)
    monkeypatch.setattr(anthropic.AsyncAnthropic, "__init__", no_claude)

    # 환경의 키·웹훅이 테스트에 새어 들어오지 않게 비운다. `.env`도 읽지 못하게 한다 (main()·translate.main()이 load_dotenv를 부른다).
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "DISCORD_WEBHOOK_URL", "CLAUDE_MODEL"):
        monkeypatch.delenv(var, raising=False)


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ---------------------------------------------------------------- 가짜 requests 세션
class FakeResponse:
    def __init__(self, url: str, body: str | bytes, status: int = 200, history: int = 0, final: str | None = None,
                 headers: dict | None = None):
        self.status_code = status
        self.content = body if isinstance(body, bytes) else body.encode("utf-8")
        self.url = final or url
        self.history = [None] * history
        self.headers = headers or {}


class FakeSession:
    """URL → (status, body) 표로 응답한다. 표에 없는 URL은 404. 받은 요청을 calls에 남긴다."""

    def __init__(self, routes: dict[str, str | tuple[int, str]] | None = None, *, default_status: int = 404):
        self.routes = dict(routes or {})
        self.default_status = default_status
        self.calls: list[dict] = []

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        r = self.routes.get(url)
        if callable(r):
            r = r(url)
        if r is None:
            return FakeResponse(url, "not found", self.default_status)
        if isinstance(r, FakeResponse):
            return r
        if isinstance(r, tuple):
            return FakeResponse(url, r[1], r[0])
        return FakeResponse(url, r)


class FakeClock:
    """RateLimiter에 주입하는 가짜 시계: sleep하면 시간이 그만큼 흐른다."""

    def __init__(self):
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def advance(self, s):
        self.t += s


def make_client(routes=None, **kw) -> tuple[HttpClient, FakeSession, FakeClock]:
    sess = FakeSession(routes)
    fc = FakeClock()
    client = HttpClient(session=sess, limiter=RateLimiter(1.2, clock=fc.clock, sleep=fc.sleep), **kw)
    return client, sess, fc


ROBOTS_HTML = "<!doctype html><html><body>not robots</body></html>"   # 호비사이트는 robots.txt 자리에 HTML을 돌려준다


# ---------------------------------------------------------------- 합성 페이지 (파이프라인 테스트용)
def schedule_html(cards: list[dict]) -> str:
    """cards: [{"num": "01_7001", "title": "...", "price": "1,100円(税10%込)", "date": "2026年10月17日 (土)", "tag": None|"-online"|"-gbase"|"-sidef", "pb": bool}]"""
    parts = ['<html><body><div class="pg-calendar__inner"><div class="p-card__wrap">']
    for c in cards:
        href = f"https://p-bandai.jp/item/{c['num']}/" if c.get("pb") else f"https://bandai-hobby.net/item/{c['num']}/"
        tag = f'<span class="p-card__tag {c["tag"]}">tag</span>' if c.get("tag") else ""
        parts.append(
            f'<a class="c-card p-card -landscape" href="{href}"><div class="p-card__img">'
            f'<img src="https://d3bk8pkqsprcvh.cloudfront.net/x.jpg?Expires=1&amp;Signature=zz"/></div>'
            f'<div class="p-card__explain">{tag}<div class="p-card__tit">{c["title"]}</div>'
            f'<div class="p-card__under"><div class="p-card__price">{c.get("price", "1,100円(税10%込)")}</div>'
            f'<div class="p-card_date">{c.get("date", "2026年10月")}</div></div></div></a>')
    parts.append("</div></div></body></html>")
    return "".join(parts)


def detail_html(title: str, brand_keys: list[str], *, price: str = "1,320 円(税10%込)", release: str = "2026年10月24日 (土)",
                images: list[str] | None = None, series: tuple[str, str] | None = None) -> str:
    links = "".join(f'<li class="p-card__link"><a class="p-card__flat" href="https://bandai-hobby.net/brand/{k}/">'
                    f'<span class="p-card__flatTit">{k}</span></a></li>' for k in brand_keys)
    if series:
        links += (f'<li class="p-card__link"><a class="p-card__flat" href="https://bandai-hobby.net/series/{series[0]}/">'
                  f'<span class="p-card__flatTit">{series[1]}</span></a></li>')
    imgs = "".join(f'<div class="swiper-slide"><img src="{u}"/></div>' for u in (images or []))
    return (f'<html><body><h1 class="p-heading__h1-product">{title}</h1>'
            f'<dl class="pg-products__detail"><dt>価格</dt><dd>{price}</dd><dt>発売日</dt><dd>{release}</dd></dl>'
            f'<ul>{links}</ul><div class="pg-products__contentLeft">{imgs}</div></body></html>')


# ---------------------------------------------------------------- 합성 조이하비 (파이프라인 테스트용, UTF-8 문자열 — EUC-KR 디코딩은 test_http가 실제 응답 바이트로 검증한다)
JOY_ROBOTS = "User-agent: *\nDisallow: /admin/\n"
JOY_BOARD = "https://www.joyhobby.co.kr/mall/board_list.asp?siteid=joyhobby&BoardCode=notice"
JOY_POST = "https://www.joyhobby.co.kr/mall/board_view.asp?SiteID=joyhobby&BoardCode=notice&B_iID={id}"


def joy_board_html(rows: list[tuple[str, str, str]], pinned: list[tuple[str, str]] | None = None) -> str:
    """rows: [(글번호, 'YYYY-MM-DD', 제목)], pinned: 쪽마다 반복되는 고정 공지 [(글번호, 제목)]."""
    out = ["<html><body><table>"]
    for pid, title in pinned or []:
        out.append(f'<tr><td><a href="/mall/Board_View.asp?SiteID=joyhobby&amp;BoardCode=notice&amp;B_iID={pid}&amp;nowPage=1&amp;Notice=true&amp;">{title}</a></td>'
                   f'<td>조이하비</td><td>2024-01-01</td></tr>')
    for pid, d, title in rows:
        out.append(f'<tr><td width="460px">  프라모델  <a href="/mall/Board_View.asp?SiteID=joyhobby&amp;BoardCode=notice&amp;B_iID={pid}&amp;nowPage=1&amp;">{title}</a></td>'
                   f'<td>조이하비</td><td>{d}</td></tr>')
    out.append("</table></body></html>")
    return "".join(out)


def joy_post_html(title: str, intro: str, items: list[tuple[str, str, str]]) -> str:
    """items: [(상품코드, 상품명, 가격 문자열)] — 코드/이름/가격이 줄마다 하나씩 나오는 본문."""
    body = "".join(f"<p>{c}</p><p>{n}</p><p>{p}</p>" for c, n, p in items)
    return (f'<html><body><table><tr><td class="Board_View_top">[ 프라모델 ] {title}</td></tr>'
            f'<tr><td><p>이 름: 조이하비</p><p>{intro}</p>{body}</td></tr></table></body></html>')
