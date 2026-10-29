#!/bin/bash
# サーバーの設定（初回と、このファイルが更新されたときに root で実行される）。
# 何度実行しても同じ状態になるように書く。
set -eu
APP_DIR=/opt/dive_searcher
DATA_DIR=/var/lib/dive_searcher
RUN_USER=ubuntu

timedatectl set-timezone Asia/Tokyo

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 curl unattended-upgrades

# OS のセキュリティ更新を自動で入れる
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# メモリ 1GB の Micro インスタンスで apt などが落ちないよう、スワップを用意する
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

install -d -o "$RUN_USER" -g "$RUN_USER" "$DATA_DIR" "$DATA_DIR/logs" "$DATA_DIR/probes-done"

# sync.sh が root で install.sh を再実行できるようにする（このファイルだけ）
cat > /etc/sudoers.d/dive_searcher <<EOF
$RUN_USER ALL=(root) NOPASSWD: /bin/bash $APP_DIR/server/install.sh
EOF
chmod 440 /etc/sudoers.d/dive_searcher

cat > /etc/cron.d/dive_searcher <<EOF
SHELL=/bin/bash
# 時刻はサーバーのタイムゾーン（Asia/Tokyo）で解釈される
# 10 分ごとに GitHub から最新のコードを取り込み、調査用スクリプトがあれば実行する
*/10 * * * * $RUN_USER flock -n $DATA_DIR/sync.lock $APP_DIR/server/sync.sh >> $DATA_DIR/logs/sync.log 2>&1
# 毎朝収集し、8:00 に Discord へ送信する
45 6 * * * $RUN_USER $APP_DIR/server/run_daily.sh
EOF
chmod 644 /etc/cron.d/dive_searcher
# タイムゾーン変更を cron に反映する
systemctl restart cron

sha256sum "$APP_DIR/server/install.sh" | cut -d' ' -f1 > "$DATA_DIR/install.sha"
chown "$RUN_USER:$RUN_USER" "$DATA_DIR/install.sha"
