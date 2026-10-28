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


def to_embed(sale: dict) -> dict:
    fields = [{"name": "受付開始", "value": sale["start"].strftime("%H:%M"), "inline": True}]
    if sale.get("type"):
        fields.append({"name": "受付方式", "value": sale["type"], "inline": True})
    if sale.get("event_date"):
        fields.append({"name": "公演日", "value": sale["event_date"].strftime("%Y/%m/%d"), "inline": True})
    if sale.get("venue"):
        fields.append({"name": "会場", "value": sale["venue"][:1024], "inline": True})
    return {
        "title": sale["title"][:256],
        "url": sale["url"],
        "description": sale["ticket_name"][:4096],
        "fields": fields,
        "footer": {"text": sale["source"]},
    }


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

    sales.sort(key=lambda s: (s["start"], s["title"]))
    header = f"**{today:%Y/%m/%d} に受付開始のチケット：{len(sales)}件**"
    if errors:
        header += "\n⚠️ 取得に失敗したサイトがあります: " + " / ".join(errors)
    if not sales:
        header += "\n本日受付開始のチケットは見つかりませんでした。"

    embeds = [to_embed(s) for s in sales]
    if dry_run:
        print(header)
        for s in sales:
            print(f"{s['start']:%H:%M} [{s['source']}] {s['title']} / {s['ticket_name']} ({s.get('type') or '-'}) {s['url']}")
    else:
        send_at = datetime.now(JST).replace(hour=SEND_AT[0], minute=SEND_AT[1], second=0, microsecond=0)
        wait = (send_at - datetime.now(JST)).total_seconds()
        if 0 < wait < 3 * 3600:
            time.sleep(wait)
        discord.send(webhook_url, header, embeds)
    return 1 if errors and not sales else 0


if __name__ == "__main__":
    sys.exit(main())
