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


def group_by_event(sales: list[dict]) -> list[dict]:
    """同じイベントの受付を1つにまとめ、受付開始の早い順に並べる。"""
    events: dict[str, dict] = {}
    for s in sorted(sales, key=lambda s: (s["start"], s["ticket_name"])):
        event = events.setdefault(s["url"], {**s, "tickets": []})
        ticket = (s["start"], s["ticket_name"], s.get("type"))
        if ticket not in event["tickets"]:
            event["tickets"].append(ticket)
    return sorted(events.values(), key=lambda e: (e["tickets"][0][0], e["title"]))


def ticket_label(ticket: tuple) -> str:
    _, name, type_ = ticket
    return name + (f"（{type_}）" if type_ else "")


def event_line(event: dict) -> str:
    """1公演を1行にする。例: `20:00` [タイトル](URL) 一般販売（先着） ｜ 11/28 会場"""
    title = event["title"].replace("[", "［").replace("]", "］")
    starts = sorted({t[0] for t in event["tickets"]})
    time_label = f"{starts[0]:%H:%M}" + ("〜" if len(starts) > 1 else "")
    tickets = " / ".join(dict.fromkeys(ticket_label(t) for t in event["tickets"]))
    if len(tickets) > 120:
        tickets = tickets[:120] + "…"
    line = f"`{time_label}` [{title}]({event['url']}) {tickets}"
    detail = " ".join(x for x in [event["event_date"].strftime("%-m/%-d") if event.get("event_date") else "", event.get("venue") or ""] if x)
    return line + (f" ｜ {detail}" if detail else "")


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

    events = group_by_event(sales)
    header = f"**{today:%Y/%m/%d} に受付開始のチケット：{len(events)}公演・{sum(len(e['tickets']) for e in events)}受付**"
    if errors:
        header += "\n⚠️ 取得に失敗したサイトがあります: " + " / ".join(errors)
    if not sales:
        header += "\n本日受付開始のチケットは見つかりませんでした。"

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
    return 1 if errors and not sales else 0


if __name__ == "__main__":
    sys.exit(main())
