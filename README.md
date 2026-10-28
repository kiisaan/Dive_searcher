# Dive_searcher

毎朝 8:00 (JST) に、その日に **先着販売** が始まるチケットを Discord に通知します（抽選は対象外）。

```
10/28チケットダイブのチケ発

20時
イベント名:○○
URL:https://ticketdive.com/event/...

イベント名:○○
URL:https://ticketdive.com/event/...

-------------------------------
21時
イベント名:○○
URL:https://ticketdive.com/event/...
```

2000 文字を超える場合は時間帯の区切りで複数メッセージに分けて送ります。

| サイト | 状態 |
| --- | --- |
| TicketDive | 対応済み |
| LivePocket | 未対応（下記参照） |

## セットアップ

1. Discord のチャンネル設定 → 連携サービス → ウェブフック で Webhook URL を作成
2. このリポジトリの Settings → Secrets and variables → Actions → New repository secret
   - Name: `DISCORD_WEBHOOK_URL`
   - Secret: 1 の URL
3. Actions タブ → 「本日発売チケット通知」→ Run workflow で動作確認
   （手動実行は 8:00 JST より前なら 8:00 まで待ち、それ以外はすぐ送信します）

## ローカルで試す

```bash
python main.py --dry-run
```

`--dry-run` を付けるか `DISCORD_WEBHOOK_URL` が未設定なら、Discord には送らず標準出力に表示します。

## 仕組み

GitHub Actions で 6:13 JST に起動し、30〜60 分かけて収集したあと 8:00 JST まで待って送信します。

### TicketDive
TicketDive には全イベント一覧がなく、検索は 1 回最大 20 件・並び順固定・ページ送りなしです。
そこで以下でイベントを集め、各イベントページの受付情報（`startApply`）が今日のものを抽出します。

- トップページ（受付中・カルーセル）
- 1 文字検索と、20 件で打ち切られた検索ワードを見つかったタイトル中で前後に伸ばした再検索（最大 800 回）

イベントごとの受付情報は `state/ticketdive.json` に保存し、Actions のキャッシュで次回に引き継ぎます。
受付前・状態が変わったイベントは毎回、それ以外は 2 日ごとに詳細ページを取り直します。

制約:
- 検索に引っかからないイベントは取りこぼす可能性があります
- 8:00 以降に公開され、同じ日に受付開始する受付は通知できません

### LivePocket
クラウド（米国のデータセンター）からのアクセスには
「不正なリクエストです。サイトへのアクセスは許可できません。」と 403 が返るため、
GitHub Actions からは取得できません。
