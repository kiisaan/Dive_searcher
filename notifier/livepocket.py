"""LivePocket (https://livepocket.jp) から、指定日に受付開始する受付を集める。

検索結果（開催日順・20件ずつ）には開催前・開催中のイベントがすべて並ぶので、それを全ページたどって
イベントを集め、各イベントページの「受付・チケット情報」から受付開始日時を読む。
イベント数が多い（約9,000件）ため、受付情報は保存して使い回し、詳細ページは必要なものだけ取り直す。
"""

import html
import http.client
import json
import os
import re
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from notifier.web import fetch

BASE = "https://livepocket.jp"
JST = timezone(timedelta(hours=9))
# 一覧ページ数の上限（安全のため。通常は 450 ページ前後で終わる）
MAX_LIST_PAGES = 800
# 1 回の実行で取得する詳細ページ数の上限（環境変数 LIVEPOCKET_MAX_DETAILS で変更可）。
# 受付情報がそろっていない初回は、事前収集で上限を上げて何度か回す
MAX_DETAIL_FETCHES = int(os.environ.get("LIVEPOCKET_MAX_DETAILS", "2500"))
# 受付情報を使い回す期間
TTL_BEFORE_SALE = timedelta(days=3)
TTL_DEFAULT = timedelta(days=7)

_CARD_RE = re.compile(r'<li class="event-card-list__item">(.*?)</li>', re.S)
_TICKET_RE = re.compile(r'<li class="event-detail-ticket__item[^"]*">(.*?)</a>', re.S)
_DATETIME_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\([^)]*\)\s*(\d{1,2}):(\d{2})")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _parse_cards(page: str) -> list[dict]:
    cards = []
    for card in _CARD_RE.findall(page):
        href = re.search(r'href="(/e/[^"]+)"', card)
        if not href:
            continue
        title = re.search(r'event-card__title">(.*?)</h3>', card, re.S)
        place = re.search(r'event-card__place">[^<]*</span>(.*?)</p>', card, re.S)
        cards.append(
            {
                "path": href.group(1),
                "title": _text(title.group(1)) if title else "",
                "tags": sorted(set(re.findall(r'event-card__tag">([^<]+)<', card))),
                "venue": _text(place.group(1)) if place else "",
            }
        )
    return cards


def _list_events() -> dict[str, dict]:
    """検索結果を全ページたどって {path: カード情報} を返す。"""
    events: dict[str, dict] = {}
    for page in range(1, MAX_LIST_PAGES + 1):
        try:
            cards = _parse_cards(fetch(f"{BASE}/event/search?sort=1&page={page}"))
        except urllib.error.HTTPError as e:
            # 最終ページの次は 404 になる
            if e.code == 404:
                break
            raise
        if not cards:
            break
        for card in cards:
            events.setdefault(card["path"], card)
        if page % 50 == 0:
            print(f"[LivePocket] 一覧 {page}ページ / {len(events)}件", flush=True)
    return events


def _parse_tickets(page: str) -> list[dict]:
    """イベントページの受付ごとに、受付名・方式（先着/抽選）・受付開始日時を返す。"""
    tickets = []
    for item in _TICKET_RE.findall(page):
        title = re.search(r'head__title">(.*?)</h3>', item, re.S)
        # 先着は label-order、抽選は label-lottery
        order = re.search(r'class="label-(?:order|lottery)[^"]*">([^<]+)<', item)
        period = re.search(r'head__list-data">(.*?)</dd>', item, re.S)
        start = _DATETIME_RE.search(_text(period.group(1))) if period else None
        name = _text(title.group(1)) if title else ""
        type_ = order.group(1).strip() if order else None
        if type_ and name.startswith(type_):
            name = name[len(type_) :].strip()
        tickets.append(
            {
                "name": name,
                "type": type_,
                "start": datetime(*map(int, start.groups()), tzinfo=JST).isoformat() if start else None,
            }
        )
    return tickets


def _load_cache(path: Path | None) -> dict:
    if path and path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return {}


def _refresh_priority(cached: dict | None, card: dict, now: datetime, today: date) -> int | None:
    """詳細ページを取り直す優先度（小さいほど先）。取り直さなくてよければ None。"""
    if not cached:
        # 初回など受付情報がないときは、これから受付が始まる販売前のイベントを先に取る
        return 0 if "販売前" in card["tags"] else 1
    if cached.get("tags") != card["tags"]:
        return 1
    starts = [datetime.fromisoformat(t["start"]).date() for t in cached["tickets"] if t.get("start")]
    # 今日・明日に受付が始まるものは、時刻の変更に備えて毎回確認する
    if any(today <= d <= today + timedelta(days=1) for d in starts):
        return 2
    ttl = TTL_BEFORE_SALE if "販売前" in card["tags"] else TTL_DEFAULT
    if now - datetime.fromisoformat(cached["fetched"]) > ttl:
        return 3
    return None


def collect(target: date, cache_path: Path | None = None) -> list[dict]:
    now = datetime.now(JST)
    cache = _load_cache(cache_path)
    events = _list_events()
    print(f"[LivePocket] 一覧から{len(events)}件", flush=True)

    queue = sorted(
        (priority, path)
        for path, card in events.items()
        if (priority := _refresh_priority(cache.get(path), card, now, target)) is not None
    )
    fetched = 0
    for _, path in queue[:MAX_DETAIL_FETCHES]:
        try:
            tickets = _parse_tickets(fetch(BASE + path))
        except (OSError, http.client.HTTPException):
            continue
        cache[path] = {"fetched": now.isoformat(), "tags": events[path]["tags"], "tickets": tickets}
        fetched += 1
        if fetched % 200 == 0:
            print(f"[LivePocket] 詳細ページ {fetched}/{min(len(queue), MAX_DETAIL_FETCHES)}件取得", flush=True)

    sales = []
    new_cache = {}
    for path, card in events.items():
        cached = cache.get(path)
        if not cached:
            continue
        new_cache[path] = cached
        for ticket in cached["tickets"]:
            start = datetime.fromisoformat(ticket["start"]) if ticket.get("start") else None
            if not start or start.date() != target:
                continue
            sales.append(
                {
                    "source": "LivePocket",
                    "title": card["title"],
                    "ticket_name": ticket["name"],
                    "type": ticket["type"],
                    "start": start,
                    "venue": card["venue"],
                    "url": BASE + path,
                }
            )

    print(
        f"[LivePocket] 詳細ページ取得 {fetched}件（未取得 {max(0, len(queue) - MAX_DETAIL_FETCHES)}件）"
        f" / 受付情報あり {len(new_cache)}/{len(events)}件 / 本日開始 {len(sales)}件",
        flush=True,
    )
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(new_cache, ensure_ascii=False))
    return sales
