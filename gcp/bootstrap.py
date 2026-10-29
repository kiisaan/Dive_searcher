# Cloud Run ジョブの起動コード。環境変数 REF の版のリポジトリを GitHub から取得して gcp/run.py を実行する。
# ジョブ定義の引数に埋め込むため、アットマーク記号を使わないこと（gcloud の引数区切りに使っている）。
import io
import os
import runpy
import sys
import tarfile
import urllib.request

ref = os.environ["REF"]
data = urllib.request.urlopen(f"https://codeload.github.com/kiisaan/Dive_searcher/tar.gz/{ref}", timeout=60).read()
with tarfile.open(fileobj=io.BytesIO(data)) as tar:
    root = tar.getnames()[0].split("/")[0]
    tar.extractall("/tmp", filter="data")
app = f"/tmp/{root}"
os.chdir(app)
sys.path.insert(0, app)
runpy.run_path("gcp/run.py", run_name="__main__")
