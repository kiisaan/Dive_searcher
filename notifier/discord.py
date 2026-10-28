import json
import time
import urllib.error
import urllib.request

# Discord の制限: embed の説明文は 4096 文字まで、1メッセージの embed 合計は 6000 文字まで
DESCRIPTION_LIMIT = 4000
EMBED_COLOR = 0x2B6CB0


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
    """header を本文に、lines を embed の説明文に詰めて送る（1メッセージ1 embed）。"""
    for i, block in enumerate(_pack(lines, DESCRIPTION_LIMIT) if lines else [""]):
        payload: dict = {}
        if block:
            payload["embeds"] = [{"description": block, "color": EMBED_COLOR}]
        if i == 0:
            payload["content"] = header
        _post(webhook_url, payload)
        time.sleep(1)
