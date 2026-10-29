#!/bin/bash
# 10 分ごとに実行: GitHub の main を取り込み、設定が変わっていれば反映し、
# まだ実行していない調査用スクリプト（probes/*.sh）があれば実行して結果を書き戻す。
set -eu
APP_DIR=/opt/dive_searcher
DATA_DIR=/var/lib/dive_searcher

cd "$APP_DIR"
git fetch -q origin main
git reset -q --hard origin/main

if [ "$(sha256sum server/install.sh | cut -d' ' -f1)" != "$(cat "$DATA_DIR/install.sha" 2>/dev/null)" ]; then
  echo "$(date '+%F %T') install.sh が更新されたので再実行"
  sudo /bin/bash "$APP_DIR/server/install.sh"
fi

# 内容が変わった調査用スクリプトだけを実行する（内容のハッシュで実行済みかを判定）
for probe in probes/*.sh; do
  [ -e "$probe" ] || continue
  name=$(basename "$probe" .sh)
  hash=$(sha256sum "$probe" | cut -d' ' -f1)
  done_mark="$DATA_DIR/probes-done/$name.$hash"
  [ -e "$done_mark" ] && continue
  touch "$done_mark"

  echo "$(date '+%F %T') 調査 $name を実行"
  out=$(mktemp -d)
  {
    echo "# $name ($(date '+%F %T %Z'), commit $(git rev-parse --short HEAD))"
    timeout 1800 bash "$probe" "$out" 2>&1 || echo "# 終了コード $?"
  } > "$out/output.txt"
  "$APP_DIR/server/publish.sh" "調査結果: $name" "$out" "probes/$name"
  rm -rf "$out"
done
