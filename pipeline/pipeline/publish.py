"""publish 步驟：把 site/public/data/ 推到 repo 的 data 分支（PLAN.md 2.3）。

data 分支永遠只有一個 commit：每次都用暫時的 index 從輸出目錄建出 tree，
做一個沒有父節點的 commit，再強制推送。重複更新不會累積歷史，也不會動到
使用者目前的工作目錄與 index。

push 到 data 分支不會觸發部署（data 分支上沒有工作流程檔），所以推送後用
`gh workflow run deploy.yml --ref main` 手動觸發。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline.core.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)

TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


class PublishError(RuntimeError):
    pass


def _git(args: list[str], *, cwd: Path, env: dict | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise PublishError(f"git {' '.join(args)} 失敗：{proc.stderr.strip()}")
    return proc.stdout.strip()


def build_data_commit(data_dir: Path, repo_root: Path, branch: str = "data") -> str:
    meta_path = data_dir / "meta.json"
    if not meta_path.exists():
        raise PublishError(f"找不到 {meta_path}，請先執行 export")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    as_of = meta.get("data_as_of") or "（尚無資料）"

    git_dir = Path(_git(["rev-parse", "--absolute-git-dir"], cwd=repo_root))
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(td) / "index")}
        base = [f"--git-dir={git_dir}", f"--work-tree={data_dir}"]
        _git([*base, "add", "--all", "--force", "."], cwd=data_dir, env=env)
        tree = _git([*base, "write-tree"], cwd=data_dir, env=env)

    message = f"data: 資料截至 {as_of}（產生於 {meta.get('generated_at')}）\n\n{TRAILER}\n"
    commit = _git([f"--git-dir={git_dir}", "commit-tree", tree, "-m", message], cwd=repo_root)
    _git([f"--git-dir={git_dir}", "update-ref", f"refs/heads/{branch}", commit], cwd=repo_root)
    return commit


def publish(
    settings: Settings,
    *,
    repo_root: Path = REPO_ROOT,
    remote: str = "origin",
    branch: str = "data",
    push: bool = True,
    trigger_deploy: bool = True,
) -> str:
    commit = build_data_commit(settings.export_dir, repo_root, branch)
    log.info("已建立 %s 分支的 commit %s", branch, commit[:10])
    if not push:
        return commit

    remotes = _git(["remote"], cwd=repo_root).split()
    if remote not in remotes:
        raise PublishError(f"找不到遠端 {remote}，請先建立 GitHub repo")
    _git(["push", "--force", remote, f"refs/heads/{branch}:refs/heads/{branch}"], cwd=repo_root)
    log.info("已推送到 %s/%s", remote, branch)

    if trigger_deploy:
        if shutil.which("gh") is None:
            log.warning("找不到 GitHub CLI（gh），請到 GitHub 手動執行 deploy 工作流程")
        else:
            proc = subprocess.run(
                ["gh", "workflow", "run", "deploy.yml", "--ref", "main"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if proc.returncode != 0:
                log.warning("觸發部署失敗：%s", proc.stderr.strip())
            else:
                log.info("已觸發部署工作流程")
    return commit
