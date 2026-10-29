#!/bin/bash
# 毎朝実行: 収集して 8:00 に Discord へ送り、実行ログを GitHub に書き戻す。
set -u
APP_DIR=/opt/dive_searcher
DATA_DIR=/var/lib/dive_searcher
LOG="$DATA_DIR/logs/daily-$(date +%F).log"

# GitHub Actions からの通知と二重にならないよう、切り替え用のファイルがあるときだけ動く
[ -e "$APP_DIR/server/ENABLE_DAILY" ] || exit 0

set -a
. /etc/dive_searcher/env
set +a

cd "$APP_DIR"
python3 main.py > "$LOG" 2>&1
echo "# 終了コード $?" >> "$LOG"
"$APP_DIR/server/publish.sh" "実行ログ: $(date +%F)" "$LOG" "logs/daily-$(date +%F).log"

# 古いログは 30 日で消す
find "$DATA_DIR/logs" -name 'daily-*.log' -mtime +30 -delete
