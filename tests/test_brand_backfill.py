"""2015년 이전 상품 채우기(--brand-backfill, hobby_backfill 단계) — 가짜 호비사이트·임시 폴더. 네트워크·Claude 없음."""
import json

import pytest
import yaml
from conftest import detail_html, schedule_html
from crawler import config
from crawler.catalog import Catalog
from crawler.pipeline import Options
from schema_check import check_dir
from test_pipeline import HOBBY, World, go, kinds, read


def card(num, title, date="2010年05月"):
    return {"num": num, "title": title, "date": date}


class OldWorld(World):
    """old[key] = [쪽1 카드들, 쪽2 카드들 …]. 페이저는 첫 쪽에 마지막 쪽 링크를 단다(실제 사이트처럼 중간 쪽은 줄여서)."""

    def __init__(self, old=None):
        super().__init__()
        self.old = old or {"hg": [[card("01_1001", "HG 1/144 옛날 A"), card("01_1002", "HG 1/144 옛날 B")], [card("01_1003", "HG 1/144 옛날 C", "2009年03月")]],
                           "mg": [[card("01_2001", "MG 1/100 옛날 M")]], "rg": [[card("01_3001", "RG 1/144 옛날 R", "2012年07月")]]}
        self.fail = set()                         # {(key, page)}

    def routes(self):
        r = super().routes()
        for key in config.OLD_BRANDS + ["bb"]:
            pages = self.old.get(key, [[]])
            for n in range(1, len(pages) + 1):
                url = f"{HOBBY}/brand/{key}/" if n == 1 else f"{HOBBY}/brand/{key}/?p={n}"
                r[url] = (lambda u, key=key, n=n: (500, "boom") if (key, n) in self.fail else self._old_page(key, n))
        return r

    def _old_page(self, key, n):
        pages = self.old.get(key, [[]])
        html = schedule_html(pages[n - 1])
        pager = "".join(f'<a class="c-archives__pagination-list-item-link" href="./?p={p}">{p}</a>' for p in (1, len(pages)) if p > 1)
        return html.replace("</body>", f"{pager}</body>")


def brand_urls(sess):
    return [u for u in kinds(sess) if "/brand/" in u]


def items_of(tmp_path):
    return {i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json", "catalog-pending.json") for i in read(tmp_path, f)["items"]}


def test_backfill_walks_old_brands_and_builds_items_from_cards_only(tmp_path):
    res, _, sess, _ = go(OldWorld(), tmp_path, Options(brand_backfill=True))
    items = items_of(tmp_path)
    assert {"bh-01_1001", "bh-01_1002", "bh-01_1003", "bh-01_2001", "bh-01_3001"} <= set(items)
    a = items["bh-01_1001"]
    assert a["line"] == "gunpla" and a["grade"] == "HG" and a["brandKeys"] == ["hg"] and a["detailAt"] is None and a["release"]["month"] == "2010-05"
    assert items["bh-01_2001"]["grade"] == "MG" and items["bh-01_3001"]["grade"] == "RG"
    assert not [u for u in kinds(sess) if "/item/" in u or "/schedule/" in u] and not any("/brand/bb/" in u for u in kinds(sess))     # 상세·일정은 받지 않고 bb는 제외
    seen = {u.split("/brand/")[1].split("/")[0] for u in brand_urls(sess)}
    assert seen == set(config.OLD_BRANDS)
    assert res["meta"]["sources"]["hobby_backfill"]["ok"] is True
    cur = res["meta"]["crawl"]["brandBackfill"]
    assert cur["hg"] == {"next": 3, "last": 2, "done": True} and all(v["done"] for v in cur.values()) and set(cur) == set(config.OLD_BRANDS)
    assert check_dir(tmp_path) == []
    assert read(tmp_path, "feed.json")["items"] == [] and res["newItems"] == 0 and res["notified"] == 0       # 과거 상품은 피드·알림에 들어가지 않는다


def test_only_the_backfill_stage_runs_and_it_is_not_part_of_normal_runs():
    assert Options(brand_backfill=True).stages() == {"hobby_backfill"}
    assert "hobby_backfill" not in Options().stages() and "hobby_backfill" not in Options(bootstrap=True).stages()
    assert Options(only={"hobby_backfill"}).stages() == {"hobby_backfill"}


def test_cursor_resumes_at_the_failed_page_and_a_finished_backfill_makes_no_requests(tmp_path):
    w = OldWorld()
    w.fail = {("hg", 2)}
    res, _, sess, _ = go(w, tmp_path, Options(brand_backfill=True))
    src = res["meta"]["sources"]["hobby_backfill"]
    assert src["ok"] is False and "hg:2" in src["error"]
    assert res["meta"]["crawl"]["brandBackfill"]["hg"] == {"next": 2, "last": 2, "done": False} and "mg" not in res["meta"]["crawl"]["brandBackfill"]
    assert "bh-01_1001" in items_of(tmp_path) and "bh-01_1003" not in items_of(tmp_path)
    w.fail = set()
    res, _, sess, _ = go(w, tmp_path, Options(brand_backfill=True))
    urls = brand_urls(sess)
    assert f"{HOBBY}/brand/hg/" not in urls and f"{HOBBY}/brand/hg/?p=2" in urls                     # 1쪽은 다시 받지 않고 2쪽부터
    assert "bh-01_1003" in items_of(tmp_path) and all(v["done"] for v in res["meta"]["crawl"]["brandBackfill"].values())
    res, _, sess, _ = go(w, tmp_path, Options(brand_backfill=True))
    assert brand_urls(sess) == []                                                                     # 끝났으면 요청 없음


def test_per_run_cap_stops_and_continues_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BRAND_BACKFILL_PAGES_PER_RUN", 2)
    w = OldWorld()
    res, _, sess, _ = go(w, tmp_path, Options(brand_backfill=True))
    assert len(brand_urls(sess)) == 2 and res["meta"]["crawl"]["brandBackfill"]["hg"]["done"] is True and "mg" not in res["meta"]["crawl"]["brandBackfill"]
    for _ in range(12):
        res, _, sess, _ = go(w, tmp_path, Options(brand_backfill=True))
    cur = res["meta"]["crawl"]["brandBackfill"]
    assert set(cur) == set(config.OLD_BRANDS) and all(v["done"] for v in cur.values())


def test_pages_beyond_the_girl_brand_cap_are_followed(tmp_path):
    many = [[card(f"01_{9000 + n}", f"HG 1/144 쪽{n}", "2011年01月")] for n in range(1, 71)]            # 70쪽 > BRAND_MAX_PAGES(60)
    res, _, sess, _ = go(OldWorld({"hg": many}), tmp_path, Options(brand_backfill=True))
    assert res["meta"]["crawl"]["brandBackfill"]["hg"] == {"next": 71, "last": 70, "done": True}
    assert len([i for i in items_of(tmp_path) if i.startswith("bh-01_9")]) == 70


def test_existing_and_excluded_items_are_not_duplicated_or_revived(tmp_path):
    (tmp_path / "catalog-pending.json").write_text(json.dumps({"updatedAt": "2026-10-01T00:00:00+09:00", "items": [], "excluded": {"bh-01_1002": "brand:claymonsters"}}), encoding="utf-8")
    go(OldWorld(), tmp_path, Options(brand_backfill=True))
    items = items_of(tmp_path)
    assert "bh-01_1002" not in items and read(tmp_path, "catalog-pending.json")["excluded"]["bh-01_1002"] == "brand:claymonsters"
    first = items["bh-01_1001"]
    go(OldWorld(), tmp_path, Options(only={"hobby_backfill"}))                                       # 같은 목록을 한 번 더 훑어도
    assert items_of(tmp_path)["bh-01_1001"]["firstSeen"] == first["firstSeen"] and len([i for i in items_of(tmp_path) if i.startswith("bh-01_10")]) == 2


def test_old_items_are_translated_last_and_get_details_after_newer_ones():
    cat = Catalog()
    now = "2026-10-09T00:00:00+09:00"
    for num, month in (("01_1001", "2010-05"), ("01_7001", "2026-09"), ("01_5001", "2021-03")):
        cat.upsert_card({"id": f"bh-{num}", "url": f"{HOBBY}/item/{num}/", "nameJa": f"HG 1/144 {num}", "release": {"month": month}, "priceJpy": 1000, "channel": "general", "pbUrl": None}, now, "hg")
    _, back = cat.select_details(0, 10, set())
    assert back == ["bh-01_7001", "bh-01_5001", "bh-01_1001"]                                     # 발매월 최신순
    assert [i["id"] for i in cat.untranslated(10)] == ["bh-01_7001", "bh-01_5001", "bh-01_1001"]     # 번역도 최신순


def test_linked_old_items_still_get_details_first_through_the_manual_path(tmp_path):
    w = OldWorld()
    go(w, tmp_path, Options(brand_backfill=True))
    (tmp_path / "collection.json").write_text(json.dumps({"version": 3, "settings": {}, "kits": [{"id": "k1", "name": "옛날 B", "list": "own", "catalogId": "bh-01_1002"}]}), encoding="utf-8")
    w.details["01_1002"] = detail_html("HG 1/144 옛날 B", ["hg"], release="2010年05月")
    w.details["01_1001"] = detail_html("HG 1/144 옛날 A", ["hg"], release="2010年05月")
    go(w, tmp_path, Options(only={"hobby_item"}, max_new=0, max_backlog=1))
    items = items_of(tmp_path)
    assert items["bh-01_1002"]["detailAt"] and items["bh-01_1002"]["manual"] is True                  # 연결된 프라가 먼저 (밀린 상품 상한 1과 별개)


def test_main_flags_and_workflow_input():
    import main as m
    assert m.parse_args(["--brand-backfill"]).brand_backfill is True
    for bad in (["--brand-backfill", "--bootstrap"], ["--brand-backfill", "--only", "hobby"], ["--brand-backfill", "--discord-test"]):
        with pytest.raises(SystemExit):
            m.parse_args(bad)
    wf = yaml.safe_load((config.ROOT / ".github" / "workflows" / "crawl.yml").read_text(encoding="utf-8"))
    inp = wf[True]["workflow_dispatch"]["inputs"]["brand_backfill"]
    assert inp["type"] == "boolean" and inp["default"] is False
    crawl = {s.get("name"): s for s in wf["jobs"]["crawl"]["steps"]}["Crawl"]
    assert crawl["env"]["BRAND_BACKFILL"] == "${{ inputs.brand_backfill }}" and "python main.py --brand-backfill" in crawl["run"]
    assert crawl["run"].index("--brand-backfill") < crawl["run"].index("args=()")
    assert "bb" not in config.OLD_BRANDS and {"hg", "hguc", "hgce", "mg", "rg", "mgsd", "sdgundamseries", "sdcs", "sdex"} <= set(config.OLD_BRANDS)
    assert set(config.OLD_BRANDS) <= set(config.BRAND_LINE)                                         # 모두 분류표에 있는 브랜드
