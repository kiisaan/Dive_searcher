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


def group_by_event(sales: list[dict]) -> list[dict]:
    """同じイベントの受付をまとめ、受付開始の早い順に並べる。"""
    events: dict[str, dict] = {}
    for s in sorted(sales, key=lambda s: s["start"]):
        event = events.setdefault(s["url"], {**s, "starts": []})
        if s["start"] not in event["starts"]:
            event["starts"].append(s["start"])
    return sorted(events.values(), key=lambda e: (e["starts"][0], e["title"]))


def event_line(event: dict) -> str:
    """1イベントを「イベント名 / 発売時間 / ページリンク」の1行にする。"""
    times = "・".join(f"{t:%H:%M}" for t in event["starts"])
    return f"{event['title']} / {times} / {event['url']}"


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

    events = group_by_event([s for s in sales if s.get("type") in NOTIFY_TYPES])
    header = f"{today:%Y/%m/%d} に先着販売が始まるチケット：{len(events)}件"
    if errors:
        header += "\n⚠️ 取得に失敗したサイトがあります: " + " / ".join(errors)
    if not events:
        header += "\n本日販売開始の先着チケットは見つかりませんでした。"

    if dry_run:
        print(header)
        for e in events:
            print(event_line(e))
    else:
        send_at = datetime.now(JST).replace(hour=SEND_AT[0], minute=SEND_AT[1], second=0, microsecond=0)
        wait = (send_at - datetime.now(JST)).total_seconds()
        if 0 < wait < 3 * 3600:
            time.sleep(wait)
        discord.send(webhook_url, header, [event_line(e) for e in events])
    return 1 if errors and not events else 0


if __name__ == "__main__":
    sys.exit(main())
