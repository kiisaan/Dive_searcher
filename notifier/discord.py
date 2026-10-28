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


def _split(text: str, limit: int) -> list[str]:
    """limit を超えるブロックを行単位で分ける。"""
    chunks = [""]
    for line in text.split("\n"):
        line = line[:limit]
        if chunks[-1] and len(chunks[-1]) + 1 + len(line) > limit:
            chunks.append("")
        chunks[-1] = f"{chunks[-1]}\n{line}" if chunks[-1] else line
    return chunks


def join(header: str, sections: list[str], separator: str) -> str:
    return header + ("\n" + f"\n{separator}\n".join(sections) if sections else "")


def _messages(header: str, sections: list[str], separator: str, limit: int) -> list[str]:
    """できるだけセクションの区切りでメッセージを分ける。"""
    messages = [header]
    for i, section in enumerate(sections):
        piece = section if i == 0 else f"{separator}\n{section}"
        if len(messages[-1]) + 1 + len(piece) <= limit:
            messages[-1] += "\n" + piece
        elif len(piece) <= limit:
            messages.append(piece)
        else:
            messages.extend(_split(piece, limit))
    return messages


def send(webhook_url: str, header: str, sections: list[str], separator: str) -> None:
    """本文として送る。スマホでもコピーしやすいよう embed は使わない。"""
    for content in _messages(header, sections, separator, CONTENT_LIMIT):
        _post(
            webhook_url,
            {
                "content": content,
                "flags": SUPPRESS_EMBEDS,
                # イベント名に @everyone などが含まれていてもメンションしない
                "allowed_mentions": {"parse": []},
            },
        )
        time.sleep(1)
