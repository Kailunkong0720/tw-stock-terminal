"""Phase 3 的輸出：最新預測、回測重播、訊號排行（PLAN.md 第 8 節）。"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from pipeline.analytics.adjust import cumulative_factors
from pipeline.export.contract import (
    Backtest,
    BacktestPoint,
    Forecast,
    ForecastStepOut,
    RankIC,
    Ranking,
    RankingItem,
    SignalOut,
    TrackRecord,
)
from pipeline.export.writer import ExportWriter
from pipeline.forecast.data import load_history, past_return, realized_returns
from pipeline.forecast.kronos_runner import BACKTEST_EVERY, BACKTEST_YEARS, LOOKBACK, MODEL_NAME, N_PATHS, PRED_LEN
from pipeline.forecast.signal import HORIZONS, LABEL_RULES, HitStats, hit_stats, signals, spearman

log = logging.getLogger(__name__)


def _r(v: float, nd: int = 4) -> float:
    return round(float(v), nd)


def _track(hs: HitStats, horizon: int) -> TrackRecord:
    n = hs.n
    return TrackRecord(
        horizon=horizon,
        n=n,
        hit_rate=_r(hs.hit_rate) if hs.hit_rate is not None else None,
        baseline_rate=_r(hs.baseline_rate) if hs.baseline_rate is not None else None,
        always_rate=_r(max(hs.base_up, n - hs.base_up) / n) if n else None,
        momentum_rate=_r(hs.momentum_hits / n) if n else None,
        z=_r(hs.z, 2) if hs.z is not None else None,
        has_edge=hs.has_edge,
    )


def _steps_out(rows: pd.DataFrame, scale: float = 1.0, nd: int = 2) -> list[ForecastStepOut]:
    return [
        ForecastStepOut(
            step=int(r.step),
            p05=round(r.p05 * scale, nd),
            p25=round(r.p25 * scale, nd),
            p50=round(r.p50 * scale, nd),
            p75=round(r.p75 * scale, nd),
            p95=round(r.p95 * scale, nd),
            up_prob=round(r.up_prob, 3),
        )
        for r in rows.itertuples()
    ]


def _signals_out(rows: pd.DataFrame, base_close: float) -> list[SignalOut]:
    steps = [r._asdict() for r in rows.itertuples(index=False)]
    return [
        SignalOut(
            horizon=s.horizon,
            up_prob=_r(s.up_prob, 3),
            exp_ret=_r(s.exp_ret),
            p10_ret=_r(s.p10_ret),
            mdd_p50=_r(s.mdd_p50),
            label=s.label,
        )
        for s in signals(steps, base_close)
    ]


def export_forecasts(engine: Engine, writer: ExportWriter, calendar: list[date]) -> None:
    runs = pd.read_sql_query(
        "SELECT id, symbol, base_date, kind, base_close, paths_json FROM forecast_run WHERE model = :m",
        engine,
        params={"m": MODEL_NAME},
    )
    if runs.empty:
        log.info("尚無 Kronos 預測結果，略過預測輸出")
        return
    runs["base_date"] = pd.to_datetime(runs["base_date"]).dt.date
    steps = pd.read_sql_query(
        "SELECT s.* FROM forecast_step s JOIN forecast_run r ON r.id = s.run_id WHERE r.model = :m ORDER BY s.run_id, s.step",
        engine,
        params={"m": MODEL_NAME},
    )
    steps_by = {rid: g for rid, g in steps.groupby("run_id")}
    secs = pd.read_sql_query("SELECT symbol, name, industry FROM security", engine).set_index("symbol")

    latest = runs[runs.kind == "latest"].sort_values("base_date").groupby("symbol").tail(1).set_index("symbol")
    back = runs[runs.kind == "backtest"]
    symbols = sorted(set(latest.index) | set(back["symbol"]))

    pool_records: dict[int, list] = defaultdict(list)
    by_date: dict[tuple[date, int], list[tuple[float, float]]] = defaultdict(list)
    items: list[RankingItem] = []
    bt_dates: set[date] = set()

    for sym in symbols:
        h = load_history(engine, sym)
        full_f = dict(zip(h.dates, cumulative_factors(h.dates, h.actions), strict=True))
        sym_records: dict[int, list] = defaultdict(list)
        points: list[BacktestPoint] = []
        for r in back[back.symbol == sym].sort_values("base_date").itertuples():
            st = steps_by.get(r.id)
            if st is None:
                continue
            actual = realized_returns(h, r.base_date, HORIZONS)
            past = past_return(h, r.base_date, 20)
            by_step = st.set_index("step")
            exp = {hz: float(by_step.loc[hz, "p50"] / r.base_close - 1) for hz in HORIZONS if hz in by_step.index}
            for hz in HORIZONS:
                if actual.get(hz) is None or hz not in exp:
                    continue
                rec = (exp[hz], actual[hz], past)
                sym_records[hz].append(rec)
                pool_records[hz].append(rec)
                by_date[(r.base_date, hz)].append((exp[hz], actual[hz]))
            bt_dates.add(r.base_date)
            points.append(
                BacktestPoint(
                    base_date=r.base_date,
                    base_close=round(r.base_close, 2),
                    scale=round(full_f.get(r.base_date, 1.0), 6),
                    steps=_steps_out(st),
                    actual={str(k): (None if v is None else _r(v)) for k, v in actual.items()},
                    exp={str(k): _r(v) for k, v in exp.items()},
                )
            )
        track = [_track(hit_stats(sym_records[hz]), hz) for hz in HORIZONS]
        if points:
            writer.write(
                f"forecast/backtest/{sym}.json", Backtest(symbol=sym, model=MODEL_NAME, points=points, track=track)
            )

        if sym in latest.index:
            lr = latest.loc[sym]
            st = steps_by.get(int(lr["id"]))
            if st is None:
                continue
            base = lr["base_date"]
            # 預測日期：日曆之外以平日估計（與 kronos_runner 相同）
            fut, d = [], base
            while len(fut) < len(st):
                d = d + pd.Timedelta(days=1)
                d = d.date() if hasattr(d, "date") else d
                if d.weekday() < 5:
                    fut.append(d)
            sig = _signals_out(st, float(lr["base_close"]))
            paths = json.loads(lr["paths_json"]) if lr["paths_json"] else []
            writer.write(
                f"forecast/{sym}.json",
                Forecast(
                    symbol=sym,
                    model=MODEL_NAME,
                    base_date=base,
                    base_close=round(float(lr["base_close"]), 2),
                    future_dates=fut,
                    steps=_steps_out(st),
                    paths=paths,
                    signals=sig,
                    track=track,
                ),
            )
            info = secs.loc[sym] if sym in secs.index else None
            items.append(
                RankingItem(
                    symbol=sym,
                    name=str(info["name"]) if info is not None else sym,
                    industry=None if info is None or pd.isna(info["industry"]) else str(info["industry"]),
                    base_date=base,
                    signals=sig,
                    track=track,
                )
            )

    rank_ic = []
    for hz in HORIZONS:
        ics = []
        for (_d, h2), pairs in by_date.items():
            if h2 != hz:
                continue
            ic = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            if ic is not None:
                ics.append(ic)
        rank_ic.append(
            RankIC(
                horizon=hz,
                mean=_r(float(np.mean(ics))) if ics else None,
                n_dates=len(ics),
                positive_share=_r(float(np.mean([i > 0 for i in ics]))) if ics else None,
            )
        )

    writer.write(
        "forecast/ranking.json",
        Ranking(
            model=MODEL_NAME,
            settings={
                "lookback": LOOKBACK,
                "pred_len": PRED_LEN,
                "n_paths": N_PATHS,
                "backtest_every": BACKTEST_EVERY,
                "backtest_years": BACKTEST_YEARS,
            },
            label_rules=[f"{name}：{desc}" for name, desc, _ in LABEL_RULES] + ["中性：其他情況"],
            items=items,
            pool=[_track(hit_stats(pool_records[hz]), hz) for hz in HORIZONS],
            rank_ic=rank_ic,
            backtest_dates=sorted(bt_dates),
        ),
    )
    log.info("預測輸出：最新 %d 檔、回測 %d 檔、%d 個基準日", len(items), back["symbol"].nunique(), len(bt_dates))
