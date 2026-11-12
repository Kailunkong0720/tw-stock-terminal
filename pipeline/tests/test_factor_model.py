from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from pipeline.events.factor_model import _overnight, rolling_factor_fit


def synthetic(T: int = 600, seed: int = 0):
    rng = np.random.default_rng(seed)
    m = rng.normal(0, 0.01, T)
    s = rng.normal(0, 0.008, T)
    o = rng.normal(0, 0.015, T)
    y = 0.0005 + 1.2 * m + 0.5 * s + 0.3 * o + rng.normal(0, 0.005, T)
    X = np.column_stack([np.ones(T), m, s, o])
    return y, X


def test_recovers_coefficients():
    y, X = synthetic()
    beta, resid, sigma = rolling_factor_fit(y, X, window=250, min_obs=120)
    assert np.isnan(beta[:120]).all()
    b = beta[-1]
    assert b[1] == pytest.approx(1.2, abs=0.1)
    assert b[2] == pytest.approx(0.5, abs=0.15)
    assert b[3] == pytest.approx(0.3, abs=0.08)
    assert sigma[-1] == pytest.approx(0.005, rel=0.2)


def test_matches_lstsq_and_excludes_day_t():
    y, X = synthetic(400, seed=1)
    y[50] = np.nan  # 無效觀測不納入
    beta, resid, _ = rolling_factor_fit(y, X, window=100, min_obs=60)
    t = 300
    # 對照：t 之前最近 100 個有效觀測的 OLS
    idx = [i for i in range(t) if not np.isnan(y[i])][-100:]
    ref, *_ = np.linalg.lstsq(X[idx], y[idx], rcond=None)
    # 極小的 ridge 項（避免類股欄全為 0 時奇異）造成約 1e-6 的差異
    assert beta[t] == pytest.approx(ref, rel=1e-4, abs=1e-6)

    # 改變 t 當天的報酬不影響 t 的係數（只影響殘差）
    y2 = y.copy()
    y2[t] += 0.1
    beta2, resid2, _ = rolling_factor_fit(y2, X, window=100, min_obs=60)
    assert beta2[t] == pytest.approx(beta[t])
    assert resid2[t] == pytest.approx(resid[t] + 0.1)


def test_overnight_uses_previous_us_session():
    us = pd.Series(
        [0.01, -0.02, 0.03],
        index=[date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],  # 美股 1/5、1/6、1/7
    )
    tw = [date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 5)]
    out = _overnight(us, sorted(tw))
    # 台股 1/5 之前沒有美股資料；1/6 對應美股 1/5；1/7 對應 1/6；1/8 對應 1/7
    assert np.isnan(out[0]) and list(out[1:]) == [0.01, -0.02, 0.03]
    assert date(2026, 1, 5) + timedelta(days=1) == date(2026, 1, 6)
