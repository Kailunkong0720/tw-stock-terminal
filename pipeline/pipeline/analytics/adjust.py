"""還原價（PLAN.md 3.2）。

累積因子 cum(t) = 所有 ex_date > t 的公司行動因子的乘積。
還原價 = 原始價 × cum(t)；還原量 = 原始量 ÷ 股數因子（只計入會改變股數的事件）。

資料庫只存原始價與公司行動，還原價在需要時計算；前端也用同樣的方式自己算
（輸出時附上累積因子），所以「還原／原始」切換不需要重新抓資料。

回測時要用 `as_of` 參數：只計入在基準日當天以前已經發生的公司行動，避免用到未來資訊。
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Action:
    ex_date: date
    factor: float
    affects_shares: bool = False


def cumulative_factors(dates: Sequence[date], actions: Sequence[Action], as_of: date | None = None) -> list[float]:
    """每個日期的累積價格因子。dates 必須遞增。"""
    acts = sorted((a for a in actions if as_of is None or a.ex_date <= as_of), key=lambda a: a.ex_date)
    ex_dates = [a.ex_date for a in acts]
    # suffix[i] = acts[i:] 的因子乘積
    suffix = [1.0] * (len(acts) + 1)
    for i in range(len(acts) - 1, -1, -1):
        suffix[i] = suffix[i + 1] * acts[i].factor
    # 日期 d 適用所有 ex_date > d 的事件
    return [suffix[bisect.bisect_right(ex_dates, d)] for d in dates]


def cumulative_share_factors(
    dates: Sequence[date], actions: Sequence[Action], as_of: date | None = None
) -> list[float]:
    return cumulative_factors(dates, [a for a in actions if a.affects_shares], as_of)


def adjust_prices(prices: Sequence[float | None], factors: Sequence[float]) -> list[float | None]:
    return [None if p is None else p * f for p, f in zip(prices, factors, strict=True)]
