"""公司基本資料（產業別、上市日、發行股數）與追蹤池（PLAN.md 1.3、3.3）。

追蹤池的定義：資料截止日市值前 150 大的上市普通股，加上 0050、0056、00878、006208。
原計劃寫「台灣 50 + 中型 100 成分股」；這兩個指數的成分本質上就是市值前 150 大
（另有流動性篩選），以市值排名取代可以不依賴額外的成分股來源，而且可重現。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from pipeline.core.config import Settings
from pipeline.core.db import session_scope
from pipeline.core.http import HttpClient
from pipeline.ingest.common import mark
from pipeline.ingest.industry import industry_name
from pipeline.ingest.parse import clean_code, to_int
from pipeline.models import DailyBar, Security

log = logging.getLogger(__name__)

SOURCE = "twse_openapi_company"
URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TRACKED_ETFS = ["0050", "0056", "00878", "006208"]
TRACKED_STOCKS = 150


def parse_company(rows: list[dict]) -> dict[str, dict]:
    from datetime import date

    out = {}
    for r in rows:
        symbol = clean_code(r.get("公司代號"))
        if not symbol:
            continue
        listed = str(r.get("上市日期") or "").strip()
        listed_on = None
        if len(listed) == 8 and listed.isdigit():
            listed_on = date(int(listed[:4]), int(listed[4:6]), int(listed[6:]))
        out[symbol] = {
            "industry": industry_name(r.get("產業別")),
            "listed_on": listed_on,
            "shares": to_int(r.get("已發行普通股數或TDR原股發行股數")),
        }
    return out


def ingest_company(settings: Settings) -> dict[str, dict]:
    with HttpClient(settings.http_cache_dir) as http:
        rows = http.get_json(URL, use_cache=False)
    info = parse_company(rows)
    with session_scope(settings) as s:
        n = 0
        for sec in s.execute(select(Security)).scalars():
            meta = info.get(sec.symbol)
            if meta:
                sec.industry = meta["industry"]
                sec.listed_on = meta["listed_on"]
                n += 1
            elif sec.kind == "etf":
                sec.industry = "ETF"
        mark(s, SOURCE, "latest", "ok", n)
    log.info("公司基本資料：%d 家上市公司，更新 %d 筆", len(info), n)
    select_tracked(settings, {k: v["shares"] for k, v in info.items() if v["shares"]})
    return info


def select_tracked(settings: Settings, shares: dict[str, int]) -> list[str]:
    with session_scope(settings) as s:
        last = s.execute(select(func.max(DailyBar.date))).scalar_one_or_none()
        if last is None:
            log.warning("尚無日線資料，無法決定追蹤池")
            return []
        closes = dict(
            s.execute(
                select(DailyBar.symbol, DailyBar.close).where(DailyBar.date == last, DailyBar.close.is_not(None))
            ).all()
        )
        secs = {sec.symbol: sec for sec in s.execute(select(Security)).scalars()}
        caps = [
            (closes[sym] * shares[sym], sym)
            for sym, sec in secs.items()
            if sec.kind == "stock" and sym in closes and sym in shares
        ]
        caps.sort(reverse=True)
        tracked = [sym for _, sym in caps[:TRACKED_STOCKS]] + [e for e in TRACKED_ETFS if e in secs]
        for sym, sec in secs.items():
            sec.tracked = sym in tracked
    log.info(
        "追蹤池：%d 檔（市值前 %d 大普通股 + %d 檔 ETF），以 %s 收盤計",
        len(tracked),
        TRACKED_STOCKS,
        len(TRACKED_ETFS),
        last,
    )
    return tracked
