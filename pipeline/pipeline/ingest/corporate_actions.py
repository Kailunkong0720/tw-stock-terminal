"""公司行動：除權息、減資、變更面額、ETF 分割與反分割（PLAN.md 3.2）。

四個證交所報表都給「停止買賣前（或除權息前）收盤價」與「參考價」，
調整因子 = 參考價 ÷ 前收。在該日之前的每一天，還原價 = 原始價 × 之後所有因子的乘積。

端點（2026-11-12 從證交所網站實測）：
- 除權除息計算結果表      /rwd/zh/exRight/TWT49U
- 股票減資恢復買賣參考價   /rwd/zh/reducation/TWTAUU   ← 路徑是 reducation（證交所原本的拼法）
- 變更面額恢復買賣參考價   /rwd/zh/change/TWTB8U
- ETF 分割（反分割）參考價 /rwd/zh/split/TWTCAU
皆接受 startDate、endDate（YYYYMMDD），以年為單位查詢。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import session_scope
from pipeline.core.http import HttpClient
from pipeline.ingest.common import done_keys, last_ready_date, mark, upsert
from pipeline.ingest.parse import clean_code, is_no_data, is_ok, roc_date, rows_as_dicts, to_float
from pipeline.models import CorporateAction

log = logging.getLogger(__name__)

BASE = "https://www.twse.com.tw/rwd/zh"


@dataclass(frozen=True)
class Report:
    source: str
    path: str


REPORTS = [
    Report("twse_twt49u", "exRight/TWT49U"),
    Report("twse_twtauu", "reducation/TWTAUU"),
    Report("twse_twtb8u", "change/TWTB8U"),
    Report("twse_twtcau", "split/TWTCAU"),
]


def _row(symbol, ex_date, type_, prev, ref, affects, detail, source) -> dict | None:  # noqa: ANN001
    if not symbol or prev is None or ref is None or prev <= 0 or ref <= 0:
        return None
    return {
        "symbol": symbol,
        "ex_date": ex_date,
        "type": type_,
        "prev_close": prev,
        "ref_price": ref,
        "factor": ref / prev,
        "affects_shares": affects,
        "detail": detail,
        "source": source,
    }


def parse_twt49u(payload: dict) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        kind = str(r.get("權/息", "")).strip()
        type_ = {"息": "dividend_cash", "權": "dividend_stock", "權息": "dividend_both"}.get(kind, f"exright_{kind}")
        row = _row(
            clean_code(r.get("股票代號")),
            roc_date(r["資料日期"]),
            type_,
            to_float(r.get("除權息前收盤價")),
            to_float(r.get("除權息參考價")),
            "權" in kind,
            f"權值+息值 {str(r.get('權值+息值', '')).strip()}",
            "TWT49U",
        )
        if row:
            out.append(row)
    return out


def parse_twtauu(payload: dict) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        row = _row(
            clean_code(r.get("股票代號")),
            roc_date(r["恢復買賣日期"]),
            "capital_reduction",
            to_float(r.get("停止買賣前收盤價格")),
            to_float(r.get("恢復買賣參考價")),
            True,
            f"減資原因：{str(r.get('減資原因', '')).strip()}",
            "TWTAUU",
        )
        if row:
            out.append(row)
    return out


def parse_twtb8u(payload: dict) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        row = _row(
            clean_code(r.get("股票代號")),
            roc_date(r["恢復買賣日期"]),
            "par_change",
            to_float(r.get("停止買賣前收盤價格")),
            to_float(r.get("恢復買賣參考價")),
            True,
            "變更面額",
            "TWTB8U",
        )
        if row:
            out.append(row)
    return out


def parse_twtcau(payload: dict) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        kind = str(r.get("分割(反分割)", "")).strip()
        row = _row(
            clean_code(r.get("ETF代號")),
            roc_date(r["恢復買賣日期"]),
            "etf_reverse_split" if "反" in kind else "etf_split",
            to_float(r.get("停止買賣前收盤價格")),
            to_float(r.get("恢復買賣參考價")),
            True,
            kind,
            "TWTCAU",
        )
        if row:
            out.append(row)
    return out


PARSERS = {
    "twse_twt49u": parse_twt49u,
    "twse_twtauu": parse_twtauu,
    "twse_twtb8u": parse_twtb8u,
    "twse_twtcau": parse_twtcau,
}


def ingest_corporate_actions(settings: Settings, start: date = COVERAGE_START, end: date | None = None) -> None:
    end = end or last_ready_date()
    # 預告的除權息也可能在未來幾天，查到年底
    years = list(range(start.year, end.year + 1))
    with HttpClient(settings.http_cache_dir) as http:
        for rep in REPORTS:
            with session_scope(settings) as s:
                done = done_keys(s, rep.source)
            for y in years:
                key = str(y)
                is_current = y == end.year
                if key in done and not is_current:
                    continue
                params = {"startDate": f"{y}0101", "endDate": f"{y}1231", "response": "json"}
                # 今年的資料會持續增加，不使用快取
                payload = http.get_json(f"{BASE}/{rep.path}", params, use_cache=not is_current, should_cache=is_ok)
                with session_scope(settings) as s:
                    if is_ok(payload):
                        rows = PARSERS[rep.source](payload)
                        upsert(s, CorporateAction, rows)
                        mark(s, rep.source, key, "ok" if not is_current else "partial", len(rows))
                        log.info("%s %d：%d 筆", rep.path, y, len(rows))
                    elif is_no_data(payload):
                        mark(s, rep.source, key, "empty" if not is_current else "partial")
                        log.info("%s %d：無資料", rep.path, y)
                    else:
                        mark(s, rep.source, key, "error", note=str(payload.get("stat"))[:200])
                        log.warning("%s %d 回應異常：%s", rep.path, y, payload.get("stat"))
