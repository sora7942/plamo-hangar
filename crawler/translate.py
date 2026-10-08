"""nameKo 번역 (SPEC 5장) — Claude API.

- `nameKo`가 없는 건프라·걸프라 항목만, 50개씩, 실행당 최대 TRANSLATE_MAX_PER_RUN개
- 모델은 config.CLAUDE_MODEL (환경변수 CLAUDE_MODEL로 덮어쓰기), 키는 ANTHROPIC_API_KEY (.env)
- 키가 없으면 통째로 건너뛴다. 이미 nameKo가 있으면(3단계에서 조이하비 이름이 먼저 채워질 수 있다) 건드리지 않는다
- 응답은 JSON 스키마로 강제(output_config.format)하고, id가 요청과 맞는 것만 받는다
- 번역 결과에 히라가나·가타카나가 남아 있거나 **원문에 없는 한자**(중국어식 `达` 같은 오번역)가 섞여 있으면 그 항목만 한 번 더 요청하고, 그래도 남으면 nameKo를 비워 둔다
  (다음 실행에서 다시 시도한다)
- 고유명사 용어집은 config.TRANSLATE_GLOSSARY 에 두고 시스템 프롬프트에 넣는다
- 수동 확인: python -m crawler.translate --sample 20   (fixture 제목 20개를 실제 파이프라인과 같은 경로로 번역해 출력.
  테스트에서는 호출하지 않는다)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field

from . import config
from .catalog import Catalog

log = logging.getLogger("plamo.translate")

_BASE_PROMPT = """너는 반다이 프라모델(건프라·걸프라) 상품명을 한국어로 옮기는 번역가다.
- 한국 반다이 정식 수입사와 국내 프라모델 매장이 쓰는 한국어 명칭을 따른다. 모르는 고유명사(기체·캐릭터·작품명)는 한국 팬 커뮤니티에서 통용되는 표기를 우선하고, 없으면 일본어 발음대로 음역한다.
- `HG`, `RG`, `MG`, `PG`, `MGSD`, `EG`, `30MS`, `Figure-rise Standard` 같은 등급 표기와 `1/144` 같은 스케일, `Ver.` 표기, 모델 번호는 그대로 둔다. `Amplified`(アンプリファイド)는 번역하거나 음역하지 말고 영문 `Amplified` 그대로 쓴다. 대괄호 색상 기호는 알파벳 부분만 그대로 두고 일본어 부분은 한글로 옮긴다 (`[カラーC]` → `[컬러C]`).
- `ko`에는 히라가나·가타카나(일본어 가나)를 한 글자도 남기지 않는다. 한글, 영문, 숫자, 기호만 쓴다. 한자(중국어 한자 포함)도 새로 쓰지 않는다 — 원문에 있는 `89式`·`改` 같은 표기만 그대로 둘 수 있다.
- 입력 항목에 `prev_ko`가 있으면 앞선 번역에 일본어 가나 또는 원문에 없는 한자가 남아 있었다는 뜻이다. 가나·한자가 하나도 남지 않도록 모두 한글로 다시 쓴다.
- 입력 목록의 모든 항목에 대해 `{"id", "ko"}` 하나씩만 돌려준다. id는 그대로 복사한다. 설명이나 주석은 쓰지 않는다.
- `grade`·`series`는 번역 힌트일 뿐이다. `ko`에 덧붙이지 않는다."""


def build_system_prompt(glossary: dict[str, str]) -> str:
    """기본 지침 + 용어집. 용어집이 비어 있으면 기본 지침만."""
    if not glossary:
        return _BASE_PROMPT
    lines = [_BASE_PROMPT, "",
             "용어집 (일본어 → 지정 표기). 상품명에 아래 용어가 들어 있으면 반드시 이 표기를 쓴다. 표기가 영문이면 영문 그대로 쓴다. "
             "다른 말과 붙어 있어도(예: `グエル・ジェターク`의 `グエル`) 해당 부분은 이 표기를 따른다:"]
    lines += [f"- {ja} → {ko}" for ja, ko in glossary.items()]
    return "\n".join(lines)


SYSTEM_PROMPT = build_system_prompt(config.TRANSLATE_GLOSSARY)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "ko": {"type": "string"}},
        "required": ["id", "ko"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}

# 히라가나(ぁ-ゖ, 반복 기호), 가타카나(ァ-ヺ, 장음 ー, ヽヾヿ), 가타카나 확장, 반각 가타카나.
# 중점 `・`(U+30FB)는 가나가 아니라 구두점이라 뺀다 — 한국어 번역에 남아도 읽는 데 문제가 없다.
_KANA_RX = re.compile("[ぁ-ゖゝ-ゟァ-ヺー-ヿㇰ-ㇿｦ-ﾟ]")


def has_kana(text: str) -> bool:
    return bool(_KANA_RX.search(text or ""))


# 한자(CJK 통합 한자 + 확장 A). 일본어 원문에도 있는 한자(`89式`·`改`)는 정상이고, **원문에 없는** 한자가 번역에 나오면
# 모델이 중국어로 새어 나온 것이다(`ヴィダール` → `비达르`). 가나 검사가 못 거르는 오번역이라 따로 본다.
_HAN_RX = re.compile("[㐀-䶿一-鿿]")


def stray_han(ja: str | None, ko: str | None) -> str:
    """번역(ko)에 있는데 원문(ja)에는 없는 한자들 (없으면 빈 문자열)."""
    src = set(_HAN_RX.findall(ja or ""))
    return "".join(sorted({c for c in _HAN_RX.findall(ko or "") if c not in src}))


def bad_translation(ja: str | None, ko: str | None) -> bool:
    """다시 번역해야 하는 결과인가: 가나가 남았거나 원문에 없는 한자가 섞였다."""
    return has_kana(ko or "") or bool(stray_han(ja, ko))


class TranslateError(Exception):
    """응답을 쓸 수 없음 (거절·잘림·형식 오류)."""


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def make_client():
    import anthropic
    return anthropic.Anthropic()          # ANTHROPIC_API_KEY 환경변수를 쓴다


def _payload(batch: list[dict], previous: dict[str, str] | None = None) -> str:
    rows = []
    for it in batch:
        row = {"id": it["id"], "ja": it["nameJa"]}
        if it.get("grade"):
            row["grade"] = it["grade"]
        if it.get("series"):
            row["series"] = it["series"]
        if previous and it["id"] in previous:
            row["prev_ko"] = previous[it["id"]]
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


def translate_batch(client, model: str, batch: list[dict], previous: dict[str, str] | None = None) -> tuple[dict[str, str], dict]:
    """한 배치를 번역한다(요청 1회). → ({id: ko}, usage 요약). previous가 있으면 항목마다 `prev_ko`로 함께 보낸다."""
    resp = client.messages.create(
        model=model,
        max_tokens=config.TRANSLATE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _payload(batch, previous)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise TranslateError(f"stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    usage = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
    return parse_response(text, {i["id"] for i in batch}), usage


@dataclass
class BatchResult:
    ok: dict[str, str] = field(default_factory=dict)        # 가나가 없는 번역만 (적용 대상)
    retried: set[str] = field(default_factory=set)          # 가나가 남아 한 번 더 요청한 id
    rejected: set[str] = field(default_factory=set)         # 재요청 후에도 가나가 남아 비워 둔 id
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None                                # API 호출 실패 (이후 호출도 중단해야 함)


_NO_USAGE = {"in": 0, "out": 0}


def _request(client, model: str, batch: list[dict], previous: dict[str, str] | None, attempts: int):
    """→ (got | None(응답 형식 오류가 계속됨), usage, error | None). 형식 오류만 attempts번까지 다시 묻는다."""
    for attempt in range(1, attempts + 1):
        try:
            got, usage = translate_batch(client, model, batch, previous)
            return got, usage, None
        except TranslateError as e:
            log.warning("번역 응답 오류(%d/%d차): %s", attempt, attempts, e)
        except Exception as e:                                # anthropic.APIError 등 — 이후 호출도 실패할 가능성이 커서 중단
            name = type(e).__name__
            log.warning("번역 API 호출 실패: %s — 이번 실행의 번역을 중단합니다", name)
            return None, _NO_USAGE, name
    return None, _NO_USAGE, None


def translate_items(client, model: str, batch: list[dict]) -> BatchResult:
    """한 배치를 번역하고 가나 검사까지 한다.

    1. 요청 (응답 형식 오류는 1회 재시도)
    2. 가나가 남은 항목이 있으면 **그 항목만 한 번** 다시 요청 (앞선 번역을 prev_ko로 알려 줌)
    3. 그래도 가나가 남으면 결과에서 뺀다 → nameKo가 비어 있어 다음 실행에서 다시 시도된다
    """
    res = BatchResult()
    got, usage, err = _request(client, model, batch, None, attempts=2)
    res.tokens_in += usage["in"]
    res.tokens_out += usage["out"]
    if err:
        res.error = err
        return res
    got = got or {}
    ja_of = {it["id"]: it["nameJa"] for it in batch}
    res.ok = {i: ko for i, ko in got.items() if not bad_translation(ja_of.get(i), ko)}
    bad = [it for it in batch if it["id"] in got and bad_translation(it["nameJa"], got[it["id"]])]
    if not bad:
        return res

    res.retried = {it["id"] for it in bad}
    log.info("번역에 가나·원문에 없는 한자가 남은 %d개를 다시 요청합니다", len(bad))
    again, usage, err = _request(client, model, bad, {it["id"]: got[it["id"]] for it in bad}, attempts=1)
    res.tokens_in += usage["in"]
    res.tokens_out += usage["out"]
    res.error = err
    for it in bad:
        ko = (again or {}).get(it["id"])
        if ko and not bad_translation(it["nameJa"], ko):
            res.ok[it["id"]] = ko
        else:
            res.rejected.add(it["id"])
    if res.rejected:
        log.warning("재요청 후에도 가나가 남아 nameKo를 비워 둡니다: %d개 (다음 실행에서 재시도)", len(res.rejected))
    return res


def translate_pending(catalog: Catalog, now_iso: str, *, client=None, model: str | None = None,
                      max_items: int = config.TRANSLATE_MAX_PER_RUN, batch_size: int = config.TRANSLATE_BATCH) -> dict:
    """nameKo가 없는 항목을 번역해 catalog에 채운다. → meta용 결과 {ok, done, pending, skipped, error, ...}."""
    model = model or config.CLAUDE_MODEL
    todo = catalog.untranslated(max_items)
    base = {"skipped": None, "error": None, "model": model, "kanaRetried": 0, "kanaRejected": 0}
    if not todo:
        return {"ok": True, "done": 0, "pending": 0, **base}
    if client is None:
        if not has_credentials():
            log.warning("ANTHROPIC_API_KEY가 없어 번역을 건너뜁니다 (대상 %d개)", len(todo))
            return {"ok": True, "done": 0, "pending": len(todo), **base, "skipped": "no api key"}
        client = make_client()

    done, tokens_in, tokens_out, error = 0, 0, 0, None
    retried = rejected = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        r = translate_items(client, model, batch)
        tokens_in += r.tokens_in
        tokens_out += r.tokens_out
        retried += len(r.retried)
        rejected += len(r.rejected)
        for it in batch:
            ko = r.ok.get(it["id"])
            if ko and not it.get("nameKoSource"):                # 조이하비·몰의 한글명으로 교체된 항목은 번역이 건드리지 않는다
                it["nameKo"] = ko
                it["updated"] = now_iso
                done += 1
        if r.error:                                           # 재요청 중 실패해도 앞서 확정된 번역은 위에서 이미 반영했다
            error = r.error
            break
    pending = len(catalog.untranslated(10**9))
    return {"ok": error is None, "done": done, "pending": pending, **base, "error": error,
            "kanaRetried": retried, "kanaRejected": rejected, "tokens": {"in": tokens_in, "out": tokens_out}}


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
    ap = argparse.ArgumentParser(description="번역 품질 확인용 — fixture 제목을 실제 파이프라인과 같은 경로로 번역해 출력한다")
    ap.add_argument("--sample", type=int, default=20)
    args = ap.parse_args(argv)
    if not has_credentials():
        print("ANTHROPIC_API_KEY가 없습니다. .env에 넣은 뒤 다시 실행하세요. (호출하지 않았습니다)")
        return 0
    batch = _sample_titles(args.sample)
    r = translate_items(make_client(), config.CLAUDE_MODEL, batch)
    print(f"model={config.CLAUDE_MODEL}  tokens in/out={r.tokens_in}/{r.tokens_out}  "
          f"가나 재요청 {len(r.retried)}개 · 재요청 후에도 남아 비움 {len(r.rejected)}개 · 용어집 {len(config.TRANSLATE_GLOSSARY)}개")
    for it in batch:
        i = it["id"]
        mark = ""
        if i in r.rejected:
            mark = "   [가나가 남아 nameKo 비움 — 다음 실행에서 재시도]"
        elif i in r.retried:
            mark = "   [가나가 남아 재요청함]"
        print(f"{it['nameJa']}  →  {r.ok.get(i, '(비어 있음)')}{mark}")
    if r.error:
        print(f"오류로 중단됨: {r.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
