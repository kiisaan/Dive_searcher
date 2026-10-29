"""ライブポケットの robots.txt・トップページ・検索ページを取得し、構造調査用に保存する（東京から実行）。"""

import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "Dive_searcher (+https://github.com/kiisaan/Dive_searcher)"
PAGES = {
    "robots.txt": "https://t.livepocket.jp/robots.txt",
    "top.html": "https://t.livepocket.jp/",
    "search.html": "https://t.livepocket.jp/event/search",
}


def main(out: Path) -> None:
    for name, url in PAGES.items():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                status, final_url, headers, body = res.status, res.url, res.headers, res.read()
        except urllib.error.HTTPError as e:
            status, final_url, headers, body = e.code, url, e.headers, e.read()
        (out / name).write_bytes(body)
        (out / f"{name}.headers").write_text(str(headers))
        print(f"{url} -> {status} {len(body)}B final={final_url}")
        time.sleep(3)
