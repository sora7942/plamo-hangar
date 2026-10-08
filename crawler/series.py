"""시리즈 한국어(seriesKo) — 카탈로그 `series`(호비사이트의 일본어 작품명)를 한국어로 옮긴다 (SPEC 4·5장, 4단계).

- seriesKey(예: `seed-d`)마다 한 번만 번역한다. 같은 키가 수백 상품에 붙어 있어서 고유 시리즈만(현재 70여 개) 번역하면 된다.
- 결과 사전은 `docs/data/series-ko.json`(크롤러만 씀)에 보관한다: `{"updatedAt", "items": {"<seriesKey>": {"ja": "<번역 당시 일본어>", "ko": "<한국어>"}}}`.
  다음 실행부터는 사전에 없는(또는 일본어 원문이 바뀐) 시리즈만 번역한다.
- 사람이 고치는 표는 `config.SERIES_KO_OVERRIDES`({seriesKey: 한국어}). 사전·번역보다 우선하고 API를 부르지 않는다.
- 사전(+덮어쓰기 표)의 값은 카탈로그 항목의 `seriesKo`로 채운다. API 키가 없어도 이미 아는 시리즈는 항상 채운다.
- 번역은 translate.py와 같은 규칙: 모델은 config.CLAUDE_MODEL, 용어집(config.TRANSLATE_GLOSSARY) 적용, JSON 스키마 강제,
  히라가나·가타카나가 남으면 그 항목만 한 번 더 요청하고 그래도 남으면 저장하지 않는다(다음 실행에서 다시 시도).
- 수동 확인: python -m crawler.series --sample 10   (실제 카탈로그의 시리즈 10개를 번역해 출력만 한다. 파일은 쓰지 않는다)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from . import config
from .catalog import Catalog
from .store import read_json, write_json
from .translate import OUTPUT_SCHEMA, TranslateError, bad_translation, has_credentials, has_kana, make_client, parse_response, stray_han

log = logging.getLogger("plamo.series")

_BASE_PROMPT = """너는 반다이 프라모델이 속한 작품(시리즈) 이름을 한국어로 옮기는 번역가다.
- 한국에서 정식 발매·방영된 제목을 따른다. 정식 제목을 모르면 한국 팬 커뮤니티에서 통용되는 표기를 쓴다. 지어내지 않는다.
- 영문·숫자 부분(`SEED`, `DESTINY`, `Re:RISE`, `00`, `Ω` 등)은 그대로 둔다. `シリーズ`는 `시리즈`로 옮긴다.
- 예: `機動戦士ガンダム 水星の魔女` → `기동전사 건담 수성의 마녀`, `機動戦士ガンダムSEED DESTINY` → `기동전사 건담 SEED DESTINY`,
  `機動戦士ガンダム　逆襲のシャア` → `기동전사 건담 역습의 샤아`.
- `ko`에는 히라가나·가타카나(일본어 가나)를 한 글자도 남기지 않는다. 한글, 영문, 숫자, 기호만 쓴다. 원문에 없는 한자(중국어 한자 포함)도 쓰지 않는다 — `怪獣8号`는 `괴수 8호`처럼 한글로 옮긴다.
- 입력 항목에 `prev_ko`가 있으면 앞선 번역에 일본어 가나가 남아 있었다는 뜻이다. 가나가 하나도 남지 않도록 다시 쓴다.
- 입력 목록의 모든 항목에 대해 `{"id", "ko"}` 하나씩만 돌려준다. id는 그대로 복사한다. 설명이나 주석은 쓰지 않는다."""


def build_system_prompt(glossary: dict[str, str]) -> str:
    if not glossary:
        return _BASE_PROMPT
    lines = [_BASE_PROMPT, "",
             "용어집 (일본어 → 지정 표기). 작품명에 아래 용어가 들어 있으면 반드시 이 표기를 쓴다. 표기가 영문이면 영문 그대로 쓴다. "
             "다른 말과 붙어 있어도 해당 부분은 이 표기를 따른다:"]
    lines += [f"- {ja} → {ko}" for ja, ko in glossary.items()]
    return "\n".join(lines)


SYSTEM_PROMPT = build_system_prompt(config.TRANSLATE_GLOSSARY)


# ---------------------------------------------------------------- 사전 파일
def load(data_dir: Path) -> dict[str, dict]:
    try:
        d = read_json(Path(data_dir) / config.SERIES_FILE, None)
    except ValueError:                       # 깨진 사전은 없는 것으로 보고 다시 번역한다 (저장할 때 새로 쓴다)
        log.warning("%s를 읽을 수 없어 사전 없이 시작합니다", config.SERIES_FILE)
        return {}
    items = d.get("items") if isinstance(d, dict) else None
    if not isinstance(items, dict):
        return {}
    return {k: {"ja": v["ja"], "ko": v["ko"]} for k, v in items.items()
            if isinstance(v, dict) and isinstance(v.get("ja"), str) and isinstance(v.get("ko"), str) and v["ko"]}


def save(data_dir: Path, known: dict[str, dict], updated_at: str) -> bool:
    """사전이 바뀌었을 때만 쓴다(updatedAt도 그대로 둔다). 쓰면 True. 비어 있고 파일도 없으면 만들지 않는다."""
    path = Path(data_dir) / config.SERIES_FILE
    try:
        prev = read_json(path, None)
    except ValueError:
        prev = {}
    body = dict(sorted(known.items()))
    if isinstance(prev, dict) and prev.get("items") == body:
        return False
    if not body and prev is None:
        return False
    write_json(path, {"updatedAt": updated_at, "items": body})
    return True


def drop_stray_han(known: dict[str, dict]) -> list[str]:
    """사전에 저장된 번역 중 원문에 없는 한자가 섞인 것을 버린다(다음 번역 때 다시 번역). 버린 seriesKey 목록."""
    bad = [k for k, e in known.items() if stray_han(e["ja"], e["ko"])]
    for k in bad:
        del known[k]
    return bad


# ---------------------------------------------------------------- 적용·대상
def _ko_for(item: dict, known: dict[str, dict], overrides: dict[str, str]) -> str | None:
    key = item.get("seriesKey")
    if not key:
        return None
    if overrides.get(key):
        return overrides[key]
    e = known.get(key)
    # 번역 당시의 일본어와 같을 때만 쓴다 (호비사이트가 시리즈 이름을 바꾸면 다시 번역한다)
    return e["ko"] if e and e["ja"] == item.get("series") else None


def apply(catalog: Catalog, known: dict[str, dict], overrides: dict[str, str] | None = None) -> int:
    """사전·덮어쓰기 표를 카탈로그 항목의 seriesKo에 채운다. 바뀐 항목 수. (updated 등 다른 필드는 건드리지 않는다)"""
    overrides = config.SERIES_KO_OVERRIDES if overrides is None else overrides
    changed = 0
    for it in catalog.items.values():
        if not it.get("seriesKey"):
            continue
        ko = _ko_for(it, known, overrides)
        if ko and it.get("seriesKo") != ko:
            it["seriesKo"] = ko
            changed += 1
        elif not ko and "seriesKo" in it:
            del it["seriesKo"]
            changed += 1
    return changed


def pending(catalog: Catalog, known: dict[str, dict], overrides: dict[str, str] | None = None) -> list[dict]:
    """번역이 필요한 고유 시리즈 [{id: seriesKey, ja: 일본어}]. 항목이 많은 시리즈 먼저."""
    overrides = config.SERIES_KO_OVERRIDES if overrides is None else overrides
    count: Counter = Counter()
    label: dict[str, str] = {}
    for it in catalog.items.values():
        key, ja = it.get("seriesKey"), it.get("series")
        if not key or not ja or _ko_for(it, known, overrides):
            continue
        count[key] += 1
        label.setdefault(key, ja)
    return [{"id": k, "ja": label[k]} for k, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))]


# ---------------------------------------------------------------- 번역 (API)
def translate_batch(client, model: str, batch: list[dict], previous: dict[str, str] | None = None) -> tuple[dict[str, str], dict]:
    rows = [({**b, "prev_ko": previous[b["id"]]} if previous and b["id"] in previous else dict(b)) for b in batch]
    resp = client.messages.create(
        model=model, max_tokens=config.TRANSLATE_MAX_TOKENS, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(rows, ensure_ascii=False)}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise TranslateError(f"stop_reason={resp.stop_reason}")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return parse_response(text, {b["id"] for b in batch}), {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}


def _request(client, model, batch, previous, attempts):
    for attempt in range(1, attempts + 1):
        try:
            got, usage = translate_batch(client, model, batch, previous)
            return got, usage, None
        except TranslateError as e:
            log.warning("시리즈 번역 응답 오류(%d/%d차): %s", attempt, attempts, e)
        except Exception as e:                                # API 호출 실패 — 이후 호출도 실패할 가능성이 커서 중단
            log.warning("시리즈 번역 API 호출 실패: %s — 이번 실행의 번역을 중단합니다", type(e).__name__)
            return None, {"in": 0, "out": 0}, type(e).__name__
    return None, {"in": 0, "out": 0}, None


def translate_items(client, model: str, batch: list[dict]) -> tuple[dict[str, str], set[str], set[str], dict, str | None]:
    """한 배치 + 가나 검사(남은 항목만 한 번 재요청). → (가나 없는 번역 {key: ko}, 재요청한 key들, 끝내 가나가 남은 key들, usage, 오류)."""
    usage = {"in": 0, "out": 0}
    got, u, err = _request(client, model, batch, None, attempts=2)
    usage = {k: usage[k] + u[k] for k in usage}
    if err:
        return {}, set(), set(), usage, err
    got = got or {}
    ja_of = {b["id"]: b["ja"] for b in batch}
    ok = {k: ko for k, ko in got.items() if not bad_translation(ja_of.get(k), ko)}
    bad = [b for b in batch if b["id"] in got and bad_translation(b["ja"], got[b["id"]])]
    retried, rejected = {b["id"] for b in bad}, set()
    if bad:
        again, u, err = _request(client, model, bad, {b["id"]: got[b["id"]] for b in bad}, attempts=1)
        usage = {k: usage[k] + u[k] for k in usage}
        for b in bad:
            ko = (again or {}).get(b["id"])
            if ko and not bad_translation(b["ja"], ko):
                ok[b["id"]] = ko
            else:
                rejected.add(b["id"])
    return ok, retried, rejected, usage, err


def translate_pending(catalog: Catalog, known: dict[str, dict], *, client=None, model: str | None = None,
                      max_items: int = config.SERIES_MAX_PER_RUN, batch_size: int = config.SERIES_BATCH) -> dict:
    """새 시리즈를 번역해 known(사전)에 넣는다. 카탈로그에는 apply()가 채운다. → meta용 {ok, done, pending, skipped, error, ...}."""
    model = model or config.CLAUDE_MODEL
    todo = pending(catalog, known)[:max_items]
    base = {"skipped": None, "error": None, "kanaRetried": 0, "kanaRejected": 0}
    if not todo:
        return {"ok": True, "done": 0, "pending": 0, **base}
    if client is None:
        if not has_credentials():
            log.warning("ANTHROPIC_API_KEY가 없어 시리즈 번역을 건너뜁니다 (대상 %d개)", len(todo))
            return {"ok": True, "done": 0, "pending": len(todo), **base, "skipped": "no api key"}
        client = make_client()
    done, error, retried, rejected = 0, None, 0, 0
    ja_of = {t["id"]: t["ja"] for t in todo}
    for i in range(0, len(todo), batch_size):
        ok, rt, rj, _usage, err = translate_items(client, model, todo[i:i + batch_size])
        retried += len(rt)
        rejected += len(rj)
        for key, ko in ok.items():
            known[key] = {"ja": ja_of[key], "ko": ko}
            done += 1
        if err:
            error = err
            break
    left = len(pending(catalog, known))
    return {"ok": error is None, "done": done, "pending": left, **base, "error": error, "kanaRetried": retried, "kanaRejected": rejected}


# ---------------------------------------------------------------- 수동 샘플 (python -m crawler.series --sample 10)
def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv()
    ap = argparse.ArgumentParser(description="시리즈 번역 품질 확인용 — 실제 카탈로그의 고유 시리즈를 번역해 출력만 한다 (파일은 쓰지 않는다)")
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = ap.parse_args(argv)
    cat = Catalog.load(args.data_dir)
    todo = pending(cat, {})
    step = max(1, len(todo) // args.sample)
    batch = todo[::step][:args.sample]
    if not has_credentials():
        print("ANTHROPIC_API_KEY가 없습니다. .env에 넣은 뒤 다시 실행하세요. (호출하지 않았습니다)")
        return 0
    ok, retried, rejected, usage, err = translate_items(make_client(), config.CLAUDE_MODEL, batch)
    print(f"model={config.CLAUDE_MODEL}  고유 시리즈 {len(todo)}개 중 {len(batch)}개  tokens in/out={usage['in']}/{usage['out']}  "
          f"가나 재요청 {len(retried)}개 · 재요청 후에도 남음 {len(rejected)}개 · 용어집 {len(config.TRANSLATE_GLOSSARY)}개")
    for b in batch:
        print(f"{b['id']:<28} {b['ja']}  →  {ok.get(b['id'], '(비어 있음)')}")
    if err:
        print(f"오류로 중단됨: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
