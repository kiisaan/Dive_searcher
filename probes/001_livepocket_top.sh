#!/bin/bash
# ライブポケットのトップページ・robots.txt・検索ページを取得し、構造調査用に保存する。
# 引数: 保存先ディレクトリ
OUT=$1
UA="Dive_searcher (+https://github.com/kiisaan/Dive_searcher)"
fetch() {
  local name=$1 url=$2
  echo "== $url"
  curl -sS -L -A "$UA" -D "$OUT/$name.headers" -o "$OUT/$name.html" \
    -w 'status=%{http_code} size=%{size_download} time=%{time_total}s final=%{url_effective}\n' "$url"
  sleep 3
}
fetch robots https://t.livepocket.jp/robots.txt
fetch top https://t.livepocket.jp/
fetch search https://t.livepocket.jp/event/search
