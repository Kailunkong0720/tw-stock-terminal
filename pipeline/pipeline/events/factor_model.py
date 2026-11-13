"""因子拆解與異常波動偵測（PLAN.md 6.1）。

對每檔股票、每個交易日，用「前 250 個有成交日」的線性迴歸把當日報酬拆成：

    個股報酬 = α + β₁·大盤 + β₂·(類股 − 大盤) + β₃·前一晚費半 + 殘差

係數只用 t 之前的資料估計（不含 t 當天），殘差除以窗口內的殘差標準差得到 z。
顯示時：大盤貢獻 = β₁·大盤、類股貢獻 = β₂·(類股 − 大盤)、隔夜美股 = β₃·費半、個股特有 = 其餘（含 α）。

異常波動日：「|z| ≥ 2.5 且個股特有部分 |idio| ≥ 2%」，或「成交量 ≥ 前 20 日均量 3 倍且 |報酬| ≥ 3%」。
與原計劃的差異（2026-11-12 依實際資料調整）：
- z 加上 |idio| ≥ 2% 的門檻。台積電這類佔指數權重極高的股票，對自己所在的指數迴歸後殘差很小，
  只跌 0.85% 也會得到 z = −4.8；沒有經濟意義的小波動不該被當成「需要解釋的大波動」。
- 量能條件加上 |報酬| ≥ 3%：只看量會納入許多價格沒怎麼動的日子。

迴歸用累積和一次算完所有窗口，不逐日呼叫 lstsq。
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import delete

from pipeline.analytics.adjust import Action, cumulative_factors
from pipeline.core.config import Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.ingest.common import upsert
from pipeline.ingest.industry import TAIEX, TAIEX_TR, sector_index_ids, sector_tr_ids
from pipeline.models import PriceMove

log = logging.getLogger(__name__)

WINDOW = 250
MIN_OBS = 120
Z_THRESHOLD = 2.5
VOL_RATIO = 3.0
VOL_MIN_RET = 0.03
MIN_IDIO = 0.02


def rolling_factor_fit(y: np.ndarray, X: np.ndarray, window: int = WINDOW, min_obs: int = MIN_OBS):
    """以 t 之前 window 個有效觀測估計係數，回傳 (beta[T,k], resid[T], sigma[T])。無法估計處為 NaN。

    y: (T,)；X: (T, k)，第一欄應為常數 1。y 或 X 有 NaN 的列視為無效、不納入估計。
    """
    T, k = X.shape
    valid = ~(np.isnan(y) | np.isnan(X).any(axis=1))
    if not valid.any():
        return np.full((T, k), np.nan), np.full(T, np.nan), np.full(T, np.nan)
    w = valid.astype(float)
    Xw = np.where(valid[:, None], X, 0.0)
    yw = np.where(valid, y, 0.0)

    def prefix(a: np.ndarray) -> np.ndarray:
        # P[i] = a[0] + … + a[i-1]；P[0] = 0
        return np.concatenate([np.zeros((1, *a.shape[1:])), np.cumsum(a, axis=0)], axis=0)

    pXX = prefix(Xw[:, :, None] * Xw[:, None, :])
    pXy = prefix(Xw * yw[:, None])
    pyy = prefix(yw * yw)
    pn = prefix(w)

    # 有效觀測的索引 → 第 t 天的窗口是 t 之前最近 window 個有效觀測
    valid_idx = np.flatnonzero(valid)
    count_before = pn[:-1].astype(int)  # t 之前有幾個有效觀測
    lo_count = np.maximum(count_before - window, 0)
    # 窗口起點（在原始索引中的位置）：第 lo_count 個有效觀測
    start = np.where(lo_count < len(valid_idx), valid_idx[np.minimum(lo_count, len(valid_idx) - 1)], T)
    end = np.arange(T)  # 窗口不含 t

    XX = pXX[end] - pXX[np.minimum(start, end)]
    Xy = pXy[end] - pXy[np.minimum(start, end)]
    yy = pyy[end] - pyy[np.minimum(start, end)]
    n = (pn[end] - pn[np.minimum(start, end)]).astype(float)

    ok = n >= min_obs
    beta = np.full((T, k), np.nan)
    resid = np.full(T, np.nan)
    sigma = np.full(T, np.nan)
    if not ok.any():
        return beta, resid, sigma
    ridge = 1e-8 * np.eye(k)
    b = np.linalg.solve(XX[ok] + ridge, Xy[ok][:, :, None])[:, :, 0]
    sse = yy[ok] - 2 * np.einsum("ij,ij->i", b, Xy[ok]) + np.einsum("ij,ijk,ik->i", b, XX[ok], b)
    dof = np.maximum(n[ok] - k, 1)
    beta[ok] = b
    sigma[ok] = np.sqrt(np.maximum(sse, 0) / dof)
    pred = np.einsum("ij,ij->i", X[ok], b)
    resid[ok] = y[ok] - pred
    return beta, resid, sigma


def _index_returns(engine) -> dict[str, pd.Series]:  # noqa: ANN001
    idx = pd.read_sql_query("SELECT index_id, date, close FROM index_bar", engine)
    idx["date"] = pd.to_datetime(idx["date"]).dt.date
    out = {}
    for iid, g in idx.groupby("index_id"):
        s = g.set_index("date")["close"].sort_index()
        out[iid] = s.pct_change()
    return out


def _combine(rets: dict[str, pd.Series], ids: list[str]) -> pd.Series | None:
    parts = [rets[i] for i in ids if i in rets]
    if not parts:
        return None
    s = parts[0]
    for p in parts[1:]:
        s = s.combine_first(p)
    return s


def _sector_series(rets: dict[str, pd.Series], industry: str | None) -> pd.Series | None:
    """產業的類股報酬：優先用報酬指數（含息），缺的日子用價格指數補；指數改名時把各名稱的序列接起來。"""
    tr = _combine(rets, sector_tr_ids(industry))
    px = _combine(rets, sector_index_ids(industry))
    if tr is None:
        return px
    return tr if px is None else tr.combine_first(px)


def _overnight(sox: pd.Series | None, tw_dates: list[date]) -> np.ndarray:
    """每個台股交易日 t 對應「t 之前最近一個美股交易日」的費半報酬。"""
    if sox is None:
        return np.full(len(tw_dates), np.nan)
    s = sox.dropna()
    us_dates = list(s.index)
    vals = s.to_numpy()
    out = np.full(len(tw_dates), np.nan)
    j = -1
    for i, d in enumerate(tw_dates):
        while j + 1 < len(us_dates) and us_dates[j + 1] < d:
            j += 1
        if j >= 0:
            out[i] = vals[j]
    return out


def compute_moves(settings: Settings) -> None:
    from pipeline.core.provenance import now, save_run

    started = now()
    engine = get_engine(settings)
    rets = _index_returns(engine)
    mkt = rets.get(TAIEX_TR)
    if mkt is None:
        log.warning("沒有加權報酬指數，改用價格指數（除息日會有誤差）")
        mkt = rets.get(TAIEX)
    elif TAIEX in rets:
        mkt = mkt.combine_first(rets[TAIEX])
    if mkt is None:
        log.warning("沒有加權指數資料，略過因子拆解")
        return
    sox = rets.get("GLOBAL:SOX")
    if sox is None:
        log.warning("沒有費半資料（先執行 ingest global），隔夜美股因子以 0 計")

    secs = pd.read_sql_query("SELECT symbol, industry FROM security WHERE kind = 'stock'", engine)
    bars = pd.read_sql_query(
        "SELECT b.symbol, b.date, b.close, b.volume FROM daily_bar b JOIN security s ON s.symbol = b.symbol "
        "WHERE s.kind = 'stock' AND b.close IS NOT NULL ORDER BY b.symbol, b.date",
        engine,
    )
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    acts = pd.read_sql_query("SELECT symbol, ex_date, factor, affects_shares FROM corporate_action", engine)
    acts["ex_date"] = pd.to_datetime(acts["ex_date"]).dt.date
    acts_by = {
        s: [Action(r.ex_date, r.factor, bool(r.affects_shares)) for r in g.itertuples()]
        for s, g in acts.groupby("symbol")
    }
    calendar = sorted(pd.to_datetime(pd.read_sql_query("SELECT DISTINCT date FROM daily_bar", engine)["date"]).dt.date)
    cal_idx = {d: i for i, d in enumerate(calendar)}
    industry = dict(zip(secs["symbol"], secs["industry"], strict=True))

    total, anomalies = 0, 0
    with session_scope(settings) as s:
        s.execute(delete(PriceMove))
    for sym, g in bars.groupby("symbol"):
        if len(g) < MIN_OBS + 2:
            continue
        dates = list(g["date"])
        f = np.array(cumulative_factors(dates, acts_by.get(sym, [])))
        adj = g["close"].to_numpy() * f
        r = np.full(len(dates), np.nan)
        r[1:] = adj[1:] / adj[:-1] - 1
        gap = np.ones(len(dates), dtype=int)
        gap[1:] = [cal_idx[b] - cal_idx[a] for a, b in zip(dates[:-1], dates[1:], strict=True)]

        # 大盤與類股報酬也要涵蓋同樣的期間（停牌後恢復時是多日報酬）
        def span_ret(series: pd.Series | None, dates=dates, gap=gap) -> np.ndarray:  # noqa: ANN001
            if series is None:
                return np.full(len(dates), np.nan)
            level = (1 + series.fillna(0)).cumprod()
            lv = level.reindex(calendar).ffill().to_numpy()
            out = np.full(len(dates), np.nan)
            for i in range(1, len(dates)):
                a, b = cal_idx[dates[i - 1]], cal_idx[dates[i]]
                if not np.isnan(lv[a]) and lv[a] > 0:
                    out[i] = lv[b] / lv[a] - 1
            return out

        m = span_ret(mkt)
        sec = _sector_series(rets, industry.get(sym))
        sx = span_ret(sec) - m if sec is not None else np.zeros(len(dates))
        sx = np.where(np.isnan(sx), 0.0, sx)
        on = _overnight(sox, dates)
        on = np.where(np.isnan(on), 0.0, on)
        X = np.column_stack([np.ones(len(dates)), m, sx, on])
        # 停牌後恢復的多日報酬不納入估計（但仍計算拆解）
        y_fit = np.where(gap == 1, r, np.nan)
        beta, _, sigma = rolling_factor_fit(y_fit, X)
        c_mkt = beta[:, 1] * m
        c_sec = beta[:, 2] * sx
        c_on = beta[:, 3] * on
        idio = r - c_mkt - c_sec - c_on
        resid = r - np.einsum("ij,ij->i", X, np.nan_to_num(beta))
        z = resid / sigma
        vol = g["volume"].to_numpy().astype(float)
        vol_ma = pd.Series(vol).shift(1).rolling(20, min_periods=10).mean().to_numpy()
        vol_ratio = np.where(vol_ma > 0, vol / vol_ma, np.nan)
        with np.errstate(invalid="ignore"):
            big_z = (np.abs(z) >= Z_THRESHOLD) & (np.abs(idio) >= MIN_IDIO)
            big_vol = (vol_ratio >= VOL_RATIO) & (np.abs(r) >= VOL_MIN_RET)
        anom = (big_z | big_vol) & ~np.isnan(z)

        def nz(v: float) -> float | None:
            return None if np.isnan(v) else round(float(v), 6)

        rows = [
            {
                "symbol": sym,
                "date": dates[i],
                "ret": round(float(r[i]), 6),
                "gap": int(gap[i]),
                "mkt": nz(c_mkt[i]),
                "sector": nz(c_sec[i]),
                "overnight": nz(c_on[i]),
                "idio": nz(idio[i]) if not np.isnan(beta[i, 0]) else None,
                "z": nz(z[i]),
                "vol_ratio": nz(vol_ratio[i]),
                "anomaly": bool(anom[i]),
            }
            for i in range(1, len(dates))
            if not np.isnan(r[i])
        ]
        with session_scope(settings) as s:
            upsert(s, PriceMove, rows, chunk=2000)
        total += len(rows)
        anomalies += int(anom.sum())
    log.info("因子拆解：%d 筆，異常波動日 %d 筆（%.1f%%）", total, anomalies, 100 * anomalies / max(total, 1))
    with engine.connect() as c:
        lo, hi = c.exec_driver_sql("SELECT MIN(date), MAX(date) FROM price_move").one()
    save_run(
        settings,
        "factor",
        started,
        pd.Timestamp(lo).date() if lo else None,
        pd.Timestamp(hi).date() if hi else None,
        {"window": WINDOW, "z": Z_THRESHOLD, "min_idio": MIN_IDIO, "vol_ratio": VOL_RATIO, "vol_min_ret": VOL_MIN_RET},
        f"{total:,} 筆日報酬，異常波動 {anomalies:,} 筆（{100 * anomalies / max(total, 1):.1f}%）",
    )
