#!/bin/bash
# 結果ファイルを GitHub の probe-results ブランチに書き戻す（書き込むのはこのサーバーだけ）。
# 使い方: publish.sh <コミットメッセージ> <ローカルのファイル/ディレクトリ> <ブランチ内の置き場所>
set -eu
MESSAGE=$1
SRC=$2
DEST=$3
RESULTS_DIR=/var/lib/dive_searcher/results
BRANCH=probe-results
TOKEN=$(cat /etc/dive_searcher/github_token)
REMOTE="https://x-access-token:${TOKEN}@github.com/kiisaan/Dive_searcher.git"

if [ ! -d "$RESULTS_DIR/.git" ]; then
  git init -q -b "$BRANCH" "$RESULTS_DIR"
fi
cd "$RESULTS_DIR"
git config user.name "Dive_searcher server"
git config user.email "dive-searcher-server@users.noreply.github.com"
if git fetch -q "$REMOTE" "$BRANCH" 2>/dev/null; then
  git reset -q --hard FETCH_HEAD
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"
git add -A
git commit -q -m "$MESSAGE" || exit 0
git push -q "$REMOTE" "HEAD:$BRANCH"
