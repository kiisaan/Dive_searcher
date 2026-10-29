"""その日に販売（受付）が始まるチケットを集めて Discord に通知する。"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from notifier import discord, ticketdive

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


def build_sections(sales: list[dict]) -> list[str]:
    """発売時刻（時・分）ごとに「イベント名:」「URL:」の2行セットを空行区切りで並べたブロックを作る。"""
    by_time: dict[str, dict[str, str]] = {}
    for s in sorted(sales, key=lambda s: (s["start"], s["title"])):
        by_time.setdefault(f"{s['start']:%H時%M分}", {}).setdefault(s["url"], s["title"])
    return [
        f"{label}\n" + "\n\n".join(f"イベント名:{title}\nURL:{url}" for url, title in events.items())
        for label, events in by_time.items()
    ]


def main() -> int:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    dry_run = "--dry-run" in sys.argv or not webhook_url
    today = datetime.now(JST).date()

    sales = []
    errors = []
    sources = [("TicketDive", lambda d: ticketdive.collect(d, cache_path=STATE_DIR / "ticketdive.json"))]
    for name, collect in sources:
        try:
            sales.extend(collect(today))
        except Exception as e:  # 片方のサイトが落ちても他方は通知する
            errors.append(f"{name}: {e!r}")

    sections = build_sections([s for s in sales if should_notify(s)])
    header = f"{today:%m/%d}チケットダイブのチケ発\n"
    if errors:
        header += "\n⚠️ 取得に失敗しました: " + " / ".join(errors)
    if not sections:
        header += "\n本日発売の先着チケットは見つかりませんでした。"

    if dry_run:
        print(discord.join(header, sections, SEPARATOR))
    else:
        send_at = datetime.now(JST).replace(hour=SEND_AT[0], minute=SEND_AT[1], second=0, microsecond=0)
        wait = (send_at - datetime.now(JST)).total_seconds()
        if 0 < wait < 6 * 3600:
            time.sleep(wait)
        discord.send(webhook_url, header, sections, SEPARATOR)
    return 1 if errors and not sections else 0


if __name__ == "__main__":
    sys.exit(main())
