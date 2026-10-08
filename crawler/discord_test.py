"""디스코드 테스트 발송 (`python main.py --discord-test`, Actions 수동 실행의 discord_test).

- 수집은 하지 않는다. 지금 feed.json의 최근 항목 3개(내 프라에 연결된 항목이 있으면 그중 1개 포함)를 실제 알림과 같은 형식으로 묶어,
  맨 앞에 "[테스트] 프라 격납고 알림 확인용"을 붙인 **1개 메시지**만 보낸다.
- 읽기만 한다: feed.json·collection.json은 바꾸지 않고 docs/data에 아무것도 쓰지 않는다 (커밋할 것도 없다).
- 웹훅은 환경변수 DISCORD_WEBHOOK_URL(Actions에서는 Secret)만 쓴다. 없으면 "웹훅 없음"만 출력하고 성공으로 끝낸다.
  URL은 출력·로그 어디에도 남기지 않는다 (발송 실패는 종류만 기록 — discord.send).
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

from . import config, discord, mine
from .store import read_json

TEST_HEAD = "[테스트] 프라 격납고 알림 확인용"
TEST_COUNT = 3


def pick_items(feed_items: list[dict], mine_map: dict[str, list[str]] | None, n: int = TEST_COUNT) -> list[dict]:
    """최근 n개. 내 프라에 연결된 항목이 있으면 그중 가장 최근 1개를 반드시 넣는다(국내 입고가 있으면 그쪽을 먼저 — 강조 형식을 볼 수 있다)."""
    recent = sorted(feed_items, key=lambda i: (i.get("added", ""), i.get("id", "")), reverse=True)
    mine_map = mine_map or {}
    linked = [i for i in recent if mine_map.get(i.get("catalogId") or "")]
    pri = [i for i in linked if discord.mine_lists(i, mine_map)]
    chosen = (pri or linked)[:1]
    for it in recent:
        if len(chosen) >= n:
            break
        if it not in chosen:
            chosen.append(it)
    return chosen


def build_message(feed_items: list[dict], mine_map: dict[str, list[str]] | None) -> dict | None:
    """테스트 메시지 1개. 보낼 항목이 없으면 None."""
    items = pick_items(feed_items, mine_map)
    if not items:
        return None
    msgs, _ = discord.plan_messages(items, mine_map)
    msg = msgs[0]
    msg["content"] = TEST_HEAD + ("\n" + msg["content"] if msg.get("content") else "")
    return msg


def run(data_dir: Path, *, dry_run: bool = False, post=requests.post, out=print, env=None) -> int:
    """→ 종료 코드. 웹훅이 없거나 dry-run이면 0, 발송에 실패하면 1(수동 실행이라 눈에 띄게)."""
    env = os.environ if env is None else env
    data_dir = Path(data_dir)
    doc = read_json(data_dir / config.FEED_FILE, {}) or {}
    feed_items = [i for i in doc.get("items", []) if isinstance(i, dict) and i.get("id") and i.get("url")]
    msg = build_message(feed_items, mine.owned_map(data_dir))
    if msg is None:
        out("[디스코드 테스트] feed.json에 보낼 항목이 없어요. 보내지 않았어요.")
        return 0
    for line in discord.describe([msg], 0):
        out(line)
    if dry_run:
        out("[디스코드 테스트] --dry-run: 위 내용을 보내지 않았어요.")
        return 0
    webhook = env.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        out("[디스코드 테스트] 웹훅 없음 — 보내지 않았어요. (Actions Secret DISCORD_WEBHOOK_URL 또는 .env를 확인하세요)")
        return 0
    sent = discord.send([msg], webhook, post=post)
    if sent != 1:
        out("[디스코드 테스트] 발송에 실패했어요. (자세한 이유는 위 경고 로그)")
        return 1
    out("[디스코드 테스트] 1개 메시지를 보냈어요.")
    return 0
