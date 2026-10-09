"""--discord-test — 발송 함수를 가짜로 바꿔 네트워크 없이 확인한다. 실제 디스코드로는 나가지 않는다."""
import hashlib
import json
import logging

import pytest
import yaml

from crawler import config, discord, discord_test
from crawler.pipeline import Options

WEBHOOK = "https://discord.com/api/webhooks/123456/SECRET-TOKEN-VALUE"


def fitem(i, added, type_="kr-new", cid="auto", title=None):
    return {"id": f"jh-1-BD{i:07d}", "type": type_, "date": "2026-10-03", "added": added,
            "catalogId": f"bh-01_{i}" if cid == "auto" else cid, "title": title or f"원문 {i}", "titleKo": f"제품 {i}",
            "url": f"https://www.joyhobby.co.kr/mall/board_view.asp?B_iID={i}", "image": None, "source": "joyhobby"}


def seed(tmp_path, items, mine=None):
    (tmp_path / "feed.json").write_text(json.dumps({"updatedAt": "2026-10-08T00:00:00+09:00", "items": items}, ensure_ascii=False), encoding="utf-8")
    kits = [{"id": f"k{n}", "name": f"프라 {n}", "list": lst, "catalogId": cid} for n, (cid, lst) in enumerate((mine or {}).items())]
    (tmp_path / "collection.json").write_text(json.dumps({"version": 3, "settings": {}, "kits": kits}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "meta.json").write_text("{}", encoding="utf-8")


def snapshot(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.iterdir())}


class Poster:
    def __init__(self, status=204):
        self.calls, self.status = [], status

    def __call__(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return type("R", (), {"status_code": self.status})()


def go(tmp_path, *, webhook=WEBHOOK, post=None, dry_run=False):
    lines, post = [], post or Poster()
    env = {"DISCORD_WEBHOOK_URL": webhook} if webhook else {}
    code = discord_test.run(tmp_path, dry_run=dry_run, post=post, out=lines.append, env=env)
    return code, post, lines


FEED = [fitem(i, f"2026-10-0{i}T09:00:00+09:00") for i in range(1, 8)]          # 1이 가장 오래됨, 7이 가장 최근


def test_sends_one_message_with_test_header_and_three_recent_items_without_touching_data(tmp_path):
    seed(tmp_path, FEED)
    before = snapshot(tmp_path)
    code, post, lines = go(tmp_path)
    assert code == 0 and len(post.calls) == 1
    msg = post.calls[0]["json"]
    assert msg["content"].startswith("[테스트] 프라 격납고 알림 확인용")
    assert [e["title"] for e in msg["embeds"]] == ["제품 7", "제품 6", "제품 5"]                    # 최근 3개, 실제 알림과 같은 임베드
    assert msg["embeds"][0] == discord.embed_for(FEED[6])
    assert post.calls[0]["timeout"] == config.DISCORD_TIMEOUT
    assert snapshot(tmp_path) == before                                                          # docs/data는 바뀌지 않는다
    assert "1개 메시지를 보냈어요" in "\n".join(lines)


def test_includes_one_mine_linked_item_even_if_it_is_old_and_formats_it_like_real_alerts(tmp_path):
    seed(tmp_path, FEED, mine={"bh-01_2": "wish"})                                              # 2번(오래된 항목)이 내 프라
    code, post, lines = go(tmp_path)
    msg = post.calls[0]["json"]
    titles = [e["title"] for e in msg["embeds"]]
    assert len(titles) == 3 and "[내 프라] 제품 2" in titles and titles[0] == "[내 프라] 제품 2"      # 내 프라 우선 형식, 맨 앞
    assert {"제품 7", "제품 6"} == {t for t in titles if not t.startswith("[내 프라]")}            # 나머지는 가장 최근 2개
    assert msg["content"].startswith("[테스트] 프라 격납고 알림 확인용\n내 프라가 국내에 입고됐어요!")
    assert msg["embeds"][0]["color"] == config.MINE_COLOR


def test_mine_item_already_among_recent_does_not_duplicate_and_prefers_kr_arrivals(tmp_path):
    items = FEED + [fitem(8, "2026-10-08T09:00:00+09:00", type_="new", cid="bh-01_9")]
    seed(tmp_path, items, mine={"bh-01_9": "own", "bh-01_3": "own"})                           # 신제품(최신)과 오래된 국내 입고 둘 다 내 프라
    code, post, _ = go(tmp_path)
    titles = [e["title"] for e in post.calls[0]["json"]["embeds"]]
    assert len(titles) == len(set(titles)) == 3
    assert titles[0] == "[내 프라] 제품 3"                                                         # 강조 형식을 볼 수 있는 국내 입고를 우선


def test_fewer_than_three_items_and_empty_feed(tmp_path):
    seed(tmp_path, FEED[:2])
    code, post, _ = go(tmp_path)
    assert len(post.calls[0]["json"]["embeds"]) == 2
    seed(tmp_path, [])
    code, post, lines = go(tmp_path)
    assert code == 0 and post.calls == [] and "보낼 항목이 없어요" in "\n".join(lines)
    (tmp_path / "feed.json").unlink()
    code, post, lines = go(tmp_path)
    assert code == 0 and post.calls == []


def test_no_webhook_prints_notice_and_exits_successfully(tmp_path):
    seed(tmp_path, FEED)
    code, post, lines = go(tmp_path, webhook=None)
    assert code == 0 and post.calls == [] and "웹훅 없음" in "\n".join(lines)


def test_dry_run_prints_content_and_never_posts_even_with_webhook(tmp_path):
    seed(tmp_path, FEED)
    code, post, lines = go(tmp_path, dry_run=True)
    text = "\n".join(lines)
    assert code == 0 and post.calls == [] and "제품 7" in text and "[테스트] 프라 격납고 알림 확인용" in text and "--dry-run" in text


def test_webhook_url_never_appears_in_output_or_logs_even_on_failure(tmp_path, caplog):
    seed(tmp_path, FEED)
    with caplog.at_level(logging.DEBUG):
        code, post, lines = go(tmp_path)
        assert code == 0
        bad_code, _, bad_lines = go(tmp_path, post=Poster(status=500))
        import requests

        def boom(*a, **k):
            raise requests.ConnectionError(f"failed for {WEBHOOK}")           # 예외 메시지에 URL이 섞여도
        err_code, _, err_lines = go(tmp_path, post=boom)
    assert bad_code == 1 and err_code == 1                                       # 수동 실행이라 실패는 눈에 띄게
    blob = "\n".join(lines + bad_lines + err_lines) + caplog.text
    assert "SECRET-TOKEN-VALUE" not in blob and "discord.com/api/webhooks" not in blob


def test_main_discord_test_runs_without_crawling_and_rejects_crawl_options(tmp_path, monkeypatch, capsys):
    import main as m

    seed(tmp_path, FEED)
    before = snapshot(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(m, "run", lambda *a, **k: pytest.fail("--discord-test는 수집(run)을 부르면 안 된다"))
    monkeypatch.setattr(m, "HttpClient", lambda *a, **k: pytest.fail("HTTP 클라이언트를 만들면 안 된다"))
    assert m.main(["--discord-test", "--data-dir", str(tmp_path)]) == 0
    assert "웹훅 없음" in capsys.readouterr().out and snapshot(tmp_path) == before
    for bad in (["--discord-test", "--bootstrap"], ["--discord-test", "--only", "hobby"], ["--discord-test", "--from", "2025-10"], ["--discord-test", "--joy-pages", "3"]):
        with pytest.raises(SystemExit):
            m.parse_args(bad)
    assert m.parse_args(["--discord-test", "--dry-run"]).dry_run is True
    assert isinstance(Options(), Options)


def test_workflow_has_discord_test_input_and_skips_commit_for_it():
    wf = yaml.safe_load((config.ROOT / ".github" / "workflows" / "crawl.yml").read_text(encoding="utf-8"))
    inp = wf[True]["workflow_dispatch"]["inputs"]["discord_test"]                  # YAML에서 `on` 키는 True로 읽힌다
    assert inp["type"] == "boolean" and inp["default"] is False
    steps = {s.get("name"): s for s in wf["jobs"]["crawl"]["steps"]}
    crawl, commit = steps["Crawl"], steps["Commit data"]
    assert crawl["env"]["DISCORD_TEST"] == "${{ inputs.discord_test }}"
    assert "python main.py --discord-test" in crawl["run"] and crawl["run"].index("--discord-test") < crawl["run"].index("args=()")
    assert commit["if"] == "${{ !inputs.discord_test && !inputs.mall_debug }}"      # 테스트 알림·몰 진단 실행은 커밋하지 않는다
    assert "DISCORD_WEBHOOK_URL" in crawl["env"] and "secrets.DISCORD_WEBHOOK_URL" in crawl["env"]["DISCORD_WEBHOOK_URL"]


def test_workflow_mall_debug_runs_only_mall_uploads_html_and_never_commits():
    wf = yaml.safe_load((config.ROOT / ".github" / "workflows" / "crawl.yml").read_text(encoding="utf-8"))
    inp = wf[True]["workflow_dispatch"]["inputs"]["mall_debug"]
    assert inp["type"] == "boolean" and inp["default"] is False
    steps = {s.get("name"): s for s in wf["jobs"]["crawl"]["steps"]}
    crawl, up = steps["Crawl"], steps["Upload mall debug"]
    assert crawl["env"]["MALL_DEBUG"] == "${{ inputs.mall_debug }}"
    run = crawl["run"]
    assert "python main.py --only mall --dry-run --mall-dump crawler/out/mall-debug" in run and run.index("--mall-dump") < run.index("args=()")
    assert up["uses"].startswith("actions/upload-artifact@") and up["with"]["retention-days"] == 3 and up["with"]["path"] == "crawler/out/mall-debug"
    assert "inputs.mall_debug" in up["if"] and "!inputs.mall_debug" in steps["Commit data"]["if"]
