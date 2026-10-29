import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Discord の制限: メッセージ本文は 2000 文字、フォーラム投稿のタイトルは 100 文字まで
CONTENT_LIMIT = 2000
THREAD_NAME_LIMIT = 100
# URL のプレビュー（自動 embed）を出さない
SUPPRESS_EMBEDS = 1 << 2
# Webhook のレート制限（2 秒に 5 回程度）に余裕を持たせた送信間隔
SEND_INTERVAL_SEC = 0.6


def _post(webhook_url: str, payload: dict, params: dict | None = None) -> dict:
    url = webhook_url
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "Dive_searcher"},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                data = res.read()
                return json.loads(data) if data else {}
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            retry_after = json.loads(e.read() or b"{}").get("retry_after", 1)
            time.sleep(float(retry_after) + 0.5)
    raise RuntimeError("unreachable")


def _message(content: str) -> dict:
    return {
        "content": content[:CONTENT_LIMIT],
        "flags": SUPPRESS_EMBEDS,
        # イベント名に @everyone などが含まれていてもメンションしない
        "allowed_mentions": {"parse": []},
    }


def send_forum_post(webhook_url: str, title: str, messages: list[str]) -> None:
    """フォーラムチャンネルに title の投稿を作り、messages を1通ずつ送る。

    1イベント1メッセージにして、スマホでも長押しでそのイベントだけコピーできるようにする。
    Webhook がフォーラムチャンネルのものでない場合は、チャンネルにそのまま送る。
    """
    first, *rest = messages
    try:
        created = _post(
            webhook_url,
            {**_message(first), "thread_name": title[:THREAD_NAME_LIMIT]},
            {"wait": "true"},
        )
        params = {"thread_id": created["channel_id"]}
    except urllib.error.HTTPError as e:
        # 通常のテキストチャンネルの Webhook は thread_name を受け付けない
        if e.code != 400:
            raise
        _post(webhook_url, _message(first))
        params = None
    for content in rest:
        time.sleep(SEND_INTERVAL_SEC)
        _post(webhook_url, _message(content), params)
