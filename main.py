"""その日に販売（受付）が始まるチケットを集めて Discord に通知する。"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from notifier import discord, livepocket, ticketdive

JST = timezone(timedelta(hours=9))
# 収集に時間がかかるので早めに起動し、この時刻まで待ってから送信する
SEND_AT = (8, 0)
# GitHub Actions のキャッシュで実行間に引き継ぐ
STATE_DIR = Path(__file__).parent / "state"


# 通知する受付方式（抽選は対象外）
NOTIFY_TYPES = {"先着"}
# イベント名か受付名にこれらを含むものは通知しない
EXCLUDE_KEYWORDS = (
    "当日券",
    "撮影会",
    "トークショー",
    "公開授業",
    "クラウドファンディング",
    "パッケージ",
    "生誕パック",
    "一日店長",
    "CLUB「ナイトフィーバー」リバイバル",
    "里菜と池田のイケティるTV",
    "オフ会",
)
# イベント名にこれらを含むものは通知しない（受付名は見ない）
# 「事前予約」はライブの受付名にも使われるため、イベント名だけで判定する
EXCLUDE_TITLE_KEYWORDS = ("事前予約",)


def should_notify(sale: dict) -> bool:
    if sale.get("type") not in NOTIFY_TYPES:
        return False
    if any(k in sale["title"] for k in EXCLUDE_TITLE_KEYWORDS):
        return False
    text = f"{sale['title']} {sale['ticket_name']}"
    return not any(k in text for k in EXCLUDE_KEYWORDS)


SEPARATOR = "-------------------------------"


def build_messages(sales: list[dict]) -> list[str]:
    """発売時刻（時・分）の見出しと、1イベント1通の「イベント名:」「URL:」を並べる。"""
    by_time: dict[str, dict[str, str]] = {}
    for s in sorted(sales, key=lambda s: (s["start"], s["title"])):
        by_time.setdefault(f"{s['start']:%H時%M分}", {}).setdefault(s["url"], s["title"])
    messages = []
    for i, (label, events) in enumerate(by_time.items()):
        messages.append(label if i == 0 else f"{SEPARATOR}\n{label}")
        messages.extend(f"イベント名:{title}\nURL:{url}" for url, title in events.items())
    return messages


# 実行するサイト: 名前 → (投稿タイトルに使う名前, 収集関数)
SOURCES = {
    "ticketdive": ("チケットダイブ", lambda d: ticketdive.collect(d, cache_path=STATE_DIR / "ticketdive.json")),
    "livepocket": ("ライブポケット", lambda d: livepocket.collect(d, cache_path=STATE_DIR / "livepocket.json")),
}


def main() -> int:
    """使い方: python main.py <ticketdive|livepocket> [--dry-run]"""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    source = args[0] if args else "ticketdive"
    label, collect = SOURCES[source]
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    dry_run = "--dry-run" in sys.argv or not webhook_url
    today = datetime.now(JST).date()

    error = None
    try:
        sales = collect(today)
    except Exception as e:  # 取得に失敗しても、その旨を通知する
        sales = []
        error = repr(e)

    messages = build_messages([s for s in sales if should_notify(s)])
    title = f"{today:%m/%d}{label}のチケ発"
    count = sum(1 for m in messages if m.startswith("イベント名:"))
    header = f"{title}\n\n先着販売 {count}件"
    if error:
        header += f"\n⚠️ 取得に失敗しました: {error}"
    if not messages:
        header += "\n本日発売の先着チケットは見つかりませんでした。"

    if dry_run:
        print("\n\n".join([header, *messages]))
    else:
        send_at = datetime.now(JST).replace(hour=SEND_AT[0], minute=SEND_AT[1], second=0, microsecond=0)
        wait = (send_at - datetime.now(JST)).total_seconds()
        if 0 < wait < 6 * 3600:
            time.sleep(wait)
        discord.send_forum_post(webhook_url, title, [header, *messages])
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
