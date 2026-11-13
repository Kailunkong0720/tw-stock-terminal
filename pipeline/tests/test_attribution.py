from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import select

from pipeline.core.db import migrate, session_scope
from pipeline.events.attribution import (
    build_action_events,
    direction_score,
    market_components,
    score,
    type_priors,
)
from pipeline.ingest.common import upsert
from pipeline.models import CorporateAction, Event


def test_every_split_has_an_event(settings):
    """PLAN.md Phase 4 驗收：所有股票分割、面額變更都有對應的事件（含沒有 MOPS 公告的 ETF）。"""
    migrate(settings)
    rows = [
        ("0050", date(2025, 6, 18), "etf_split", 188.65, 47.16),
        ("6919", date(2025, 7, 21), "par_change", 500.0, 50.0),
        ("3557", date(2020, 1, 20), "capital_reduction", 38.05, 48.57),
        ("2330", date(2025, 6, 12), "dividend_cash", 1000.0, 995.0),  # 除息不產生事件
    ]
    with session_scope(settings) as s:
        upsert(
            s,
            CorporateAction,
            [
                {
                    "symbol": sym,
                    "ex_date": d,
                    "type": t,
                    "prev_close": p,
                    "ref_price": r,
                    "factor": r / p,
                    "affects_shares": True,
                    "detail": None,
                    "source": "test",
                    "limit_up": None,
                    "limit_down": None,
                }
                for sym, d, t, p, r in rows
            ],
        )
    assert build_action_events(settings) == 3
    assert build_action_events(settings) == 3  # 重跑不重複
    with session_scope(settings) as s:
        evs = {(e.symbol, e.trade_date): (e.type, e.level, e.title) for e in s.execute(select(Event)).scalars()}
    assert len(evs) == 3
    type_, level, title = evs[("0050", date(2025, 6, 18))]
    assert type_ == "split" and level == "official" and "1 拆 4" in title
    assert "1 拆 10" in evs[("6919", date(2025, 7, 21))][2]  # 面額變更 1 拆 10
    assert evs[("3557", date(2020, 1, 20))][0] == "capital_reduction"


def test_scoring():
    c = {"relevance": 1.0, "prior": 0.0, "direction": 0.5, "proximity": 1.0, "credibility": 1.0}
    assert score(c) == pytest.approx(0.675)  # 本公司當天的公告一定過門檻 0.6
    assert direction_score(1, 0.05) == 1.0
    assert direction_score(-1, 0.05) == 0.2
    assert direction_score(0, 0.05) == 0.5


def test_market_event_must_match_direction():
    # 大盤大跌 -2.6% 那天漲停：個股特有 +12%，市場事件不是原因
    assert market_components(-1, 0.0995, -0.02, 0.12) is None
    # 費半大跌、個股特有部分也大跌（敏感度超出 beta）：可以列出，但相關性低
    c = market_components(-1, -0.09, -0.03, -0.06)
    assert c is not None and c["relevance"] == 0.3 and c["direction"] == 1.0
    assert score(c) >= 0.6
    # 共同部分占主導：事件解釋的是共同部分
    c = market_components(-1, -0.07, -0.05, -0.02)
    assert c is not None and c["relevance"] == 0.8
    # 跌勢主要來自大盤，但個股特有部分反向：方向只看共同部分
    c = market_components(-1, -0.03, -0.05, 0.02)
    assert c is not None and c["direction"] == 1.0


def test_type_priors_from_data():
    moves = pd.DataFrame(
        {
            "symbol": ["A"] * 100,
            "date": [date(2024, 1, 1) + pd.Timedelta(days=i) for i in range(100)],
            "idio": [0.01] * 100,
        }
    )
    moves.loc[:24, "idio"] = 0.05  # 前 25 天波動大
    events = pd.DataFrame(
        {
            "symbol": ["A"] * 45,
            "trade_date": list(moves["date"][:25]) + list(moves["date"][50:70]),
            "level": ["official"] * 45,
            "type": ["clarification"] * 25 + ["personnel"] * 20,
        }
    )
    p = type_priors(moves, events)
    assert p["clarification"] > 0.5  # 澄清公告當天的波動遠大於平均
    assert p["personnel"] == 0.0
