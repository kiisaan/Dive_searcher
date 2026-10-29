#!/bin/bash
# Google Cloud の初期設定（Cloud Shell で 1 回だけ実行する）。
#   bash setup.sh <プロジェクトID>
# GitHub Actions が鍵なし（Workload Identity 連携）で東京の Cloud Run ジョブを動かせるようにする。
# 何度実行しても同じ状態になる。
set -eu
PROJECT_ID=${1:?プロジェクトIDを指定してください: bash setup.sh <プロジェクトID>}
REGION=asia-northeast1
# GitHub のリポジトリ ID（名前を変えても変わらない）。kiisaan/Dive_searcher の main ブランチだけを許可する
GITHUB_REPO_ID=1436935091
POOL=github
PROVIDER=github
DEPLOYER=github-deployer
RUNNER=dive-runner

gcloud config set project "$PROJECT_ID"
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

echo "== API を有効化"
gcloud services enable run.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com logging.googleapis.com cloudscheduler.googleapis.com

echo "== サービスアカウントを作成"
create_sa() {
  gcloud iam service-accounts describe "$1@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$1" --display-name="$2"
}
create_sa "$DEPLOYER" "GitHub Actions から Cloud Run ジョブを操作する"
create_sa "$RUNNER" "Cloud Run ジョブの実行用（権限なし）"
DEPLOYER_EMAIL="$DEPLOYER@$PROJECT_ID.iam.gserviceaccount.com"
RUNNER_EMAIL="$RUNNER@$PROJECT_ID.iam.gserviceaccount.com"

for role in roles/run.developer roles/run.invoker roles/logging.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --condition=None --quiet \
    --member="serviceAccount:$DEPLOYER_EMAIL" --role="$role" >/dev/null
done
# ジョブを実行用サービスアカウントで動かす権限
gcloud iam service-accounts add-iam-policy-binding "$RUNNER_EMAIL" --quiet \
  --member="serviceAccount:$DEPLOYER_EMAIL" --role=roles/iam.serviceAccountUser >/dev/null

echo "== GitHub Actions との連携（Workload Identity）を作成"
gcloud iam workload-identity-pools describe "$POOL" --location=global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" --location=global \
  --workload-identity-pool="$POOL" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --location=global \
    --workload-identity-pool="$POOL" --display-name="GitHub" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository_id=='$GITHUB_REPO_ID' && assertion.ref=='refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_EMAIL" --quiet \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository_id/$GITHUB_REPO_ID" >/dev/null

cat <<EOF

========================================================
設定が終わりました。GitHub の Settings → Secrets and variables → Actions →
「Variables」タブ → New repository variable で、次の 3 つを登録してください。
（秘密の値ではないので Variables で大丈夫です）

  GCP_PROJECT_ID     $PROJECT_ID
  GCP_WIF_PROVIDER   projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER
  GCP_SA_EMAIL       $DEPLOYER_EMAIL
========================================================
EOF
