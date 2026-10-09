"""엔 정가 → 원화 추정가(세전 × 12): 식, 사이트와의 상수 일치, 몰 연결 항목 전체 일치율. 네트워크 없음."""
import re

import pytest

from crawler import config, price


# 몰 연결 항목의 실제 (엔 정가, 몰 판매가) 쌍
REAL = [(3080, 33600), (4950, 54000), (1760, 19200), (550, 6000), (660, 7200), (1980, 21600), (2750, 30000), (3300, 36000), (4290, 46800), (4620, 50400), (7700, 84000)]


@pytest.mark.parametrize("jpy,krw", REAL)
def test_estimate_matches_real_mall_prices(jpy, krw):
    assert price.estimate_krw(jpy) == krw
    assert krw / jpy == pytest.approx(12 / 1.1, rel=0.01), "몰 연결 비율 10.91과 같은 이야기"


def test_estimate_edge_cases():
    assert price.estimate_krw("4950") == 54000
    for bad in (None, 0, -5, "", "x", float("nan"), float("inf")):
        assert price.estimate_krw(bad) is None, bad


def test_site_constants_are_the_same_as_config():
    js = (config.ROOT / "docs" / "catalog.js").read_text(encoding="utf-8")
    assert int(re.search(r"var KR_PRICE_RATE = (\d+);", js).group(1)) == config.KR_PRICE_RATE == 12
    assert float(re.search(r"var JP_TAX_DIVISOR = ([\d.]+);", js).group(1)) == config.JP_TAX_DIVISOR == 1.1


def test_match_report_counts_same_and_different():
    items = [{"id": "a", "priceJpy": 3080, "priceKrw": 33600}, {"id": "b", "priceJpy": 8030, "priceKrw": 78000, "mallSoldOut": True, "nameKo": "다름"},
             {"id": "c", "priceJpy": 3080}, {"id": "d", "priceKrw": 1000}]
    rep = price.match_report(items)
    assert (rep["pairs"], rep["same"], rep["rate"]) == (2, 1, 0.5)
    assert rep["diff"] == [{"id": "b", "nameKo": "다름", "priceJpy": 8030, "estimate": 87600, "priceKrw": 78000, "delta": -9600, "soldOut": True}]
    assert price.match_report([])["rate"] is None


def test_repo_catalog_estimate_rate(capsys):
    """저장소의 카탈로그에서 몰 연결 항목의 추정식 일치율 (연결이 아직 적으면 건너뜀)."""
    rep = price.match_report(price.load_items())
    if rep["pairs"] < 30:
        pytest.skip("몰 연결 항목이 적다")
    assert rep["rate"] >= 0.95, f"{rep['same']}/{rep['pairs']}"
    assert price.main(["--show", "3"]) == 0
    assert "정확히 같음" in capsys.readouterr().out
