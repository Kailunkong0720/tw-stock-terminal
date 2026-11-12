"""資料品質不變量（PLAN.md 3.2）。

台股普通股有 ±10% 漲跌幅限制，所以還原後的日報酬絕對值超過 10.5% 就代表漏了一個公司行動。
兩次成交之間若隔了 k 個交易日（中間的日子有掛牌但無成交，例如跌停鎖死），
限制會複利累積：上限 1.105^k − 1、下限 1 − 0.895^k。
已知的例外：
- 新上市（資料期間內才開始交易）的前 5 個交易日：無漲跌幅限制
- 停止買賣後恢復交易的第一天（與前一次成交之間隔了 5 個以上的交易日）
只檢查普通股：國外成分 ETF 沒有漲跌幅限制，槓桿 ETF 的限制也不同。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import Engine

from pipeline.analytics.adjust import Action, cumulative_factors

LIMIT = 0.105
NEW_LISTING_DAYS = 5
HALT_GAP_DAYS = 5


@dataclass
class Violation:
    symbol: str
    date: date
    prev_date: date
    ret: float
    raw_ret: float
    reason: str | None  # None 表示無法解釋


def find_violations(engine: Engine, coverage_start: date) -> list[Violation]:
    bars = pd.read_sql_query(
        "SELECT b.symbol, b.date, b.close FROM daily_bar b JOIN security s ON s.symbol = b.symbol "
        "WHERE s.kind = 'stock' AND b.close IS NOT NULL ORDER BY b.symbol, b.date",
        engine,
    )
    if bars.empty:
        return []
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    acts = pd.read_sql_query(
        "SELECT symbol, ex_date, factor, affects_shares, limit_up, limit_down FROM corporate_action", engine
    )
    acts["ex_date"] = pd.to_datetime(acts["ex_date"]).dt.date
    acts_by = {
        s: [Action(r.ex_date, r.factor, bool(r.affects_shares)) for r in g.itertuples()]
        for s, g in acts.groupby("symbol")
    }
    # 公司行動日當天的實際漲跌停價（含現增的除權日不對稱）
    limits = {
        (r.symbol, r.ex_date): (r.limit_down, r.limit_up)
        for r in acts.itertuples()
        if pd.notna(r.limit_up) and pd.notna(r.limit_down)
    }
    calendar = sorted(set(bars["date"]))
    cal_idx = {d: i for i, d in enumerate(calendar)}
    first_day = calendar[0]

    out: list[Violation] = []
    for sym, g in bars.groupby("symbol"):
        dates = list(g["date"])
        closes = list(g["close"])
        f = cumulative_factors(dates, acts_by.get(sym, []))
        adj = [c * k for c, k in zip(closes, f, strict=True)]
        listed_late = dates[0] > first_day
        for i in range(1, len(dates)):
            r = adj[i] / adj[i - 1] - 1
            k = cal_idx[dates[i]] - cal_idx[dates[i - 1]]
            if -(1 - (1 - LIMIT) ** k) <= r <= (1 + LIMIT) ** k - 1:
                continue
            lim = limits.get((sym, dates[i]))
            if lim and k == 1 and lim[0] * 0.999 <= closes[i] <= lim[1] * 1.001:
                continue  # 在報表公布的當日漲跌停範圍內
            reason = None
            if listed_late and i < NEW_LISTING_DAYS:
                reason = "新上市前 5 日無漲跌幅限制"
            elif k > HALT_GAP_DAYS:
                reason = f"停止買賣 {k - 1} 個交易日後恢復交易"
            out.append(Violation(sym, dates[i], dates[i - 1], r, closes[i] / closes[i - 1] - 1, reason))
    return out
