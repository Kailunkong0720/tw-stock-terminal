from __future__ import annotations

import json
import subprocess

import pytest

from pipeline.core.db import migrate
from pipeline.export.contract import CONTRACT_VERSION, Meta
from pipeline.export.run import json_schema, run_export
from pipeline.export.writer import ExportWriter, OverBudget
from pipeline.publish import build_data_commit


def test_export_writes_valid_meta(settings):
    run_export(settings)
    raw = json.loads((settings.export_dir / "meta.json").read_text(encoding="utf-8"))
    meta = Meta.model_validate(raw)
    assert meta.contract_version == CONTRACT_VERSION
    assert meta.generated_at.utcoffset() is not None, "時間必須帶時區"
    assert meta.coverage_start.isoformat() == "2020-01-01"


def test_budget_check(settings):
    w = ExportWriter(settings.export_dir)
    w.write("meta.json", Meta(generated_at="2026-11-12T16:30:00+08:00", data_as_of=None, coverage_start="2020-01-01"))
    with pytest.raises(OverBudget):
        w.check_budget(budget=10)


def test_schema_contains_meta():
    schema = json_schema()
    assert "Meta" in schema["$defs"]
    assert schema["properties"]["Meta"] == {"$ref": "#/$defs/Meta"}


def test_migrate_creates_tables(settings):
    migrate(settings)
    migrate(settings)  # 重跑不應出錯
    import sqlite3

    con = sqlite3.connect(settings.db_path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "ingest_log" in names


def _git(*args, cwd):  # noqa: ANN001
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_data_commit_is_single_orphan_commit(tmp_path, settings):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.name", "test", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    (repo / "README.md").write_text("x")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "init", cwd=repo)

    run_export(settings)
    (settings.export_dir / "bars").mkdir()
    (settings.export_dir / "bars" / "2330.json").write_text("{}")

    c1 = build_data_commit(settings.export_dir, repo)
    c2 = build_data_commit(settings.export_dir, repo)
    # 每次都是沒有父節點的單一 commit
    assert _git("rev-list", "--count", "data", cwd=repo) == "1"
    assert _git("rev-parse", "data", cwd=repo) == c2
    assert c1 and c2
    files = set(_git("ls-tree", "-r", "--name-only", "data", cwd=repo).splitlines())
    assert {"meta.json", "bars/2330.json"} <= files
    # 使用者的工作目錄與 index 不受影響
    assert _git("status", "--porcelain", cwd=repo) == ""
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo) == "main"
