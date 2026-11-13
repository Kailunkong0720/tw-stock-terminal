from __future__ import annotations

from datetime import date

from pipeline.ingest.news import parse_articles, query_for, window

CAL = [date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9)]


def test_window_is_previous_close_to_close_in_utc():
    # 11/06 的影響窗口：11/05 13:30 到 11/06 13:30（台北）= 05:30 UTC
    assert window(CAL, date(2026, 11, 6)) == ("20261105053000", "20261106053000")
    # 週一：從上週五收盤開始，週末的新聞都算
    assert window(CAL, date(2026, 11, 9)) == ("20261106053000", "20261109053000")


def test_parse_articles_maps_to_trading_day_and_keeps_only_title_link():
    payload = {
        "articles": [
            {
                "url": "https://example.tw/a",
                "title": "台積電法說會上調全年營收",
                "seendate": "20261106T010000Z",
                "domain": "example.tw",
            },
            # 盤後（台北 15:00）→ 下一個交易日
            {"url": "https://example.tw/b", "title": "某新聞", "seendate": "20261106T070000Z", "domain": "example.tw"},
            {"url": "", "title": "沒有網址", "seendate": "20261106T010000Z"},
        ]
    }
    rows = parse_articles(payload, "2330", CAL)
    assert len(rows) == 2
    a, b = rows
    assert a["trade_date"] == date(2026, 11, 6) and a["level"] == "media" and a["symbol"] == "2330"
    assert b["trade_date"] == date(2026, 11, 9)
    assert a["uid"].startswith("gdelt:2330:") and a["uid"] != b["uid"]
    assert set(a) >= {"title", "url", "source", "at"} and a["detail"] is None
    assert parse_articles({}, "2330", CAL) == []


def test_query_prefers_english_name_with_taiwan_media():
    assert query_for("台積電", "TSMC") == '"TSMC" sourcecountry:taiwan'
    assert query_for("台積電", None) == '"台積電"'
