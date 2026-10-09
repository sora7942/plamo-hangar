"""엔 정가 → 원화 추정가 — 사이트(`docs/catalog.js` `estimateKrw`)와 같은 식의 점검용 사본.

반다이 프라모델 국내 정가 = 일본 세전 가격 × 12. 호비 `priceJpy`는 세금 10% 포함이라 `round(priceJpy / 1.1) × 12`.
(반다이남코코리아몰 판매가 ÷ 호비 정가가 연결된 항목에서 늘 10.91(= 12 ÷ 1.1)이던 것과 같은 이야기다.)

크롤러는 이 값을 저장하지 않는다 — 사이트가 화면에서만 계산한다(구매 가격 기본값의 마지막 단계, "추정"). 이 모듈은 식이 맞는지 몰 연결 항목 전체로 재 보는 용도다:

    python -m crawler.price            # 몰 연결 항목에서 "추정 == 몰 가격" 일치율과 다른 항목 목록
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from . import config


def estimate_krw(jpy) -> int | None:
    """JS의 Math.round(n / 1.1) * 12 와 같다(양수는 반올림 half-up). 엔 정가가 없거나 0 이하면 None."""
    try:
        n = float(jpy)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n <= 0:
        return None
    return math.floor(n / config.JP_TAX_DIVISOR + 0.5) * config.KR_PRICE_RATE


def match_report(items: list[dict]) -> dict:
    """몰 가격(`priceKrw`)과 엔 정가(`priceJpy`)가 둘 다 있는 항목에서 추정식이 몰 가격과 정확히 같은지.
    → {pairs, same, diff: [{id, nameKo, priceJpy, estimate, priceKrw, delta, soldOut}], rate}"""
    pairs = [i for i in items if i.get("priceKrw") and i.get("priceJpy")]
    diff = []
    for i in pairs:
        est = estimate_krw(i["priceJpy"])
        if est != i["priceKrw"]:
            diff.append({"id": i["id"], "nameKo": i.get("nameKo"), "priceJpy": i["priceJpy"], "estimate": est, "priceKrw": i["priceKrw"],
                         "delta": i["priceKrw"] - est, "soldOut": bool(i.get("mallSoldOut"))})
    same = len(pairs) - len(diff)
    return {"pairs": len(pairs), "same": same, "diff": diff, "rate": same / len(pairs) if pairs else None}


def load_items(data_dir: Path = config.DATA_DIR) -> list[dict]:
    out: list[dict] = []
    for name in config.CATALOG_FILES.values():
        p = Path(data_dir) / name
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8")).get("items", [])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="몰 연결 항목에서 엔 정가 → 원화 추정식(세전 × 12)의 일치율을 잰다")
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--show", type=int, default=10, help="다른 항목을 몇 개까지 보여 줄지")
    args = ap.parse_args(argv)
    rep = match_report(load_items(args.data_dir))
    if not rep["pairs"]:
        print("몰 가격과 엔 정가가 모두 있는 항목이 없습니다.")
        return 0
    print(f"몰 연결 항목 {rep['pairs']}개 중 추정식과 정확히 같음 {rep['same']}개 ({rep['rate'] * 100:.1f}%), 다름 {len(rep['diff'])}개")
    for d in rep["diff"][: args.show]:
        print(f"  {d['id']}  {d['nameKo']}  ¥{d['priceJpy']:,} → 추정 ₩{d['estimate']:,} / 몰 ₩{d['priceKrw']:,} (차 {d['delta']:+,}){' 품절' if d['soldOut'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
