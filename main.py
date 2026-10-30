"""その日に販売（受付）が始まるチケットを集めて Discord に通知する。

使い方:
  python main.py collect <ticketdive|livepocket> <結果.json>   サイトから集めて保存する
  python main.py send [--dry-run] <結果.json>...             まとめて 1 つの投稿として送る
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import importlib

from notifier import discord

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

def _collector(module: str):
    """サイトのコードは収集するときだけ読み込む。1 サイトのコードの不具合で他サイトや送信が止まらないようにするため"""
    return lambda d: importlib.import_module(f"notifier.{module}").collect(d, cache_path=STATE_DIR / f"{module}.json")


# サイト: 名前 → (表示名, 収集関数)。投稿の中ではこの順に並べる
SOURCES = {
    "livepocket": ("ライブポケット", _collector("livepocket")),
    "ticketdive": ("チケットダイブ", _collector("ticketdive")),
}


def build_messages(sales: list[dict]) -> list[str]:
    """発売時刻（時・分）ごと、さらにプレイガイドごとに、1イベント1通の「イベント名:」「URL:」を並べる。"""
    order = list(SOURCES)
    by_time: dict[str, dict[str, dict[str, str]]] = {}
    for s in sorted(sales, key=lambda s: (s["start"], order.index(s["source"]), s["title"])):
        by_time.setdefault(f"{s['start']:%H時%M分}", {}).setdefault(s["source"], {}).setdefault(s["url"], s["title"])
    messages = []
    for i, (label, by_source) in enumerate(by_time.items()):
        heading = label if i == 0 else f"{SEPARATOR}\n{label}"
        for j, (source, events) in enumerate(by_source.items()):
            # イベント名と見分けやすいよう、プレイガイド名は Discord の見出しにする
            name = f"### 【{SOURCES[source][0]}】"
            messages.append(f"{heading}\n{name}" if j == 0 else name)
            messages.extend(f"イベント名:{title}\nURL:{url}" for url, title in events.items())
    return messages


def collect(source: str, out: Path) -> int:
    today = datetime.now(JST).date()
    result: dict = {"source": source, "date": today.isoformat(), "sales": [], "error": None}
    try:
        sales = SOURCES[source][1](today)
        result["sales"] = [{**s, "source": source, "start": s["start"].isoformat()} for s in sales]
    except Exception as e:  # 取得に失敗しても、その旨を通知できるよう結果は保存する
        result["error"] = repr(e)
    out.write_text(json.dumps(result, ensure_ascii=False, default=str))
    print(f"[{source}] 本日開始 {len(result['sales'])}件" + (f" / 失敗: {result['error']}" if result["error"] else ""))
    return 1 if result["error"] else 0


def send(paths: list[Path], dry_run: bool) -> int:
    today = datetime.now(JST).date()
    sales = []
    failed = []
    loaded = set()
    for path in paths:
        try:
            result = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        loaded.add(result["source"])
        if result["error"]:
            failed.append(result["source"])
        sales.extend({**s, "start": datetime.fromisoformat(s["start"])} for s in result["sales"])
    # 結果ファイルが届かなかったサイトも失敗として扱う
    failed += [s for s in SOURCES if s not in loaded]

    messages = build_messages([s for s in sales if should_notify(s)])
    title = f"{today:%m/%d} 本日のチケ発情報"
    header = title
    for source in failed:
        header += f"\n⚠️ {SOURCES[source][0]}の取得に失敗しました"
    if not messages:
        header += "\n本日発売の先着チケットは見つかりませんでした。"

    if dry_run:
        print("\n\n".join([header, *messages]))
    else:
        send_at = datetime.now(JST).replace(hour=SEND_AT[0], minute=SEND_AT[1], second=0, microsecond=0)
        wait = (send_at - datetime.now(JST)).total_seconds()
        if 0 < wait < 6 * 3600:
            time.sleep(wait)
        discord.send_forum_post(os.environ["DISCORD_WEBHOOK_URL"], title, [header, *messages])
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) == 3 and args[0] == "collect":
        return collect(args[1], Path(args[2]))
    if len(args) >= 1 and args[0] == "send":
        dry_run = "--dry-run" in sys.argv or not os.environ.get("DISCORD_WEBHOOK_URL")
        return send([Path(p) for p in args[1:]], dry_run)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
