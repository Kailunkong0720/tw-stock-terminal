from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.core.config import Settings


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    if config.getoption("-m"):
        return
    skip = pytest.mark.skip(reason="需要連網；用 -m network 執行")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(data_dir=tmp_path / "data", export_dir=tmp_path / "export")
    s.ensure_dirs()
    return s


FIXTURES = Path(__file__).parent / "fixtures"
