"""SPEC 4장 형식 검사 — 테스트와 실제 실행 결과 확인(`python tests/schema_check.py <data-dir>`)에 같이 쓴다."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ISO_KST = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")
STABLE_HOSTS = {"bandai-a.akamaihd.net", "bandai-hobby.net"}
CATALOG_ID = re.compile(r"^(bh-01_\d+|pb-item-\d+)$")
FEED_ID = re.compile(r"^(bh-new-01_\d+|pb-new-item-\d+|jh-\d+-[A-Z0-9]+)$")


def _opt_str(v):
    return v is None or isinstance(v, str)


def check_release(rel, where):
    errs = []
    if rel is None:
        return errs
    if not (isinstance(rel, dict) and re.fullmatch(r"\d{4}-\d{2}", rel.get("month", ""))):
        return [f"{where}: release.month 형식 오류 {rel!r}"]
    if "date" in rel and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", rel["date"]) and rel["date"].startswith(rel["month"])):
        errs.append(f"{where}: release.date 형식 오류 {rel!r}")
    return errs


def check_catalog_item(it: dict, line: str | None) -> list[str]:
    w = it.get("id", "?")
    errs = []
    if not CATALOG_ID.match(w):
        errs.append(f"{w}: id 형식")
    if it.get("line") != line:
        errs.append(f"{w}: line {it.get('line')!r} != 파일의 {line!r}")
    if not (isinstance(it.get("brandKeys"), list) and all(isinstance(k, str) for k in it["brandKeys"])):
        errs.append(f"{w}: brandKeys")
    for k in ("grade", "scale", "seriesKey", "series", "nameKo", "pbUrl", "channel"):
        if k not in it or not _opt_str(it[k]):
            errs.append(f"{w}: {k} 누락/형식")
    if it.get("channel") not in (None, "general", "online", "gbase"):
        errs.append(f"{w}: channel {it.get('channel')!r}")
    if not (isinstance(it.get("nameJa"), str) and it["nameJa"]):
        errs.append(f"{w}: nameJa")
    if not (it.get("priceJpy") is None or isinstance(it["priceJpy"], int)):
        errs.append(f"{w}: priceJpy")
    if not str(it.get("url", "")).startswith("https://"):
        errs.append(f"{w}: url")
    errs += check_release(it.get("release"), w)
    if not isinstance(it.get("kr"), list):
        errs.append(f"{w}: kr")
    imgs = it.get("images")
    if not isinstance(imgs, list):
        errs.append(f"{w}: images")
    else:
        for u in imgs:
            if urlparse(u).netloc not in STABLE_HOSTS or "Expires=" in u or "Signature=" in u:
                errs.append(f"{w}: 안정 URL이 아닌 이미지 {u[:60]}")
    for k in ("firstSeen", "updated"):
        if not ISO_KST.match(str(it.get(k, ""))):
            errs.append(f"{w}: {k} 형식")
    if not (it.get("detailAt") is None or ISO_KST.match(str(it["detailAt"]))):
        errs.append(f"{w}: detailAt 형식")
    return errs


def check_catalog_file(doc: dict, line: str | None) -> list[str]:
    errs = []
    if not ISO_KST.match(str(doc.get("updatedAt", ""))):
        errs.append("catalog updatedAt 형식")
    ids = [i.get("id") for i in doc.get("items", [])]
    if len(ids) != len(set(ids)):
        errs.append("catalog id 중복")
    for it in doc.get("items", []):
        errs += check_catalog_item(it, line)
    return errs


def check_feed(doc: dict) -> list[str]:
    errs = []
    if not ISO_KST.match(str(doc.get("updatedAt", ""))):
        errs.append("feed updatedAt 형식")
    items = doc.get("items", [])
    if len(items) > 1000:
        errs.append("feed 1000개 초과")
    if len({i.get("id") for i in items}) != len(items):
        errs.append("feed id 중복")
    addeds = [i.get("added", "") for i in items]
    if addeds != sorted(addeds, reverse=True):
        errs.append("feed added 내림차순 아님")
    for it in items:
        w = it.get("id", "?")
        if not FEED_ID.match(w):
            errs.append(f"{w}: id 형식")
        if it.get("type") not in ("new", "pb-new", "kr-restock", "kr-new"):
            errs.append(f"{w}: type")
        if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(it.get("date", ""))):
            errs.append(f"{w}: date")
        if not ISO_KST.match(str(it.get("added", ""))):
            errs.append(f"{w}: added")
        if not (isinstance(it.get("title"), str) and it["title"] and _opt_str(it.get("titleKo")) and _opt_str(it.get("catalogId"))):
            errs.append(f"{w}: title/titleKo/catalogId")
        if not str(it.get("url", "")).startswith("https://"):
            errs.append(f"{w}: url")
        img = it.get("image")
        if img is not None and (urlparse(img).netloc not in STABLE_HOSTS or "Expires=" in img):
            errs.append(f"{w}: image가 안정 URL이 아님")
        if it.get("source") not in ("bandai-hobby", "joyhobby"):
            errs.append(f"{w}: source")
    return errs


def check_meta(doc: dict) -> list[str]:
    errs = []
    if not ISO_KST.match(str(doc.get("updatedAt", ""))):
        errs.append("meta updatedAt 형식")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(doc.get("since", ""))):
        errs.append("meta since 형식")
    srcs = doc.get("sources")
    if not (isinstance(srcs, dict) and srcs):
        errs.append("meta sources 없음")
    for name, s in (srcs or {}).items():
        if not (isinstance(s.get("ok"), bool) and ISO_KST.match(str(s.get("at", ""))) and isinstance(s.get("items"), int)
                and _opt_str(s.get("error"))):
            errs.append(f"meta.sources.{name} 형식")
    if not isinstance(doc.get("crawl"), dict):
        errs.append("meta.crawl")
    return errs


def check_dir(d: Path) -> list[str]:
    d = Path(d)
    errs = []
    for name, line in (("catalog-gunpla.json", "gunpla"), ("catalog-girl.json", "girl"), ("catalog-pending.json", None)):
        p = d / name
        if p.exists():
            errs += [f"{name}: {e}" for e in check_catalog_file(json.loads(p.read_text(encoding="utf-8")), line)]
        else:
            errs.append(f"{name} 없음")
    for name, fn in (("feed.json", check_feed), ("meta.json", check_meta)):
        p = d / name
        errs += [f"{name}: {e}" for e in fn(json.loads(p.read_text(encoding="utf-8")))] if p.exists() else [f"{name} 없음"]
    return errs


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    problems = check_dir(Path(sys.argv[1]))
    print("\n".join(problems) if problems else "OK — SPEC 4장 형식과 일치")
    raise SystemExit(1 if problems else 0)
