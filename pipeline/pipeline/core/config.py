"""路徑與設定。所有路徑都由這裡決定，其他模組不要自己拼路徑。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = PIPELINE_DIR.parent

# 資料涵蓋的起點（PLAN.md 1.1）
COVERAGE_START = date(2020, 1, 1)

# 輸出資料的總大小預算（PLAN.md 第 8 節）。2026-11-13 加入上櫃（約 900 檔）後為 218 MB，
# 由 200 MB 調高到 300 MB；GitHub Pages 網站上限是 1 GB，單一檔案遠小於 GitHub 的 100 MB 限制
EXPORT_BUDGET_BYTES = 300 * 1024 * 1024


def _load_dotenv(path: Path) -> None:
    """讀取 repo 根目錄的 .env（不覆蓋已存在的環境變數）。刻意不引入 python-dotenv。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: PIPELINE_DIR / "data")
    export_dir: Path = field(default_factory=lambda: REPO_ROOT / "site" / "public" / "data")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tw.sqlite"

    @property
    def http_cache_dir(self) -> Path:
        return self.data_dir / "http_cache"

    @property
    def run_dir(self) -> Path:
        return self.data_dir / "run"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.http_cache_dir, self.run_dir):
            d.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    _load_dotenv(REPO_ROOT / ".env")
    data_dir = os.environ.get("TWST_DATA_DIR")
    export_dir = os.environ.get("TWST_EXPORT_DIR")
    kwargs = {}
    if data_dir:
        kwargs["data_dir"] = Path(data_dir)
    if export_dir:
        kwargs["export_dir"] = Path(export_dir)
    return Settings(**kwargs)
