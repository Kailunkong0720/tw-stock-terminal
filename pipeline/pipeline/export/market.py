"""Phase 1 的輸出：日曆、證券清單、日線、法人資金流向、市場總覽（PLAN.md 第 8 節）。"""

from __future__ import annotations

import logging
import math
from datetime import date

import pandas as pd
from sqlalchemy import Engine

from pipeline.export.contract import (
    ActionInfo,
    Bars,
    Breadth,
    Calendar,
    Flows,
    HeatItem,
    Heatmap,
    HeatmapHistory,
    IndexSeries,
    IndustryFlows,
    IndustryFlowSeries,
    MarketFlows,
    Overview,
    SectorPerf,
    Securities,
    SecurityInfo,
)
from pipeline.export.writer import ExportWriter
from pipeline.ingest.industry import INDUSTRIES, TAIEX
from pipeline.ingest.institutional import weekly_last_days

log = logging.getLogger(__name__)

EXPORT_KINDS = ("stock", "etf")


def _num(v: float | None, nd: int = 2) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd)


def _k(v: float) -> int:
    """股 → 張（或元 → 千元），四捨五入（不用 Python round 的銀行家捨入）。負數對稱處理。"""
    return int(math.copysign(math.floor(abs(v) / 1000 + 0.5), v))


def _dates(series: pd.Series) -> list[date]:
    return [d if isinstance(d, date) else pd.Timestamp(d).date() for d in series]


class MarketExporter:
    def __init__(self, engine: Engine, writer: ExportWriter) -> None:
        self.engine = engine
        self.w = writer
        self.calendar: list[date] = []
        self.idx: dict[date, int] = {}

    def q(self, sql: str, **params) -> pd.DataFrame:  # noqa: ANN003
        return pd.read_sql_query(sql, self.engine, params=params or None)

    # ── 日曆 ────────────────────────────────────────────────────────────
    def export_calendar(self) -> list[date]:
        df = self.q("SELECT DISTINCT date FROM daily_bar ORDER BY date")
        self.calendar = _dates(pd.to_datetime(df["date"]).dt.date)
        self.idx = {d: i for i, d in enumerate(self.calendar)}
        self.w.write("calendar.json", Calendar(dates=self.calendar))
        return self.calendar

    def _align(self, dates: list[date], values: list, fill) -> tuple[int, list]:  # noqa: ANN001
        """把 (日期, 值) 對齊到日曆區間 [第一天, 最後一天]，缺的日子補 fill。

        日曆之外的日期（例如回補程序在輸出途中新寫入的日子）略過，確保整份輸出是同一個快照。
        """
        pairs = [(d, v) for d, v in zip(dates, values, strict=True) if d in self.idx]
        if not pairs:
            return 0, []
        start, end = self.idx[pairs[0][0]], self.idx[pairs[-1][0]]
        out = [fill] * (end - start + 1)
        for d, v in pairs:
            out[self.idx[d] - start] = v
        return start, out

    # ── 證券清單 ────────────────────────────────────────────────────────
    def export_securities(self) -> pd.DataFrame:
        # 起訖日期直接由日線計算（security.first_bar 只在回補結束時更新，回補途中可能是空的）
        secs = self.q(
            "SELECT s.symbol, s.name, s.kind, s.industry, s.tracked, s.market, r.first_bar, r.last_bar FROM security s "
            "JOIN (SELECT symbol, MIN(date) AS first_bar, MAX(date) AS last_bar FROM daily_bar "
            "WHERE date <= :end GROUP BY symbol) r "
            "ON r.symbol = s.symbol WHERE s.kind IN ('stock', 'etf') ORDER BY s.symbol",
            end=self.calendar[-1].isoformat(),
        )
        last_day = self.calendar[-1]
        # 每檔最後一個有成交日的收盤，與截止日的漲跌（漲跌價差 ÷ 前收）
        last = self.q(
            "SELECT b.symbol, b.date, b.close, b.change FROM daily_bar b JOIN ("
            "  SELECT symbol, MAX(date) AS d FROM daily_bar WHERE close IS NOT NULL AND date <= :end GROUP BY symbol"
            ") m ON m.symbol = b.symbol AND m.d = b.date",
            end=last_day.isoformat(),
        ).set_index("symbol")

        def last_quote(sym: str) -> tuple[float | None, float | None]:
            if sym not in last.index:
                return None, None
            r = last.loc[sym]
            close, chg = float(r["close"]), r["change"]
            on_last_day = pd.Timestamp(r["date"]).date() == last_day
            if not on_last_day or chg is None or pd.isna(chg) or close - chg <= 0:
                return close, None
            return close, _num(chg / (close - chg) * 100)

        items = []
        for r in secs.itertuples():
            close, pct = last_quote(r.symbol)
            items.append(
                SecurityInfo(
                    symbol=r.symbol,
                    name=r.name,
                    kind=r.kind,
                    market="TPEx" if r.market == "TPEx" else "TWSE",
                    industry=None if pd.isna(r.industry) else r.industry,
                    tracked=bool(r.tracked),
                    first=pd.Timestamp(r.first_bar).date(),
                    last=pd.Timestamp(r.last_bar).date(),
                    active=pd.Timestamp(r.last_bar).date() == last_day,
                    close=close,
                    change_pct=pct,
                )
            )
        self.w.write("securities.json", Securities(items=items))
        return secs

    # ── 日線 ────────────────────────────────────────────────────────────
    def export_bars(self, symbols: list[str]) -> None:
        acts = self.q("SELECT * FROM corporate_action ORDER BY symbol, ex_date")
        acts_by = {s: g for s, g in acts.groupby("symbol")}
        for i, sym in enumerate(symbols):
            df = self.q(
                "SELECT date, open, high, low, close, volume, value FROM daily_bar WHERE symbol = :s ORDER BY date",
                s=sym,
            )
            if df.empty:
                continue
            dates = _dates(pd.to_datetime(df["date"]).dt.date)
            cols = {}
            for c in ("open", "high", "low", "close"):
                start, cols[c] = self._align(dates, [_num(v) for v in df[c]], None)
            _, vol = self._align(dates, [_k(v) for v in df["volume"]], 0)
            _, val = self._align(dates, [_k(v) for v in df["value"]], 0)
            a = acts_by.get(sym)
            actions = (
                []
                if a is None
                else [
                    ActionInfo(
                        ex_date=pd.Timestamp(r.ex_date).date(),
                        type=r.type,
                        prev_close=r.prev_close,
                        ref_price=r.ref_price,
                        factor=round(r.factor, 6),
                        affects_shares=bool(r.affects_shares),
                        detail=r.detail,
                    )
                    for r in a.itertuples()
                ]
            )
            self.w.write(
                f"bars/{sym}.json",
                Bars(symbol=sym, start=start, volume=vol, value=val, actions=actions, **cols),
            )
            if (i + 1) % 200 == 0:
                log.info("日線輸出 %d/%d", i + 1, len(symbols))

    # ── 法人資金流向 ───────────────────────────────────────────────────
    def export_flows(self, symbols: list[str]) -> None:
        flows = self.q(
            "SELECT f.symbol, f.date, f.foreign_net, f.trust_net, f.dealer_net, b.close "
            "FROM institutional_flow f LEFT JOIN daily_bar b ON b.symbol = f.symbol AND b.date = f.date "
            "ORDER BY f.symbol, f.date"
        )
        hold = self.q("SELECT symbol, date, foreign_pct FROM foreign_holding ORDER BY symbol, date")
        hold_by = {s: g for s, g in hold.groupby("symbol")}
        wanted = set(symbols)
        for sym, g in flows.groupby("symbol"):
            if sym not in wanted:
                continue
            g = g.copy()
            g["close"] = g["close"].ffill()
            dates = _dates(pd.to_datetime(g["date"]).dt.date)
            start, fnet = self._align(dates, [_k(v) for v in g["foreign_net"]], 0)
            _, tnet = self._align(dates, [_k(v) for v in g["trust_net"]], 0)
            _, dnet = self._align(dates, [_k(v) for v in g["dealer_net"]], 0)
            fval_raw = (g["foreign_net"] * g["close"].fillna(0) / 1e6).round(2).tolist()
            _, fval = self._align(dates, fval_raw, 0.0)
            h = hold_by.get(sym)
            self.w.write(
                f"flows/{sym}.json",
                Flows(
                    symbol=sym,
                    start=start,
                    foreign_net=fnet,
                    trust_net=tnet,
                    dealer_net=dnet,
                    foreign_value=fval,
                    holding_dates=[] if h is None else _dates(pd.to_datetime(h["date"]).dt.date),
                    foreign_pct=[] if h is None else [round(v, 2) for v in h["foreign_pct"]],
                ),
            )

    def export_market_flows(self) -> None:
        mf = self.q("SELECT date, investor, net FROM market_flow")
        if mf.empty:
            return
        piv = mf.pivot_table(index="date", columns="investor", values="net", aggfunc="sum").sort_index()
        if "dealer_self" in piv.columns and "dealer_hedge" in piv.columns:
            piv["dealer"] = piv["dealer_self"] + piv["dealer_hedge"]
        dates = _dates(pd.to_datetime(piv.index).date)

        def col(name: str) -> list[float | None]:
            if name not in piv.columns:
                return self._align(dates, [None] * len(dates), None)[1]
            vals = [None if pd.isna(v) else _num(v / 1e8) for v in piv[name]]
            return self._align(dates, vals, None)[1]

        start = self.idx[dates[0]]
        self.w.write(
            "flows/market.json",
            MarketFlows(
                start=start, foreign=col("foreign"), trust=col("trust"), dealer=col("dealer"), total=col("total")
            ),
        )

    def export_industry_flows(self) -> None:
        df = self.q(
            "SELECT s.industry, f.date, f.foreign_net, b.close FROM institutional_flow f "
            "JOIN security s ON s.symbol = f.symbol AND s.kind = 'stock' AND s.industry IS NOT NULL "
            "LEFT JOIN daily_bar b ON b.symbol = f.symbol AND b.date = f.date"
        )
        if df.empty:
            return
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["val"] = df["foreign_net"] * df["close"].fillna(0) / 1e8
        weeks = weekly_last_days(sorted(set(df["date"])))
        week_of = {}
        wi = 0
        for d in sorted(set(df["date"])):
            while weeks[wi] < d:
                wi += 1
            week_of[d] = weeks[wi]
        df["week"] = df["date"].map(week_of)
        piv = df.pivot_table(index="week", columns="industry", values="val", aggfunc="sum").reindex(weeks).fillna(0)
        series = [
            IndustryFlowSeries(industry=ind, foreign_value=[round(v, 2) for v in piv[ind].tolist()])
            for ind in piv.columns
        ]
        self.w.write("flows/industry.json", IndustryFlows(weeks=weeks, industries=series))

    # ── 市場總覽 ────────────────────────────────────────────────────────
    def export_overview(self) -> None:
        idx = self.q("SELECT index_id, date, close, change_pct FROM index_bar ORDER BY date")
        idx["date"] = pd.to_datetime(idx["date"]).dt.date
        last = self.calendar[-1]
        idx = idx[idx["date"] <= last]

        t = idx[idx.index_id == TAIEX]
        tdates = list(t["date"])
        tstart, tclose = self._align(tdates, [_num(v) for v in t["close"]], None)
        taiex = IndexSeries(id=TAIEX, name="發行量加權股價指數", start=tstart, close=tclose)
        from pipeline.ingest.tpex import OTC_INDEX

        o = idx[idx.index_id == OTC_INDEX]
        otc = None
        if not o.empty:
            ostart, oclose = self._align(list(o["date"]), [_num(v) for v in o["close"]], None)
            otc = IndexSeries(id=OTC_INDEX, name="櫃買指數", start=ostart, close=oclose)

        sectors = []
        for name, cands in INDUSTRIES.values():
            for cand in cands:
                iid = f"TWSE:{cand}"
                s = idx[idx.index_id == iid].set_index("date")["close"]
                if last not in s.index:
                    continue
                pct = idx[(idx.index_id == iid) & (idx.date == last)]["change_pct"]

                def ret(n: int, s=s) -> float | None:  # noqa: ANN001
                    if len(s) <= n:
                        return None
                    return _num((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100)

                ytd_base = s[[d.year < last.year for d in s.index]]
                sectors.append(
                    SectorPerf(
                        industry=name,
                        index_id=iid,
                        close=float(s.iloc[-1]),
                        change_pct=_num(pct.iloc[0]) if len(pct) else None,
                        ret_1m=ret(21),
                        ret_ytd=_num((s.iloc[-1] / ytd_base.iloc[-1] - 1) * 100) if len(ytd_base) else None,
                        ret_1y=ret(252),
                    )
                )
                break
        # 同一個指數可能對應多個產業（例如「其他類指數」），只留第一個
        seen, uniq = set(), []
        for sp in sectors:
            if sp.index_id not in seen:
                seen.add(sp.index_id)
                uniq.append(sp)

        br = self.q(
            "SELECT b.date, SUM(b.change > 0) AS up, SUM(b.change < 0) AS down, SUM(b.change = 0) AS flat "
            "FROM daily_bar b JOIN security s ON s.symbol = b.symbol AND s.kind = 'stock' "
            "GROUP BY b.date ORDER BY b.date"
        )
        bdates = _dates(pd.to_datetime(br["date"]).dt.date)
        bstart, up = self._align(bdates, [int(v or 0) for v in br["up"]], 0)
        _, down = self._align(bdates, [int(v or 0) for v in br["down"]], 0)
        _, flat = self._align(bdates, [int(v or 0) for v in br["flat"]], 0)

        self.w.write(
            "market/overview.json",
            Overview(taiex=taiex, otc=otc, sectors=uniq, breadth=Breadth(start=bstart, up=up, down=down, flat=flat)),
        )

    # ── 市值熱力圖 ──────────────────────────────────────────────────────
    HEATMAP_SIZE = 300

    def export_heatmap(self) -> None:
        from pipeline.analytics.adjust import Action, cumulative_factors

        last = self.calendar[-1]
        cap = self.q(
            "SELECT h.symbol, h.shares_issued, s.name, s.industry FROM foreign_holding h "
            "JOIN (SELECT symbol, MAX(date) AS d FROM foreign_holding WHERE date <= :end GROUP BY symbol) m "
            "  ON m.symbol = h.symbol AND m.d = h.date "
            "JOIN security s ON s.symbol = h.symbol AND s.kind = 'stock' AND s.industry IS NOT NULL",
            end=last.isoformat(),
        )
        if cap.empty:
            log.info("尚無發行股數資料（外資持股），略過熱力圖")
            return
        bars = self.q(
            "SELECT symbol, date, close, change FROM daily_bar WHERE close IS NOT NULL AND date <= :end",
            end=last.isoformat(),
        )
        bars["date"] = pd.to_datetime(bars["date"]).dt.date
        latest = bars.sort_values("date").groupby("symbol").tail(1).set_index("symbol")
        cap = cap[cap["symbol"].isin(latest.index)].copy()
        cap["cap"] = cap.apply(lambda r: r.shares_issued * latest.loc[r.symbol, "close"] / 1e8, axis=1)
        top = cap.sort_values("cap", ascending=False).head(self.HEATMAP_SIZE)
        syms = list(top["symbol"])

        acts = self.q("SELECT symbol, ex_date, factor, affects_shares FROM corporate_action")
        acts["ex_date"] = pd.to_datetime(acts["ex_date"]).dt.date
        acts_by = {
            s: [Action(r.ex_date, r.factor, bool(r.affects_shares)) for r in g.itertuples()]
            for s, g in acts.groupby("symbol")
        }
        weeks = weekly_last_days(self.calendar)
        week_idx = {d: i for i, d in enumerate(weeks)}

        flows = self.q(
            "SELECT f.symbol, f.date, f.foreign_net * b.close / 1e8 AS v FROM institutional_flow f "
            "JOIN daily_bar b ON b.symbol = f.symbol AND b.date = f.date WHERE f.date <= :end",
            end=last.isoformat(),
        )
        flows["date"] = pd.to_datetime(flows["date"]).dt.date

        ret = [[None] * len(syms) for _ in weeks]
        foreign = [[None] * len(syms) for _ in weeks]
        ret_1d: list[float | None] = []
        foreign_1d: list[float | None] = []
        by_sym = {s: g.set_index("date") for s, g in bars[bars["symbol"].isin(syms)].groupby("symbol")}
        fl_by = {s: g for s, g in flows[flows["symbol"].isin(syms)].groupby("symbol")}
        for j, sym in enumerate(syms):
            g = by_sym[sym]
            dates = list(g.index)
            adj = pd.Series(g["close"].to_numpy() * cumulative_factors(dates, acts_by.get(sym, [])), index=dates)
            # 每週最後一個交易日的還原收盤；那天沒成交的週略過（報酬併入下一個有成交的週）
            wk = adj[adj.index.isin(week_idx)]
            prev = None
            for d, v in wk.items():
                if prev is not None:
                    ret[week_idx[d]][j] = round((v / prev - 1) * 100, 2)
                prev = v
            row = g.iloc[-1]
            chg = row["change"]
            ret_1d.append(
                None
                if g.index[-1] != last or chg is None or pd.isna(chg)
                else round(chg / (row["close"] - chg) * 100, 2)
            )
            fl = fl_by.get(sym)
            if fl is not None:
                fl = fl.copy()
                fl["week"] = [weeks[min(len(weeks) - 1, _week_of(week_idx, weeks, d))] for d in fl["date"]]
                for w, v in fl.groupby("week")["v"].sum().items():
                    foreign[week_idx[w]][j] = round(float(v), 2)
                today = fl[fl["date"] == last]["v"]
                foreign_1d.append(round(float(today.iloc[0]), 2) if len(today) else None)
            else:
                foreign_1d.append(None)

        items = [
            HeatItem(symbol=r.symbol, name=r.name, industry=r.industry, cap=round(float(r.cap), 1))
            for r in top.itertuples()
        ]
        # 首頁只需要當天的顏色；各週的歷史（播放、累積報酬）另存一檔，用到才載入
        self.w.write(
            "market/heatmap.json",
            Heatmap(as_of=last, items=items, ret_1d=ret_1d, foreign_1d=foreign_1d, weeks=weeks),
        )
        self.w.write("market/heatmap-history.json", HeatmapHistory(weeks=weeks, ret=ret, foreign=foreign))

    def run(self) -> None:
        if not self.export_calendar():
            log.warning("尚無日線資料，略過市場資料輸出")
            return
        secs = self.export_securities()
        symbols = list(secs["symbol"])
        log.info("輸出 %d 檔的日線", len(symbols))
        self.export_bars(symbols)
        self.export_flows(symbols)
        self.export_market_flows()
        self.export_industry_flows()
        self.export_overview()
        self.export_heatmap()


def _week_of(week_idx: dict[date, int], weeks: list[date], d: date) -> int:
    """日期 d 所屬的週（該週最後一個交易日）在 weeks 中的索引。"""
    import bisect

    return bisect.bisect_left(weeks, d)


def source_status(engine: Engine) -> dict[str, tuple[str | None, int, int]]:
    """每個來源：(最新的 ok 鍵, ok 數, error 數)。"""
    df = pd.read_sql_query(
        "SELECT source, MAX(CASE WHEN status IN ('ok','partial') THEN key END) AS last_ok, "
        "SUM(status IN ('ok','partial')) AS n_ok, SUM(status = 'error') AS n_err FROM ingest_log GROUP BY source",
        engine,
    )
    return {r.source: (r.last_ok, int(r.n_ok or 0), int(r.n_err or 0)) for r in df.itertuples()}
