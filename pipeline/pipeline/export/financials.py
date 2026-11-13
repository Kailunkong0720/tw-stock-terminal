"""金融股專區：金控、銀行、保險、證券期貨（使用者 2026-11-13 要求）。

每檔：價格表現（還原，含除權息）、近一年除權息合計殖利率、外資與投信動向、外資持股變化、
對美國十年期公債殖利率的敏感度，以及近一年的週線（迷你走勢圖）。另附金融保險類指數與加權指數的週線。
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from pipeline.export.contract import Financials, FinancialStock, WeeklySeries
from pipeline.export.writer import ExportWriter
from pipeline.ingest.industry import TAIEX

log = logging.getLogger(__name__)

FIN_INDEX = "TWSE:金融保險類指數"
SENS_DAYS = 500
GROUPS = ["金控", "銀行", "保險", "證券期貨", "其他"]


def group_of(symbol: str, name: str) -> str:
    """依名稱判斷類別（證交所的產業別只有「金融保險」一類）。"""
    if name.endswith("金") or re.fullmatch(r"28(8\d|9[0-2])|5880", symbol) and "銀" not in name:
        return "金控"
    if "銀" in name:
        return "銀行"
    if re.search(r"保|產險|壽|再保|新產|台產", name):
        return "保險"
    if re.search(r"證|期", name):
        return "證券期貨"
    return "其他"


def _r(v: float | None, n: int = 2) -> float | None:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), n)


def export_financials(engine: Engine, writer: ExportWriter, calendar: list[date]) -> None:
    from pipeline.analytics.adjust import Action, cumulative_factors
    from pipeline.export.globe import overnight_changes
    from pipeline.ingest.institutional import weekly_last_days

    if not calendar:
        return
    last = calendar[-1]
    secs = pd.read_sql_query(
        "SELECT symbol, name, market, tracked, last_bar FROM security "
        "WHERE kind = 'stock' AND industry = '金融保險' AND last_bar = :d ORDER BY symbol",
        engine,
        params={"d": last.isoformat()},
    )
    if secs.empty:
        log.info("沒有金融保險類股票，略過金融股專區")
        return
    syms = list(secs["symbol"])
    ph = ",".join(f"'{s}'" for s in syms)
    bars = pd.read_sql_query(
        f"SELECT symbol, date, close, change FROM daily_bar WHERE symbol IN ({ph}) AND close IS NOT NULL", engine
    )
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    acts = pd.read_sql_query(
        f"SELECT symbol, ex_date, type, prev_close, ref_price, factor, affects_shares FROM corporate_action "
        f"WHERE symbol IN ({ph})",
        engine,
    )
    acts["ex_date"] = pd.to_datetime(acts["ex_date"]).dt.date
    flows = pd.read_sql_query(
        f"SELECT f.symbol, f.date, f.foreign_net * b.close / 1e8 AS fv, f.trust_net * b.close / 1e8 AS tv "
        f"FROM institutional_flow f JOIN daily_bar b ON b.symbol = f.symbol AND b.date = f.date "
        f"WHERE f.symbol IN ({ph})",
        engine,
    )
    flows["date"] = pd.to_datetime(flows["date"]).dt.date
    holds = pd.read_sql_query(
        f"SELECT symbol, date, shares_issued, foreign_pct FROM foreign_holding WHERE symbol IN ({ph}) ORDER BY date",
        engine,
    )
    holds["date"] = pd.to_datetime(holds["date"]).dt.date
    us10y = pd.read_sql_query("SELECT date, close FROM index_bar WHERE index_id = 'GLOBAL:US10Y'", engine)
    us10y["date"] = pd.to_datetime(us10y["date"]).dt.date
    us_chg = np.array(
        [np.nan if v is None else v for v in overnight_changes(us10y.set_index("date")["close"], calendar, "bp")],
        dtype=float,
    )
    cal_idx = {d: i for i, d in enumerate(calendar)}
    year_ago = last - timedelta(days=365)
    weeks = [d for d in calendar if d >= year_ago]
    week_ends = weekly_last_days(weeks)

    def ret_since(adj: pd.Series, d: date) -> float | None:
        base = adj[adj.index <= d]
        return None if base.empty else (adj.iloc[-1] / base.iloc[-1] - 1) * 100

    items = []
    for r in secs.itertuples():
        g = bars[bars["symbol"] == r.symbol].sort_values("date")
        a = acts[acts["symbol"] == r.symbol]
        dates = list(g["date"])
        adj = pd.Series(
            g["close"].to_numpy()
            * cumulative_factors(dates, [Action(x.ex_date, x.factor, bool(x.affects_shares)) for x in a.itertuples()]),
            index=dates,
        )
        close = float(g["close"].iloc[-1])
        chg = g["change"].iloc[-1]
        change_pct = None if chg is None or pd.isna(chg) or close - chg <= 0 else chg / (close - chg) * 100
        # 近一年除權息合計（每股，元）：前收 − 參考價；含股票股利的價值，純現增不算
        recent = a[(a["ex_date"] > year_ago) & (a["ex_date"] <= last) & a["type"].str.startswith("dividend")]
        payout = float((recent["prev_close"] - recent["ref_price"]).sum()) if len(recent) else 0.0
        f = flows[flows["symbol"] == r.symbol].sort_values("date")
        h = holds[holds["symbol"] == r.symbol]
        pct_now = h["foreign_pct"].iloc[-1] if len(h) else None
        pct_4w = h[h["date"] <= last - timedelta(days=28)]["foreign_pct"]
        shares = h["shares_issued"].iloc[-1] if len(h) else None
        # 對美債殖利率的敏感度：日報酬 vs 美債前一晚變動（基點），近 SENS_DAYS 個交易日
        y = adj.pct_change().to_numpy()[-SENS_DAYS:]
        x = np.array([us_chg[cal_idx[d]] if d in cal_idx else np.nan for d in dates])[-SENS_DAYS:]
        ok = ~(np.isnan(x) | np.isnan(y))
        rho = float(np.corrcoef(x[ok], y[ok])[0, 1]) if ok.sum() >= 120 else None
        beta = float(np.polyfit(x[ok], y[ok] * 100, 1)[0]) if ok.sum() >= 120 else None  # 每 1bp 的 %
        wk = adj.reindex(week_ends, method="ffill")
        items.append(
            FinancialStock(
                symbol=r.symbol,
                name=r.name,
                group=group_of(r.symbol, r.name),
                market="TPEx" if r.market == "TPEx" else "TWSE",
                tracked=bool(r.tracked),
                close=close,
                change_pct=_r(change_pct),
                ret_1m=_r(ret_since(adj, calendar[max(0, len(calendar) - 22)])),
                ret_ytd=_r(ret_since(adj, date(last.year - 1, 12, 31))),
                ret_1y=_r(ret_since(adj, year_ago)),
                cap=_r(shares * close / 1e8, 0) if shares else None,
                payout_1y=_r(payout, 3),
                yield_1y=_r(payout / close * 100) if payout else None,
                foreign_5d=_r(f["fv"].tail(5).sum()) if len(f) else None,
                foreign_20d=_r(f["fv"].tail(20).sum()) if len(f) else None,
                trust_20d=_r(f["tv"].tail(20).sum()) if len(f) else None,
                foreign_pct=_r(pct_now),
                foreign_pct_chg_4w=_r(pct_now - pct_4w.iloc[-1]) if pct_now is not None and len(pct_4w) else None,
                us10y_rho=_r(rho),
                us10y_beta=_r(beta, 4),
                weekly=[_r(v, 2) for v in wk.to_numpy()],
            )
        )

    idx = pd.read_sql_query(
        "SELECT index_id, date, close FROM index_bar WHERE index_id IN (:a, :b) ORDER BY date",
        engine,
        params={"a": FIN_INDEX, "b": TAIEX},
    )
    idx["date"] = pd.to_datetime(idx["date"]).dt.date
    series = []
    all_weeks = weekly_last_days(calendar)
    for iid, name in ((FIN_INDEX, "金融保險類指數"), (TAIEX, "發行量加權股價指數")):
        s = idx[idx["index_id"] == iid].set_index("date")["close"].sort_index()
        if s.empty:
            continue
        s = s.reindex(all_weeks, method="ffill")
        series.append(WeeklySeries(id=iid, name=name, values=[_r(v) for v in s.to_numpy()]))

    writer.write(
        "sector/financials.json",
        Financials(
            as_of=last,
            groups=[g for g in GROUPS if any(i.group == g for i in items)],
            items=items,
            weeks=all_weeks,
            weeks_1y=week_ends,
            index=series,
        ),
    )
    log.info("金融股專區：%d 檔", len(items))
