"""TicketDive (https://ticketdive.com) から、指定日に受付開始する受付を集める。

全イベント一覧も検索のページ送りもない（検索は1回最大20件）ため、
トップページと多数の検索ワードからイベントを集め、各イベントページの受付情報を見る。
"""

import http.client
import json
import urllib.parse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from notifier.web import fetch, next_page_props

BASE = "https://ticketdive.com"
SEARCH_LIMIT = 20
# 検索リクエスト数の上限（1回あたり約1.5秒）
MAX_SEARCH_QUERIES = 800
# 受付中イベントの受付情報を使い回す期間
CACHE_TTL = timedelta(days=2)
JST = timezone(timedelta(hours=9))

RECEPTION_TYPES = {
    "lottery": "抽選",
    "first": "先着",
}

# 1文字の検索でも部分一致で20件返るので、文字種を広く使って取りこぼしを減らす
SEARCH_QUERIES = (
    list("abcdefghijklmnopqrstuvwxyz0123456789")
    + list("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわん")
    + list("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン")
    + ["ライブ", "公演", "東京", "大阪", "名古屋", "福岡", "ワンマン", "LIVE", "TOUR", "祭", "フェス", "生誕", "定期", "対バン", "単独"]
)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(JST)


def _search(q: str) -> list[dict]:
    try:
        return next_page_props(fetch(f"{BASE}/search?q={urllib.parse.quote(q)}")).get("eventList") or []
    except (OSError, http.client.HTTPException, ValueError):
        return []


def _discover(max_queries: int) -> dict[str, dict]:
    """イベント一覧の要約を {url: summary} で返す。

    検索は部分一致・最大20件・並び順固定なので、20件で打ち切られたワードだけを
    見つかったタイトル中で前後に1文字伸ばして再検索し、取りこぼしを減らす。
    """
    found: dict[str, dict] = {}

    top = next_page_props(fetch(BASE + "/"))
    for key in ("carousel", "entryNow"):
        for e in top.get(key) or []:
            found.setdefault(e["url"], e)

    done: set[str] = set()
    capped: list[str] = []

    def run(q: str) -> None:
        done.add(q)
        events = _search(q)
        for e in events:
            found.setdefault(e["url"], e)
        if len(events) >= SEARCH_LIMIT:
            capped.append(q)

    for q in SEARCH_QUERIES:
        run(q)

    while capped and len(done) < max_queries:
        # 打ち切られたワードを含むタイトルから、前後1文字伸ばした候補を出現回数順に試す
        counts: Counter[str] = Counter()
        for q in capped:
            for e in found.values():
                title = e.get("title") or ""
                for i in range(len(title)):
                    if title.startswith(q, i):
                        if i > 0:
                            counts[title[i - 1 : i + len(q)]] += 1
                        if i + len(q) < len(title):
                            counts[title[i : i + len(q) + 1]] += 1
        capped = []
        candidates = [q for q, _ in counts.most_common() if q not in done and q.strip() == q]
        if not candidates:
            break
        for q in candidates[: max_queries - len(done)]:
            run(q)
    return found


def _load_cache(path: Path | None) -> dict:
    if path and path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return {}


def _needs_refresh(cached: dict | None, summary: dict, now: datetime) -> bool:
    if not cached:
        return True
    # 受付前・状態が変わったイベントは毎回取り直す（新しい受付が追加されやすい）
    if summary.get("salesStatus") in (None, "coming") or summary.get("salesStatus") != cached.get("status"):
        return True
    return now - datetime.fromisoformat(cached["fetched"]) > CACHE_TTL


def collect(target: date, max_queries: int = MAX_SEARCH_QUERIES, cache_path: Path | None = None) -> list[dict]:
    """target 日（JST）に受付開始する受付を返す。

    cache_path を渡すと、イベントごとの受付情報を保存して次回以降に使い回し、
    詳細ページの取得回数を減らす。
    """
    now = datetime.now(JST)
    cache = _load_cache(cache_path)
    events = {url_id: c["summary"] for url_id, c in cache.items()}
    discovered = _discover(max_queries)
    events.update(discovered)
    print(f"[TicketDive] 検索で{len(discovered)}件、キャッシュと合わせて{len(events)}件", flush=True)
    fetched = 0

    sales = []
    new_cache = {}
    for url_id, summary in events.items():
        if summary.get("salesStatus") == "closed":
            continue
        # 終演済みのイベントは対象外
        end = _parse(summary.get("endEventDate") or summary.get("startEventDate"))
        if end and end < now - timedelta(days=1):
            continue
        cached = cache.get(url_id)
        if _needs_refresh(cached, summary, now):
            fetched += 1
            if fetched % 100 == 0:
                print(f"[TicketDive] 詳細ページ {fetched}件取得", flush=True)
            try:
                detail = next_page_props(fetch(f"{BASE}/event/{url_id}"))["eventDetail"]
            except (OSError, http.client.HTTPException, ValueError, KeyError):
                if not cached:
                    continue
            else:
                cached = {
                    "fetched": now.isoformat(),
                    "status": summary.get("salesStatus"),
                    "title": (detail.get("event") or {}).get("name"),
                    "tickets": [
                        {k: info.get(k) for k in ("name", "startApply", "receptionType")}
                        for info in detail.get("ticketInfoList") or []
                    ],
                }
        new_cache[url_id] = {**cached, "summary": summary}

        for info in cached["tickets"]:
            start = _parse(info.get("startApply"))
            if not start or start.date() != target:
                continue
            sales.append(
                {
                    "source": "TicketDive",
                    "title": cached.get("title") or summary.get("title", ""),
                    "ticket_name": info.get("name") or "",
                    "type": RECEPTION_TYPES.get(info.get("receptionType"), info.get("receptionType")),
                    "start": start,
                    "event_date": _parse(summary.get("displayStageDate") or summary.get("startEventDate")),
                    "venue": summary.get("venueName"),
                    "url": f"{BASE}/event/{url_id}",
                }
            )

    print(f"[TicketDive] 詳細ページ取得 {fetched}件 / 対象イベント {len(new_cache)}件 / 本日開始 {len(sales)}件", flush=True)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(new_cache, ensure_ascii=False))
    return sales
