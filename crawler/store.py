"""JSON 읽기·쓰기와 시간 helper.

- 시간은 timezone-aware, 저장은 `+09:00` ISO 문자열
- JSON은 `encoding="utf-8"`, `ensure_ascii=False`
- 큰 목록·사전은 한 항목당 한 줄로 써서 git diff가 읽히고 크기도 작다
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


def now_kst() -> datetime:
    return datetime.now(config.KST)


def iso(dt: datetime) -> str:
    """초 단위 ISO 문자열 (+09:00)."""
    if dt.tzinfo is None:
        raise ValueError("timezone-aware datetime이 필요하다")
    return dt.astimezone(config.KST).isoformat(timespec="seconds")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _compact(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def dumps(data: dict) -> str:
    """최상위 dict. 값이 list(dict 원소)거나 항목이 많은 dict면 한 항목당 한 줄, 나머지는 한 줄 압축."""
    parts = []
    for k, v in data.items():
        key = _compact(k)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            body = ",\n".join(_compact(x) for x in v)
            parts.append(f"{key}:[\n{body}\n]")
        elif isinstance(v, dict) and len(v) > 8:
            body = ",\n".join(f"{_compact(kk)}:{_compact(vv)}" for kk, vv in v.items())
            parts.append(f"{key}:{{\n{body}\n}}")
        else:
            parts.append(f"{key}:{_compact(v)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def write_json(path: Path, data: dict) -> None:
    """임시 파일에 쓴 뒤 교체한다 (중간에 끊겨도 반쯤 쓴 파일이 남지 않게)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    os.replace(tmp, path)
