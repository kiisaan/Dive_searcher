import http.client
import json
import re
import time
import urllib.error
import urllib.request

USER_AGENT = "Dive_searcher (+https://github.com/kiisaan/Dive_searcher)"
REQUEST_INTERVAL_SEC = 0.5

_last_request = 0.0


def fetch(url: str, retries: int = 3) -> str:
    """URL を取得する。サーバー負荷を抑えるためリクエスト間隔を空ける。"""
    global _last_request
    for attempt in range(retries):
        wait = REQUEST_INTERVAL_SEC - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == retries - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def next_page_props(html: str) -> dict:
    """Next.js ページに埋め込まれた pageProps を取り出す（superjson 形式にも対応）。"""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise ValueError("__NEXT_DATA__ not found")
    props = json.loads(m.group(1))["props"]["pageProps"]
    return props.get("__superjsonProps", {}).get("json", props)
