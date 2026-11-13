from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from pipeline.core.db import get_engine, migrate
from pipeline.core.provenance import now, save_run
from pipeline.export.provenance import build_analyses

TPE = ZoneInfo("Asia/Taipei")


def test_analyses_with_and_without_runs(settings):
    migrate(settings)
    engine = get_engine(settings)
    cal = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    gen = datetime(2026, 1, 8, 9, 0, tzinfo=TPE)

    items = {a.id: a for a in build_analyses(settings, engine, cal, gen)}
    # 沒有執行紀錄也要能輸出，並說明原因
    assert {"adjust", "flows", "factor", "attribution", "graph", "overnight"} <= set(items)
    assert items["factor"].run_last is None and "尚無執行紀錄" in (items["factor"].summary or "")
    assert items["adjust"].run_last == gen
    assert all(a.method and a.inputs for a in items.values())

    started = now()
    save_run(settings, "factor", started, date(2026, 1, 5), date(2026, 1, 7), {"window": 250}, "3 筆")
    items = {a.id: a for a in build_analyses(settings, engine, cal, gen)}
    f = items["factor"]
    assert f.data_from == date(2026, 1, 5) and f.data_to == date(2026, 1, 7)
    assert f.summary == "3 筆"
    assert f.run_last is not None and f.run_last.utcoffset() is not None  # 時間帶時區（台北）
