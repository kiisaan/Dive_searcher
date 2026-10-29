# Google Cloud（東京リージョン）の設定手順

ライブポケットは日本国外からのアクセスを受け付けないため、ライブポケットの処理だけを
Google Cloud の東京リージョン（Cloud Run ジョブ）で動かします。チケットダイブは今までどおり GitHub Actions で動きます。

画面の文言は Google 側の変更で多少変わることがあります。見当たらない項目があれば、近い名前のものを選んでください。

## 1. Google Cloud に登録してプロジェクトを作る

1. https://console.cloud.google.com/ を開き、Google アカウントでログイン
2. 利用規約に同意し、案内に沿って **お支払い情報（クレジットカード）** を登録
   - 無料トライアル（クレジット付与）の案内が出たらそのまま開始して大丈夫です
3. 画面上部のプロジェクト選択 → **新しいプロジェクト**
   - プロジェクト名: `dive-searcher`（任意）
   - 作成後に表示される **プロジェクト ID**（例: `dive-searcher-123456`）を控える

## 2. 予算アラートを設定する（念のため）

無料枠を超えても自動では止まらないため、少しでも費用が発生したらメールが届くようにします。

1. 左上のメニュー → **お支払い** → **予算とアラート** → **予算を作成**
2. 名前: `dive-searcher`、対象: 1 のプロジェクト
3. 金額: **100 円**（指定金額）
4. アラートのしきい値: 50% と 100%（初期値のままで可）→ **完了**

## 3. 初期設定スクリプトを実行する

ブラウザ上で動くターミナル（Cloud Shell）を使います。パソコンに何かを入れる必要はありません。

1. 画面右上の **「>_」アイコン（Cloud Shell をアクティブにする）** を押す
2. 画面下に黒い画面が開いたら、プロンプトの `(...)` 内が 1 で作ったプロジェクト ID になっていることを確認
   - 違う場合は `gcloud config set project プロジェクトID` を実行（プロジェクトID は 1 で控えたものに置き換え）
3. 次の 2 行をそのまま貼り付けて Enter（いま選ばれているプロジェクトに設定されます）
   ```bash
   curl -sSLO https://raw.githubusercontent.com/kiisaan/Dive_searcher/main/gcp/setup.sh
   bash setup.sh "$(gcloud config get-value project)"
   ```
   - 途中で「承認」を求められたら **承認** を押す
4. 最後に表示される 3 つの値を控える

## 4. GitHub に 3 つの値を登録する

1. https://github.com/kiisaan/Dive_searcher/settings/variables/actions を開く
2. **Variables** タブ → **New repository variable** で、3 の最後に表示された次の 3 つを登録
   - `GCP_PROJECT_ID`
   - `GCP_WIF_PROVIDER`
   - `GCP_SA_EMAIL`

ここまで終わったら連絡してください。以降の調査・開発はこちらで進めます。

## 設定される内容

- Cloud Run・Cloud Scheduler などの API の有効化
- サービスアカウント 2 つ（GitHub Actions からジョブを操作する用、ジョブ実行用）
- GitHub Actions との鍵なし連携（Workload Identity）。**このリポジトリの main ブランチからだけ** 操作できます
