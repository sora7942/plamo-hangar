"""디스코드 알림 (SPEC 7장).

- 이번 실행에서 새로 들어온 피드 항목을 묶어 보낸다. 항목 1개 = 임베드 1개, 메시지당 10개, 실행당 3메시지, 넘치면 "외 N건"
- 순서: ① 내 프라(내 보유·위시와 catalogId가 같은 국내 입고, 맨 앞·강조 색) ② kr 항목 → ③ pb-new → ④ new (config.FEED_TYPES의 우선순위)
- 최초 실행(이전 피드·카탈로그가 비었음)이거나 --bootstrap 중이면 보내지 않는다
- `DISCORD_WEBHOOK_URL`이 없거나 --dry-run/--no-discord면 콘솔에 보낼 내용만 출력한다
- 웹훅 URL은 코드·로그·출력 어디에도 남기지 않는다. 예외 메시지에 URL이 섞일 수 있어 예외는 종류만 기록한다
"""
from __future__ import annotations

import logging
import time

import requests

from . import config

log = logging.getLogger("plamo.discord")


def _meta(item: dict) -> tuple[str, int, int]:
    label, color, prio = config.FEED_TYPES.get(item["type"], (item["type"], 0x95A5A6, 99))
    return label, color, prio


def mine_lists(item: dict, mine: dict[str, list[str]] | None) -> list[str]:
    """내 프라인 국내 입고면 ['own'|'wish', ...], 아니면 []. 신제품·P-반다이는 내 프라 우선 대상이 아니다 (SPEC 7장)."""
    if not mine or item.get("type") not in config.MINE_PRIORITY_TYPES:
        return []
    return mine.get(item.get("catalogId") or "", [])


def embed_for(item: dict, mine: dict[str, list[str]] | None = None) -> dict:
    label, color, _ = _meta(item)
    when = item.get("date") or ""
    own = mine_lists(item, mine)
    desc = f"{label} · {when}" if when else label
    title = (item.get("titleKo") or item["title"])
    if own:
        who = "·".join(config.MINE_LABELS[k] for k in ("own", "wish") if k in own)
        title, desc, color = f"[내 프라] {title}", f"내 프라({who}) · {desc}", config.MINE_COLOR
    emb = {
        "title": title[:256],
        "url": item["url"],
        "description": desc,
        "color": color,
    }
    if item.get("image"):                       # 안정 URL이 있을 때만 (피드가 서명 URL을 저장하지 않는다)
        emb["thumbnail"] = {"url": item["image"]}
    return emb


def plan_messages(items: list[dict], mine: dict[str, list[str]] | None = None) -> tuple[list[dict], int]:
    """→ (메시지 페이로드 목록, 한도를 넘어 못 보낸 항목 수). mine = {catalogId: ['own'|'wish']} (collection.json에서 읽음)."""
    rank = lambda it: -1 if mine_lists(it, mine) else _meta(it)[2]            # 내 프라가 맨 앞 (한도를 넘어도 이쪽이 먼저 살아남는다)
    ordered = sorted(enumerate(items), key=lambda p: (rank(p[1]), p[0]))
    embeds = [embed_for(it, mine) for _, it in ordered]
    n_mine = sum(1 for _, it in ordered if mine_lists(it, mine))
    cap = config.DISCORD_PER_MESSAGE * config.DISCORD_MAX_MESSAGES
    overflow = max(0, len(embeds) - cap)
    embeds = embeds[:cap]
    messages = [{"embeds": embeds[i:i + config.DISCORD_PER_MESSAGE],
                 "allowed_mentions": {"parse": []}}
                for i in range(0, len(embeds), config.DISCORD_PER_MESSAGE)]
    if n_mine and messages:
        messages[0]["content"] = f"내 프라가 국내에 입고됐어요! ({min(n_mine, len(embeds))}건)"
    if overflow and messages:
        extra = f"외 {overflow}건 — 사이트에서 보기: {config.SITE_URL}"
        messages[-1]["content"] = f"{messages[-1]['content']}\n{extra}" if messages[-1].get("content") else extra
    return messages, overflow


def skip_reason(*, prev_feed_empty: bool, prev_catalog_empty: bool, bootstrap: bool) -> str | None:
    if bootstrap:
        return "--bootstrap 중이라 알림 없음"
    if prev_catalog_empty:
        return "카탈로그가 비어 있던 첫 실행이라 알림 없음"
    if prev_feed_empty:
        return "이전 피드가 비어 있어 알림 없음"
    return None


def describe(messages: list[dict], overflow: int) -> list[str]:
    """dry-run 콘솔 출력용 줄들."""
    lines = []
    for n, msg in enumerate(messages, 1):
        lines.append(f"[디스코드 메시지 {n}/{len(messages)}] 임베드 {len(msg['embeds'])}개")
        for e in msg["embeds"]:
            thumb = " [썸네일]" if "thumbnail" in e else ""
            lines.append(f"  - {e['title']}  ({e['description']}){thumb}  {e['url']}")
        if msg.get("content"):
            lines.append(f"  * {msg['content']}")
    if not messages:
        lines.append("[디스코드] 보낼 항목 없음")
    return lines


def send(messages: list[dict], webhook_url: str, *, post=requests.post, sleep=time.sleep) -> int:
    """실제 발송. 보낸 메시지 수를 돌려준다. 실패는 경고만 남기고 멈춘다(배포는 계속된다)."""
    sent = 0
    for i, msg in enumerate(messages):
        if i:
            sleep(config.DISCORD_SEND_INTERVAL)
        try:
            r = post(webhook_url, json=msg, timeout=config.DISCORD_TIMEOUT)
        except requests.RequestException as e:
            log.warning("디스코드 발송 실패(%s) — 이후 메시지는 건너뜀", type(e).__name__)   # 메시지에 URL이 섞일 수 있어 종류만
            break
        if r.status_code >= 400:
            log.warning("디스코드 발송 실패(HTTP %s) — 이후 메시지는 건너뜀", r.status_code)
            break
        sent += 1
    return sent
