from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from pipeline.export.globe import overnight_changes, spiral
from pipeline.ingest.company import parse_city


@pytest.mark.parametrize(
    ("addr", "en", "city"),
    [
        ("新竹科學園區力行六路8號", None, "新竹科學園區"),
        ("新竹科學園區新竹巿力行路16號", None, "新竹科學園區"),
        ("新竹科學工業園區新竹市力行六路十號", None, "新竹科學園區"),
        ("新竹科學園區苗栗縣竹南鎮科學路160號", None, "苗栗縣"),
        ("新竹科學園區新竹縣竹北市生醫五路66之2號", None, "新竹縣"),
        ("北市後港街六十六號", None, "台北市"),
        ("(11568)台北市南港區經貿二路66號13樓", None, "台北市"),
        ("71001台南市永康區中正路301號", None, "台南市"),
        ("臺北市南港區南港路一段209號10樓", None, "台北市"),
        ("桃園巿觀音區觀音工業區大同一路18號", None, "桃園市"),
        ("台北市內湖區內湖科學園區某路1號", None, "台北市"),  # 不是竹科
        (
            "Windward 3,Regatta Office Park,PO Box 1350,Grand Cayman KY1",
            "Rm. 711, No 237, Fu-Hsing S. Rd. Sec.2Taipei , Taiwan",
            "台北市",
        ),
        ("Grand Cayman", "No. 1, New Taipei City", "新北市"),
        ("", None, None),
    ],
)
def test_parse_city(addr, en, city):
    assert parse_city(addr, en) == city


def test_overnight_alignment_and_holidays():
    # 台股交易日：週四、週五、（週一放假）週二
    tw = [date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 13)]
    us = pd.Series(
        [100.0, 110.0, 99.0, 99.0, 108.9],
        index=[date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 12), date(2026, 1, 13)],
    )
    out = overnight_changes(us, tw, "pct")
    assert out[0] is None
    # 1/9 台股開盤前：美股 1/8（+10%）
    assert out[1] == pytest.approx(0.10)
    # 1/13 台股開盤前：美股 1/9（-10%）與 1/12（0%）累積；1/13 當天的美股收盤在台股收盤之後，不算
    assert out[2] == pytest.approx(-0.10)


def test_overnight_bp_and_gaps():
    tw = [date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 12)]
    us = pd.Series([4.00, 4.05, 4.02], index=[date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)])
    out = overnight_changes(us, tw, "bp")
    assert out[1] == pytest.approx(5.0)
    assert out[2] == pytest.approx(-3.0)
    # 期間沒有海外交易日
    assert overnight_changes(us, [date(2026, 1, 10), date(2026, 1, 11)], "pct") == [None, None]


def test_spiral_points_are_distinct():
    pts = {spiral((25.0, 121.5), i) for i in range(60)}
    assert len(pts) == 60
    assert spiral((25.0, 121.5), 0) == (25.0, 121.5)
