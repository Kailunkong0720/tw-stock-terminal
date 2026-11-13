"""公司基本資料（產業別、上市日、發行股數）與追蹤池（PLAN.md 1.3、3.3）。

追蹤池的定義：資料截止日市值前 150 大的上市普通股，加上 0050、0056、00878、006208。
原計劃寫「台灣 50 + 中型 100 成分股」；這兩個指數的成分本質上就是市值前 150 大
（另有流動性篩選），以市值排名取代可以不依賴額外的成分股來源，而且可重現。
"""

from __future__ import annotations

import logging
import re

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


CITIES = [
    "台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "基隆市", "新竹市", "嘉義市",
    "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣",
]  # fmt: skip
SCIENCE_PARK = "新竹科學園區"
# 外國企業（-KY）的登記地址在開曼群島等地，改用英文通訊地址（多在台灣）判斷
EN_CITIES = [
    ("new taipei", "新北市"), ("taipei", "台北市"), ("taoyuan", "桃園市"), ("hsinchu science", SCIENCE_PARK),
    ("hsinchu county", "新竹縣"), ("zhubei", "新竹縣"), ("hsinchu", "新竹市"), ("taichung", "台中市"),
    ("tainan", "台南市"), ("kaohsiung", "高雄市"), ("keelung", "基隆市"), ("changhua", "彰化縣"),
    ("miaoli", "苗栗縣"), ("pingtung", "屏東縣"), ("yunlin", "雲林縣"), ("nantou", "南投縣"), ("chiayi", "嘉義市"),
    ("yilan", "宜蘭縣"), ("hualien", "花蓮縣"), ("taitung", "台東縣"),
]  # fmt: skip


def parse_city(addr: str | None, en_addr: str | None = None) -> str | None:
    """公司地址 → 縣市。新竹科學園區（竹科）單獨一類；竹南、竹北園區歸到所在縣。"""
    a = (addr or "").replace("臺", "台").replace("巿", "市").strip()
    hits = [(a.find(c), c) for c in CITIES if c in a]
    first = min(hits)[1] if hits else None
    park = re.search(r"(新竹|中部|南部)科學(工業)?園區", a)
    if park and park.group(1) == "新竹":
        if "苗栗縣" in a or "竹南" in a:
            return "苗栗縣"
        if "新竹縣" in a or "竹北" in a:
            return "新竹縣"
        return SCIENCE_PARK
    if park:
        return first or {"中部": "台中市", "南部": "台南市"}[park.group(1)]
    if a.lstrip("0123456789()（） ").startswith("北市"):
        return "台北市"
    if first:
        return first
    en = (en_addr or "").lower()
    for key, city in EN_CITIES:
        if key in en:
            return city
    return None


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
            "city": parse_city(r.get("住址"), r.get("英文通訊地址")),
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
                sec.city = meta["city"]
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
