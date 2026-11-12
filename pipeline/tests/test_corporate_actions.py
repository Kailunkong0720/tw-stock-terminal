from __future__ import annotations

import json
from datetime import date

import pytest

from pipeline.analytics.adjust import Action, adjust_prices, cumulative_factors, cumulative_share_factors
from pipeline.ingest.corporate_actions import parse_twt49u, parse_twtauu, parse_twtb8u, parse_twtcau
from tests.conftest import FIXTURES


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_twt49u_fixture():
    rows = parse_twt49u(load("twt49u_202506.json"))
    assert len(rows) == 245
    r = next(x for x in rows if x["symbol"] == "1598")
    assert r["ex_date"] == date(2025, 6, 2)
    assert r["type"] == "dividend_cash" and not r["affects_shares"]
    assert r["factor"] == pytest.approx(22.20 / 22.70)
    assert all(0 < x["factor"] <= 1.0001 for x in rows), "除權息的參考價不會高於前收"


# 以下三個報表的資料列取自 2026-11-12 對證交所網站的實際查詢結果
TWTAUU = {
    "stat": "OK",
    "fields": [
        "恢復買賣日期",
        "股票代號",
        "名稱",
        "停止買賣前收盤價格",
        "恢復買賣參考價",
        "漲停價格",
        "跌停價格",
        "開盤競價基準",
        "除權參考價",
        "減資原因",
        "詳細資料",
    ],
    "data": [
        ["109/01/20", "3557", "嘉威", "38.05", "48.57", "53.40", "43.75", "48.55", "--", "彌補虧損", "3557  ,20200108"]
    ],
}
TWTB8U = {
    "stat": "OK",
    "fields": [
        "恢復買賣日期",
        "股票代號",
        "名稱",
        "停止買賣前收盤價格",
        "恢復買賣參考價",
        "漲停價格",
        "跌停價格",
        "開盤競價基準",
        "詳細資料",
    ],
    "data": [["109/08/17", "8070", "長華", "190.00", "19.00", "20.90", "17.10", "19.00", "8070,20200806,20200817"]],
}
TWTCAU = {
    "stat": "OK",
    "fields": [
        "恢復買賣日期",
        "ETF代號",
        "名稱",
        "分割(反分割)",
        "停止買賣前收盤價格",
        "恢復買賣參考價",
        "漲停價格",
        "跌停價格",
        "開盤競價基準",
    ],
    "data": [
        ["114/06/18", "0050", "元大台灣50", "分割", "188.65", "47.16", "51.85", "42.45", "47.16"],
        ["114/02/19", "00676R", "富邦臺灣加權反1", "反分割", "2.04", "12.23", "13.45", "11.01", "12.23"],
    ],
}


def test_parse_reduction_par_change_and_etf_split():
    (red,) = parse_twtauu(TWTAUU)
    assert red["type"] == "capital_reduction" and red["ex_date"] == date(2020, 1, 20)
    assert red["factor"] == pytest.approx(48.57 / 38.05) and red["affects_shares"]

    (par,) = parse_twtb8u(TWTB8U)
    assert par["type"] == "par_change" and par["factor"] == pytest.approx(0.1)

    split, rev = parse_twtcau(TWTCAU)
    assert split["symbol"] == "0050" and split["type"] == "etf_split"
    assert split["ex_date"] == date(2025, 6, 18)
    assert split["factor"] == pytest.approx(0.25, abs=0.001)  # 1 拆 4
    assert rev["type"] == "etf_reverse_split" and rev["factor"] == pytest.approx(6, rel=0.01)


def test_cumulative_factors_split_makes_series_continuous():
    # 0050：分割前一天收 188.65，分割日開在 47.16 附近
    dates = [date(2025, 6, 16), date(2025, 6, 17), date(2025, 6, 18), date(2025, 6, 19)]
    closes = [189.0, 188.65, 47.5, 47.8]
    acts = [Action(date(2025, 6, 18), 47.16 / 188.65, True)]
    f = cumulative_factors(dates, acts)
    assert f[:2] == pytest.approx([0.25, 0.25], abs=0.001) and f[2:] == [1.0, 1.0]
    adj = adjust_prices(closes, f)
    ret = adj[2] / adj[1] - 1
    assert abs(ret) < 0.02, "還原後分割日的報酬應接近 0，而不是 -75%"


def test_cumulative_factors_multiple_actions_and_as_of():
    dates = [date(2024, 1, 1), date(2024, 6, 1), date(2025, 1, 1)]
    acts = [Action(date(2024, 3, 1), 0.9), Action(date(2024, 9, 1), 0.5, True)]
    assert cumulative_factors(dates, acts) == pytest.approx([0.45, 0.5, 1.0])
    # 回測時，基準日 2024-06-01 還不知道 9 月的分割
    assert cumulative_factors(dates, acts, as_of=date(2024, 6, 1)) == pytest.approx([0.9, 1.0, 1.0])
    assert cumulative_share_factors(dates, acts) == pytest.approx([0.5, 0.5, 1.0])
