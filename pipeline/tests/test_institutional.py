from __future__ import annotations

import json
from datetime import date

from pipeline.ingest.institutional import parse_bfi82u, parse_mi_qfiis, parse_t86, weekly_last_days
from tests.conftest import FIXTURES


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_t86_2020_and_2026():
    rows = parse_t86(load("t86_20200102.json"), date(2020, 1, 2))
    assert len(rows) == 1037
    r = next(x for x in rows if x["symbol"] == "00637L")
    assert r["foreign_net"] == 15_365_000
    assert r["foreign_buy"] - r["foreign_sell"] == r["foreign_net"]
    assert r["total_net"] == 59_604_000
    # 三大法人合計 = 外資（不含外資自營商）+ 投信 + 自營商；外資自營商已含在自營商裡
    for x in rows:
        assert x["foreign_net"] + x["trust_net"] + x["dealer_net"] == x["total_net"], x["symbol"]

    rows26 = parse_t86(load("t86_20261111.json"), date(2026, 11, 11))
    assert len(rows26) == 1340


def test_parse_bfi82u():
    rows = {r["investor"]: r for r in parse_bfi82u(load("bfi82u_20200102.json"), date(2020, 1, 2))}
    assert set(rows) == {"dealer_self", "dealer_hedge", "trust", "foreign", "foreign_dealer", "total"}
    assert rows["dealer_self"]["net"] == 1_395_424_086
    # 證交所註記：外資自營商已計入自營商，不納入合計
    parts = sum(v["net"] for k, v in rows.items() if k not in ("total", "foreign_dealer"))
    assert parts == rows["total"]["net"]


def test_parse_mi_qfiis():
    rows = parse_mi_qfiis(load("mi_qfiis_20200102.json"), date(2020, 1, 2))
    assert len(rows) > 1000
    r = next(x for x in rows if x["symbol"] == "0050")
    assert r["shares_issued"] == 687_000_000
    assert r["foreign_pct"] == 27.87
    assert abs(r["foreign_shares"] / r["shares_issued"] * 100 - r["foreign_pct"]) < 0.01


def test_weekly_last_days():
    days = [date(2026, 11, d) for d in (2, 3, 4, 5, 6, 9, 10, 11)]
    assert weekly_last_days(days) == [date(2026, 11, 6), date(2026, 11, 11)]
