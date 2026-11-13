"""櫃買中心解析：用 2026-11-13 實際請求存下的回應（tests/fixtures/tpex/）。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.ingest.tpex import (
    OTC_INDEX,
    OTC_TR_INDEX,
    parse_company_otc,
    parse_daily_trade,
    parse_exdailyq,
    parse_otc,
    parse_pvchg,
    parse_qfii,
    parse_revivt,
    parse_roe,
)

FIX = Path(__file__).parent / "fixtures" / "tpex"


def load(name: str):  # noqa: ANN201
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def test_otc_keeps_only_common_stocks():
    bars, names = parse_otc(load("otc"), date(2024, 7, 15))
    syms = {b["symbol"] for b in bars}
    assert "00679B" not in syms and "00687B" not in syms  # 債券 ETF 不收
    assert all(len(s) == 4 and s.isdigit() for s in syms)
    assert set(names) == syms


def test_daily_trade_columns_add_up():
    rows = parse_daily_trade(load("dailyTrade"), date(2024, 7, 15))
    assert rows, "fixture 裡應該有普通股"
    for r in rows:
        assert r["foreign_buy"] - r["foreign_sell"] == r["foreign_net"]
        assert r["trust_buy"] - r["trust_sell"] == r["trust_net"]
        assert r["foreign_net"] + r["trust_net"] + r["dealer_net"] == r["total_net"]
        assert not r["symbol"].startswith("00")


def test_exdailyq_dividend_and_rights():
    rows = {r["symbol"]: r for r in parse_exdailyq(load("exDailyQ"))}
    r = rows["3373"]  # 熱映 113/07/01 除息 1 元：27.00 → 26.00
    assert r["ex_date"] == date(2024, 7, 1) and r["type"] == "dividend_cash"
    assert r["factor"] == pytest.approx(26 / 27)
    assert r["limit_up"] == pytest.approx(28.60) and r["limit_down"] == pytest.approx(23.40)
    s = rows["4188"]  # 安克 純現金增資除權：減除股利參考價 = 前收，價格不調整
    assert s["type"] == "rights_issue" and not s["affects_shares"] and s["factor"] == pytest.approx(1)


def test_capital_reduction_and_par_change():
    red = {r["symbol"]: r for r in parse_revivt(load("revivt"))}
    r = red["3064"]  # 泰偉 減資彌補虧損 10.65 → 35.50
    assert r["ex_date"] == date(2024, 2, 5) and r["type"] == "capital_reduction"
    assert r["factor"] == pytest.approx(35.5 / 10.65)
    pv = {r["symbol"]: r for r in parse_pvchg(load("pvChgRslt"))}
    assert pv["6613"]["factor"] == pytest.approx(0.5) and pv["6613"]["ex_date"] == date(2022, 8, 29)


def test_qfii_percent_and_issued():
    rows = {r["symbol"]: r for r in parse_qfii(load("qfii"), date(2024, 7, 15))}
    r = rows["8455"]
    assert r["shares_issued"] == 25_219_056 and r["foreign_shares"] == 22_165_306
    assert r["foreign_pct"] == pytest.approx(87.89) and r["limit_pct"] == pytest.approx(100)


def test_roe_gives_price_and_total_return_index():
    rows = parse_roe(load("ROE"))
    first = [r for r in rows if r["date"] == date(2024, 7, 1)]
    assert {r["index_id"]: r["close"] for r in first} == {OTC_INDEX: 275.57, OTC_TR_INDEX: 481.13}


def test_company_industry_listing_and_city():
    info = parse_company_otc(load("company"))
    r = info["1240"]
    assert r["industry"] == "農業科技" and r["listed_on"] == date(2018, 8, 8) and r["city"] == "台北市"
    assert info["1264"]["city"] == "新北市"
