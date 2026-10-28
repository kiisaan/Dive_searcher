import json
import time
import urllib.error
import urllib.request

# Discord の制限: 1メッセージあたり embed 10個まで
EMBEDS_PER_MESSAGE = 10


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


def send(webhook_url: str, header: str, embeds: list[dict]) -> None:
    if not embeds:
        _post(webhook_url, {"content": header})
        return
    for i in range(0, len(embeds), EMBEDS_PER_MESSAGE):
        payload = {"embeds": embeds[i : i + EMBEDS_PER_MESSAGE]}
        if i == 0:
            payload["content"] = header
        _post(webhook_url, payload)
        time.sleep(1)
