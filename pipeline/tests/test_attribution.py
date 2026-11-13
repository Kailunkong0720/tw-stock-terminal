from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import select

from pipeline.core.db import migrate, session_scope
from pipeline.events.attribution import build_action_events, direction_score, score, type_priors
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
