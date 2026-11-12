"""證交所每日收盤行情（MI_INDEX，type=ALLBUT0999）。

一個請求拿到當日全部上市股票、ETF 的開高低收量，以及所有證交所編製的價格指數
（加權指數與各類股指數）。PLAN.md 3.1。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import session_scope
from pipeline.core.http import HttpClient
from pipeline.ingest.common import Progress, done_keys, last_ready_date, mark, upsert, weekdays
from pipeline.ingest.parse import (
    clean_code,
    clean_name,
    find_table,
    is_no_data,
    is_ok,
    rows_as_dicts,
    sign_of,
    to_float,
    to_int,
)
from pipeline.models import DailyBar, IndexBar, Security

log = logging.getLogger(__name__)

SOURCE = "twse_mi_index"
URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"


def classify(symbol: str, name: str) -> str:
    """依代號與名稱判斷證券類別。"""
    if re.fullmatch(r"00\d{2,4}[A-Z]?", symbol):
        return "etf"
    if re.fullmatch(r"02\d{4}[A-Z]?", symbol):
        return "etn"
    if name.endswith("-DR") or (name.endswith("DR") and re.fullmatch(r"9\d{3,5}", symbol)):
        return "tdr"
    if re.fullmatch(r"[1-9]\d{3}", symbol):
        return "stock"
    if re.fullmatch(r"[1-9]\d{3}[A-Z]", symbol):
        return "preferred"
    return "other"


def signed(sign: int, magnitude: float | None) -> float | None:
    """證交所把漲跌的正負號與數值分開給。平盤為 0；符號是 X（除權息等）時無法判斷，回傳 None。"""
    if magnitude is None:
        return None
    if sign:
        return sign * magnitude
    return 0.0 if magnitude == 0 else None


@dataclass
class DayResult:
    day: date
    bars: list[dict] = field(default_factory=list)
    indices: list[dict] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)


def parse_mi_index(payload: dict, day: date) -> DayResult:
    out = DayResult(day)

    quotes = find_table(payload, title_contains="每日收盤行情")
    if quotes is None:
        raise ValueError(f"{day} 的回應中找不到「每日收盤行情」表")
    for r in rows_as_dicts(quotes["fields"], quotes["data"]):
        symbol = clean_code(r["證券代號"])
        if not symbol:
            continue
        out.names[symbol] = clean_name(r["證券名稱"])
        out.bars.append(
            {
                "symbol": symbol,
                "date": day,
                "open": to_float(r["開盤價"]),
                "high": to_float(r["最高價"]),
                "low": to_float(r["最低價"]),
                "close": to_float(r["收盤價"]),
                "change": signed(sign_of(r.get("漲跌(+/-)")), to_float(r.get("漲跌價差"))),
                "volume": to_int(r["成交股數"]) or 0,
                "value": to_int(r["成交金額"]) or 0,
                "trades": to_int(r["成交筆數"]) or 0,
                "pe": to_float(r.get("本益比")) or None,
            }
        )

    # 價格指數與報酬指數（含息）。因子模型用報酬指數：權重股除息時價格指數會下跌，
    # 用價格指數會把除息誤當成類股下跌（例：2603 長榮 2023-06-30 除息，航運類價格指數當日 −9.9%）。
    for title, name_col in (("價格指數(臺灣證券交易所)", "指數"), ("報酬指數(臺灣證券交易所)", "報酬指數")):
        idx = find_table(payload, title_contains=title)
        if idx is None:
            continue
        for r in rows_as_dicts(idx["fields"], idx["data"]):
            close = to_float(r.get("收盤指數"))
            if close is None:
                continue
            out.indices.append(
                {
                    "index_id": f"TWSE:{clean_name(r[name_col])}",
                    "date": day,
                    "close": close,
                    "change": signed(sign_of(r.get("漲跌(+/-)")), to_float(r.get("漲跌點數"))),
                    # 百分比欄位本身已帶正負號
                    "change_pct": to_float(r.get("漲跌百分比(%)")),
                }
            )
    return out


def fetch_day(http: HttpClient, day: date) -> dict:
    return http.get_json(
        URL,
        {"date": day.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"},
        # 只快取成功的回應；「查無資料」可能是今天還沒公布
        should_cache=is_ok,
    )


def _upsert_securities(session, names: dict[str, str]) -> None:  # noqa: ANN001
    existing = {s.symbol: s for s in session.execute(select(Security)).scalars()}
    for symbol, name in names.items():
        sec = existing.get(symbol)
        if sec is None:
            session.add(Security(symbol=symbol, name=name, market="TWSE", kind=classify(symbol, name)))
        elif sec.name != name:
            sec.name = name  # 以最新名稱為準（依日期遞增處理時）


def refresh_bar_ranges(session) -> None:  # noqa: ANN001
    rows = session.execute(
        select(DailyBar.symbol, func.min(DailyBar.date), func.max(DailyBar.date)).group_by(DailyBar.symbol)
    ).all()
    ranges = {s: (a, b) for s, a, b in rows}
    for sec in session.execute(select(Security)).scalars():
        if sec.symbol in ranges:
            sec.first_bar, sec.last_bar = ranges[sec.symbol]


def ingest_daily(settings: Settings, start: date = COVERAGE_START, end: date | None = None) -> None:
    end = end or last_ready_date()
    with session_scope(settings) as s:
        done = done_keys(s, SOURCE)
    pending = [d for d in weekdays(start, end) if d.isoformat() not in done]
    if not pending:
        log.info("每日收盤行情：已是最新（至 %s）", end)
        return
    log.info("每日收盤行情：待抓 %d 天（%s ~ %s）", len(pending), pending[0], pending[-1])

    progress = Progress("每日收盤行情", len(pending))
    with HttpClient(settings.http_cache_dir) as http:
        for day in pending:
            payload = fetch_day(http, day)
            with session_scope(settings) as s:
                if is_ok(payload):
                    res = parse_mi_index(payload, day)
                    _upsert_securities(s, res.names)
                    upsert(s, DailyBar, res.bars)
                    upsert(s, IndexBar, res.indices)
                    mark(s, SOURCE, day.isoformat(), "ok", len(res.bars))
                elif is_no_data(payload):
                    # 休市日。今天的「查無資料」可能只是還沒公布，不記錄
                    if day < last_ready_date():
                        mark(s, SOURCE, day.isoformat(), "empty")
                else:
                    mark(s, SOURCE, day.isoformat(), "error", note=str(payload.get("stat"))[:200])
                    log.warning("%s 回應異常：%s", day, payload.get("stat"))
            progress.tick(f"（網路 {http.stats['network']}、快取 {http.stats['cache_hit']}）")

    with session_scope(settings) as s:
        refresh_bar_ranges(s)
