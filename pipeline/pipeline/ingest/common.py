"""抓取步驟共用的工具：日期迭代、抓取紀錄、批次寫入、進度回報。"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from pipeline.models import IngestLog

log = logging.getLogger(__name__)
TPE = ZoneInfo("Asia/Taipei")

# 收盤資料通常在 14:00–15:00 之間公布；15:30 之前不把「今天」當成可抓的日子
SAME_DAY_READY = (15, 30)


def now_tpe() -> datetime:
    return datetime.now(TPE)


def last_ready_date(now: datetime | None = None) -> date:
    """最後一個「收盤資料應該已經公布」的日期（不判斷是否為交易日）。"""
    now = now or now_tpe()
    if (now.hour, now.minute) >= SAME_DAY_READY:
        return now.date()
    return now.date() - timedelta(days=1)


def weekdays(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def done_keys(session: Session, source: str) -> set[str]:
    rows = session.execute(
        select(IngestLog.key).where(IngestLog.source == source, IngestLog.status.in_(("ok", "empty")))
    ).scalars()
    return set(rows)


def mark(session: Session, source: str, key: str, status: str, rows: int = 0, note: str | None = None) -> None:
    stmt = insert(IngestLog).values(source=source, key=key, status=status, rows=rows, note=note)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "key"],
        set_={"status": status, "rows": rows, "note": note, "fetched_at": datetime.now()},
    )
    session.execute(stmt)


def upsert(session: Session, model: Any, rows: Sequence[dict], chunk: int = 500) -> int:
    """以主鍵為準，存在就覆蓋（INSERT OR REPLACE）。"""
    if not rows:
        return 0
    table = model.__table__
    for i in range(0, len(rows), chunk):
        session.execute(insert(table).prefix_with("OR REPLACE"), list(rows[i : i + chunk]))
    return len(rows)


class Progress:
    """長時間回補的進度與預估剩餘時間。"""

    def __init__(self, label: str, total: int, every: int = 25) -> None:
        self.label, self.total, self.every = label, total, every
        self.done = 0
        self.t0 = time.monotonic()

    def tick(self, extra: str = "") -> None:
        self.done += 1
        if self.done % self.every == 0 or self.done == self.total:
            elapsed = time.monotonic() - self.t0
            rate = elapsed / self.done
            eta = rate * (self.total - self.done)
            log.info(
                "%s：%d/%d（%.0f%%），已用 %.0f 分，預估剩 %.0f 分 %s",
                self.label,
                self.done,
                self.total,
                100 * self.done / max(self.total, 1),
                elapsed / 60,
                eta / 60,
                extra,
            )


def chunked(items: Iterable[Any], n: int) -> Iterator[list[Any]]:
    buf: list[Any] = []
    for it in items:
        buf.append(it)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf
