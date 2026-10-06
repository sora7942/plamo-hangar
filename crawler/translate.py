"""nameKo 번역 (SPEC 5장) — Claude API.

- `nameKo`가 없는 건프라·걸프라 항목만, 50개씩, 실행당 최대 TRANSLATE_MAX_PER_RUN개
- 모델은 config.CLAUDE_MODEL (환경변수 CLAUDE_MODEL로 덮어쓰기), 키는 ANTHROPIC_API_KEY (.env)
- 키가 없으면 통째로 건너뛴다. 이미 nameKo가 있으면(3단계에서 조이하비 이름이 먼저 채워질 수 있다) 건드리지 않는다
- 응답은 JSON 스키마로 강제(output_config.format)하고, id가 요청과 맞는 것만 받는다
- 수동 확인: python -m crawler.translate --sample 20   (fixture 제목 20개를 한 번 번역해 출력. 테스트에서는 호출하지 않는다)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from . import config
from .catalog import Catalog

log = logging.getLogger("plamo.translate")

SYSTEM_PROMPT = """너는 반다이 프라모델(건프라·걸프라) 상품명을 한국어로 옮기는 번역가다.
- 한국 반다이 정식 수입사와 국내 프라모델 매장이 쓰는 한국어 명칭을 따른다. 모르는 고유명사(기체·캐릭터·작품명)는 한국 팬 커뮤니티에서 통용되는 표기를 우선하고, 없으면 일본어 발음대로 음역한다.
- `HG`, `RG`, `MG`, `PG`, `MGSD`, `EG`, `30MS`, `Figure-rise Standard` 같은 등급 표기와 `1/144` 같은 스케일, `[カラーB]` 같은 색상 기호, `Ver.` 표기는 그대로 둔다.
- 입력 목록의 모든 항목에 대해 `{"id", "ko"}` 하나씩만 돌려준다. id는 그대로 복사한다. 설명이나 주석은 쓰지 않는다.
- `grade`·`series`는 번역 힌트일 뿐이다. `ko`에 덧붙이지 않는다."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "ko": {"type": "string"}},
        "required": ["id", "ko"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}


class TranslateError(Exception):
    """응답을 쓸 수 없음 (거절·잘림·형식 오류)."""


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def make_client():
    import anthropic
    return anthropic.Anthropic()          # ANTHROPIC_API_KEY 환경변수를 쓴다


def _payload(batch: list[dict]) -> str:
    rows = []
    for it in batch:
        row = {"id": it["id"], "ja": it["nameJa"]}
        if it.get("grade"):
            row["grade"] = it["grade"]
        if it.get("series"):
            row["series"] = it["series"]
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def parse_response(text: str, wanted: set[str]) -> dict[str, str]:
    """응답 JSON → {id: ko}. 요청에 없는 id·빈 문자열은 버린다. 형식이 틀리면 TranslateError."""
    try:
        data = json.loads(text)
        rows = data["items"]
    except (ValueError, KeyError, TypeError) as e:
        raise TranslateError(f"응답 JSON 형식 오류: {type(e).__name__}") from e
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id") in wanted and isinstance(r.get("ko"), str) and r["ko"].strip():
            out[r["id"]] = r["ko"].strip()[:200]
    return out


def translate_batch(client, model: str, batch: list[dict]) -> tuple[dict[str, str], dict]:
    """한 배치를 번역한다. → ({id: ko}, usage 요약)."""
    resp = client.messages.create(
        model=model,
        max_tokens=config.TRANSLATE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _payload(batch)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise TranslateError(f"stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    usage = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
    return parse_response(text, {i["id"] for i in batch}), usage


def translate_pending(catalog: Catalog, now_iso: str, *, client=None, model: str | None = None,
                      max_items: int = config.TRANSLATE_MAX_PER_RUN, batch_size: int = config.TRANSLATE_BATCH) -> dict:
    """nameKo가 없는 항목을 번역해 catalog에 채운다. → meta용 결과 {ok, done, pending, skipped, error}."""
    model = model or config.CLAUDE_MODEL
    todo = catalog.untranslated(max_items)
    if not todo:
        return {"ok": True, "done": 0, "pending": 0, "skipped": None, "error": None, "model": model}
    if client is None:
        if not has_credentials():
            log.warning("ANTHROPIC_API_KEY가 없어 번역을 건너뜁니다 (대상 %d개)", len(todo))
            return {"ok": True, "done": 0, "pending": len(todo), "skipped": "no api key", "error": None, "model": model}
        client = make_client()

    done, tokens_in, tokens_out, error = 0, 0, 0, None
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        got: dict[str, str] = {}
        for attempt in (1, 2):                                  # 형식 오류는 1회 재시도, 그래도 안 되면 그 배치만 건너뜀
            try:
                got, usage = translate_batch(client, model, batch)
                tokens_in += usage["in"]
                tokens_out += usage["out"]
                break
            except TranslateError as e:
                log.warning("번역 응답 오류(%d차): %s", attempt, e)
            except Exception as e:                              # anthropic.APIError 등 — 이후 호출도 실패할 가능성이 커서 중단
                error = f"{type(e).__name__}"
                log.warning("번역 API 호출 실패: %s — 이번 실행의 번역을 중단합니다", error)
                break
        if error:
            break
        for it in batch:
            ko = got.get(it["id"])
            if ko:
                it["nameKo"] = ko
                it["updated"] = now_iso
                done += 1
    pending = len(catalog.untranslated(10**9))
    return {"ok": error is None, "done": done, "pending": pending, "skipped": None, "error": error, "model": model,
            "tokens": {"in": tokens_in, "out": tokens_out}}


# ---------------------------------------------------------------- 수동 샘플 (python -m crawler.translate --sample 20)
def _sample_titles(n: int) -> list[dict]:
    from .catalog import classify_title
    from .sources.hobby_brand import parse_brand_page
    from .sources.hobby_schedule import parse_schedule

    fx = config.ROOT / "tests" / "fixtures"
    cards = []
    for name in ("hobby-schedule-202210.html", "hobby-schedule-202610.html"):
        cards += parse_schedule((fx / name).read_text(encoding="utf-8"))
    cards += parse_brand_page((fx / "hobby-brand-30ms.html").read_text(encoding="utf-8"))["items"]
    seen, picked = set(), []
    for c in cards:
        line, grade = classify_title(c["nameJa"])
        if line and c["nameJa"] not in seen:
            seen.add(c["nameJa"])
            picked.append({"id": c["id"], "nameJa": c["nameJa"], "grade": grade})
    step = max(1, len(picked) // n)
    return picked[::step][:n]


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv()
    ap = argparse.ArgumentParser(description="번역 품질 확인용 — fixture 제목을 한 번 번역해 출력한다")
    ap.add_argument("--sample", type=int, default=20)
    args = ap.parse_args(argv)
    if not has_credentials():
        print("ANTHROPIC_API_KEY가 없습니다. .env에 넣은 뒤 다시 실행하세요. (호출하지 않았습니다)")
        return 0
    batch = _sample_titles(args.sample)
    got, usage = translate_batch(make_client(), config.CLAUDE_MODEL, batch)
    print(f"model={config.CLAUDE_MODEL}  tokens in/out={usage['in']}/{usage['out']}")
    for it in batch:
        print(f"{it['nameJa']}  →  {got.get(it['id'], '(번역 없음)')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
