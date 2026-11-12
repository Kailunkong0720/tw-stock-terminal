from __future__ import annotations

import json
from datetime import date

import pytest

from pipeline.analytics.checks import find_violations
from pipeline.core.db import get_engine, migrate, session_scope
from pipeline.export.contract import Bars, Calendar, Flows, Meta, Overview, Securities
from pipeline.export.run import run_export
from pipeline.ingest.common import mark, upsert
from pipeline.models import CorporateAction, DailyBar, IndexBar, InstitutionalFlow, MarketFlow, Security

D = [date(2025, 6, 16), date(2025, 6, 17), date(2025, 6, 18), date(2025, 6, 19), date(2025, 6, 20)]


def bar(sym, d, c, vol=2_000_500):  # noqa: ANN001
    return {
        "symbol": sym,
        "date": d,
        "open": c,
        "high": c,
        "low": c,
        "close": c,
        "change": 0.0,
        "volume": vol,
        "value": int(vol * c),
        "trades": 10,
        "pe": None,
    }


@pytest.fixture
def db(settings):  # noqa: ANN001
    migrate(settings)
    with session_scope(settings) as s:
        s.add_all(
            [
                Security(
                    symbol="2330",
                    name="台積電",
                    kind="stock",
                    industry="半導體",
                    tracked=True,
                    first_bar=D[0],
                    last_bar=D[-1],
                ),
                Security(
                    symbol="0050",
                    name="元大台灣50",
                    kind="etf",
                    industry="ETF",
                    tracked=True,
                    first_bar=D[0],
                    last_bar=D[-1],
                ),
                # 只有中間兩天有資料的股票，用來測日曆對齊
                Security(symbol="9999", name="測試", kind="stock", industry="其他", first_bar=D[1], last_bar=D[3]),
            ]
        )
        upsert(s, DailyBar, [bar("2330", d, c) for d, c in zip(D, [1000, 1010, 1020, 1015, 1030], strict=True)])
        # 0050 在 6/18 一拆四
        upsert(s, DailyBar, [bar("0050", d, c) for d, c in zip(D, [189.0, 188.65, 47.5, 47.8, 48.0], strict=True)])
        upsert(
            s,
            DailyBar,
            [
                bar("9999", D[1], 10.0),
                {**bar("9999", D[2], 10.0), "close": None, "open": None, "high": None, "low": None, "volume": 0},
                bar("9999", D[3], 10.5),
            ],
        )
        upsert(
            s,
            CorporateAction,
            [
                {
                    "symbol": "0050",
                    "ex_date": D[2],
                    "type": "etf_split",
                    "prev_close": 188.65,
                    "ref_price": 47.16,
                    "factor": 47.16 / 188.65,
                    "affects_shares": True,
                    "detail": "分割",
                    "source": "TWTCAU",
                }
            ],
        )
        upsert(
            s,
            InstitutionalFlow,
            [
                {
                    "symbol": "2330",
                    "date": d,
                    "foreign_buy": 0,
                    "foreign_sell": 0,
                    "foreign_net": 1_000_000,
                    "trust_buy": 0,
                    "trust_sell": 0,
                    "trust_net": -2000,
                    "dealer_net": 0,
                    "total_net": 998_000,
                }
                for d in D
            ],
        )
        upsert(
            s,
            MarketFlow,
            [
                {"date": d, "investor": inv, "buy": 0, "sell": 0, "net": 1e9}
                for d in D
                for inv in ("foreign", "trust", "dealer_self", "dealer_hedge", "total")
            ],
        )
        upsert(
            s,
            IndexBar,
            [
                {"index_id": iid, "date": d, "close": 20000 + i, "change": 1.0, "change_pct": 0.1}
                for i, d in enumerate(D)
                for iid in ("TWSE:發行量加權股價指數", "TWSE:半導體類指數")
            ],
        )
        for d in D:
            mark(s, "twse_mi_index", d.isoformat(), "ok", 3)
    return settings


def read(settings, rel):  # noqa: ANN001
    return json.loads((settings.export_dir / rel).read_text(encoding="utf-8"))


def test_export_market_files(db):
    run_export(db)
    cal = Calendar.model_validate(read(db, "calendar.json"))
    assert cal.dates == D

    secs = Securities.model_validate(read(db, "securities.json"))
    assert {s.symbol for s in secs.items} == {"2330", "0050", "9999"}
    assert next(s for s in secs.items if s.symbol == "9999").active is False

    b = Bars.model_validate(read(db, "bars/0050.json"))
    assert b.start == 0 and len(b.close) == 5
    assert b.volume[0] == 2001  # 2,000,500 股 → 2,001 張
    assert b.actions[0].ex_date == D[2] and b.actions[0].factor == pytest.approx(0.25, abs=0.001)

    b9 = Bars.model_validate(read(db, "bars/9999.json"))
    assert b9.start == 1 and b9.close == [10.0, None, 10.5]

    f = Flows.model_validate(read(db, "flows/2330.json"))
    assert f.foreign_net == [1000] * 5  # 張
    assert f.foreign_value[0] == pytest.approx(1000.0)  # 1,000,000 股 × 1000 元 = 10 億 = 1,000 百萬

    mf = read(db, "flows/market.json")
    assert mf["dealer"][0] == pytest.approx(20.0)  # 自行買賣 + 避險，各 10 億

    ov = Overview.model_validate(read(db, "market/overview.json"))
    assert ov.taiex.close[-1] == 20004
    assert any(sp.industry == "半導體" for sp in ov.sectors)

    meta = Meta.model_validate(read(db, "meta.json"))
    assert meta.data_as_of == D[-1]
    assert meta.tracked == ["0050", "2330"]
    assert next(s for s in meta.sources if s.id == "twse_daily").status == "ok"


def test_invariant_flags_missing_split(db):
    engine = get_engine(db)
    assert find_violations(engine, D[0]) == []  # 0050 是 ETF，不檢查；2330 正常

    # 一檔普通股在 6/18 一拆十，但沒有公司行動紀錄 → 必須被抓出來
    with session_scope(db) as s:
        s.add(Security(symbol="1111", name="漏資料", kind="stock", first_bar=D[0], last_bar=D[-1]))
        upsert(s, DailyBar, [bar("1111", d, c) for d, c in zip(D, [100, 101, 10.1, 10.2, 10.0], strict=True)])
    vs = find_violations(engine, D[0])
    assert len(vs) == 1 and vs[0].symbol == "1111" and vs[0].reason is None

    # 補上面額變更後就不再違規
    with session_scope(db) as s:
        upsert(
            s,
            CorporateAction,
            [
                {
                    "symbol": "1111",
                    "ex_date": D[2],
                    "type": "par_change",
                    "prev_close": 101,
                    "ref_price": 10.1,
                    "factor": 0.1,
                    "affects_shares": True,
                    "detail": None,
                    "source": "TWTB8U",
                }
            ],
        )
    assert find_violations(engine, D[0]) == []
