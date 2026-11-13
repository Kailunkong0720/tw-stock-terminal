"""全球脈動頁的輸出：隔夜傳導（美股前一晚 → 台股當天）與全球供應鏈地圖。"""

from __future__ import annotations

import bisect
import json
import logging
import math
import re
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import Engine

from pipeline.export.contract import GlobeLink, GlobeOvernight, GlobePlace, GlobeSupply, OvernightSeries
from pipeline.export.graph import REL_NAMES
from pipeline.export.writer import ExportWriter
from pipeline.ingest.industry import TAIEX

log = logging.getLogger(__name__)

TAIPEI = (25.034, 121.564)  # 證交所（台北 101）
HSINCHU_PARK = (24.774, 121.003)  # 新竹科學園區（台積電總部）

# (series id, 名稱, 單位, lat, lng, 地點, 落點)
OVERNIGHT: list[tuple[str, str, str, float, float, str, str]] = [
    ("GLOBAL:SOX", "費城半導體指數", "pct", 39.952, -75.165, "美國費城", "tsmc"),
    ("GLOBAL:TSM_ADR", "台積電 ADR", "pct", 40.707, -74.011, "美國紐約證交所", "tsmc"),
    ("GLOBAL:NASDAQ", "那斯達克", "pct", 40.757, -73.986, "美國紐約", "taiex"),
    ("GLOBAL:SP500", "標普 500", "pct", 41.878, -87.636, "美國芝加哥（期貨）", "taiex"),
    ("GLOBAL:US10Y", "美國十年期公債殖利率", "bp", 38.899, -77.034, "美國華盛頓特區（財政部）", "taiex"),
]
# 不放美元兌台幣：新台幣匯率主要在台北時段決定，Yahoo 的日線也以台北日期標示，不是「前一晚」的訊號

# 縣市的代表座標（公司登記地址只到縣市，同一縣市的公司在這個點周圍以螺旋排開）
CITY_COORDS: dict[str, tuple[float, float]] = {
    "台北市": (25.050, 121.560),
    "新北市": (25.012, 121.465),
    "桃園市": (24.993, 121.301),
    "新竹科學園區": (24.776, 121.005),
    "新竹市": (24.804, 120.968),
    "新竹縣": (24.830, 121.013),
    "苗栗縣": (24.687, 120.880),
    "台中市": (24.162, 120.647),
    "彰化縣": (24.076, 120.542),
    "南投縣": (23.910, 120.684),
    "雲林縣": (23.708, 120.431),
    "嘉義市": (23.480, 120.449),
    "嘉義縣": (23.452, 120.256),
    "台南市": (22.999, 120.227),
    "高雄市": (22.627, 120.301),
    "屏東縣": (22.669, 120.488),
    "基隆市": (25.128, 121.741),
    "宜蘭縣": (24.702, 121.738),
    "花蓮縣": (23.987, 121.601),
    "台東縣": (22.756, 121.144),
    "澎湖縣": (23.571, 119.579),
}
SPIRAL_STEP = 0.011  # 度；第 i 家公司離中心 step × √i
GOLDEN = math.radians(137.508)


def overnight_changes(us: pd.Series, tw_dates: list[date], unit: str) -> list[float | None]:
    """把海外每日變動對齊到台股交易日。

    台股第 i 天受到「上一個台股交易日（含當天，因為美股收盤在台股收盤之後）到第 i 天之前」
    的海外交易日影響；連假期間有多個海外交易日時累積起來。
    """
    s = us.dropna().sort_index()
    if s.empty:
        return [None] * len(tw_dates)
    chg = s.diff() * 100 if unit == "bp" else s.pct_change()
    days = list(chg.index)
    vals = chg.to_numpy()
    out: list[float | None] = [None] * len(tw_dates)
    for i in range(1, len(tw_dates)):
        lo = bisect.bisect_left(days, tw_dates[i - 1])
        hi = bisect.bisect_left(days, tw_dates[i])
        window = [v for v in vals[lo:hi] if not np.isnan(v)]
        if not window:
            continue
        if unit == "bp":
            out[i] = round(float(sum(window)), 3)
        else:
            out[i] = round(float(np.prod([1 + v for v in window]) - 1), 6)
    return out


def spiral(center: tuple[float, float], i: int) -> tuple[float, float]:
    if i == 0:
        return center
    r = SPIRAL_STEP * math.sqrt(i)
    a = i * GOLDEN
    lat = center[0] + r * math.sin(a)
    lng = center[1] + r * math.cos(a) / math.cos(math.radians(center[0]))
    return round(lat, 4), round(lng, 4)


def _align(values: pd.Series, calendar: list[date]) -> list[float | None]:
    v = values.reindex(calendar)
    return [None if pd.isna(x) else round(float(x), 6) for x in v]


def export_overnight(engine: Engine, writer: ExportWriter, calendar: list[date]) -> None:
    ids = [o[0] for o in OVERNIGHT] + [TAIEX]
    idx = pd.read_sql_query(
        "SELECT index_id, date, close FROM index_bar WHERE index_id IN (" + ",".join(f"'{i}'" for i in ids) + ")",
        engine,
    )
    idx["date"] = pd.to_datetime(idx["date"]).dt.date
    by_id = {k: g.set_index("date")["close"].sort_index() for k, g in idx.groupby("index_id")}
    series = []
    for sid, name, unit, lat, lng, place, target in OVERNIGHT:
        if sid not in by_id:
            log.warning("缺少 %s，隔夜傳導略過這個序列", sid)
            continue
        series.append(
            OvernightSeries(
                id=sid,
                name=name,
                unit=unit,
                lat=lat,
                lng=lng,
                place=place,
                target=target,
                values=overnight_changes(by_id[sid], calendar, unit),
            )
        )
    taiex = by_id.get(TAIEX, pd.Series(dtype=float)).reindex(calendar).pct_change(fill_method=None)
    tsmc = pd.read_sql_query("SELECT date, ret FROM price_move WHERE symbol = '2330'", engine)
    tsmc["date"] = pd.to_datetime(tsmc["date"]).dt.date
    writer.write(
        "globe/overnight.json",
        GlobeOvernight(
            start=0,
            series=series,
            taiex=_align(taiex, calendar),
            tsmc=_align(tsmc.set_index("date")["ret"], calendar),
            landing={"taiex": list(TAIPEI), "tsmc": list(HSINCHU_PARK)},
        ),
    )


def _signed_rho(confidence: float, note: str | None) -> float:
    m = re.search(r"相關係數 ([-+−]?\d+\.\d+)", note or "")
    if m:
        return round(float(m.group(1).replace("−", "-")), 3)
    return round(float(confidence), 3)


def export_supply(engine: Engine, writer: ExportWriter) -> None:
    nodes = pd.read_sql_query("SELECT id, type, name, attrs FROM kg_node", engine)
    if nodes.empty:
        log.info("尚無知識圖譜，略過全球供應鏈輸出")
        return
    edges = pd.read_sql_query("SELECT src, dst, rel, confidence, source, note FROM kg_edge", engine)
    secs = pd.read_sql_query("SELECT symbol, name, industry, city, tracked FROM security WHERE kind = 'stock'", engine)
    sec_by = {r.symbol: r for r in secs.itertuples()}
    cap = pd.read_sql_query(
        "SELECT h.symbol, h.shares_issued * b.close AS cap FROM foreign_holding h "
        "JOIN (SELECT symbol, MAX(date) AS d FROM foreign_holding GROUP BY symbol) m ON m.symbol = h.symbol AND m.d = h.date "
        "JOIN daily_bar b ON b.symbol = h.symbol AND b.date = h.date",
        engine,
    )
    cap_by = dict(zip(cap["symbol"], cap["cap"], strict=True))

    places: dict[str, GlobePlace] = {}
    for r in nodes.itertuples():
        attrs = json.loads(r.attrs or "{}")
        if r.type != "company" and "lat" in attrs and "lng" in attrs:
            places[r.id] = GlobePlace(
                id=r.id, name=r.name, type=r.type, lat=attrs["lat"], lng=attrs["lng"], place=attrs.get("place", "")
            )

    companies = [r for r in nodes.itertuples() if r.type == "company"]
    by_city: dict[str, list] = {}
    for r in companies:
        sym = r.id.split(":", 1)[1]
        sec = sec_by.get(sym)
        if sec is None:
            continue
        city = sec.city if isinstance(sec.city, str) and sec.city in CITY_COORDS else None
        by_city.setdefault(city or "", []).append((sym, r, sec))
    for city, items in by_city.items():
        items.sort(key=lambda x: -(cap_by.get(x[0]) or 0))
        center = CITY_COORDS.get(city, TAIPEI)
        for i, (sym, r, sec) in enumerate(items):
            lat, lng = spiral(center, i)
            places[r.id] = GlobePlace(
                id=r.id,
                name=r.name,
                type="company",
                lat=lat,
                lng=lng,
                place=city or "台灣（地址未能判讀）",
                symbol=sym,
                industry=sec.industry if isinstance(sec.industry, str) else None,
                tracked=bool(sec.tracked),
            )

    links = []
    for e in edges.itertuples():
        if e.src not in places or e.dst not in places:
            continue
        a, b = places[e.src], places[e.dst]
        if (a.type == "company") == (b.type == "company"):
            continue  # 只要台股公司與海外節點之間的關係
        data = e.source == "data"
        links.append(
            GlobeLink(
                source=e.src,
                target=e.dst,
                rel=e.rel,
                rel_name=REL_NAMES.get(e.rel, e.rel),
                origin="data" if data else "seed",
                rho=_signed_rho(e.confidence, e.note) if data else None,
                note=None if data or not isinstance(e.note, str) else e.note,
            )
        )
    writer.write("globe/supply.json", GlobeSupply(places=list(places.values()), links=links))
    log.info(
        "全球脈動：%d 個地點（台股 %d 家），%d 條關係",
        len(places),
        sum(p.type == "company" for p in places.values()),
        len(links),
    )


def export_globe(engine: Engine, writer: ExportWriter, calendar: list[date]) -> None:
    export_overnight(engine, writer, calendar)
    export_supply(engine, writer)
