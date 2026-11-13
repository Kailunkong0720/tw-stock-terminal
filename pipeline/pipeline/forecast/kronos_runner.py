"""Kronos 推論（PLAN.md 5.2）。

KronosPredictor.predict 的 sample_count 會把路徑平均掉（vendor/kronos/model/kronos.py 第 467 行），
所以這裡直接呼叫 auto_regressive_inference：把同一條序列複製 n 份當成批次、每份 sample_count=1，
得到 n 條獨立的取樣路徑。

設定依這台機器的 CPU 實測決定（6 執行緒，預測 20 天，每條路徑）：
  Kronos-small 回看 400：2.69s　回看 256：1.71s
  Kronos-mini  回看 400：0.61s　回看 256：0.34s
採用 Kronos-mini、回看 256、20 條路徑：每檔每個基準日約 7 秒。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import delete, select

from pipeline.core.config import PIPELINE_DIR, Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.forecast.data import load_history, model_input
from pipeline.forecast.signal import step_stats
from pipeline.ingest.common import Progress
from pipeline.models import ForecastRun, ForecastStep, Security

log = logging.getLogger(__name__)

MODEL_NAME = "Kronos-mini"
TOKENIZER_REPO = "NeoQuasar/Kronos-Tokenizer-2k"
MODEL_REPO = "NeoQuasar/Kronos-mini"
LOOKBACK = 256
PRED_LEN = 20
N_PATHS = 20
BACKTEST_EVERY = 20  # 每隔幾個交易日取一個回測基準日
BACKTEST_YEARS = 2


class KronosEngine:
    def __init__(self, settings: Settings, lookback: int = LOOKBACK, pred_len: int = PRED_LEN, n_paths: int = N_PATHS):
        os.environ.setdefault("HF_HOME", str(settings.data_dir / "hf"))
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        vendor = str(PIPELINE_DIR / "vendor" / "kronos")
        if vendor not in sys.path:
            sys.path.insert(0, vendor)
        import torch
        from model import Kronos, KronosTokenizer
        from model.kronos import auto_regressive_inference, calc_time_stamps

        self.torch = torch
        self._infer = auto_regressive_inference
        self._stamps = calc_time_stamps
        self.lookback, self.pred_len, self.n_paths = lookback, pred_len, n_paths
        t0 = time.time()
        # 有 NVIDIA 顯示卡（且安裝了 CUDA 版 torch）就用 GPU；可用環境變數 TWST_DEVICE=cpu／cuda 強制指定
        self.device = os.environ.get("TWST_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = KronosTokenizer.from_pretrained(TOKENIZER_REPO).eval().to(self.device)
        self.model = Kronos.from_pretrained(MODEL_REPO).eval().to(self.device)
        log.info(
            "載入 %s（%.1f 秒），裝置 %s，執行緒 %d", MODEL_NAME, time.time() - t0, self.device, torch.get_num_threads()
        )

    def sample_paths(self, inp: pd.DataFrame, future: list[date], seed: int) -> np.ndarray:
        """回傳 (n_paths, pred_len) 的還原收盤價路徑。"""
        torch = self.torch
        torch.manual_seed(seed)
        x = inp[["open", "high", "low", "close", "volume", "amount"]].to_numpy(dtype=np.float32)
        mu, sd = x.mean(axis=0), x.std(axis=0)
        xn = np.clip((x - mu) / (sd + 1e-5), -5, 5)
        xs = self._stamps(pd.Series(pd.to_datetime(list(inp.index)))).to_numpy(dtype=np.float32)
        ys = self._stamps(pd.Series(pd.to_datetime(future))).to_numpy(dtype=np.float32)
        n = self.n_paths
        preds = self._infer(
            self.tokenizer,
            self.model,
            torch.from_numpy(np.repeat(xn[None], n, 0)).to(self.device),
            torch.from_numpy(np.repeat(xs[None], n, 0)).to(self.device),
            torch.from_numpy(np.repeat(ys[None], n, 0)).to(self.device),
            512,
            self.pred_len,
            clip=5,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=1,
        )
        close = preds[:, -self.pred_len :, 3] * (sd[3] + 1e-5) + mu[3]
        return close


def _seed(symbol: str, base: date) -> int:
    return zlib.crc32(f"{symbol}:{base.isoformat()}".encode()) & 0x7FFFFFFF


def _future_weekdays(base: date, n: int) -> list[date]:
    out, d = [], base
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _save(
    settings: Settings, symbol: str, base: date, kind: str, base_close: float, paths: np.ndarray, secs: float
) -> None:
    steps = step_stats(paths, base_close)
    with session_scope(settings) as s:
        s.execute(
            delete(ForecastRun).where(
                ForecastRun.symbol == symbol,
                ForecastRun.base_date == base,
                ForecastRun.kind == kind,
                ForecastRun.model == MODEL_NAME,
            )
        )
        run = ForecastRun(
            symbol=symbol,
            base_date=base,
            kind=kind,
            model=MODEL_NAME,
            lookback=LOOKBACK,
            pred_len=PRED_LEN,
            n_paths=paths.shape[0],
            base_close=base_close,
            paths_json=json.dumps(np.round(paths, 2).tolist()) if kind == "latest" else None,
            seconds=secs,
        )
        s.add(run)
        s.flush()
        s.add_all([ForecastStep(run_id=run.id, **st) for st in steps])


def tracked_symbols(settings: Settings) -> list[str]:
    with session_scope(settings) as s:
        return list(
            s.execute(select(Security.symbol).where(Security.tracked.is_(True)).order_by(Security.symbol)).scalars()
        )


def run_latest(settings: Settings, symbols: list[str] | None = None) -> None:
    """以每檔最後一個交易日為基準，預測之後 PRED_LEN 個交易日。"""
    symbols = symbols or tracked_symbols(settings)
    engine = get_engine(settings)
    kronos = KronosEngine(settings)
    prog = Progress("最新預測", len(symbols), every=10)
    for sym in symbols:
        h = load_history(engine, sym)
        if h.bars.empty:
            prog.tick()
            continue
        base = h.dates[-1]
        with session_scope(settings) as s:
            exists = s.execute(
                select(ForecastRun.id).where(
                    ForecastRun.symbol == sym,
                    ForecastRun.base_date == base,
                    ForecastRun.kind == "latest",
                    ForecastRun.model == MODEL_NAME,
                )
            ).first()
        if exists:
            prog.tick()
            continue
        inp = model_input(h, base, LOOKBACK)
        if inp is None:
            log.info("%s 資料不足 %d 根 K 線，略過", sym, LOOKBACK)
            prog.tick()
            continue
        t0 = time.time()
        paths = kronos.sample_paths(inp, _future_weekdays(base, PRED_LEN), _seed(sym, base))
        _save(settings, sym, base, "latest", float(inp["close"].iloc[-1]), paths, time.time() - t0)
        prog.tick()


def backtest_dates(calendar: list[date], every: int = BACKTEST_EVERY, years: int = BACKTEST_YEARS) -> list[date]:
    """最近 years 年內、之後還有 PRED_LEN 個交易日可以驗證的基準日，每隔 every 個交易日一個（新到舊）。"""
    if len(calendar) <= PRED_LEN:
        return []
    last_ok = len(calendar) - 1 - PRED_LEN
    start = calendar[-1] - timedelta(days=365 * years)
    out = []
    i = last_ok
    while i >= 0 and calendar[i] >= start:
        out.append(calendar[i])
        i -= every
    return out


def run_backtest(settings: Settings, symbols: list[str] | None = None) -> None:
    """滾動起點回測：在每個基準日只用當天以前的資料預測。可中斷續跑。"""
    engine = get_engine(settings)
    symbols = symbols or tracked_symbols(settings)
    calendar = [
        pd.Timestamp(d).date()
        for d in pd.read_sql_query("SELECT DISTINCT date FROM daily_bar ORDER BY date", engine)["date"]
    ]
    dates = backtest_dates(calendar)
    with session_scope(settings) as s:
        done = {
            (r.symbol, r.base_date)
            for r in s.execute(
                select(ForecastRun.symbol, ForecastRun.base_date).where(
                    ForecastRun.kind == "backtest", ForecastRun.model == MODEL_NAME
                )
            )
        }
    jobs = [(d, sym) for d in dates for sym in symbols if (sym, d) not in done]
    log.info("回測：%d 個基準日 × %d 檔，待跑 %d 次（已完成 %d）", len(dates), len(symbols), len(jobs), len(done))
    if not jobs:
        return
    histories = {sym: load_history(engine, sym) for sym in symbols}
    cal_idx = {d: i for i, d in enumerate(calendar)}
    kronos = KronosEngine(settings)
    prog = Progress("回測", len(jobs), every=25)
    for base, sym in jobs:
        h = histories[sym]
        if base not in h.bars.index:
            prog.tick()  # 該日沒有成交（停牌等），略過
            continue
        inp = model_input(h, base, LOOKBACK)
        if inp is None:
            prog.tick()
            continue
        i = cal_idx[base]
        future = calendar[i + 1 : i + 1 + PRED_LEN]
        t0 = time.time()
        paths = kronos.sample_paths(inp, future, _seed(sym, base))
        _save(settings, sym, base, "backtest", float(inp["close"].iloc[-1]), paths, time.time() - t0)
        prog.tick()
