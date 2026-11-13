"""記錄分析的執行時間、資料期間與參數，輸出到網站的「分析說明」。"""

from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pipeline.core.config import Settings
from pipeline.core.db import session_scope

TPE = ZoneInfo("Asia/Taipei")


def now() -> str:
    return datetime.now(TPE).replace(microsecond=0).isoformat()


def save_run(
    settings: Settings,
    step: str,
    started_at: str,
    data_from: date | None,
    data_to: date | None,
    params: dict | None = None,
    summary: str | None = None,
) -> None:
    from pipeline.models import AnalysisRun

    with session_scope(settings) as s:
        s.add(
            AnalysisRun(
                step=step,
                started_at=started_at,
                finished_at=now(),
                data_from=data_from,
                data_to=data_to,
                params=json.dumps(params or {}, ensure_ascii=False, default=str),
                summary=summary,
            )
        )
