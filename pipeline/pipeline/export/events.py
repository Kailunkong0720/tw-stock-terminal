"""Phase 4 的輸出：異常波動日、個股事件、市場時間軸（PLAN.md 第 8 節）。"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from pipeline.events.classify import TYPE_NAMES
from pipeline.events.factor_model import MIN_IDIO, VOL_MIN_RET, VOL_RATIO, Z_THRESHOLD
from pipeline.export.contract import Candidate, EventOut, Events, MoveOut, Moves, Timeline, TimelineMove
from pipeline.export.writer import ExportWriter

log = logging.getLogger(__name__)


def _f(v, nd: int = 5):  # noqa: ANN001, ANN202
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd)


def _event(r) -> dict:  # noqa: ANN001
    return {
        "id": int(r.id),
        "at": pd.Timestamp(r.at).to_pydatetime(),
        "trade_date": pd.Timestamp(r.trade_date).date(),
        "level": r.level,
        "type": r.type,
        "type_name": TYPE_NAMES.get(r.type, r.type),
        "direction": int(r.direction),
        "title": r.title,
        "source": r.source,
        "url": None if r.url is None or (isinstance(r.url, float) and math.isnan(r.url)) else r.url,
    }


def export_events(engine: Engine, writer: ExportWriter, calendar_end) -> None:  # noqa: ANN001
    end = calendar_end.isoformat()
    moves = pd.read_sql_query(
        "SELECT p.*, s.tracked, s.name FROM price_move p JOIN security s ON s.symbol = p.symbol "
        "WHERE p.anomaly AND p.date <= :end ORDER BY p.symbol, p.date",
        engine,
        params={"end": end},
    )
    if moves.empty:
        log.info("尚無異常波動資料，略過事件輸出")
        return
    moves["date"] = pd.to_datetime(moves["date"]).dt.date
    ev = pd.read_sql_query("SELECT * FROM event WHERE trade_date <= :end", engine, params={"end": end})
    ev_by_id = {int(r.id): r for r in ev.itertuples()}
    attr = pd.read_sql_query("SELECT * FROM attribution ORDER BY symbol, date, rank", engine)
    attr["date"] = pd.to_datetime(attr["date"]).dt.date
    cands: dict[tuple[str, object], list[Candidate]] = defaultdict(list)
    for a in attr.itertuples():
        e = ev_by_id.get(int(a.event_id))
        if e is None:
            continue
        cands[(a.symbol, a.date)].append(
            Candidate(**_event(e), score=round(a.score, 3), components=json.loads(a.components))
        )

    # 外資：當日買賣超與其在該股歷史中的百分位
    flows = pd.read_sql_query(
        "SELECT f.symbol, f.date, f.foreign_net, b.close FROM institutional_flow f "
        "LEFT JOIN daily_bar b ON b.symbol = f.symbol AND b.date = f.date "
        "WHERE f.symbol IN (SELECT DISTINCT symbol FROM price_move WHERE anomaly)",
        engine,
    )
    flows["date"] = pd.to_datetime(flows["date"]).dt.date
    flows["value"] = flows["foreign_net"] * flows["close"].fillna(0) / 1e6
    flow_by: dict[str, pd.DataFrame] = {s: g.set_index("date") for s, g in flows.groupby("symbol")}

    thresholds = {"z": Z_THRESHOLD, "min_idio": MIN_IDIO, "vol_ratio": VOL_RATIO, "vol_min_ret": VOL_MIN_RET}
    for sym, g in moves.groupby("symbol"):
        fb = flow_by.get(sym)
        abs_sorted = np.sort(fb["value"].abs().to_numpy()) if fb is not None and len(fb) else None
        out = []
        for m in g.itertuples():
            lots = val = rank = None
            if fb is not None and m.date in fb.index:
                row = fb.loc[m.date]
                lots = int(round(row["foreign_net"] / 1000))
                val = round(float(row["value"]), 2)
                rank = round(float(np.searchsorted(abs_sorted, abs(val), side="right") / len(abs_sorted)), 3)
            out.append(
                MoveOut(
                    date=m.date,
                    ret=round(m.ret, 5),
                    gap=int(m.gap),
                    mkt=_f(m.mkt),
                    sector=_f(m.sector),
                    overnight=_f(m.overnight),
                    idio=_f(m.idio),
                    z=_f(m.z, 2),
                    vol_ratio=_f(m.vol_ratio, 2),
                    foreign_lots=lots,
                    foreign_value=val,
                    foreign_rank=rank,
                    candidates=cands.get((sym, m.date), []),
                )
            )
        writer.write(
            f"moves/{sym}.json", Moves(symbol=sym, tracked=bool(g["tracked"].iloc[0]), thresholds=thresholds, moves=out)
        )

    # 個股事件（追蹤池、不含例行公告）
    tracked = set(moves.loc[moves["tracked"].astype(bool), "symbol"])
    official = ev[(ev["level"] == "official") & (ev["type"] != "routine")]
    for sym, g in official.groupby("symbol"):
        if sym not in tracked:
            continue
        items = [EventOut(**_event(r)) for r in g.sort_values("at").itertuples()]
        writer.write(f"events/{sym}.json", Events(symbol=sym, events=items))

    # 市場時間軸：市場事件 + 追蹤池最大的異常波動
    market = [EventOut(**_event(r)) for r in ev[ev["level"] == "market"].sort_values("at").itertuples()]
    tm = moves[moves["tracked"].astype(bool)].copy()
    tm["mag"] = tm["idio"].abs().fillna(0)
    top = tm.sort_values("mag", ascending=False).head(400).sort_values("date")
    tl = [
        TimelineMove(
            symbol=r.symbol,
            name=r.name,
            date=r.date,
            ret=round(r.ret, 5),
            idio=_f(r.idio),
            top=(cands.get((r.symbol, r.date)) or [None])[0],
        )
        for r in top.itertuples()
    ]
    writer.write("events/timeline.json", Timeline(market=market, moves=tl))
    log.info(
        "事件輸出：異常波動 %d 檔、個股事件 %d 檔、市場事件 %d 個", moves["symbol"].nunique(), len(tracked), len(market)
    )
