"""公開資訊觀測站歷史重大訊息（PLAN.md 3.4 第一層）。

端點（2026-11-12 從新版 MOPS 網站實測）：
  POST https://mops.twse.com.tw/mops/api/t05st01
  本文 {"companyId": "2330", "year": "114", "month": "all", "firstDay": "", "lastDay": ""}
  回應 result.data 每列：[代號, 名稱, 民國日期, 時間, 主旨, {明細參數}]
限速：每個請求間隔至少 5 秒。只抓追蹤池。
"""

from __future__ import annotations

import bisect
import logging
from datetime import date, datetime, time, timedelta

import pandas as pd
from sqlalchemy.dialects.sqlite import insert

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.core.http import HttpClient
from pipeline.events.classify import classify
from pipeline.ingest.common import Progress, done_keys, last_ready_date, mark
from pipeline.ingest.parse import clean_code, roc_date
from pipeline.models import Event

log = logging.getLogger(__name__)

SOURCE = "mops_t05st01"
URL = "https://mops.twse.com.tw/mops/api/t05st01"
CLOSE = time(13, 30)


def trading_calendar(engine) -> list[date]:  # noqa: ANN001
    return [
        pd.Timestamp(d).date()
        for d in pd.read_sql_query("SELECT DISTINCT date FROM daily_bar ORDER BY date", engine)["date"]
    ]


def effective_trade_date(at: datetime, calendar: list[date]) -> date:
    """公告影響的交易日：交易日 13:30 前公告 → 當天；盤後或非交易日 → 下一個交易日。"""
    d = at.date()
    i = bisect.bisect_left(calendar, d)
    if i < len(calendar) and calendar[i] == d and at.time() < CLOSE:
        return d
    j = bisect.bisect_right(calendar, d)
    if j < len(calendar):
        return calendar[j]
    # 超出資料期間：以下一個平日估計
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n


def parse_t05st01(payload: dict, calendar: list[date]) -> list[dict]:
    rows = ((payload or {}).get("result") or {}).get("data") or []
    out = []
    for r in rows:
        if len(r) < 5:
            continue
        symbol, d_str, t_str, title = clean_code(r[0]), r[2], str(r[3]).strip(), " ".join(str(r[4]).split())
        try:
            d = roc_date(d_str)
            h, m, s = (int(x) for x in t_str.split(":"))
            at = datetime.combine(d, time(h, m, s))
        except (ValueError, TypeError):
            continue
        params = (r[5] or {}).get("parameters", {}) if len(r) > 5 and isinstance(r[5], dict) else {}
        serial = params.get("serialNumber", "")
        type_, direction = classify(title)
        out.append(
            {
                "uid": f"mops:{symbol}:{d.isoformat()}:{t_str}:{serial}",
                "symbol": symbol,
                "at": at,
                "trade_date": effective_trade_date(at, calendar),
                "level": "official",
                "type": type_,
                "direction": direction,
                "title": title,
                "source": "MOPS",
                "url": "https://mops.twse.com.tw/mops/#/web/t05st01",
                "detail": None,
            }
        )
    return out


def ingest_mops(settings: Settings, symbols: list[str] | None = None) -> None:
    from pipeline.forecast.kronos_runner import tracked_symbols

    engine = get_engine(settings)
    calendar = trading_calendar(engine)
    symbols = symbols or tracked_symbols(settings)
    # ETF 不是公司，MOPS 會回「公司代號格式錯誤」
    etfs = set(pd.read_sql_query("SELECT symbol FROM security WHERE kind = 'etf'", engine)["symbol"])
    symbols = [s for s in symbols if s not in etfs]
    end = last_ready_date()
    years = list(range(COVERAGE_START.year, end.year + 1))
    with session_scope(settings) as s:
        done = done_keys(s, SOURCE)
    jobs = [(sym, y) for sym in symbols for y in years if f"{sym}:{y}" not in done or y == end.year]
    log.info("歷史重大訊息：待抓 %d 個（%d 檔 × %d 年）", len(jobs), len(symbols), len(years))
    prog = Progress("歷史重大訊息", len(jobs), every=50)
    with HttpClient(settings.http_cache_dir) as http:
        for sym, y in jobs:
            body = {"companyId": sym, "year": str(y - 1911), "month": "all", "firstDay": "", "lastDay": ""}
            payload = http.get_json(
                URL, json_body=body, use_cache=y != end.year, should_cache=lambda p: p.get("code") == 200
            )
            with session_scope(settings) as s:
                if payload.get("code") == 200:
                    rows = parse_t05st01(payload, calendar)
                    for row in rows:
                        stmt = insert(Event).values(**row)
                        s.execute(
                            stmt.on_conflict_do_update(
                                index_elements=["uid"], set_={k: row[k] for k in row if k != "uid"}
                            )
                        )
                    mark(s, SOURCE, f"{sym}:{y}", "ok" if y != end.year else "partial", len(rows))
                else:
                    # 該公司該年可能尚未上市（查無資料），記錄後不重試
                    msg = str(payload.get("message"))[:200]
                    mark(s, SOURCE, f"{sym}:{y}", "empty" if "查無" in msg or "無資料" in msg else "error", note=msg)
            prog.tick()
