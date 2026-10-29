"""Cloud Run ジョブ（東京リージョン）の入口。環境変数 TASK で処理を選ぶ。

- probe:<名前>  probes/<名前>.py を実行し、出力を GitHub の probe-results ブランチに書き戻す
"""

import base64
import contextlib
import importlib.util
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "kiisaan/Dive_searcher"
RESULT_BRANCH = "probe-results"


class Tee:
    """標準出力をファイルと Cloud Logging の両方に出す。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for stream in self.streams:
            stream.write(s)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def github(method: str, path: str, body: dict | None = None) -> dict | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Dive_searcher",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read() or b"null")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def publish(local_dir: Path, dest: str, message: str) -> None:
    """local_dir 以下のファイルを probe-results ブランチの dest 以下に置く（1ファイル1コミット）。"""
    for file in sorted(p for p in local_dir.rglob("*") if p.is_file()):
        path = f"{dest}/{file.relative_to(local_dir).as_posix()}"
        current = github("GET", f"contents/{path}?ref={RESULT_BRANCH}")
        body = {
            "message": f"{message}: {path}",
            "content": base64.b64encode(file.read_bytes()).decode(),
            "branch": RESULT_BRANCH,
        }
        if current:
            body["sha"] = current["sha"]
        github("PUT", f"contents/{path}", body)


def run_probe(name: str) -> None:
    spec = importlib.util.spec_from_file_location(name, Path("probes") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    out = Path(tempfile.mkdtemp())
    with open(out / "output.txt", "w") as log, contextlib.redirect_stdout(Tee(sys.stdout, log)):
        print(f"# {name} (REF {os.environ['REF'][:7]})")
        try:
            spec.loader.exec_module(module)
            module.main(out)
        except Exception as e:  # 失敗も結果として書き戻す
            print(f"# 失敗: {e!r}")
    publish(out, f"probes/{name}", f"調査結果 {name}")


def main() -> None:
    task = os.environ["TASK"]
    kind, _, arg = task.partition(":")
    if kind == "probe":
        run_probe(arg)
    else:
        raise SystemExit(f"unknown TASK: {task}")


if __name__ == "__main__":
    main()
