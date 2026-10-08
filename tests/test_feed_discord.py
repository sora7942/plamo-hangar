"""feed.py + discord.py — 생성 조건, 병합, 알림 규칙. 디스코드는 가짜 post로만 (실제 발송 없음)."""
import logging
from datetime import datetime

import pytest
import requests

from conftest import FakeResponse
from crawler import config, discord, feed
from crawler.catalog import Catalog
from crawler.pipeline import Options, _notify

KST = config.KST
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=KST)
NOW_ISO = "2026-10-06T09:00:00+09:00"
WEBHOOK = "https://discord.com/api/webhooks/123/SECRET-TOKEN"


def item(cid="bh-01_7001", name="HG 1/144 A", month="2026-10", date=None, pb=False, line="gunpla", images=(), ko=None):
    num = cid.split("-", 1)[1]
    url = f"https://p-bandai.jp/item/{num}/" if pb else f"https://bandai-hobby.net/item/{num}/"
    return {"id": cid, "url": url, "line": line, "brandKeys": [], "grade": "HG", "scale": None, "seriesKey": None,
            "series": None, "nameJa": name, "nameKo": ko, "priceJpy": 1100, "channel": "online" if pb else "general",
            "pbUrl": url if pb else None, "release": {"month": month, **({"date": date} if date else {})},
            "kr": [], "images": list(images), "firstSeen": NOW_ISO, "updated": NOW_ISO, "detailAt": None}


def catalog_with(*items):
    cat = Catalog()
    for it in items:
        cat.items[it["id"]] = it
    return cat


def fitem(i, added, type_="new", title=None):
    return {"id": f"bh-new-01_{i}", "type": type_, "date": "2026-10", "added": added, "catalogId": f"bh-01_{i}",
            "title": title or f"T{i}", "titleKo": None, "url": f"https://bandai-hobby.net/item/01_{i}/", "image": None,
            "source": "bandai-hobby"}


# ---------------------------------------------------------------- 피드 생성
def test_new_feed_items_conditions_and_shapes():
    img = "https://bandai-a.akamaihd.net/bc/img/model/xl/1_1.jpg"
    cat = catalog_with(
        item("bh-01_7001", month="2026-10", date="2026-10-24", images=[img], ko="한글"),            # 이번 달 → 피드
        item("bh-01_7002", month="2027-01"),                                                          # 미래 → 피드
        item("bh-01_7003", month="2026-09"),                                                          # 지난 달 → 제외
        item("bh-01_7004", line=None),                                                                # 판정 전 → 제외
        item("pb-item-1000253222", month="2026-12", pb=True),                                         # P-반다이 → pb-new
        item("bh-01_7005", line="girl", month="2026-11"),
    )
    got = feed.new_feed_items(cat, ["bh-01_7001", "bh-01_7002", "bh-01_7003", "bh-01_7004", "pb-item-1000253222",
                                    "bh-01_7005", "bh-01_9999"], NOW, NOW_ISO)
    assert [g["id"] for g in got] == ["bh-new-01_7001", "bh-new-01_7002", "pb-new-item-1000253222", "bh-new-01_7005"]
    first = got[0]
    assert first == {"id": "bh-new-01_7001", "type": "new", "date": "2026-10-24", "added": NOW_ISO,
                     "catalogId": "bh-01_7001", "title": "HG 1/144 A", "titleKo": "한글",
                     "url": "https://bandai-hobby.net/item/01_7001/", "image": img, "source": "bandai-hobby"}
    pb = got[2]
    assert pb["type"] == "pb-new" and pb["url"] == "https://p-bandai.jp/item/item-1000253222/" and pb["image"] is None
    assert got[1]["date"] == "2027-01" and got[1]["image"] is None


# ---------------------------------------------------------------- 피드 병합
def test_merge_feed_ignores_duplicate_ids_and_keeps_added():
    prev = [fitem(1, "2026-10-01T09:00:00+09:00")]
    new = [fitem(1, NOW_ISO), fitem(2, NOW_ISO)]
    merged, added = feed.merge_feed(prev, new, Catalog())
    assert [m["id"] for m in merged] == ["bh-new-01_2", "bh-new-01_1"]            # added 내림차순
    assert [a["id"] for a in added] == ["bh-new-01_2"]
    assert next(m for m in merged if m["id"] == "bh-new-01_1")["added"] == "2026-10-01T09:00:00+09:00"


def test_merge_feed_caps_at_1000_keeping_newest():
    prev = [fitem(i, f"2025-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}T00:00:00+09:00") for i in range(1005)]
    new = [fitem(5000, NOW_ISO)]
    merged, added = feed.merge_feed(prev, new, Catalog())
    assert len(merged) == config.FEED_MAX == 1000
    assert merged[0]["id"] == "bh-new-01_5000" and [a["id"] for a in added] == ["bh-new-01_5000"]


def test_merge_feed_drops_items_later_excluded_as_non_target():
    cat = Catalog()
    cat.excluded["bh-01_2"] = "brand:claymonsters"
    prev = [fitem(1, "2026-10-01T09:00:00+09:00"), fitem(2, "2026-10-02T09:00:00+09:00")]
    merged, added = feed.merge_feed(prev, [], cat)
    assert [m["id"] for m in merged] == ["bh-new-01_1"] and added == []


def test_merge_feed_backfills_blank_title_ko_and_image_without_touching_added():
    img = "https://bandai-a.akamaihd.net/bc/img/model/xl/1_1.jpg"
    cat = catalog_with(item("bh-01_1", ko="번역됨", images=[img]))
    prev = [fitem(1, "2026-10-01T09:00:00+09:00")]
    merged, added = feed.merge_feed(prev, [], cat)
    assert merged[0]["titleKo"] == "번역됨" and merged[0]["image"] == img
    assert merged[0]["added"] == "2026-10-01T09:00:00+09:00" and added == []


# ---------------------------------------------------------------- 디스코드 구성
def test_plan_messages_order_split_and_overflow():
    items = [fitem(i, NOW_ISO) for i in range(35)]
    items[20]["type"] = "pb-new"
    items[30]["type"] = "kr-restock"
    msgs, overflow = discord.plan_messages(items)
    assert len(msgs) == config.DISCORD_MAX_MESSAGES == 3 and overflow == 5
    assert [len(m["embeds"]) for m in msgs] == [10, 10, 10]
    assert msgs[0]["embeds"][0]["description"].startswith("국내 재입고")                  # kr → pb-new → new 순서
    assert msgs[0]["embeds"][1]["description"].startswith("P-반다이 한정 신규")
    assert "외 5건" in msgs[-1]["content"] and config.SITE_URL in msgs[-1]["content"]
    assert all("content" not in m for m in msgs[:-1])
    assert all(m["allowed_mentions"] == {"parse": []} for m in msgs)


def test_embed_has_title_link_type_date_color_and_thumbnail_only_with_image():
    it = fitem(1, NOW_ISO)
    it["titleKo"], it["image"] = "한글 이름", "https://bandai-a.akamaihd.net/x.jpg"
    emb = discord.embed_for(it)
    assert emb["title"] == "한글 이름" and emb["url"] == it["url"] and emb["description"] == "신제품 발매 · 2026-10"
    assert emb["thumbnail"] == {"url": it["image"]} and isinstance(emb["color"], int)
    assert "thumbnail" not in discord.embed_for(fitem(2, NOW_ISO)) and discord.embed_for(fitem(2, NOW_ISO))["title"] == "T2"


def test_no_messages_when_nothing_added():
    assert discord.plan_messages([]) == ([], 0)


def test_skip_reasons():
    assert discord.skip_reason(prev_feed_empty=False, prev_catalog_empty=False, bootstrap=False) is None
    assert "bootstrap" in discord.skip_reason(prev_feed_empty=False, prev_catalog_empty=False, bootstrap=True)
    assert discord.skip_reason(prev_feed_empty=True, prev_catalog_empty=False, bootstrap=False)
    assert discord.skip_reason(prev_feed_empty=False, prev_catalog_empty=True, bootstrap=False)


# ---------------------------------------------------------------- 발송 (가짜 post)
class Poster:
    def __init__(self, fail_at=None, exc=None):
        self.calls, self.fail_at, self.exc = [], fail_at, exc

    def __call__(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.exc:
            raise self.exc
        return FakeResponse(url, "", 500 if self.fail_at == len(self.calls) else 204)


def test_send_posts_each_message_with_timeout_and_pauses_between():
    msgs, _ = discord.plan_messages([fitem(i, NOW_ISO) for i in range(25)])
    post, sleeps = Poster(), []
    assert discord.send(msgs, WEBHOOK, post=post, sleep=sleeps.append) == 3
    assert len(post.calls) == 3 and all(c["timeout"] == config.DISCORD_TIMEOUT for c in post.calls)
    assert sleeps == [config.DISCORD_SEND_INTERVAL] * 2


def test_send_failure_warns_without_webhook_url_and_stops(caplog):
    msgs, _ = discord.plan_messages([fitem(i, NOW_ISO) for i in range(25)])
    with caplog.at_level(logging.WARNING):
        assert discord.send(msgs, WEBHOOK, post=Poster(fail_at=2), sleep=lambda s: None) == 1
        post = Poster(exc=requests.ConnectionError(f"failed to reach {WEBHOOK}"))
        assert discord.send(msgs, WEBHOOK, post=post, sleep=lambda s: None) == 0
    assert "SECRET-TOKEN" not in caplog.text and "webhooks" not in caplog.text            # 웹훅 URL은 로그에 남지 않는다


# ---------------------------------------------------------------- 파이프라인의 알림 판정
def run_notify(opts, added, *, feed_empty=False, catalog_empty=False, poster=None, webhook=None, monkeypatch=None):
    if webhook and monkeypatch:
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook)
    lines = []
    poster = poster or Poster()
    n = _notify(opts, added, prev_feed_empty=feed_empty, prev_catalog_empty=catalog_empty, post=poster, out=lines.append)
    return n, poster, lines


def test_notify_sends_when_not_first_run_and_webhook_set(monkeypatch):
    n, post, lines = run_notify(Options(), [fitem(1, NOW_ISO)], webhook=WEBHOOK, monkeypatch=monkeypatch)
    assert n == 1 and len(post.calls) == 1 and post.calls[0]["url"] == WEBHOOK
    assert WEBHOOK not in "\n".join(lines)


@pytest.mark.parametrize("kwargs,opts", [
    ({"feed_empty": True}, Options()),                      # 이전 피드가 비었음
    ({"catalog_empty": True}, Options()),                   # 카탈로그가 비어 있던 첫 실행
    ({}, Options(bootstrap=True)),                          # 최초 채우기 중
])
def test_notify_skips_first_run_and_bootstrap(monkeypatch, kwargs, opts):
    n, post, lines = run_notify(opts, [fitem(1, NOW_ISO)], webhook=WEBHOOK, monkeypatch=monkeypatch, **kwargs)
    assert n == 0 and post.calls == [] and any("알림 없음" in l for l in lines)


def test_notify_dry_run_never_posts_and_prints_content_even_on_first_run(monkeypatch):
    n, post, lines = run_notify(Options(dry_run=True), [fitem(1, NOW_ISO, title="미리보기 제품")], feed_empty=True,
                                webhook=WEBHOOK, monkeypatch=monkeypatch)
    text = "\n".join(lines)
    assert n == 0 and post.calls == [] and "미리보기 제품" in text and "형식 확인용" in text and WEBHOOK not in text


def test_notify_without_webhook_or_with_no_discord_only_prints(monkeypatch):
    n, post, lines = run_notify(Options(), [fitem(1, NOW_ISO)])
    assert n == 0 and post.calls == [] and any("DISCORD_WEBHOOK_URL 없음" in l for l in lines)
    n, post, lines = run_notify(Options(no_discord=True), [fitem(1, NOW_ISO)], webhook=WEBHOOK, monkeypatch=monkeypatch)
    assert n == 0 and post.calls == [] and any("--no-discord" in l for l in lines)


# ---------------------------------------------------------------- 내 프라 우선 (SPEC 7장 ①)
def kr_item(i, type_="kr-restock", cid="auto"):
    f = fitem(i, NOW_ISO, type_=type_)
    f.update(id=f"jh-1-BD{i}", date="2026-10-03", catalogId=f"bh-01_{i}" if cid == "auto" else cid, url="https://www.joyhobby.co.kr/mall/board_view.asp?B_iID=1")
    return f


def test_mine_kr_items_go_first_with_highlight_color_and_who_label():
    items = [fitem(1, NOW_ISO), fitem(2, NOW_ISO, type_="pb-new"), kr_item(3), kr_item(4, "kr-new"), kr_item(5, cid=None), kr_item(6)]
    mine = {"bh-01_4": ["wish"], "bh-01_6": ["own", "wish"], "bh-01_1": ["own"], "bh-01_2": ["wish"]}      # 신제품·P-반다이가 내 프라여도 우선 대상이 아니다
    msgs, overflow = discord.plan_messages(items, mine)
    embeds = msgs[0]["embeds"]
    assert [e["title"] for e in embeds] == ["[내 프라] T4", "[내 프라] T6", "T3", "T5", "T2", "T1"]
    assert [e["title"].startswith("[내 프라]") for e in embeds] == [True, True, False, False, False, False]
    assert [e["url"] for e in embeds[:2]] == [items[3]["url"], items[5]["url"]]                           # 내 프라 안에서는 원래 순서
    assert embeds[0]["color"] == config.MINE_COLOR == embeds[1]["color"] and embeds[2]["color"] != config.MINE_COLOR
    assert embeds[0]["description"] == "내 프라(위시) · 국내 신규 입고 · 2026-10-03"
    assert embeds[1]["description"] == "내 프라(보유·위시) · 국내 재입고 · 2026-10-03"
    assert [e["title"] for e in embeds[2:]] == ["T3", "T5", "T2", "T1"]                                   # 나머지는 kr → pb-new → new
    assert msgs[0]["content"] == "내 프라가 국내에 입고됐어요! (2건)" and overflow == 0


def test_without_mine_or_mine_map_nothing_changes():
    items = [fitem(1, NOW_ISO), kr_item(3)]
    base, _ = discord.plan_messages(items)
    assert discord.plan_messages(items, {})[0] == base and discord.plan_messages(items, None)[0] == base
    assert "content" not in base[0] and not any(e["title"].startswith("[내 프라]") for e in base[0]["embeds"])
    assert discord.plan_messages(items, {"bh-01_9": ["own"]})[0] == base                               # 관련 없는 내 프라


def test_mine_items_survive_the_message_cap_and_overflow_note_is_kept():
    items = [fitem(i, NOW_ISO) for i in range(100, 135)] + [kr_item(1), kr_item(2)]                      # 새 제품 35개 + 내 프라 2개 (한도 30)
    msgs, overflow = discord.plan_messages(items, {"bh-01_1": ["own"], "bh-01_2": ["wish"]})
    flat = [e["title"] for m in msgs for e in m["embeds"]]
    assert len(flat) == 30 and flat[:2] == ["[내 프라] T1", "[내 프라] T2"] and not any(t.startswith("[내 프라]") for t in flat[2:])
    assert overflow == 7 and msgs[0]["content"].startswith("내 프라가 국내에 입고됐어요! (2건)")
    assert msgs[-1]["content"] == f"외 7건 — 사이트에서 보기: {config.SITE_URL}"
    msgs1, _ = discord.plan_messages([kr_item(1)] + [fitem(i, NOW_ISO) for i in range(100, 108)], {"bh-01_1": ["own"]})
    assert len(msgs1) == 1 and msgs1[0]["content"] == "내 프라가 국내에 입고됐어요! (1건)"


def test_mine_lists_only_for_kr_types():
    mine = {"bh-01_1": ["own"]}
    assert discord.mine_lists(kr_item(1), mine) == ["own"] and discord.mine_lists(kr_item(1, "kr-new"), mine) == ["own"]
    assert discord.mine_lists(fitem(1, NOW_ISO), mine) == [] and discord.mine_lists(fitem(1, NOW_ISO, "pb-new"), mine) == []
    assert discord.mine_lists({"type": "kr-new", "catalogId": None}, mine) == []


def test_notify_dry_run_prints_mine_embed_and_pipeline_reads_collection_read_only(monkeypatch, tmp_path):
    lines = []
    n = _notify(Options(dry_run=True), [kr_item(1)], prev_feed_empty=False, prev_catalog_empty=False, post=None, out=lines.append, mine_map={"bh-01_1": ["wish"]})
    text = "\n".join(lines)
    assert n == 0 and "[내 프라]" in text and "내 프라(위시)" in text and "내 프라가 국내에 입고됐어요!" in text


def test_run_reads_collection_for_mine_and_never_writes_it(tmp_path, monkeypatch):
    import json as _json
    from test_pipeline import World, go
    from conftest import joy_board_html  # noqa: F401  (World의 게시판 fixture와 같은 모듈)

    coll = _json.dumps({"version": 3, "settings": {}, "kits": [{"id": "k1", "name": "내 프라", "list": "wish", "catalogId": "bh-01_7001"}]}) + "\n"
    (tmp_path / "collection.json").write_text(coll, encoding="utf-8")
    seen = {}
    real = discord.plan_messages
    monkeypatch.setattr(discord, "plan_messages", lambda items, mine=None: (seen.setdefault("mine", mine), real(items, mine))[1])
    go(World(), tmp_path, Options(bootstrap=True, from_month="2026-09"))
    assert seen["mine"] == {"bh-01_7001": ["wish"]}
    assert (tmp_path / "collection.json").read_text(encoding="utf-8") == coll
