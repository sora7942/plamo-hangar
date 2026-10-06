"""crawler/http.py — 요청 간격·robots·timeout·UA·연속 실패 중단. 네트워크 없이 가짜 세션으로."""
import pytest
import requests

from conftest import ROBOTS_HTML, FakeSession, make_client, fixture_text
from crawler import config
from crawler.http import Blocked, HttpClient, RateLimiter, Robots, SourceAborted

HOBBY = "https://bandai-hobby.net"


def test_rate_limiter_enforces_min_interval_between_starts():
    from conftest import FakeClock
    fc = FakeClock()
    rl = RateLimiter(1.2, clock=fc.clock, sleep=fc.sleep)
    starts = []
    for _ in range(4):
        rl.wait()
        starts.append(fc.t)
        fc.advance(0.3)                      # 요청 자체가 0.3초 걸렸다고 가정
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= 1.2 - 1e-9 for g in gaps)


def test_rate_limiter_does_not_sleep_when_enough_time_passed():
    from conftest import FakeClock
    fc = FakeClock()
    rl = RateLimiter(1.2, clock=fc.clock, sleep=fc.sleep)
    rl.wait()
    fc.advance(5)
    rl.wait()
    assert fc.sleeps == []


def test_rate_limiter_survives_sleep_that_wakes_early():
    """Windows처럼 sleep이 일찍 깨는 환경: 시계로 확인될 때까지 다시 기다린다."""
    from conftest import FakeClock
    fc = FakeClock()

    def early_sleep(s):                      # 요청한 시간의 90%만 흐른다
        fc.sleeps.append(s)
        fc.t += s * 0.9
    rl = RateLimiter(1.2, clock=fc.clock, sleep=early_sleep)
    starts = []
    for _ in range(5):
        rl.wait()
        starts.append(fc.t)
    assert all(b - a >= 1.2 for a, b in zip(starts, starts[1:]))


def test_request_log_timestamp_is_request_start_not_completion(tmp_path):
    """응답이 느려도 로그의 시각 간격은 시작~시작 간격(>= 1.2초)이어야 한다."""
    import datetime as dt
    from conftest import FakeClock
    log = tmp_path / "req.log"
    fc = FakeClock()

    latencies = iter([0.0, 5.0, 0.0])        # robots 즉시, 첫 요청 5초, 둘째 즉시 — 완료 시각 간격은 시작 간격과 달라진다

    class SlowSession(FakeSession):
        def get(self, url, **kw):
            fc.advance(next(latencies))
            return super().get(url, **kw)
    from crawler import http as http_mod
    orig = http_mod.now_kst
    http_mod.now_kst = lambda: dt.datetime(2026, 1, 1, tzinfo=config.KST) + dt.timedelta(seconds=fc.t)   # 가짜 시계에 맞춘 벽시계
    try:
        client = HttpClient(session=SlowSession({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/a": "a", f"{HOBBY}/b": "b"}),
                            limiter=RateLimiter(1.2, clock=fc.clock, sleep=fc.sleep), log_path=log)
        client.get(f"{HOBBY}/a")
        client.get(f"{HOBBY}/b")
    finally:
        http_mod.now_kst = orig
    stamps = [dt.datetime.fromisoformat(l.split("	")[0]) for l in log.read_text(encoding="utf-8").splitlines()]
    assert all((b - a).total_seconds() >= 1.2 for a, b in zip(stamps, stamps[1:]))


def test_get_sends_timeout_and_browser_user_agent():
    client, sess, _ = make_client({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/a": "ok"})
    res = client.get(f"{HOBBY}/a")
    assert res.ok and res.text == "ok"
    for call in sess.calls:                                   # robots 요청 포함 모든 요청
        assert call["timeout"] == config.TIMEOUT == 20
        assert "Mozilla/5.0" in call["headers"]["User-Agent"]


def test_every_request_goes_through_the_limiter_with_min_gap():
    client, sess, fc = make_client({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/a": "a", f"{HOBBY}/b": "b"})
    client.get(f"{HOBBY}/a")
    client.get(f"{HOBBY}/b")
    assert len(sess.calls) == 3                              # robots + a + b
    assert client.stats.min_gap is not None and client.stats.requests == 3


def test_html_robots_means_no_rules_and_robots_fetched_once():
    client, sess, _ = make_client({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/a": "a", f"{HOBBY}/b": "b"})
    client.get(f"{HOBBY}/a")
    client.get(f"{HOBBY}/b")
    assert [c["url"] for c in sess.calls].count(f"{HOBBY}/robots.txt") == 1


def test_robots_disallow_blocks_request():
    client, sess, _ = make_client({f"{HOBBY}/robots.txt": "User-agent: *\nDisallow: /admin/\n", f"{HOBBY}/admin/x": "x"})
    with pytest.raises(Blocked):
        client.get(f"{HOBBY}/admin/x")
    assert all(c["url"].endswith("/robots.txt") for c in sess.calls)      # 막힌 경로는 요청하지 않았다


def test_robots_wildcard_and_end_anchor_and_longest_rule():
    rb = Robots(fixture_text("robots-pbandai-global.txt"))
    assert not rb.allowed("https://p-bandai.com/us/search?limit=20&sortType=NewArrival")
    assert rb.allowed("https://p-bandai.com/us/")
    rb2 = Robots("User-agent: *\nDisallow: /a/\nAllow: /a/ok$\n")
    assert rb2.allowed("https://x/a/ok") and not rb2.allowed("https://x/a/ok2")


def test_detail_limit_blocks_extra_detail_requests():
    routes = {f"{HOBBY}/robots.txt": ROBOTS_HTML, **{f"{HOBBY}/item/{i}/": "d" for i in "abc"}}
    client, sess, _ = make_client(routes, detail_limit=2)
    client.get(f"{HOBBY}/item/a/", kind="detail")
    client.get(f"{HOBBY}/item/b/", kind="detail")
    with pytest.raises(Blocked):
        client.get(f"{HOBBY}/item/c/", kind="detail")
    assert client.stats.by_kind["detail"] == 2


def test_consecutive_failures_abort_source_and_404_does_not_count():
    routes = {f"{HOBBY}/robots.txt": ROBOTS_HTML}
    routes.update({f"{HOBBY}/e{i}": (500, "err") for i in range(10)})
    client, _, _ = make_client(routes)
    for i in range(config.MAX_CONSECUTIVE_FAILURES - 1):
        assert not client.get(f"{HOBBY}/e{i}").ok
    with pytest.raises(SourceAborted):
        client.get(f"{HOBBY}/e{config.MAX_CONSECUTIVE_FAILURES}")
    client.reset_breaker()
    for i in range(10):                                       # 404는 사이트 장애가 아니라 그 페이지만의 문제
        client.get(f"{HOBBY}/missing{i}")


def test_429_aborts_immediately():
    client, _, _ = make_client({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/x": (429, "slow down")})
    with pytest.raises(SourceAborted):
        client.get(f"{HOBBY}/x")


def test_network_error_is_returned_not_raised_and_logged_without_url_detail(tmp_path):
    class Boom(FakeSession):
        def get(self, url, **kw):
            if url.endswith("/robots.txt"):
                return super().get(url, **kw)
            raise requests.ConnectionError("secret-detail https://hooks.example/abc")
    from conftest import FakeClock
    fc = FakeClock()
    log = tmp_path / "req.log"
    client = HttpClient(session=Boom({f"{HOBBY}/robots.txt": ROBOTS_HTML}),
                        limiter=RateLimiter(1.2, clock=fc.clock, sleep=fc.sleep), log_path=log)
    res = client.get(f"{HOBBY}/x")
    assert not res.ok and res.error == "ConnectionError"
    assert "secret-detail" not in log.read_text(encoding="utf-8")


def test_request_log_format(tmp_path):
    log = tmp_path / "sub" / "req.log"
    client, _, _ = make_client({f"{HOBBY}/robots.txt": ROBOTS_HTML, f"{HOBBY}/a": "a"}, log_path=log)
    client.get(f"{HOBBY}/a", kind="schedule")
    rows = [line.split("\t") for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and all(len(r) == 8 for r in rows)
    ts, method, kind, status, redirects, url, final, note = rows[-1]
    assert ts.endswith("+09:00") and method == "GET" and kind == "schedule" and status == "200" and url == f"{HOBBY}/a"
