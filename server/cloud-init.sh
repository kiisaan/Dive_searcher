#!/bin/bash
# Oracle Cloud のインスタンス作成時に「初期化スクリプト（cloud-init）」へ貼り付けるスクリプト。
# 下の 2 つの値だけ書き換えて貼り付ければ、あとは自動で設定される。
# 作り直すときも同じものを貼り付ければよい。

DISCORD_WEBHOOK_URL="ここに Discord の Webhook URL を貼り付け"
GITHUB_TOKEN="ここに GitHub のトークンを貼り付け"

# ---- ここから下は書き換え不要 ----
set -eu
REPO_URL="https://github.com/kiisaan/Dive_searcher.git"
APP_DIR=/opt/dive_searcher
CONF_DIR=/etc/dive_searcher
RUN_USER=ubuntu

install -d -m 700 -o "$RUN_USER" -g "$RUN_USER" "$CONF_DIR"
printf 'DISCORD_WEBHOOK_URL=%s\n' "$DISCORD_WEBHOOK_URL" > "$CONF_DIR/env"
printf '%s\n' "$GITHUB_TOKEN" > "$CONF_DIR/github_token"
chown "$RUN_USER:$RUN_USER" "$CONF_DIR/env" "$CONF_DIR/github_token"
chmod 600 "$CONF_DIR/env" "$CONF_DIR/github_token"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$RUN_USER:$RUN_USER" "$APP_DIR"
fi
bash "$APP_DIR/server/install.sh"
