"""호비사이트 파서 — 일정(3묶음), 브랜드 목록, 상세. 실제 응답 fixture로만 검사한다."""
import json
from collections import Counter

import pytest

from conftest import fixture_text
from crawler.sources.hobby_brand import brand_url, parse_brand_page
from crawler.sources.hobby_item import is_stable_image, parse_detail
from crawler.sources.hobby_schedule import (month_add, month_range, parse_price, parse_release, parse_schedule,
                                            schedule_url)


# ---------------------------------------------------------------- 일정
def test_schedule_202610_three_groups_and_ids():
    cards = parse_schedule(fixture_text("hobby-schedule-202610.html"))
    assert len(cards) == 21
    assert Counter(c["channel"] for c in cards) == {"general": 17, "online": 4}
    general = next(c for c in cards if c["id"] == "bh-01_7121")
    assert general == {"id": "bh-01_7121", "url": "https://bandai-hobby.net/item/01_7121/",
                       "nameJa": "ドラゴンクエストねんどモンスターズ スライム", "priceJpy": 770, "channel": "general",
                       "pbUrl": None, "release": {"month": "2026-10", "date": "2026-10-17"}}
    online = [c for c in cards if c["channel"] == "online"]
    assert all(c["id"].startswith("pb-item-") and c["pbUrl"] == c["url"] and c["release"].get("date") is None for c in online)
    assert next(c for c in online if c["id"] == "pb-item-1000253221")["nameJa"].startswith("ＭＧ 1/100")   # 전각 그대로 보관


def test_schedule_202210_gbase_and_sidef_map_to_gbase():
    cards = parse_schedule(fixture_text("hobby-schedule-202210.html"))
    assert Counter(c["channel"] for c in cards) == {"general": 9, "online": 3, "gbase": 3}
    assert next(c for c in cards if c["id"] == "bh-01_4354")["channel"] == "gbase"     # GUNDAM SIDE-F
    assert next(c for c in cards if c["id"] == "bh-01_4257")["release"] == {"month": "2022-10", "date": "2022-10-01"}


def test_schedule_old_month_has_month_only_dates():
    cards = parse_schedule(fixture_text("hobby-schedule-199510.html"))
    assert len(cards) == 4 and cards[0]["release"] == {"month": "1995-10"}


def test_schedule_never_keeps_thumbnails_or_signed_urls():
    cards = parse_schedule(fixture_text("hobby-schedule-202610.html"))
    assert "Expires=" not in json.dumps(cards) and "cloudfront" not in json.dumps(cards)


def test_release_and_price_parsing():
    assert parse_release("2026年10月17日 (土)") == {"month": "2026-10", "date": "2026-10-17"}
    assert parse_release("2027年03月") == {"month": "2027-03"}
    assert parse_release("発売日未定") is None and parse_release("2026年13月") is None
    assert parse_price("1,320円(税10%込)") == 1320 and parse_price("価格未定") is None


def test_month_helpers_and_url():
    assert month_add("2026-11", 3) == "2027-02" and month_add("2026-01", -1) == "2025-12"
    assert month_range("2026-11", "2027-01") == ["2026-11", "2026-12", "2027-01"]
    assert schedule_url("2026-10").endswith("/schedule/index.php?saledate=202610")


# ---------------------------------------------------------------- 브랜드 목록
def test_brand_page_cards_exclude_slides_and_find_last_page():
    data = parse_brand_page(fixture_text("hobby-brand-30ms.html"))
    assert len(data["items"]) == 10 and data["last_page"] == 20
    assert data["items"][0]["id"] == "bh-01_7394" and data["items"][0]["release"] == {"month": "2027-03"}
    assert len({c["id"] for c in data["items"]}) == 10                # 슬라이드(p-slide__link) 링크가 섞이지 않았다


def test_brand_url_pages():
    assert brand_url("30ms") == "https://bandai-hobby.net/brand/30ms/"
    assert brand_url("30ms", 3) == "https://bandai-hobby.net/brand/30ms/?p=3"


# ---------------------------------------------------------------- 상세
@pytest.mark.parametrize("num,keys,series,grade_name,n_images", [
    ("01_4257", ["hg"], "g-witch", "HG 1/144 ガンダムエアリアル", 11),
    ("01_4259", ["figurerise-standard"], "g-witch", "Figure-rise Standard スレッタ・マーキュリー", 11),
    ("01_3024", ["hg", "pb_gunpla", "pb_hg"], "x", "ＨＧ 1/144 ドートレス", 10),
    ("01_1547", [], "endlesswaltz", "1/60 ウイングガンダムゼロ", 1),
])
def test_detail_fields(num, keys, series, grade_name, n_images):
    d = parse_detail(fixture_text(f"hobby-item-{num}.html"))
    assert d["nameJa"] == grade_name and d["brandKeys"] == keys and d["seriesKey"] == series
    assert len(d["images"]) == n_images and all(is_stable_image(u) for u in d["images"])


def test_detail_price_release_pblink():
    d = parse_detail(fixture_text("hobby-item-01_4257.html"))
    assert d["priceJpy"] == 1760 and d["release"] == {"month": "2022-10", "date": "2022-10-01"}
    assert d["pbUrl"] == "https://p-bandai.jp/item/item-1000188677/"
    assert d["images"][0] == "https://bandai-a.akamaihd.net/bc/img/model/xl/1000179163_1.jpg"     # 갤러리 순서 그대로


def test_detail_drops_signed_urls():
    for num in ("01_6969", "01_7142"):                                # 서명 URL뿐인 상품
        d = parse_detail(fixture_text(f"hobby-item-{num}.html"))
        assert d["images"] == []
        assert d["brandKeys"]                                         # 이미지가 없어도 나머지는 파싱된다


def test_is_stable_image_rules():
    assert is_stable_image("https://bandai-a.akamaihd.net/bc/img/model/xl/1_1.jpg")
    assert is_stable_image("https://bandai-hobby.net/images/153_1_s_abc.jpg")
    assert not is_stable_image("https://bandai-hobby.net/images/common/ico_gunpla.png")      # 로고·아이콘
    assert not is_stable_image("https://bandai-hobby.net/img/x.jpg")
    assert not is_stable_image("https://d3bk8pkqsprcvh.cloudfront.net/hobby/jp/product/a.jpg")
    assert not is_stable_image("https://bandai-a.akamaihd.net/x.jpg?Expires=1&Signature=a")  # 호스트가 안정이어도 서명이면 버린다
    assert not is_stable_image("data:image/png;base64,AAAA") and not is_stable_image("") and not is_stable_image("/images/a.jpg")
