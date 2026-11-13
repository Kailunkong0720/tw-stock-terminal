"""事件歸因（PLAN.md 6.2）。

對每個異常波動日，收集候選事件並評分。分數由五個分項組成並分項保存：

  實體相關性 0.35：本公司的公告 1.0；市場事件依當天大盤／類股／隔夜美股是否主導而定
  事件類型先驗 0.25：這類事件歷史上當天的平均 |個股特有報酬| 相對於所有日子的倍數（用自己的資料統計）
  方向一致性 0.15：事件方向與波動方向一致 1.0、相反 0.2、未知 0.5
  時間接近度 0.15：影響交易日即當天 1.0、前一天 0.45、前兩天 0.2
  來源可信度 0.10：官方公告 1.0、市場資料 0.9、媒體 0.7

UI 用語是「可能相關的事件」，不是「原因」。分數低於門檻的不列出；都沒有就如實顯示「未找到」。
例行公告（取得固定收益證券、背書保證等）不列為候選。
另外產生資料驅動的市場事件：前一晚費半、當天加權指數的大幅波動。
"""

from __future__ import annotations

import bisect
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time

import numpy as np
import pandas as pd
from sqlalchemy import delete, update
from sqlalchemy.dialects.sqlite import insert

from pipeline.core.config import Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.events.classify import TYPE_NAMES
from pipeline.ingest.common import upsert
from pipeline.ingest.industry import TAIEX
from pipeline.ingest.mops import trading_calendar
from pipeline.models import Attribution, Event

log = logging.getLogger(__name__)

WEIGHTS = {"relevance": 0.35, "prior": 0.25, "direction": 0.15, "proximity": 0.15, "credibility": 0.10}
PROXIMITY = {0: 1.0, 1: 0.45, 2: 0.2}
CREDIBILITY = {"official": 1.0, "market": 0.9, "media": 0.7}
# 本公司當天的公告一定過門檻（0.675 起）；前一天、前兩天的公告要該類型有一定先驗才會列出
MIN_SCORE = 0.6
EXCLUDED_TYPES = {"routine"}
TOP_N = 5
SOX_BIG = 0.03
TAIEX_BIG = 0.025


def score(components: dict[str, float]) -> float:
    return sum(WEIGHTS[k] * components[k] for k in WEIGHTS)


def direction_score(event_dir: int, move: float) -> float:
    if event_dir == 0 or move == 0:
        return 0.5
    return 1.0 if (event_dir > 0) == (move > 0) else 0.2


def market_components(event_dir: int, ret: float, common: float, idio: float) -> dict[str, float] | None:
    """市場事件對某一天個股波動的評分項目；不可能相關時回傳 None。

    - 事件方向和當天的總報酬相反：不是原因（例如大盤大跌那天漲停）。
    - 大盤＋類股＋隔夜部分占主導：事件解釋的是共同部分，方向跟共同部分比。
    - 個股特有部分占主導：事件頂多解釋超出 beta 的敏感度，方向要跟個股特有報酬一致。
    """
    if event_dir and ret and (event_dir > 0) != (ret > 0):
        return None
    dominant = abs(common) >= abs(idio)
    return {
        "relevance": 0.8 if dominant else 0.3,
        "prior": 0.7,
        "direction": direction_score(event_dir, common if dominant else idio),
        "proximity": 1.0,
        "credibility": CREDIBILITY["market"],
    }


def build_market_events(settings: Settings) -> int:
    """資料驅動的市場事件：前一晚費半大幅波動、加權指數大幅波動。"""
    engine = get_engine(settings)
    calendar = trading_calendar(engine)
    idx = pd.read_sql_query(
        "SELECT index_id, date, close FROM index_bar WHERE index_id IN (:a, :b)",
        engine,
        params={"a": "GLOBAL:SOX", "b": TAIEX},
    )
    idx["date"] = pd.to_datetime(idx["date"]).dt.date
    rows = []
    for iid, g in idx.groupby("index_id"):
        s = g.set_index("date")["close"].sort_index()
        r = s.pct_change().dropna()
        for d, v in r.items():
            if iid == "GLOBAL:SOX" and abs(v) >= SOX_BIG:
                j = bisect.bisect_right(calendar, d)  # 美股收盤後的下一個台股交易日
                if j >= len(calendar):
                    continue
                td = calendar[j]
                title = f"費城半導體指數前一晚{'大漲' if v > 0 else '大跌'} {v * 100:+.1f}%"
                rows.append(
                    ("market:sox:" + d.isoformat(), datetime.combine(d, time(16, 0)), td, title, int(np.sign(v)))
                )
            elif iid == TAIEX and abs(v) >= TAIEX_BIG:
                title = f"加權指數當日{'大漲' if v > 0 else '大跌'} {v * 100:+.1f}%"
                rows.append(
                    ("market:taiex:" + d.isoformat(), datetime.combine(d, time(13, 30)), d, title, int(np.sign(v)))
                )
    with session_scope(settings) as s:
        for uid, at, td, title, direction in rows:
            vals = {
                "uid": uid,
                "symbol": None,
                "at": at,
                "trade_date": td,
                "level": "market",
                "type": "market",
                "direction": direction,
                "title": title,
                "source": "市場資料",
                "url": None,
                "detail": None,
            }
            s.execute(insert(Event).values(**vals).on_conflict_do_update(index_elements=["uid"], set_=vals))
    return len(rows)


ACTION_EVENT = {
    "etf_split": ("split", "ETF 分割"),
    "etf_reverse_split": ("split", "ETF 反分割"),
    "par_change": ("split", "變更面額"),
    "capital_reduction": ("capital_reduction", "減資"),
}


def build_action_events(settings: Settings) -> int:
    """由證交所的分割、面額變更、減資報表產生官方事件（恢復買賣日），不依賴 MOPS。

    ETF 不是公司，MOPS 沒有它的公告；用交易所資料確保每一次分割都有對應事件。
    """
    engine = get_engine(settings)
    acts = pd.read_sql_query(
        "SELECT symbol, ex_date, type, prev_close, ref_price, detail FROM corporate_action WHERE type IN :t".replace(
            ":t", "(" + ",".join(f"'{t}'" for t in ACTION_EVENT) + ")"
        ),
        engine,
    )
    n = 0
    with session_scope(settings) as s:
        for r in acts.itertuples():
            ex = pd.Timestamp(r.ex_date).date()
            type_, label = ACTION_EVENT[r.type]
            ratio = r.prev_close / r.ref_price if r.ref_price else None
            how = (
                f"（約 1 拆 {ratio:.0f}）"
                if ratio and ratio > 1.5
                else f"（約 {1 / ratio:.0f} 合 1）"
                if ratio and ratio < 0.67
                else ""
            )
            vals = {
                "uid": f"twse:action:{r.symbol}:{ex.isoformat()}:{r.type}",
                "symbol": r.symbol,
                "at": datetime.combine(ex, time(9, 0)),
                "trade_date": ex,
                "level": "official",
                "type": type_,
                "direction": 0,
                "title": f"{label}後恢復買賣{how}：前收 {r.prev_close:g}，參考價 {r.ref_price:g}",
                "source": "證交所",
                "url": None,
                "detail": r.detail,
            }
            s.execute(insert(Event).values(**vals).on_conflict_do_update(index_elements=["uid"], set_=vals))
            n += 1
    return n


def type_priors(moves: pd.DataFrame, events: pd.DataFrame) -> dict[str, float]:
    """事件類型先驗：該類事件影響日的平均 |個股特有報酬| ÷ 全部日子的平均，壓到 0–1。"""
    base = moves["idio"].abs().mean()
    if not base or np.isnan(base):
        return {}
    m = moves.set_index(["symbol", "date"])["idio"].abs()
    out = {}
    for t, g in events[events["level"] == "official"].groupby("type"):
        keys = [k for k in zip(g["symbol"], g["trade_date"], strict=True) if k in m.index]
        if len(keys) < 20:
            continue
        ratio = float(m.loc[keys].mean() / base)
        out[t] = round(min(1.0, max(0.0, (ratio - 0.8) / 1.7)), 3)  # 0.8 倍以下 → 0；2.5 倍以上 → 1
    return out


def reclassify(settings: Settings) -> int:
    """依目前的規則重新分類所有官方公告（規則改了不必重抓）。"""
    from pipeline.events.classify import classify

    engine = get_engine(settings)
    ev = pd.read_sql_query("SELECT id, title, type, direction FROM event WHERE level = 'official'", engine)
    changed = 0
    with session_scope(settings) as s:
        for r in ev.itertuples():
            t, d = classify(r.title)
            if t != r.type or d != r.direction:
                s.execute(update(Event).where(Event.id == int(r.id)).values(type=t, direction=d))
                changed += 1
    return changed


def attribute(settings: Settings) -> None:
    engine = get_engine(settings)
    n_re = reclassify(settings)
    if n_re:
        log.info("依目前規則重新分類 %d 則公告", n_re)
    n_market = build_market_events(settings)
    n_actions = build_action_events(settings)
    log.info("由證交所報表產生分割／面額變更／減資事件 %d 個", n_actions)
    calendar = trading_calendar(engine)
    cal_idx = {d: i for i, d in enumerate(calendar)}

    moves = pd.read_sql_query(
        "SELECT p.* FROM price_move p JOIN security s ON s.symbol = p.symbol WHERE s.tracked AND p.idio IS NOT NULL",
        engine,
    )
    moves["date"] = pd.to_datetime(moves["date"]).dt.date
    events = pd.read_sql_query("SELECT id, symbol, trade_date, level, type, direction FROM event", engine)
    events["trade_date"] = pd.to_datetime(events["trade_date"]).dt.date
    priors = type_priors(moves, events)
    priors["routine"] = min(priors.get("routine", 0.05), 0.05)
    log.info("事件類型先驗：%s", json.dumps(priors, ensure_ascii=False))

    by_sym_day: dict[tuple[str, date], list] = defaultdict(list)
    market_by_day: dict[date, list] = defaultdict(list)
    for e in events.itertuples():
        if e.level == "market":
            market_by_day[e.trade_date].append(e)
        elif e.symbol:
            by_sym_day[(e.symbol, e.trade_date)].append(e)

    rows = []
    anomalies = moves[moves["anomaly"].astype(bool)]
    found = 0
    for m in anomalies.itertuples():
        i = cal_idx.get(m.date)
        if i is None:
            continue
        common = (m.mkt or 0) + (m.sector or 0) + (m.overnight or 0)
        cands = []
        for lag in (0, 1, 2):
            if i - lag < 0:
                continue
            d = calendar[i - lag]
            for e in by_sym_day.get((m.symbol, d), []):
                if e.type in EXCLUDED_TYPES:
                    continue
                c = {
                    "relevance": 1.0,
                    "prior": priors.get(e.type, 0.3),
                    "direction": direction_score(e.direction, m.idio),
                    "proximity": PROXIMITY[lag],
                    "credibility": CREDIBILITY["official"],
                }
                cands.append((score(c), e.id, c))
            if lag == 0:
                for e in market_by_day.get(d, []):
                    c = market_components(e.direction, m.ret, common, m.idio)
                    if c is not None:
                        cands.append((score(c), e.id, c))
        cands = [c for c in cands if c[0] >= MIN_SCORE]
        cands.sort(key=lambda x: -x[0])
        if cands:
            found += 1
        for rank, (sc, eid, comp) in enumerate(cands[:TOP_N], start=1):
            rows.append(
                {
                    "symbol": m.symbol,
                    "date": m.date,
                    "event_id": int(eid),
                    "rank": rank,
                    "score": round(sc, 4),
                    "components": json.dumps({k: round(v, 3) for k, v in comp.items()}),
                }
            )
    with session_scope(settings) as s:
        s.execute(delete(Attribution))
        upsert(s, Attribution, rows, chunk=2000)
    log.info(
        "歸因：市場事件 %d 個；追蹤池異常波動日 %d 個，其中 %d 個找到可能相關的事件（%.0f%%）",
        n_market,
        len(anomalies),
        found,
        100 * found / max(len(anomalies), 1),
    )


__all__ = [
    "TYPE_NAMES",
    "attribute",
    "build_market_events",
    "direction_score",
    "market_components",
    "reclassify",
    "score",
    "type_priors",
]
