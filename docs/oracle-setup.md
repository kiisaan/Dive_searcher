# Oracle Cloud（Always Free）でのサーバー設定手順

ライブポケットは日本国外からのアクセスを受け付けないため、通知は Oracle Cloud の東京リージョンの
無料サーバーで動かします。ターミナル（黒い画面）の操作は不要です。

画面の文言は Oracle 側の変更で多少変わることがあります。見当たらない項目があれば、近い名前のものを選んでください。

## 1. GitHub のトークンを作る

サーバーが調査結果や実行ログをこのリポジトリに書き戻すためのものです。**このリポジトリだけ**に書き込める権限にします。

1. GitHub 右上のアイコン → **Settings** → 左メニュー最下部の **Developer settings**
2. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
3. 次のように設定
   - Token name: `dive-searcher-server`（任意）
   - Expiration: 選べる中で一番長い期間（期限が来たら作り直して、サーバーを作り直します）
   - Repository access: **Only select repositories** → `kiisaan/Dive_searcher`
   - Permissions → Repository permissions → **Contents: Read and write**（ほかは触らない）
4. **Generate token** を押し、表示された `github_pat_...` をコピーしてメモ帳などに控える（この画面でしか表示されません）

## 2. 初期化スクリプトを用意する

1. [`server/cloud-init.sh`](../server/cloud-init.sh) を開き、中身をすべてコピーしてメモ帳に貼り付ける
2. 先頭の 2 行を書き換える（`"` は消さない）
   ```
   DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."   ← フォーラムチャンネルの Webhook URL
   GITHUB_TOKEN="github_pat_..."                                ← 1 で作ったトークン
   ```

## 3. サーバー（インスタンス）を作る

1. Oracle Cloud にログインし、右上のリージョンが **Japan East (Tokyo)** になっていることを確認
2. 左上のメニュー → **Compute** → **Instances** → **Create instance**
3. 次のように設定
   - Name: `dive-searcher`（任意）
   - **Image**: Change image → **Canonical Ubuntu** → **24.04**
   - **Shape**: Change shape → **Virtual machine** → **Specialty and previous generation** → **VM.Standard.E2.1.Micro**
     （「Always Free-eligible」と表示されているもの）
   - Networking: 初期値のまま（新しい VCN を作成し、パブリック IPv4 アドレスを割り当てる）
   - SSH keys: **No SSH keys**（ログインしないため不要）
   - 下の方の **Show advanced options** → **Management** → **Initialization script** で
     **Paste cloud-init script** を選び、2 で用意したスクリプトを貼り付ける
4. **Create** を押す。状態が **Running** になれば完了

10〜20 分ほどで自動設定が終わり、最初の調査結果が GitHub の `probe-results` ブランチに届きます。
作成が終わったら連絡してください。

### 「Out of capacity」と出て作成できない場合
東京リージョンの無料枠が一時的に埋まっています。時間をおいて再度作成してください。

## 作り直すとき

サーバーが Oracle に回収された・調子が悪いなどで作り直すときは、古いインスタンスを削除してから
3 と同じ手順で作成し、同じ初期化スクリプトを貼り付けるだけで元に戻ります。
