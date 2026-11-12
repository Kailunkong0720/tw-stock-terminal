"""從取樣路徑算出分位數、上漲機率、訊號標籤，以及回測指標（純 numpy，不需要 torch）。"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

HORIZONS = [5, 10, 20]
QUANTILES = {"p05": 5, "p10": 10, "p25": 25, "p50": 50, "p75": 75, "p90": 90, "p95": 95}

# 五級標籤的門檻（在網站的說明浮層中公開）
LABEL_RULES = [
    ("偏多", "up_prob ≥ 65% 且預期報酬 > 0", lambda p, r: p >= 0.65 and r > 0),
    ("偏空", "up_prob ≤ 35% 且預期報酬 < 0", lambda p, r: p <= 0.35 and r < 0),
    ("略偏多", "up_prob ≥ 55%", lambda p, r: p >= 0.55),
    ("略偏空", "up_prob ≤ 45%", lambda p, r: p <= 0.45),
]


def label(up_prob: float, exp_ret: float) -> str:
    for name, _, rule in LABEL_RULES:
        if rule(up_prob, exp_ret):
            return name
    return "中性"


def step_stats(paths: np.ndarray, base_close: float) -> list[dict]:
    """paths：(n_paths, pred_len) 的收盤價路徑。回傳每一步的分位數、上漲機率、最大回檔中位數。"""
    n, steps = paths.shape
    out = []
    running_peak = np.full(n, base_close)
    worst_dd = np.zeros(n)
    for k in range(steps):
        col = paths[:, k]
        running_peak = np.maximum(running_peak, col)
        worst_dd = np.minimum(worst_dd, col / running_peak - 1)
        q = {name: float(np.percentile(col, pct)) for name, pct in QUANTILES.items()}
        out.append(
            {"step": k + 1, **q, "up_prob": float(np.mean(col > base_close)), "mdd_p50": float(np.median(worst_dd))}
        )
    return out


@dataclass
class Signal:
    horizon: int
    up_prob: float
    exp_ret: float  # 期末報酬的中位數
    p10_ret: float  # 期末報酬的第 10 百分位（下檔風險）
    mdd_p50: float  # 途中最大回檔的中位數
    label: str


def signals(steps: list[dict], base_close: float) -> list[Signal]:
    by = {s["step"]: s for s in steps}
    out = []
    for h in HORIZONS:
        s = by.get(h)
        if not s:
            continue
        exp_ret = s["p50"] / base_close - 1
        out.append(
            Signal(h, s["up_prob"], exp_ret, s["p10"] / base_close - 1, s["mdd_p50"], label(s["up_prob"], exp_ret))
        )
    return out


# ── 回測指標 ──────────────────────────────────────────────────────────


@dataclass
class HitStats:
    n: int
    hits: int  # 模型方向正確的次數
    base_up: int  # 實際上漲的次數（「一律看多」基準）
    momentum_hits: int  # 「延續近 20 日趨勢」基準答對的次數

    @property
    def hit_rate(self) -> float | None:
        return self.hits / self.n if self.n else None

    @property
    def baseline_rate(self) -> float | None:
        """兩種單純基準中較好的那個：一律看多／一律看空（取多數方向）、或延續近 20 日趨勢。"""
        if not self.n:
            return None
        always = max(self.base_up, self.n - self.base_up) / self.n
        return max(always, self.momentum_hits / self.n)

    @property
    def z(self) -> float | None:
        """命中率相對於基準的 z 值（二項分布的常態近似）。"""
        p0 = self.baseline_rate
        if not self.n or p0 is None or p0 <= 0 or p0 >= 1:
            return None
        return (self.hits - self.n * p0) / math.sqrt(self.n * p0 * (1 - p0))

    @property
    def has_edge(self) -> bool:
        """命中率明顯優於基準（單尾 p < 0.1，且樣本至少 20 次）。"""
        z = self.z
        return self.n >= 20 and z is not None and z > 1.2816


def hit_stats(records: list[tuple[float, float, float | None]]) -> HitStats:
    """records：(模型預期報酬, 實際報酬, 基準日前 20 日報酬)。預期報酬 > 0 視為看多。"""
    n = hits = up = mom = 0
    for exp_ret, actual, past in records:
        if actual == 0:
            continue  # 平盤不計入
        n += 1
        hits += int((exp_ret > 0) == (actual > 0))
        up += int(actual > 0)
        if past is not None:
            mom += int((past > 0) == (actual > 0))
    return HitStats(n, hits, up, mom)


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 5:
        return None
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])
