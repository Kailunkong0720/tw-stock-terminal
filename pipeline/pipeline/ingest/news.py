"""媒體新聞（GDELT DOC 2.0）：針對追蹤池最近三個月的大波動日查詢，一輪抓完存進資料庫。

- GDELT 只保留最近三個月，所以只查這段期間的大波動日；更早的日子只有官方公告與市場事件。
- 每個（股票, 大波動日）查一次：時間窗是前一個交易日 13:30 到當天 13:30（台北），也就是可能影響當天的消息。
- 只存標題、來源網域、連結、時間（PLAN.md 第 10 節：不轉載全文）。
- 回應存在磁碟快取，抓過的組合記在 ingest_log，重跑不會重複請求；之後每季更新只會補新的大波動日。
- GDELT 要求每 5 秒最多一次請求；被限流（429）時長時間退避。
"""

from __future__ import annotations

import bisect
import hashlib
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy.dialects.sqlite import insert

from pipeline.core.config import Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.core.http import FetchError, HttpClient
from pipeline.events.classify import classify
from pipeline.ingest.common import Progress, done_keys, mark
from pipeline.ingest.mops import effective_trade_date
from pipeline.models import Event

log = logging.getLogger(__name__)

SOURCE = "gdelt_doc"
URL = "https://api.gdeltproject.org/api/v2/doc/doc"
COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
LOOKBACK_DAYS = 88  # GDELT 只保留最近三個月，留一點餘裕
MAX_RECORDS = 75
TPE = ZoneInfo("Asia/Taipei")
UTC = ZoneInfo("UTC")
CLOSE = time(13, 30)


def query_for(name: str, name_en: str | None) -> str:
    """GDELT 的查詢字串。英文簡稱搭配台灣媒體，避免同名的外國公司。"""
    if name_en:
        return f'"{name_en}" sourcecountry:taiwan'
    return f'"{name}"'


def window(calendar: list[date], d: date) -> tuple[str, str]:
    """可能影響 d 當天的時間窗（UTC，GDELT 格式）：前一個交易日 13:30 到 d 13:30（台北）。"""
    i = bisect.bisect_left(calendar, d)
    prev = calendar[i - 1] if i > 0 else d - timedelta(days=1)
    lo = datetime.combine(prev, CLOSE, TPE).astimezone(UTC)
    hi = datetime.combine(d, CLOSE, TPE).astimezone(UTC)
    return lo.strftime("%Y%m%d%H%M%S"), hi.strftime("%Y%m%d%H%M%S")


def parse_articles(payload: dict, symbol: str, calendar: list[date]) -> list[dict]:
    rows = []
    for a in payload.get("articles") or []:
        url = a.get("url")
        title = (a.get("title") or "").strip()
        seen = a.get("seendate")  # 例如 20261106T031500Z
        if not url or not title or not seen:
            continue
        try:
            at = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(TPE)
        except ValueError:
            continue
        type_, direction = classify(title)
        rows.append(
            {
                "uid": f"gdelt:{symbol}:{hashlib.sha1(url.encode()).hexdigest()[:16]}",
                "symbol": symbol,
                "at": at.replace(tzinfo=None),
                "trade_date": effective_trade_date(at.replace(tzinfo=None), calendar),
                "level": "media",
                "type": type_,
                "direction": direction,
                "title": title[:300],
                "source": a.get("domain") or "",
                "url": url,
                "detail": None,
            }
        )
    return rows


def english_names(http: HttpClient) -> dict[str, str]:
    rows = http.get_json(COMPANY_URL)
    out = {}
    for r in rows:
        sym = str(r.get("公司代號") or "").strip()
        en = str(r.get("英文簡稱") or "").strip()
        if sym and en:
            out[sym] = en
    return out


def ingest_news(settings: Settings, today: date | None = None) -> None:
    from pipeline.core.provenance import now, save_run

    started = now()
    engine = get_engine(settings)
    cal = pd.read_sql_query("SELECT DISTINCT date FROM daily_bar ORDER BY date", engine)
    calendar = [pd.Timestamp(d).date() for d in cal["date"]]
    since = (today or date.today()) - timedelta(days=LOOKBACK_DAYS)
    days = pd.read_sql_query(
        "SELECT p.symbol, p.date, s.name FROM price_move p JOIN security s ON s.symbol = p.symbol "
        "WHERE s.tracked AND s.kind = 'stock' AND p.anomaly AND p.date >= :since ORDER BY p.date",
        engine,
        params={"since": since.isoformat()},
    )
    with session_scope(settings) as s:
        done = done_keys(s, SOURCE)
    jobs = [r for r in days.itertuples() if f"{r.symbol}:{r.date}" not in done]
    log.info("媒體新聞（GDELT）：最近三個月的大波動日 %d 個，待查 %d 個", len(days), len(jobs))
    if not jobs:
        return

    n_rows = 0
    with HttpClient(
        settings.http_cache_dir,
        intervals={"api.gdeltproject.org": 6.0},
        base_backoff=60.0,
        max_backoff=900.0,
        max_attempts=7,
    ) as http:
        names_en = english_names(http)
        prog = Progress("媒體新聞", len(jobs), every=20)
        for r in jobs:
            d = pd.Timestamp(r.date).date()
            lo, hi = window(calendar, d)
            params = {
                "query": query_for(r.name, names_en.get(r.symbol)),
                "mode": "artlist",
                "format": "json",
                "maxrecords": str(MAX_RECORDS),
                "sort": "datedesc",
                "startdatetime": lo,
                "enddatetime": hi,
            }
            key = f"{r.symbol}:{r.date}"
            try:
                payload = http.get_json(URL, params)
            except FetchError as e:
                # GDELT 對沒有結果或查詢太短的情況會回純文字；限流重試用盡時也到這裡
                msg = str(e)
                if "429" in msg or "重試" in msg:
                    log.warning("GDELT 持續限流，先停在這裡（已查 %d 個）；稍後重跑會從這裡繼續", prog.done)
                    break
                with session_scope(settings) as s:
                    mark(s, SOURCE, key, "empty", note=msg[:200])
                prog.tick()
                continue
            rows = parse_articles(payload if isinstance(payload, dict) else {}, r.symbol, calendar)
            with session_scope(settings) as s:
                for row in rows:
                    s.execute(insert(Event).values(**row).on_conflict_do_update(index_elements=["uid"], set_=row))
                mark(s, SOURCE, key, "ok" if rows else "empty", len(rows))
            n_rows += len(rows)
            prog.tick()

    save_run(
        settings,
        "news",
        started,
        since,
        calendar[-1] if calendar else None,
        {"query": query_for("名稱", "English name"), "max_records": MAX_RECORDS, "lookback_days": LOOKBACK_DAYS},
        f"查詢 {prog.done} 個大波動日，取得 {n_rows} 則新聞標題",
    )
    log.info("媒體新聞（GDELT）：查詢 %d 個大波動日，取得 %d 則新聞標題", prog.done, n_rows)
