"""外資與三大法人資金流向（PLAN.md 3.5）。

- T86      三大法人買賣超日報：每一檔股票，每個交易日
- BFI82U   三大法人買賣金額統計：全市場，每個交易日
- MI_QFIIS 外資及陸資投資持股：每一檔股票。持股比率變化慢，只抓每週最後一個交易日與最新一天
           （約省下 1,300 個請求；見 meta.json 的 build_notes）

都依「已抓到收盤行情的交易日」來排程，不會對休市日發請求。
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from pipeline.core.config import Settings
from pipeline.core.db import session_scope
from pipeline.core.http import FetchError, HttpClient
from pipeline.ingest.common import Progress, done_keys, last_ready_date, mark, upsert
from pipeline.ingest.parse import clean_code, is_no_data, is_ok, rows_as_dicts, to_float, to_int
from pipeline.ingest.twse_daily import SOURCE as DAILY_SOURCE
from pipeline.models import ForeignHolding, IngestLog, InstitutionalFlow, MarketFlow

log = logging.getLogger(__name__)

BASE = "https://www.twse.com.tw/rwd/zh/fund"
SRC_T86, SRC_BFI, SRC_QFII = "twse_t86", "twse_bfi82u", "twse_mi_qfiis"

INVESTOR_IDS = {
    "自營商(自行買賣)": "dealer_self",
    "自營商(避險)": "dealer_hedge",
    "投信": "trust",
    "外資及陸資(不含外資自營商)": "foreign",
    "外資自營商": "foreign_dealer",
    "合計": "total",
}


def _g(r: dict, *names: str) -> int:
    """依欄位名稱取整數；不同年份的欄位名稱可能略有不同，依序嘗試。"""
    for n in names:
        if n in r:
            return to_int(r[n]) or 0
    return 0


def parse_t86(payload: dict, day: date) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        symbol = clean_code(r.get("證券代號"))
        if not symbol:
            continue
        # 「外資」採證交所的定義：外資及陸資（不含外資自營商）。
        # 證交所註記：外資自營商的買賣已計入自營商，加進外資會重複計算。
        fb = _g(r, "外陸資買進股數(不含外資自營商)", "外資買進股數")
        fs = _g(r, "外陸資賣出股數(不含外資自營商)", "外資賣出股數")
        fn = _g(r, "外陸資買賣超股數(不含外資自營商)", "外資買賣超股數")
        out.append(
            {
                "symbol": symbol,
                "date": day,
                "foreign_buy": fb,
                "foreign_sell": fs,
                "foreign_net": fn,
                "trust_buy": _g(r, "投信買進股數"),
                "trust_sell": _g(r, "投信賣出股數"),
                "trust_net": _g(r, "投信買賣超股數"),
                "dealer_net": _g(r, "自營商買賣超股數"),
                "total_net": _g(r, "三大法人買賣超股數"),
            }
        )
    return out


def parse_bfi82u(payload: dict, day: date) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        inv = INVESTOR_IDS.get(str(r.get("單位名稱", "")).strip())
        if not inv:
            continue
        out.append(
            {
                "date": day,
                "investor": inv,
                "buy": to_int(r.get("買進金額")) or 0,
                "sell": to_int(r.get("賣出金額")) or 0,
                "net": to_int(r.get("買賣差額")) or 0,
            }
        )
    return out


def parse_mi_qfiis(payload: dict, day: date) -> list[dict]:
    out = []
    for r in rows_as_dicts(payload.get("fields") or [], payload.get("data") or []):
        symbol = clean_code(r.get("證券代號"))
        issued = to_int(r.get("發行股數"))
        held = to_int(r.get("全體外資及陸資持有股數"))
        pct = to_float(r.get("全體外資及陸資持股比率"))
        if not symbol or issued is None or held is None or pct is None:
            continue
        out.append(
            {
                "symbol": symbol,
                "date": day,
                "shares_issued": issued,
                "foreign_shares": held,
                "foreign_pct": pct,
                "limit_pct": to_float(r.get("外資及陸資共用法令投資上限比率")),
            }
        )
    return out


def weekly_last_days(days: list[date]) -> list[date]:
    """每個 ISO 週的最後一個交易日，再加上整體最後一天。"""
    by_week: dict[tuple[int, int], date] = {}
    for d in sorted(days):
        by_week[d.isocalendar()[:2]] = d
    out = sorted(set(by_week.values()))
    if days and max(days) not in out:
        out.append(max(days))
    return out


def trading_days(settings: Settings) -> list[date]:
    with session_scope(settings) as s:
        keys = s.execute(
            select(IngestLog.key).where(IngestLog.source == DAILY_SOURCE, IngestLog.status == "ok")
        ).scalars()
        return sorted(date.fromisoformat(k) for k in keys)


def _fetch(http: HttpClient, path: str, params: dict) -> dict:
    return http.get_json(f"{BASE}/{path}", {**params, "response": "json"}, should_cache=is_ok)


def ingest_institutional(settings: Settings) -> None:
    days = [d for d in trading_days(settings) if d <= last_ready_date()]
    if not days:
        log.warning("尚無交易日資料，請先執行 ingest daily")
        return
    qfii_days = set(weekly_last_days(days))
    with session_scope(settings) as s:
        done = {src: done_keys(s, src) for src in (SRC_T86, SRC_BFI, SRC_QFII)}

    jobs: list[tuple[str, date]] = []
    for d in days:
        k = d.isoformat()
        if k not in done[SRC_T86]:
            jobs.append((SRC_T86, d))
        if k not in done[SRC_BFI]:
            jobs.append((SRC_BFI, d))
        if d in qfii_days and k not in done[SRC_QFII]:
            jobs.append((SRC_QFII, d))
    if not jobs:
        log.info("法人資金流向：已是最新")
        return
    log.info("法人資金流向：待抓 %d 個請求（%s ~ %s）", len(jobs), jobs[0][1], jobs[-1][1])

    progress = Progress("法人資金流向", len(jobs), every=50)
    failures = 0
    with HttpClient(settings.http_cache_dir) as http:
        for src, d in jobs:
            ymd = d.strftime("%Y%m%d")
            try:
                if src == SRC_T86:
                    payload, parser, model = (
                        _fetch(http, "T86", {"date": ymd, "selectType": "ALLBUT0999"}),
                        parse_t86,
                        InstitutionalFlow,
                    )
                elif src == SRC_BFI:
                    payload, parser, model = (
                        _fetch(http, "BFI82U", {"type": "day", "dayDate": ymd}),
                        parse_bfi82u,
                        MarketFlow,
                    )
                else:
                    payload, parser, model = (
                        _fetch(http, "MI_QFIIS", {"date": ymd, "selectType": "ALLBUT0999"}),
                        parse_mi_qfiis,
                        ForeignHolding,
                    )
            except FetchError as e:
                # 單筆失敗不中斷整個回補；記為 error，下次執行會重試。連續失敗太多代表網路或來源有問題，停下來
                failures += 1
                with session_scope(settings) as s:
                    mark(s, src, d.isoformat(), "error", note=str(e)[:200])
                log.warning("%s %s 抓取失敗（連續第 %d 次），略過：%s", src, d, failures, e)
                if failures >= 5:
                    raise
                progress.tick()
                continue
            failures = 0
            with session_scope(settings) as s:
                if is_ok(payload):
                    rows = parser(payload, d)
                    upsert(s, model, rows)
                    mark(s, src, d.isoformat(), "ok", len(rows))
                elif is_no_data(payload):
                    mark(s, src, d.isoformat(), "empty")
                else:
                    mark(s, src, d.isoformat(), "error", note=str(payload.get("stat"))[:200])
                    log.warning("%s %s 回應異常：%s", src, d, payload.get("stat"))
            progress.tick()
