"""Kronos 的輸入資料。

最重要的規則：基準日 T 的輸入只能用 T 當天以前已知的資訊——
價格只取到 T，還原也只計入 ex_date ≤ T 的公司行動。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from pipeline.analytics.adjust import Action, cumulative_factors, cumulative_share_factors


@dataclass
class SymbolHistory:
    """一檔股票的原始日線（只含有成交的日子）與全部公司行動。"""

    symbol: str
    bars: pd.DataFrame  # index: date；欄位 open high low close volume value
    actions: list[Action]

    @property
    def dates(self) -> list[date]:
        return list(self.bars.index)


def load_history(engine: Engine, symbol: str) -> SymbolHistory:
    bars = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume, value FROM daily_bar "
        "WHERE symbol = :s AND close IS NOT NULL AND open IS NOT NULL ORDER BY date",
        engine,
        params={"s": symbol},
    )
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    acts = pd.read_sql_query(
        "SELECT ex_date, factor, affects_shares FROM corporate_action WHERE symbol = :s",
        engine,
        params={"s": symbol},
    )
    actions = [
        Action(pd.Timestamp(r.ex_date).date(), float(r.factor), bool(r.affects_shares)) for r in acts.itertuples()
    ]
    return SymbolHistory(symbol, bars.set_index("date"), actions)


def model_input(h: SymbolHistory, base: date, lookback: int) -> pd.DataFrame | None:
    """基準日 base（含）之前最近 lookback 根 K 線的還原資料。不足 lookback 根時回傳 None。

    還原只計入 ex_date ≤ base 的公司行動，所以結果與「base 之後發生什麼事」完全無關。
    """
    past = h.bars[h.bars.index <= base]
    if len(past) < lookback:
        return None
    past = past.iloc[-lookback:]
    dates = list(past.index)
    pf = np.array(cumulative_factors(dates, h.actions, as_of=base))
    sf = np.array(cumulative_share_factors(dates, h.actions, as_of=base))
    return pd.DataFrame(
        {
            "open": past["open"].to_numpy() * pf,
            "high": past["high"].to_numpy() * pf,
            "low": past["low"].to_numpy() * pf,
            "close": past["close"].to_numpy() * pf,
            "volume": past["volume"].to_numpy() / sf,
            "amount": past["value"].to_numpy().astype(float),
        },
        index=pd.Index(dates, name="date"),
    )


def realized_returns(h: SymbolHistory, base: date, horizons: list[int]) -> dict[int, float | None]:
    """基準日之後第 h 根 K 線相對基準日的實際總報酬（含除權息）。這是結果，可以用全部的公司行動。"""
    dates = h.dates
    if base not in h.bars.index:
        return dict.fromkeys(horizons)
    i = dates.index(base)
    f = cumulative_factors(dates, h.actions)
    close = h.bars["close"].to_numpy()
    out: dict[int, float | None] = {}
    for hz in horizons:
        j = i + hz
        out[hz] = None if j >= len(dates) else float(close[j] * f[j] / (close[i] * f[i]) - 1)
    return out


def past_return(h: SymbolHistory, base: date, n: int) -> float | None:
    """基準日之前 n 根 K 線的報酬（動能基準用）。只用 base 以前的資訊。"""
    inp = model_input(h, base, n + 1)
    if inp is None:
        return None
    c = inp["close"].to_numpy()
    return float(c[-1] / c[0] - 1)
