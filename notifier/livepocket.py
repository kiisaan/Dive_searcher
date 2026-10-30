import asyncio
import html
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "https://livepocket.jp"
JST = timezone(timedelta(hours=9))
MAX_LIST_PAGES = 450
MAX_DETAIL_FETCHES = int(os.environ.get("LIVEPOCKET_MAX_DETAILS", "2500"))
TTL_BEFORE_SALE = timedelta(days=3)
TTL_DEFAULT = timedelta(days=7)

# --- ボット対策・リソースブロック設定 ---
BLOCK_RESOURCE_TYPES = {"image", "media", "font"}
BLOCK_URL_KEYWORDS = (
    "googletagmanager.com", "google-analytics.com", "doubleclick.net", "googlesyndication.com",
    "facebook.net", "facebook.com/tr", "wovn.io", "clarity.ms", "hotjar.com",
    "ads-twitter.com", "analytics.twitter.com", "adsrvr.org", "criteo",
)


async def _route_handler(route):
    req = route.request
    if req.resource_type in BLOCK_RESOURCE_TYPES or any(k in req.url for k in BLOCK_URL_KEYWORDS):
        await route.abort()
    else:
        await route.continue_()


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _parse_cards(page_html: str) -> list[dict]:
    cards = []
    card_matches = re.findall(r'<li class="event-card-list__item">(.*?)</li>', page_html, re.S)
    for card in card_matches:
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


def _parse_tickets(page_html: str) -> list[dict]:
    tickets = []
    ticket_re = re.compile(r'<li class="event-detail-ticket__item[^"]*">(.*?)</a>', re.S)
    datetime_re = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\([^)]*\)\s*(\d{1,2}):(\d{2})")

    for item in ticket_re.findall(page_html):
        title = re.search(r'head__title">(.*?)</h3>', item, re.S)
        order = re.search(r'class="label-(?:order|lottery)[^"]*">([^<]+)<', item)
        period = re.search(r'head__list-data">(.*?)</dd>', item, re.S)
        start = datetime_re.search(_text(period.group(1))) if period else None
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
    if not cached:
        return 0 if "販売前" in card["tags"] else 1
    if cached.get("tags") != card["tags"]:
        return 1
    starts = [datetime.fromisoformat(t["start"]).date() for t in cached["tickets"] if t.get("start")]
    if any(today <= d <= today + timedelta(days=1) for d in starts):
        return 2
    ttl = TTL_BEFORE_SALE if "販売前" in card["tags"] else TTL_DEFAULT
    if now - datetime.fromisoformat(cached["fetched"]) > ttl:
        return 3
    return None


async def _async_collect(target: date, cache_path: Path | None = None) -> list[dict]:
    now = datetime.now(JST)
    cache = _load_cache(cache_path)
    events = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            extra_http_headers={"Accept-Language": "ja-JP,ja;q=0.9"},
        )
        
        # 不要なトラッキングや広告スクリプトを遮断してWAF検知を回避
        await context.route("**/*", _route_handler)
        page = await context.new_page()

        # 1. 一覧ページを全巡回
        for page_num in range(1, MAX_LIST_PAGES + 1):
            url = f"{BASE}/event/search?sort=1&page={page_num}"
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if response.status != 200:
                    print(f"[LivePocket] ステータス {response.status} (ページ {page_num})")
                    break
                
                try:
                    await page.wait_for_selector(".event-card-list__item", timeout=10000)
                except Exception:
                    pass

                html_content = await page.content()
                cards = _parse_cards(html_content)
                if not cards:
                    print(f"[LivePocket] ページ {page_num}: カードが0件のため終了します")
                    break
                
                for card in cards:
                    events[card["path"]] = card
                
                if page_num % 10 == 0:
                    print(f"[LivePocket] 一覧 {page_num}ページ / {len(events)}件", flush=True)
                
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[LivePocket] エラー (ページ {page_num}): {e}")
                break

        print(f"[LivePocket] 一覧から合計 {len(events)}件を取得", flush=True)

        # 2. 優先度をつけて詳細ページを取得
        queue = sorted(
            (priority, path)
            for path, card in events.items()
            if (priority := _refresh_priority(cache.get(path), card, now, target)) is not None
        )
        
        fetched = 0
        for _, path in queue[:MAX_DETAIL_FETCHES]:
            try:
                await page.goto(BASE + path, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(500)
                detail_html = await page.content()
                tickets = _parse_tickets(detail_html)
                cache[path] = {"fetched": now.isoformat(), "tags": events[path]["tags"], "tickets": tickets}
                fetched += 1
                if fetched % 200 == 0:
                    print(f"[LivePocket] 詳細ページ {fetched}/{min(len(queue), MAX_DETAIL_FETCHES)}件取得", flush=True)
                await asyncio.sleep(0.3)
            except (OSError, Exception):
                continue

        await browser.close()

    # 3. 指定日のセール情報を抽出
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


def collect(target: date, cache_path: Path | None = None) -> list[dict]:
    """main.py から同期関数として呼び出されるエントリーポイント"""
    return asyncio.run(_async_collect(target, cache_path))
