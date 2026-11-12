"""全球市場背景資料（PLAN.md 3.4）：因子模型的「隔夜美股」與全球傳導用。

來源：Yahoo Finance 的 chart JSON 端點（非官方，有快取與失敗降級）。
原計劃用 yfinance，但它底層的 curl_cffi 無法處理含中文的安裝路徑（憑證檔路徑），
改為直接呼叫同一個端點。這些資料只用於計算，網站上只顯示計算結果，不輸出原始序列。
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import session_scope
from pipeline.core.http import FetchError, HttpClient
from pipeline.ingest.common import mark, upsert
from pipeline.models import IndexBar

log = logging.getLogger(__name__)

SOURCE = "yahoo_chart"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
HOST_INTERVAL = {"query1.finance.yahoo.com": 2.0}

SERIES: dict[str, tuple[str, str]] = {
    "GLOBAL:SOX": ("^SOX", "費城半導體指數"),
    "GLOBAL:NASDAQ": ("^IXIC", "那斯達克綜合指數"),
    "GLOBAL:SP500": ("^GSPC", "標普 500"),
    "GLOBAL:TSM_ADR": ("TSM", "台積電 ADR"),
    "GLOBAL:USDTWD": ("TWD=X", "美元兌台幣"),
    "GLOBAL:US10Y": ("^TNX", "美國十年期公債殖利率"),
}


def parse_chart(payload: dict, index_id: str) -> list[dict]:
    res = (payload.get("chart") or {}).get("result") or []
    if not res:
        return []
    r = res[0]
    offset = int((r.get("meta") or {}).get("gmtoffset") or 0)
    ts = r.get("timestamp") or []
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows, prev = [], None
    for t, c in zip(ts, closes, strict=False):
        if c is None:
            continue
        d = datetime.fromtimestamp(t + offset, UTC).date()
        rows.append(
            {
                "index_id": index_id,
                "date": d,
                "close": float(c),
                "change": None if prev is None else float(c) - prev,
                "change_pct": None if not prev else (float(c) / prev - 1) * 100,
            }
        )
        prev = float(c)
    # 同一天可能出現兩筆（盤中快照），保留最後一筆
    dedup = {}
    for row in rows:
        dedup[row["date"]] = row
    return list(dedup.values())


def ingest_global(settings: Settings) -> None:
    start = int(datetime(COVERAGE_START.year - 1, 12, 1, tzinfo=UTC).timestamp())
    end = int(time.time())
    with HttpClient(settings.http_cache_dir, intervals=HOST_INTERVAL) as http:
        for index_id, (sym, name) in SERIES.items():
            try:
                payload = http.get_json(
                    URL.format(sym=sym), {"period1": start, "period2": end, "interval": "1d"}, use_cache=False
                )
            except FetchError as e:
                log.warning("%s（%s）抓取失敗，略過：%s", name, sym, e)
                with session_scope(settings) as s:
                    mark(s, SOURCE, index_id, "error", note=str(e)[:200])
                continue
            rows = parse_chart(payload, index_id)
            with session_scope(settings) as s:
                upsert(s, IndexBar, rows)
                mark(s, SOURCE, index_id, "ok" if rows else "empty", len(rows))
            log.info(
                "%s：%d 筆（%s ~ %s）",
                name,
                len(rows),
                rows[0]["date"] if rows else "-",
                rows[-1]["date"] if rows else "-",
            )
