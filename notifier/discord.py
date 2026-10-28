import json
import time
import urllib.error
import urllib.request

# Discord の制限: メッセージ本文は 2000 文字まで
CONTENT_LIMIT = 2000
# URL のプレビュー（自動 embed）を出さない
SUPPRESS_EMBEDS = 1 << 2


def _post(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "ticket-sale-notifier"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30):
                return
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            retry_after = json.loads(e.read() or b"{}").get("retry_after", 1)
            time.sleep(float(retry_after) + 0.5)


def _pack(lines: list[str], limit: int) -> list[str]:
    blocks = [""]
    for line in lines:
        line = line[:limit]
        if blocks[-1] and len(blocks[-1]) + 1 + len(line) > limit:
            blocks.append("")
        blocks[-1] = f"{blocks[-1]}\n{line}" if blocks[-1] else line
    return blocks


def send(webhook_url: str, header: str, lines: list[str]) -> None:
    """header と lines を本文として送る。スマホでもコピーしやすいよう embed は使わない。"""
    for block in _pack([header, *lines], CONTENT_LIMIT):
        _post(
            webhook_url,
            {
                "content": block,
                "flags": SUPPRESS_EMBEDS,
                # イベント名に @everyone などが含まれていてもメンションしない
                "allowed_mentions": {"parse": []},
            },
        )
        time.sleep(1)
