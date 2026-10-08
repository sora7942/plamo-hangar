"""사용자가 사이트에서 연결한 미등록 catalogId → 상세 받기 (manual / line:"other"). 가짜 호비사이트·임시 폴더만 쓴다."""
import json

from conftest import detail_html
from crawler import config, mine
from crawler.pipeline import Options
from schema_check import check_dir
from test_pipeline import HOBBY, World, go, kinds, read

AKAMAI = "https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"


def collection(*ids, wish=()):
    kits = [{"id": f"k{i}", "name": f"프라 {i}", "list": "wish" if cid in wish else "own", "catalogId": cid} for i, cid in enumerate(ids)]
    kits.append({"id": "kx", "name": "연결 안 함", "list": "own", "catalogId": None})
    return json.dumps({"version": 3, "settings": {}, "kits": kits}, ensure_ascii=False) + "\n"


class W(World):
    def __init__(self):
        super().__init__()
        self.details.update({
            "01_8001": detail_html("HG 1/144 직접 연결한 기체", ["hg"], images=[AKAMAI]),                 # 분류표 안 → 정상 등록
            "01_8002": detail_html("제외 브랜드 상품", ["figurerise-bust"]),                              # 제외 목록에 있던 id → 되살려 other
            "01_8003": detail_html("ドラゴンクエスト スライム", ["claymonsters"], series=("dq", "ドラゴンクエスト")),   # 제외 브랜드 → other
            "01_8004": detail_html("브랜드 키가 없는 상품", []),                                           # 제목으로도 판정 불가 → other
        })

    def routes(self):
        r = super().routes()
        r[f"{HOBBY}/item/01_8500/"] = lambda u: (500, "boom")                  # 일시 오류
        return r                                                              # 01_8404 는 라우트가 없어 404


def seed(tmp_path, ids, excluded=None, **kw):
    (tmp_path / "collection.json").write_text(collection(*ids, **kw), encoding="utf-8")
    if excluded:
        (tmp_path / "catalog-pending.json").write_text(json.dumps({"updatedAt": "2026-10-01T00:00:00+09:00", "items": [], "excluded": excluded}), encoding="utf-8")


def items_of(tmp_path):
    return {i["id"]: i for f in ("catalog-gunpla.json", "catalog-girl.json") for i in read(tmp_path, f)["items"]}


def detail_calls(sess):
    return [u for u in kinds(sess) if "/item/" in u]


def test_mine_reads_only_valid_ids_and_marks_own_and_wish(tmp_path):
    seed(tmp_path, ["bh-01_1", "bh-01_1", "pb-item-9", "x-1", "<script>"], wish={"pb-item-9"})
    assert mine.catalog_ids(tmp_path) == ["bh-01_1", "pb-item-9"]
    assert mine.owned_map(tmp_path) == {"bh-01_1": ["own"], "pb-item-9": ["wish"]}
    (tmp_path / "collection.json").write_text("{깨진", encoding="utf-8")
    assert mine.catalog_ids(tmp_path) == [] and mine.owned_map(tmp_path) == {}
    (tmp_path / "collection.json").unlink()
    assert mine.catalog_ids(tmp_path) == []
    (tmp_path / "collection.json").write_text('{"kits": "x"}', encoding="utf-8")
    assert mine.catalog_ids(tmp_path) == []


def test_unregistered_ids_get_details_and_non_target_brands_become_other(tmp_path):
    seed(tmp_path, ["bh-01_8001", "bh-01_8002", "bh-01_8003", "bh-01_8004"], excluded={"bh-01_8002": "brand:figurerise-bust"})
    before = (tmp_path / "collection.json").read_bytes()
    res, _, sess, _ = go(W(), tmp_path, Options(only={"hobby_item"}))
    items = items_of(tmp_path)
    ok = items["bh-01_8001"]
    assert ok["line"] == "gunpla" and ok["grade"] == "HG" and ok["manual"] is True and ok["detailAt"] and ok["images"] == [AKAMAI]
    for cid in ("bh-01_8002", "bh-01_8003", "bh-01_8004"):
        it = items[cid]
        assert it["line"] == "other" and it["manual"] is True and it["grade"] is None and it["detailAt"] and it["nameJa"]
    assert items["bh-01_8003"]["series"] == "ドラゴンクエスト" and items["bh-01_8003"]["brandKeys"] == ["claymonsters"]
    assert "bh-01_8002" not in read(tmp_path, "catalog-pending.json")["excluded"]                    # 제외 목록에서 되살림
    assert not [i for i in read(tmp_path, "catalog-girl.json")["items"] if i["line"] == "other"]      # other는 catalog-gunpla.json에만
    assert sorted(detail_calls(sess)) == sorted(f"{HOBBY}/item/{n}/" for n in ("01_8001", "01_8002", "01_8003", "01_8004"))
    man = res["meta"]["sources"]["hobby_item"]["manual"]
    assert man == {"requested": 4, "added": 4, "other": 3, "unsupported": [], "failed": []}
    assert res["meta"]["crawl"]["counts"]["other"] == 3
    assert check_dir(tmp_path) == []
    assert (tmp_path / "collection.json").read_bytes() == before                                      # collection.json은 읽기만


def test_manual_items_are_not_reexcluded_or_refetched_and_stay_out_of_feed(tmp_path):
    seed(tmp_path, ["bh-01_8003"])
    go(W(), tmp_path, Options(only={"hobby_item"}))
    first = items_of(tmp_path)["bh-01_8003"]
    res, _, sess, _ = go(W(), tmp_path, Options(only={"hobby_item"}))          # 2회차: 분류표가 제외라고 해도 재분류가 건드리지 않는다
    assert items_of(tmp_path)["bh-01_8003"] == first and "bh-01_8003" not in read(tmp_path, "catalog-pending.json")["excluded"]
    assert detail_calls(sess) == [] and res["meta"]["crawl"]["lastFixups"]["toExcluded"] == 0
    assert not [f for f in read(tmp_path, "feed.json")["items"] if f.get("catalogId") == "bh-01_8003"]     # 새 상품 피드·알림에 섞이지 않는다


def test_404_is_excluded_and_reported_but_transient_failure_keeps_previous_exclusion(tmp_path):
    seed(tmp_path, ["bh-01_8404", "bh-01_8500", "pb-item-1000000001"], excluded={"bh-01_8500": "brand:keitorabusou"})
    res, *_ = go(W(), tmp_path, Options(only={"hobby_item"}))
    pend = read(tmp_path, "catalog-pending.json")["excluded"]
    assert pend["bh-01_8404"] == "detail-404"                                                          # 없는 상품: 다시 받지 않는다
    assert pend["bh-01_8500"] == "brand:keitorabusou"                                                  # 일시 오류: 원래 제외 사유로 되돌린다
    assert "bh-01_8500" not in items_of(tmp_path) and "bh-01_8404" not in items_of(tmp_path)
    man = res["meta"]["sources"]["hobby_item"]["manual"]
    assert sorted(man["failed"]) == ["bh-01_8404", "bh-01_8500"] and man["unsupported"] == ["pb-item-1000000001"] and man["added"] == 0
    src = res["meta"]["sources"]["hobby_item"]
    assert src["ok"] is False and "bh-01_8500" in src["error"] and "bh-01_8404" not in src["error"]      # 404는 오류로 치지 않는다


def test_per_run_cap_keeps_the_rest_for_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MANUAL_DETAIL_MAX", 1)
    seed(tmp_path, ["bh-01_8001", "bh-01_8003"])
    res, _, sess, _ = go(W(), tmp_path, Options(only={"hobby_item"}))
    assert len(detail_calls(sess)) == 1 and set(items_of(tmp_path)) == {"bh-01_8001"} and res["meta"]["sources"]["hobby_item"]["manual"]["requested"] == 1
    res, _, sess, _ = go(W(), tmp_path, Options(only={"hobby_item"}))
    assert set(items_of(tmp_path)) == {"bh-01_8001", "bh-01_8003"} and len(detail_calls(sess)) == 1


def test_existing_provisional_item_is_fetched_first_and_kept_when_its_brand_is_excluded(tmp_path):
    w = W()
    w.schedule["2026-10"].append({"num": "01_8003", "title": "ドラゴンクエスト スライム", "date": "2026年10月17日 (土)"})
    seed(tmp_path, ["bh-01_8003"])
    go(w, tmp_path, Options(only={"hobby_schedule"}))                                  # 일정 카드로 임시 항목만 생긴 상태
    assert "bh-01_8003" not in items_of(tmp_path) or items_of(tmp_path)["bh-01_8003"]["detailAt"] is None
    go(w, tmp_path, Options(only={"hobby_item"}))
    it = items_of(tmp_path)["bh-01_8003"]
    assert it["line"] == "other" and it["manual"] is True and it["detailAt"]
    assert "bh-01_8003" not in read(tmp_path, "catalog-pending.json")["excluded"]


def test_already_registered_items_are_left_alone(tmp_path):
    w = W()
    go(w, tmp_path, Options(bootstrap=True, from_month="2026-09"))               # 상세까지 끝난 항목
    seed(tmp_path, ["bh-01_7001"])
    before = items_of(tmp_path)["bh-01_7001"]
    res, _, sess, _ = go(w, tmp_path, Options(only={"hobby_item"}))
    assert "manual" not in items_of(tmp_path)["bh-01_7001"] and items_of(tmp_path)["bh-01_7001"] == before
    assert res["meta"]["sources"]["hobby_item"]["manual"]["requested"] == 0


def test_other_items_are_translated_but_never_matched_or_fed(tmp_path):
    from types import SimpleNamespace

    def create(**kw):
        rows = json.loads(kw["messages"][0]["content"])
        text = json.dumps({"items": [{"id": r["id"], "ko": f"한글 {r['id']}"} for r in rows]}, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    seed(tmp_path, ["bh-01_8003"])
    go(W(), tmp_path, Options(only={"hobby_item", "translate"}), anthropic_client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    it = items_of(tmp_path)["bh-01_8003"]
    assert it["nameKo"] == "한글 bh-01_8003" and it["seriesKo"] == "한글 dq"
