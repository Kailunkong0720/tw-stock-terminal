from __future__ import annotations

from datetime import date, datetime

import pytest

from pipeline.events.classify import classify
from pipeline.ingest.mops import effective_trade_date, parse_t05st01


@pytest.mark.parametrize(
    ("title", "type_", "direction"),
    [
        ("本公司代子公司 TSMC Global Ltd. 公告取得固定收益證券", "routine", 0),
        ("台積公司2024年12月營收報告", "revenue", 0),
        ("台積公司2024年第四季每股盈餘新台幣14.45元", "earnings", 0),
        ("本公司董事會決議股利分派", "dividend", 0),
        ("本公司訂定民國113年第四季之現金股利除息交易日", "dividend", 0),
        ("說明媒體報導", "clarification", 0),
        ("本公司董事會決議買回本公司股份", "buyback", 1),
        ("本公司董事會決議辦理現金增資發行新股", "capital_increase", -1),
        ("公告本公司董事會決議股票分割", "split", 0),
        ("本公司受邀參加機構投資人說明會", "investor_conf", 0),
        ("本公司廠區發生火災", "disaster", -1),
        ("代子公司富士康工業互聯網股份有限公司公告監事辭職", "personnel", 0),
        ("台積公司宣布有意增加在美投資金額至1,650億美元 以驅動人工智慧未來", "capex", 0),
        ("本公司113年度合併財務報告虧損", "earnings", -1),
        ("某些無法分類的公告", "other", 0),
        ("代子公司NHOA S.A.公告董事會決議增資NHOA Energy s.r.l.", "investment", 0),
        ("本公司參與認購飛宏科技股份有限公司私募普通股股份", "investment", 0),
        ("本公司董事會決議召開民國114年股東常會", "shareholder", 0),
        ("公告本公司111年1月份自結合併盈餘", "earnings", 0),
        ("公告本公司2022年6月合併營業額", "revenue", 0),
        ("公告本公司2022年第2季自結合併損益", "earnings", 0),
    ],
)
def test_classify(title, type_, direction):
    assert classify(title) == (type_, direction)


CAL = [date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8), date(2025, 1, 10)]


def test_effective_trade_date():
    assert effective_trade_date(datetime(2025, 1, 7, 10, 0), CAL) == date(2025, 1, 7)  # 盤中 → 當天
    assert effective_trade_date(datetime(2025, 1, 7, 13, 30), CAL) == date(2025, 1, 8)  # 收盤後 → 下一個交易日
    assert effective_trade_date(datetime(2025, 1, 8, 17, 0), CAL) == date(2025, 1, 10)  # 跳過休市日
    assert effective_trade_date(datetime(2025, 1, 9, 9, 0), CAL) == date(2025, 1, 10)  # 休市日公告
    assert effective_trade_date(datetime(2025, 1, 10, 18, 0), CAL) == date(2025, 1, 13)  # 超出日曆 → 下一個平日


def test_parse_t05st01():
    payload = {
        "code": 200,
        "result": {
            "data": [
                [
                    "2330",
                    "台積電",
                    "114/01/10",
                    "14:05:13",
                    "台積公司2024年12月營收報告",
                    {
                        "parameters": {"enterDate": "1140110", "serialNumber": "1", "companyId": "2330"},
                        "apiName": "t05st01_detail",
                    },
                ],
                [
                    "2330",
                    "台積電",
                    "114/03/04",
                    "06:03:39",
                    "台積公司宣布有意增加在美投資金額至1,650億美元\r\n以驅動人工智慧未來",
                    {"parameters": {"serialNumber": "1"}},
                ],
            ]
        },
    }
    cal = [date(2025, 1, 10), date(2025, 1, 13), date(2025, 3, 4)]
    rows = parse_t05st01(payload, cal)
    assert len(rows) == 2
    assert rows[0]["trade_date"] == date(2025, 1, 13)  # 14:05 盤後公告
    assert rows[0]["type"] == "revenue" and rows[0]["level"] == "official"
    assert rows[1]["trade_date"] == date(2025, 3, 4)  # 06:03 盤前公告
    assert "\r" not in rows[1]["title"] and "\n" not in rows[1]["title"]
    assert rows[0]["uid"] != rows[1]["uid"]
