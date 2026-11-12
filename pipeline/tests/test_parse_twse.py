from __future__ import annotations

import json
from datetime import date

import pytest

from pipeline.ingest.parse import is_no_data, is_ok, roc_date, sign_of, to_float, to_int
from pipeline.ingest.twse_daily import classify, parse_mi_index
from tests.conftest import FIXTURES


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("raw", "want"),
    [("1,234.50", 1234.5), ("--", None), ("", None), ("0.00", 0.0), (72.12, 72.12), (" 97.05 ", 97.05)],
)
def test_to_float(raw, want):
    assert to_float(raw) == want


def test_to_int_and_sign_and_date():
    assert to_int("4,882,015") == 4882015
    assert sign_of("<p style= color:red>+</p>") == 1
    assert sign_of("<p style ='color:green'>-</p>") == -1
    assert sign_of("<p> </p>") == 0
    assert sign_of("X") == 0
    assert roc_date("109年01月02日") == date(2020, 1, 2)
    assert roc_date("114/06/18") == date(2025, 6, 18)
    assert roc_date("115/11/17") == date(2026, 11, 17)


def test_holiday_is_no_data():
    p = load("mi_index_20200101_holiday.json")
    assert is_no_data(p) and not is_ok(p)


def test_parse_mi_index_2020():
    res = parse_mi_index(load("mi_index_20200102.json"), date(2020, 1, 2))
    assert len(res.bars) == 1114
    bars = {b["symbol"]: b for b in res.bars}
    b = bars["0050"]
    assert (b["open"], b["high"], b["low"], b["close"]) == (97.05, 98.0, 97.05, 97.65)
    assert b["change"] == pytest.approx(0.70)
    assert b["volume"] == 4882015 and b["trades"] == 2421 and b["value"] == 476649683
    assert res.names["0050"] == "元大台灣50"
    # 下跌的股票，漲跌為負
    assert any(x["change"] is not None and x["change"] < 0 for x in res.bars)

    idx = {i["index_id"]: i for i in res.indices}
    assert "TWSE:發行量加權股價指數" in idx
    assert "TWSE:半導體類指數" in idx
    taiex = idx["TWSE:發行量加權股價指數"]
    assert 11000 < taiex["close"] < 13000  # 2020-01-02 加權指數約 12,100
    assert (taiex["change"] > 0) == (taiex["change_pct"] > 0)


def test_parse_mi_index_2026_has_same_shape():
    res = parse_mi_index(load("mi_index_20261111.json"), date(2026, 11, 11))
    assert len(res.bars) == 1390
    assert any(i["index_id"] == "TWSE:發行量加權股價指數" for i in res.indices)


@pytest.mark.parametrize(
    ("symbol", "name", "kind"),
    [
        ("2330", "台積電", "stock"),
        ("0050", "元大台灣50", "etf"),
        ("00632R", "元大台灣50反1", "etf"),
        ("00400A", "主動國泰動能高息", "etf"),
        ("020000", "富邦特選蘋果N", "etn"),
        ("2881A", "富邦特", "preferred"),
        ("9105", "泰金寶-DR", "tdr"),
        ("01001T", "土銀富邦R1", "other"),
    ],
)
def test_classify(symbol, name, kind):
    assert classify(symbol, name) == kind
