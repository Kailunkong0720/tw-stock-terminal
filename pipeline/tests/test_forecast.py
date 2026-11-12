from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.analytics.adjust import Action
from pipeline.forecast.data import SymbolHistory, model_input, past_return, realized_returns
from pipeline.forecast.kronos_runner import backtest_dates
from pipeline.forecast.signal import hit_stats, label, signals, spearman, step_stats


def history(n: int = 60, split_on: int | None = None) -> SymbolHistory:
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    close = np.linspace(100, 130, n)
    actions = []
    if split_on is not None:
        close[split_on:] /= 4
        actions.append(Action(dates[split_on], 0.25, True))
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, 1000.0),
            "value": close * 1000,
        },
        index=pd.Index(dates, name="date"),
    )
    return SymbolHistory("TEST", bars, actions)


def test_model_input_has_no_lookahead():
    """基準日 T 的輸入，不受 T 之後的價格或公司行動影響（PLAN.md 9 Phase 3 驗收）。"""
    T = date(2024, 1, 1) + timedelta(days=39)
    full = history(60, split_on=50)  # 分割發生在 T 之後
    a = model_input(full, T, 30)

    # 把 T 之後的資料與公司行動全部拿掉
    cut = SymbolHistory("TEST", full.bars[full.bars.index <= T], [x for x in full.actions if x.ex_date <= T])
    b = model_input(cut, T, 30)
    pd.testing.assert_frame_equal(a, b)
    assert a.index[-1] == T and len(a) == 30

    # 改動 T 之後的價格也不影響
    altered = history(60, split_on=50)
    altered.bars.loc[altered.bars.index > T, "close"] *= 3
    pd.testing.assert_frame_equal(a, model_input(altered, T, 30))


def test_model_input_adjusts_for_past_split_only():
    h = history(60, split_on=20)
    T = h.dates[40]
    x = model_input(h, T, 30)  # 窗口跨過分割日
    ret = x["close"].pct_change().dropna()
    assert ret.abs().max() < 0.05, "窗口內的分割必須被還原"
    assert model_input(h, h.dates[10], 30) is None  # 不足 30 根


def test_realized_and_past_returns():
    h = history(60, split_on=50)
    T = h.dates[45]
    r = realized_returns(h, T, [5, 10, 20])
    assert r[20] is None
    assert r[5] == pytest.approx(h.bars["close"].iloc[50] * 4 / h.bars["close"].iloc[45] - 1)  # 跨分割仍是真實報酬
    assert past_return(h, T, 20) > 0


def test_step_stats_and_signals():
    rng = np.random.default_rng(0)
    paths = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.02, (200, 20)), axis=1))
    steps = step_stats(paths, 100.0)
    assert len(steps) == 20 and steps[0]["step"] == 1
    for s in steps:
        assert s["p05"] <= s["p25"] <= s["p50"] <= s["p75"] <= s["p95"]
        assert 0 <= s["up_prob"] <= 1 and s["mdd_p50"] <= 0
    sig = {s.horizon: s for s in signals(steps, 100.0)}
    assert set(sig) == {5, 10, 20}
    assert sig[20].up_prob > 0.5


def test_labels():
    assert label(0.7, 0.03) == "偏多"
    assert label(0.6, 0.01) == "略偏多"
    assert label(0.5, 0.0) == "中性"
    assert label(0.42, -0.01) == "略偏空"
    assert label(0.3, -0.04) == "偏空"


def test_hit_stats_and_edge():
    # 模型永遠看多、市場 60% 上漲：命中率 60%，與「一律看多」基準相同 → 沒有優勢
    recs = [(0.01, 0.02, None)] * 60 + [(0.01, -0.02, None)] * 40
    hs = hit_stats(recs)
    assert hs.hit_rate == pytest.approx(0.6) and hs.baseline_rate == pytest.approx(0.6)
    assert not hs.has_edge
    # 模型每次都對 → 有優勢
    good = [(0.01, 0.02, -0.01)] * 30 + [(-0.01, -0.02, 0.01)] * 30
    assert hit_stats(good).has_edge


def test_spearman_and_backtest_dates():
    assert spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    cal = [date(2023, 1, 2) + timedelta(days=i) for i in range(900)]
    ds = backtest_dates(cal, every=20, years=2)
    assert ds[0] == cal[-21]  # 最新的基準日之後還有 20 天可驗證
    assert all(a > b for a, b in zip(ds, ds[1:], strict=False))
    assert ds[-1] >= cal[-1] - timedelta(days=730)
