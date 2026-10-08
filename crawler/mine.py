"""내 컬렉션(collection.json) 읽기 전용 도우미 — 크롤러는 이 파일을 절대 쓰지 않는다 (CLAUDE.md Critical).

- 사이트에서 연결한 `catalogId`를 모아, (1) 카탈로그에 아직 없는 호비 상품의 상세를 받고 (2) 디스코드 알림에서 "내 프라"를 먼저 보낸다.
- 파일이 없거나 깨졌으면 빈 결과다 (수집·알림은 그대로 계속된다).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from . import config
from .store import read_json

log = logging.getLogger("plamo.mine")

_ID_RX = re.compile(r"^(bh|pb)-[A-Za-z0-9_-]{1,60}$")      # 사이트 normKit의 catalogId 형식과 같다


def _kits(data_dir: Path) -> list[dict]:
    try:
        doc = read_json(Path(data_dir) / config.COLLECTION_FILE, {})
    except ValueError:
        log.warning("%s를 읽을 수 없어 '내 프라' 정보 없이 계속합니다", config.COLLECTION_FILE)
        return []
    kits = doc.get("kits") if isinstance(doc, dict) else None
    return [k for k in kits if isinstance(k, dict)] if isinstance(kits, list) else []


def catalog_ids(data_dir: Path) -> list[str]:
    """보유·위시에 연결된 catalogId (중복 없이, 컬렉션 순서대로)."""
    seen: dict[str, None] = {}
    for k in _kits(data_dir):
        cid = k.get("catalogId")
        if isinstance(cid, str) and _ID_RX.match(cid):
            seen.setdefault(cid)
    return list(seen)


def owned_map(data_dir: Path) -> dict[str, list[str]]:
    """{catalogId: ['own'|'wish', ...]} — 알림에서 "내 프라"를 알아보고 보유/위시를 표시하는 데 쓴다."""
    out: dict[str, list[str]] = {}
    for k in _kits(data_dir):
        cid = k.get("catalogId")
        if isinstance(cid, str) and _ID_RX.match(cid):
            lst = "wish" if k.get("list") == "wish" else "own"
            if lst not in out.setdefault(cid, []):
                out[cid].append(lst)
    return out
