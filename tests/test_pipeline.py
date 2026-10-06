"""pipeline.run() 전체 흐름 — 가짜 호비사이트(합성 HTML)로 임시 폴더에서 돌린다. 네트워크·디스코드·Claude 호출 없음."""
import json
from datetime import datetime, timedelta

import pytest

from conftest import ROBOTS_HTML, detail_html, make_client, schedule_html
from crawler import config
from crawler.pipeline import Options, run
from crawler.sources.hobby_schedule import schedule_url
from schema_check import check_dir

HOBBY = "https://bandai-hobby.net"
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=config.KST)
AKAMAI = "https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"
SIGNED = "https://bandai-a.akamaihd.net/bc/img/model/xl/2_1.jpg?Expires=1&Signature=abc"
DATA_FILES = {"catalog-gunpla.json", "catalog-girl.json", "catalog-pending.json", "feed.json", "meta.json"}


def c(num, title, date="2026年10月24日 (土)", **kw):
    return {"num": num, "title": title, "date": date, **kw}


class World:
    """가짜 호비사이트: 월별 일정·브랜드 목록·상세를 합성 HTML로 돌려준다."""

    def __init__(self):
        self.schedule = {
            "2026-09": [c("01_6001", "HG 1/144 昔の機体", "2026年09月12日 (土)")],
            "2026-10": [c("01_7001", "HG 1/144 テスト機A"),
                        c("01_7002", "ドラゴンクエストねんどモンスターズ スライム", "2026年10月17日 (土)"),
                        c("item-1000250001", "ＭＧ 1/100 テストＭ", "2026年10月", tag="-online", pb=True)],
            "2026-11": [c("01_7003", "RG 1/144 テストR", "2026年11月14日 (土)")],
        }
        self.brand = {("30ms", 1): [c("01_7101", "ミャスティ[カラーC]", "2026年12月19日 (土)"),
                                    c("01_7102", "ディルミア", "2027年03月")],
                      ("30ms", 2): [c("01_7103", "古いシスター", "2025年01月18日 (土)")]}
        self.details = {
            "01_6001": detail_html("HG 1/144 昔の機体", ["hg"], release="2026年09月12日 (土)", images=[AKAMAI]),
            "01_7001": detail_html("HG 1/144 テスト機A", ["hg"], images=[AKAMAI, SIGNED], series=("g-witch", "水星の魔女")),
            "01_7002": detail_html("ドラゴンクエストねんどモンスターズ スライム", ["claymonsters"]),
            "01_7003": detail_html("RG 1/144 テストR", ["rg"], release="2026年11月14日 (土)"),
            "01_7101": detail_html("30MS ミャスティ[カラーC]", ["30ms"], release="2026年12月19日 (土)"),
            "01_7102": detail_html("30MS ディルミア", ["30ms"], release="2027年03月"),
            "01_7103": detail_html("30MS 古いシスター", ["30ms"], release="2025年01月18日 (土)"),
        }
        self.fail_schedule = False

    def _brand_page(self, key, page):
        cards = self.brand.get((key, page), [])
        last = max([p for (k, p) in self.brand if k == key] or [1])
        pager = "".join(f'<a class="c-archives__pagination-list-item-link" href="./?p={p}">{p}</a>' for p in range(2, last + 1))
        return schedule_html(cards).replace("</body>", f"{pager}</body>")

    def routes(self):
        r = {f"{HOBBY}/robots.txt": ROBOTS_HTML}
        for ym in {f"2026-{m:02d}" for m in range(1, 13)} | {"2027-01", "2027-02"}:
            r[schedule_url(ym)] = (lambda u, ym=ym: (500, "boom") if self.fail_schedule else schedule_html(self.schedule.get(ym, [])))
        for key in config.GIRL_BRANDS:
            for page in range(1, 4):
                url = f"{HOBBY}/brand/{key}/" if page == 1 else f"{HOBBY}/brand/{key}/?p={page}"
                r[url] = (lambda u, key=key, page=page: self._brand_page(key, page))
        for num, html in self.details.items():
            r[f"{HOBBY}/item/{num}/"] = html
        return r


def go(world, tmp_path, opts=None, *, now=NOW, **kw):
    client, sess, fc = make_client(world.routes())
    lines = []
    opts = opts or Options(data_dir=tmp_path)
    opts.data_dir = tmp_path
    res = run(opts, client, now=now, out=lines.append, **kw)
    return res, client, sess, lines


def read(tmp_path, name):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


def kinds(sess):
    return [c["url"] for c in sess.calls]


# ---------------------------------------------------------------- 첫 실행(최초 채우기)
def test_first_bootstrap_run_builds_all_files_in_spec_format(tmp_path):
    w = World()
    posted = []
    res, client, sess, lines = go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=2, max_backlog=3),
                                  post=lambda *a, **k: posted.append(a))
    assert {p.name for p in tmp_path.iterdir()} == DATA_FILES                    # collection.json·photos는 만들지도 건드리지도 않는다
    assert check_dir(tmp_path) == []                                              # SPEC 4장 형식
    cat = {**{i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json", "catalog-pending.json")
              for i in read(tmp_path, f)["items"]}}
    assert set(cat) == {"bh-01_6001", "bh-01_7001", "bh-01_7002", "bh-01_7003", "pb-item-1000250001",
                        "bh-01_7101", "bh-01_7102", "bh-01_7103"}
    assert res["newItems"] == 8 and posted == []                                  # 첫 실행은 알림 없음 (웹훅이 있어도)


def test_detail_requests_respect_new_plus_backlog_caps_and_min_gap(tmp_path):
    w = World()
    res, client, sess, _ = go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=2, max_backlog=3))
    assert client.stats.by_kind["detail"] == 5 <= 2 + 3
    assert res["meta"]["crawl"]["backlog"] == 2                                   # bh- 7개 중 5개 처리, 2개 남음 (pb 카드는 상세 없음)
    assert client.stats.min_gap >= 1.2 - 1e-9 and res["meta"]["stats"]["minGapSec"] >= 1.2
    assert all(call["timeout"] == 20 for call in sess.calls)


def test_provisional_items_are_searchable_before_details_and_pending_goes_to_pending_file(tmp_path):
    go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=0, max_backlog=0))   # 상세 0개
    gun = {i["id"]: i for i in read(tmp_path, "catalog-gunpla.json")["items"]}
    assert {"bh-01_7001", "bh-01_6001", "bh-01_7003", "pb-item-1000250001"} <= set(gun)
    assert gun["bh-01_7001"]["detailAt"] is None and gun["bh-01_7001"]["nameJa"] == "HG 1/144 テスト機A"
    assert gun["bh-01_7001"]["grade"] == "HG" and gun["bh-01_7001"]["scale"] == "1/144" and gun["bh-01_7001"]["priceJpy"] == 1100
    assert [i["id"] for i in read(tmp_path, "catalog-pending.json")["items"]] == ["bh-01_7002"]
    assert {i["id"] for i in read(tmp_path, "catalog-girl.json")["items"]} == {"bh-01_7101", "bh-01_7102", "bh-01_7103"}


def test_signed_urls_never_reach_any_output_file(tmp_path):
    go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"))
    for name in DATA_FILES:
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "Expires=" not in text and "Signature=" not in text and "cloudfront" not in text
    it = next(i for i in read(tmp_path, "catalog-gunpla.json")["items"] if i["id"] == "bh-01_7001")
    assert it["images"] == [AKAMAI] and it["series"] == "水星の魔女" and it["detailAt"] is not None


def test_feed_contains_upcoming_items_only_with_new_and_pb_new_types(tmp_path):
    go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"))
    feed = read(tmp_path, "feed.json")["items"]
    ids = {f["id"]: f for f in feed}
    assert set(ids) == {"bh-new-01_7001", "bh-new-01_7003", "pb-new-item-1000250001", "bh-new-01_7101", "bh-new-01_7102"}
    assert ids["pb-new-item-1000250001"]["type"] == "pb-new" and ids["pb-new-item-1000250001"]["image"] is None
    assert ids["bh-new-01_7001"]["image"] == AKAMAI and ids["bh-new-01_7001"]["type"] == "new"
    assert "bh-new-01_6001" not in ids and "bh-new-01_7103" not in ids          # 이미 지난 발매는 피드에 넣지 않는다
    assert all(f["added"] == "2026-10-06T09:00:00+09:00" for f in feed)


def test_non_target_brand_is_excluded_and_remembered(tmp_path):
    res, *_ = go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"))
    pend = read(tmp_path, "catalog-pending.json")
    assert pend["items"] == [] and pend["excluded"] == {"bh-01_7002": "brand:claymonsters"}
    assert res["details"]["excluded"] == 1 and res["meta"]["crawl"]["counts"]["excluded"] == 1


def test_cursors_make_second_run_skip_past_months_and_extra_brand_pages(tmp_path):
    w = World()
    res1, *_ = go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    assert res1["meta"]["crawl"]["scheduleFrom"] == "2026-09"
    assert res1["meta"]["crawl"]["girlBrandsDone"] == config.GIRL_BRANDS
    res2, client2, sess2, _ = go(w, tmp_path, Options(), now=NOW + timedelta(days=1))
    urls = kinds(sess2)
    assert schedule_url("2026-09") not in urls                                    # 과거 달은 다시 받지 않는다
    assert not any("?p=" in u for u in urls)                                      # 걸프라는 1쪽만
    assert schedule_url("2026-10") in urls and schedule_url("2027-01") in urls   # 이번 달 ~ +3개월
    assert res2["meta"]["crawl"]["scheduleFrom"] == "2026-09"


def test_bootstrap_resumes_where_it_stopped_when_a_past_month_fails(tmp_path):
    w = World()
    client, sess, _ = make_client(w.routes())
    orig = sess.routes[schedule_url("2026-08")]
    sess.routes[schedule_url("2026-08")] = (500, "boom")
    run(Options(bootstrap=True, from_month="2026-07", data_dir=tmp_path), client, now=NOW, out=lambda s: None)
    meta = read(tmp_path, "meta.json")
    assert meta["crawl"]["scheduleFrom"] == "2026-09"                              # 2026-08에서 막혀 09까지만 끝난 것으로 기록
    assert meta["sources"]["hobby_schedule"]["ok"] is False and "2026-08" in meta["sources"]["hobby_schedule"]["error"]
    sess.routes[schedule_url("2026-08")] = orig                                    # 복구 후 다시 실행하면 08부터 이어서
    client2, sess2, _ = make_client(sess.routes)
    run(Options(bootstrap=True, from_month="2026-07", data_dir=tmp_path), client2, now=NOW, out=lambda s: None)
    assert read(tmp_path, "meta.json")["crawl"]["scheduleFrom"] == "2026-07"
    urls2 = [c["url"] for c in sess2.calls]
    assert schedule_url("2026-09") not in urls2                                    # 이미 끝난 달(커서 이후)은 다시 받지 않는다
    assert schedule_url("2026-08") in urls2 and schedule_url("2026-07") in urls2


# ---------------------------------------------------------------- 두 번째 실행
def test_second_run_notifies_only_new_items_keeps_added_and_finishes_backlog(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/SECRET")
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=2, max_backlog=3))
    feed1 = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}
    w.schedule["2026-10"].append(c("01_7004", "HG 1/144 新機体", "2026年10月31日 (土)"))
    w.details["01_7004"] = detail_html("HG 1/144 新機体", ["hg"], release="2026年10月31日 (土)", images=[AKAMAI])
    posted = []
    res, client, sess, lines = go(w, tmp_path, Options(), now=NOW + timedelta(days=1),
                                  post=lambda url, json=None, timeout=None: posted.append(json) or type("R", (), {"status_code": 204})())
    assert res["newItems"] == 1 and res["feedAdded"] == 1 and res["notified"] == 1
    assert len(posted) == 1 and [e["title"] for e in posted[0]["embeds"]] == ["HG 1/144 新機体"]
    feed2 = {f["id"]: f for f in read(tmp_path, "feed.json")["items"]}
    assert set(feed2) == set(feed1) | {"bh-new-01_7004"}
    assert all(feed2[k]["added"] == feed1[k]["added"] for k in feed1)             # added는 바뀌지 않는다
    assert res["meta"]["crawl"]["backlog"] == 0                                    # 남은 밀린 상품이 이번에 모두 처리됨
    assert "SECRET" not in "\n".join(lines)
    assert check_dir(tmp_path) == []


def test_unchanged_world_second_run_changes_nothing(tmp_path):
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    before = {n: (tmp_path / n).read_bytes() for n in DATA_FILES - {"meta.json"}}
    res, *_ = go(w, tmp_path, Options(), now=NOW + timedelta(days=1))
    assert res["newItems"] == 0 and res["feedAdded"] == 0 and res["details"] == {"new": 0, "backlog": 0, "excluded": 0, "failed": 0}
    assert {n: (tmp_path / n).read_bytes() for n in before} == before             # 카탈로그·피드는 바이트까지 그대로 (updatedAt 포함)
    assert read(tmp_path, "meta.json")["since"] == "2026-10-06"                    # since는 첫 실행일 고정


def test_excluded_item_details_are_never_requested_again(tmp_path):
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    _, _, sess, _ = go(w, tmp_path, Options(), now=NOW + timedelta(days=1))
    assert f"{HOBBY}/item/01_7002/" not in kinds(sess)


# ---------------------------------------------------------------- 소스 격리·옵션
def test_failed_schedule_does_not_stop_brand_and_detail_stages(tmp_path):
    w = World()
    w.fail_schedule = True
    res, *_ = go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    src = res["meta"]["sources"]
    assert src["hobby_schedule"]["ok"] is False and src["hobby_schedule"]["error"]
    assert src["hobby_brand"]["ok"] is True and src["hobby_item"]["ok"] is True
    assert {i["id"] for i in read(tmp_path, "catalog-girl.json")["items"]} == {"bh-01_7101", "bh-01_7102", "bh-01_7103"}
    assert check_dir(tmp_path) == []


def test_dry_run_writes_files_prints_content_and_never_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/SECRET")
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))
    w.schedule["2026-10"].append(c("01_7004", "HG 1/144 新機体", "2026年10月31日 (土)"))
    w.details["01_7004"] = detail_html("HG 1/144 新機体", ["hg"])
    posted = []
    res, _, _, lines = go(w, tmp_path, Options(dry_run=True), now=NOW + timedelta(days=1), post=lambda *a, **k: posted.append(a))
    text = "\n".join(lines)
    assert posted == [] and res["notified"] == 0 and "HG 1/144 新機体" in text and "SECRET" not in text
    assert "bh-new-01_7004" in {f["id"] for f in read(tmp_path, "feed.json")["items"]}          # dry-run도 파일은 쓴다
    assert res["meta"]["sources"]["translate"]["skipped"] == "dry-run"                         # 번역(API 비용)은 기본으로 건너뜀


def test_only_item_stage_requests_no_schedule_or_brand_pages(tmp_path):
    w = World()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09", max_new=0, max_backlog=0))
    _, _, sess, _ = go(w, tmp_path, Options(only={"hobby_item"}), now=NOW + timedelta(days=1))
    urls = kinds(sess)
    assert urls and all("/item/" in u or u.endswith("/robots.txt") for u in urls)


def test_options_stages_parsing():
    assert Options(only={"hobby"}).stages() == {"hobby_schedule", "hobby_brand", "hobby_item"}
    assert Options(only={"translate"}, dry_run=True).stages() == {"translate"}
    assert "translate" in Options().stages() and "translate" not in Options(dry_run=True).stages()
    with pytest.raises(ValueError):
        Options(only={"joyhobby"}).stages()


def test_translate_stage_fills_name_ko_and_feed_title_ko(tmp_path):
    from types import SimpleNamespace

    def create(**kw):
        rows = json.loads(kw["messages"][0]["content"])
        text = json.dumps({"items": [{"id": r["id"], "ko": f"한글 {r['id']}"} for r in rows]}, ensure_ascii=False)   # 가나 없는 번역
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    fake = SimpleNamespace(messages=SimpleNamespace(create=create))
    res, *_ = go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"), anthropic_client=fake)
    items = {i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json") for i in read(tmp_path, f)["items"]}
    assert all(i["nameKo"] for i in items.values()) and res["meta"]["sources"]["translate"]["ok"] is True
    feed = read(tmp_path, "feed.json")["items"]
    assert all(f["titleKo"] for f in feed)
