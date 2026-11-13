"""櫃買中心（上櫃）：每日收盤行情、櫃買指數、公司行動、三大法人、外資持股（PLAN.md 3.1、3.2、3.5）。

端點（2026-11-13 從櫃買中心網站實測，回應存在 tests/fixtures/tpex/）皆為 POST 表單，
日期用西元 `YYYY/MM/DD`，回應 `stat` 是小寫 `ok`：

- 上櫃股票每日收盤行情   /www/zh-tw/afterTrading/otc        date, type=EW
- 櫃買指數與報酬指數（月）/www/zh-tw/indexInfo/ROE           date（該月任一天）
- 除權除息計算結果表     /www/zh-tw/bulletin/exDailyQ       startDate, endDate
- 減資恢復買賣參考價     /www/zh-tw/bulletin/revivt         startDate, endDate
- 變更面額恢復買賣參考價 /www/zh-tw/bulletin/pvChgRslt      startDate, endDate
- 三大法人買賣明細       /www/zh-tw/insti/dailyTrade        type=Daily, sect=EW, date
- 僑外資及陸資持股       /www/zh-tw/insti/qfii              date
- 上櫃股票基本資料       https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O（產業別、上櫃日、英文地址）

只收普通股（四碼代號）；上櫃的 ETF 多為債券 ETF，不在本站範圍。
深度分析（預測、事件、圖譜）的追蹤池仍是上市市值前 150 大，上櫃股票有日線、還原價、法人與大波動標記。
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import session_scope
from pipeline.core.http import FetchError, HttpClient
from pipeline.ingest.common import Progress, done_keys, last_ready_date, mark, upsert, weekdays
from pipeline.ingest.company import parse_city
from pipeline.ingest.corporate_actions import _row
from pipeline.ingest.industry import industry_name
from pipeline.ingest.parse import clean_code, clean_name, is_ok, roc_date, rows_as_dicts, to_float, to_int
from pipeline.ingest.twse_daily import classify, refresh_bar_ranges
from pipeline.models import CorporateAction, DailyBar, ForeignHolding, IndexBar, IngestLog, InstitutionalFlow, Security

log = logging.getLogger(__name__)

BASE = "https://www.tpex.org.tw/www/zh-tw"
COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
SRC_DAILY, SRC_INDEX = "tpex_otc", "tpex_roe"
SRC_FLOW, SRC_QFII = "tpex_daily_trade", "tpex_qfii"
ACTION_REPORTS = {
    "tpex_exdailyq": "bulletin/exDailyQ",
    "tpex_revivt": "bulletin/revivt",
    "tpex_pvchg": "bulletin/pvChgRslt",
}
OTC_INDEX = "TPEX:櫃買指數"
OTC_TR_INDEX = "TPEX:櫃買報酬指數"


def _ymd(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def _table(payload: dict, i: int = 0) -> tuple[list[str], list[list]]:
    tables = payload.get("tables") or []
    if len(tables) <= i:
        return [], []
    t = tables[i]
    # 欄位名稱常帶前後空白與 <br>
    fields = [str(f).replace("<br>", "").strip() for f in t.get("fields") or []]
    return fields, t.get("data") or []


def _is_stock(symbol: str, name: str) -> bool:
    return classify(symbol, name) == "stock"


# ── 每日收盤行情 ──────────────────────────────────────────────────────────


def parse_otc(payload: dict, day: date) -> tuple[list[dict], dict[str, str]]:
    fields, data = _table(payload)
    bars, names = [], {}
    for r in rows_as_dicts(fields, data):
        symbol = clean_code(r.get("代號"))
        name = clean_name(r.get("名稱"))
        if not symbol or not _is_stock(symbol, name):
            continue
        names[symbol] = name
        bars.append(
            {
                "symbol": symbol,
                "date": day,
                "open": to_float(r.get("開盤")),
                "high": to_float(r.get("最高")),
                "low": to_float(r.get("最低")),
                "close": to_float(r.get("收盤")),
                "change": to_float(r.get("漲跌")),  # 已帶正負號；除權息日等文字無法解析時為 None
                "volume": to_int(r.get("成交股數")) or 0,
                "value": to_int(r.get("成交金額(元)")) or 0,
                "trades": to_int(r.get("成交筆數")) or 0,
                "pe": None,
            }
        )
    return bars, names


def parse_roe(payload: dict) -> list[dict]:
    fields, data = _table(payload)
    out = []
    for r in data:
        if len(r) < 3:
            continue
        d = roc_date(r[0])
        for iid, v in ((OTC_INDEX, r[1]), (OTC_TR_INDEX, r[2])):
            close = to_float(v)
            if close is not None:
                out.append({"index_id": iid, "date": d, "close": close, "change": None, "change_pct": None})
    return out


def _upsert_securities(session, names: dict[str, str]) -> None:  # noqa: ANN001
    existing = {s.symbol: s for s in session.execute(select(Security)).scalars()}
    for symbol, name in names.items():
        sec = existing.get(symbol)
        if sec is None:
            session.add(Security(symbol=symbol, name=name, market="TPEx", kind="stock"))
        elif sec.market == "TPEx" and sec.name != name:
            sec.name = name


def ingest_tpex_daily(settings: Settings, start: date = COVERAGE_START, end: date | None = None) -> None:
    end = end or last_ready_date()
    with session_scope(settings) as s:
        done = done_keys(s, SRC_DAILY)
        done_idx = done_keys(s, SRC_INDEX)
    pending = [d for d in weekdays(start, end) if d.isoformat() not in done]
    months = sorted({(d.year, d.month) for d in weekdays(start, end)})
    cur = (end.year, end.month)
    pending_months = [m for m in months if f"{m[0]}-{m[1]:02d}" not in done_idx or m == cur]
    log.info("上櫃收盤行情：待抓 %d 天；櫃買指數：%d 個月", len(pending), len(pending_months))

    with HttpClient(settings.http_cache_dir) as http:
        progress = Progress("上櫃收盤行情", max(len(pending), 1), every=50)
        for day in pending:
            payload = http.get_json(
                f"{BASE}/afterTrading/otc",
                form={"date": _ymd(day), "type": "EW", "response": "json"},
                should_cache=lambda p: is_ok(p) and bool(_table(p)[1]),
            )
            with session_scope(settings) as s:
                if is_ok(payload) and _table(payload)[1]:
                    bars, names = parse_otc(payload, day)
                    _upsert_securities(s, names)
                    upsert(s, DailyBar, bars)
                    mark(s, SRC_DAILY, day.isoformat(), "ok", len(bars))
                elif is_ok(payload) or "沒有" in str(payload.get("stat", "")):
                    if day < last_ready_date():
                        mark(s, SRC_DAILY, day.isoformat(), "empty")  # 休市
                else:
                    mark(s, SRC_DAILY, day.isoformat(), "error", note=str(payload.get("stat"))[:200])
            progress.tick()

        for y, m in pending_months:
            is_cur = (y, m) == cur
            payload = http.get_json(
                f"{BASE}/indexInfo/ROE",
                form={"date": f"{y}/{m:02d}/01", "response": "json"},
                use_cache=not is_cur,
                should_cache=is_ok,
            )
            with session_scope(settings) as s:
                rows = parse_roe(payload) if is_ok(payload) else []
                upsert(s, IndexBar, rows)
                mark(s, SRC_INDEX, f"{y}-{m:02d}", "partial" if is_cur else ("ok" if rows else "empty"), len(rows))
    with session_scope(settings) as s:
        refresh_bar_ranges(s)


# ── 公司行動 ──────────────────────────────────────────────────────────────


def parse_exdailyq(payload: dict) -> list[dict]:
    """除權除息計算結果表。與證交所 TWT49U 同樣用「減除股利參考價」（見 corporate_actions.parse_twt49u）。"""
    fields, data = _table(payload)
    out = []
    for r in rows_as_dicts(fields, data):
        kind = str(r.get("權/息", "")).strip()
        prev = to_float(r.get("除權息前收盤價"))
        ex_ref = to_float(r.get("除權息參考價"))
        div_ref = to_float(r.get("減除股利參考價"))
        ref = div_ref if div_ref else ex_ref
        detail = f"權值+息值 {str(r.get('權值+息值', '')).strip()}"
        has_rights = bool(div_ref and ex_ref and div_ref - ex_ref > 0.005)
        type_ = {"除息": "dividend_cash", "除權": "dividend_stock", "除權息": "dividend_both"}.get(
            kind, {"息": "dividend_cash", "權": "dividend_stock", "權息": "dividend_both"}.get(kind, f"exright_{kind}")
        )
        affects = "權" in kind
        if has_rights:
            detail += f"；含現金增資（除權息參考價 {ex_ref}，現增部分不調整價格）"
            if prev and ref and abs(ref / prev - 1) < 0.001:
                type_, affects = "rights_issue", False
        raw = {"漲停價格": r.get("漲停價"), "跌停價格": r.get("跌停價")}
        row = _row(
            clean_code(r.get("代號")),
            roc_date(r["除權息日期"]),
            type_,
            prev,
            ref,
            affects,
            detail,
            "TPEx exDailyQ",
            raw,
        )
        if row and _is_stock(row["symbol"], ""):
            out.append(row)
    return out


def parse_revivt(payload: dict) -> list[dict]:
    fields, data = _table(payload)
    out = []
    for r in rows_as_dicts(fields, data):
        row = _row(
            clean_code(r.get("股票代號")),
            roc_date(r["恢復買賣日期"]),
            "capital_reduction",
            to_float(r.get("最後交易日之收盤價格")),
            to_float(r.get("減資恢復買賣開始日參考價格")),
            True,
            f"減資原因：{str(r.get('減資原因', '')).strip()}",
            "TPEx revivt",
            r,
        )
        if row:
            out.append(row)
    return out


def parse_pvchg(payload: dict) -> list[dict]:
    fields, data = _table(payload)
    out = []
    for r in rows_as_dicts(fields, data):
        row = _row(
            clean_code(r.get("證券代號")),
            roc_date(r["恢復買賣日期"]),
            "par_change",
            to_float(r.get("最後交易日之收盤價格")),
            to_float(r.get("恢復買賣開始參考價")),
            True,
            "變更面額",
            "TPEx pvChgRslt",
            r,
        )
        if row:
            out.append(row)
    return out


ACTION_PARSERS = {"tpex_exdailyq": parse_exdailyq, "tpex_revivt": parse_revivt, "tpex_pvchg": parse_pvchg}


def ingest_tpex_actions(settings: Settings, start: date = COVERAGE_START, end: date | None = None) -> None:
    end = end or last_ready_date()
    years = list(range(start.year, end.year + 1))
    with HttpClient(settings.http_cache_dir) as http:
        for src, path in ACTION_REPORTS.items():
            with session_scope(settings) as s:
                done = done_keys(s, src)
            for y in years:
                is_cur = y == end.year
                if str(y) in done and not is_cur:
                    continue
                payload = http.get_json(
                    f"{BASE}/{path}",
                    form={"startDate": f"{y}/01/01", "endDate": f"{y}/12/31", "response": "json"},
                    use_cache=not is_cur,
                    should_cache=is_ok,
                )
                with session_scope(settings) as s:
                    if is_ok(payload):
                        rows = ACTION_PARSERS[src](payload)
                        upsert(s, CorporateAction, rows)
                        mark(s, src, str(y), "partial" if is_cur else ("ok" if rows else "empty"), len(rows))
                        log.info("%s %d：%d 筆", path, y, len(rows))
                    else:
                        mark(s, src, str(y), "error", note=str(payload.get("stat"))[:200])
                        log.warning("%s %d 回應異常：%s", path, y, payload.get("stat"))


# ── 三大法人與外資持股 ────────────────────────────────────────────────────


def parse_daily_trade(payload: dict, day: date) -> list[dict]:
    """三大法人買賣明細。欄位名稱重複，依位置取：
    外資及陸資(不含外資自營商) 2–4、外資自營商 5–7、外資及陸資合計 8–10、投信 11–13、
    自營商(自行買賣) 14–16、自營商(避險) 17–19、自營商合計 20–22、三大法人合計 23。
    「外資」與上市一致採不含外資自營商（外資自營商已計入自營商）。
    """
    _, data = _table(payload)
    out = []
    for r in data:
        if len(r) < 24:
            continue
        symbol = clean_code(r[0])
        if not _is_stock(symbol, clean_name(r[1])):
            continue
        n = [to_int(x) or 0 for x in r]
        out.append(
            {
                "symbol": symbol,
                "date": day,
                "foreign_buy": n[2],
                "foreign_sell": n[3],
                "foreign_net": n[4],
                "trust_buy": n[11],
                "trust_sell": n[12],
                "trust_net": n[13],
                "dealer_net": n[22],
                "total_net": n[23],
            }
        )
    return out


def parse_qfii(payload: dict, day: date) -> list[dict]:
    fields, data = _table(payload)

    def col(prefix: str) -> str | None:
        return next((f for f in fields if f.startswith(prefix)), None)

    c_code, c_issued, c_held = col("代號"), col("發行股數"), col("僑外資及陸資持有股數")
    c_pct, c_limit = col("僑外資及陸資持股比率"), col("法令投資上限比率")
    out = []
    for r in rows_as_dicts(fields, data):
        symbol = clean_code(r.get(c_code))
        issued, held = to_int(r.get(c_issued)), to_int(r.get(c_held))
        pct = to_float(str(r.get(c_pct, "")).replace("%", ""))
        if not symbol or issued is None or held is None or pct is None or not _is_stock(symbol, ""):
            continue
        out.append(
            {
                "symbol": symbol,
                "date": day,
                "shares_issued": issued,
                "foreign_shares": held,
                "foreign_pct": pct,
                "limit_pct": to_float(str(r.get(c_limit, "")).replace("%", "")),
            }
        )
    return out


def ingest_tpex_flows(settings: Settings) -> None:
    from pipeline.ingest.institutional import weekly_last_days

    with session_scope(settings) as s:
        keys = s.execute(select(IngestLog.key).where(IngestLog.source == SRC_DAILY, IngestLog.status == "ok")).scalars()
        days = sorted(date.fromisoformat(k) for k in keys)
        done = {src: done_keys(s, src) for src in (SRC_FLOW, SRC_QFII)}
    days = [d for d in days if d <= last_ready_date()]
    if not days:
        log.warning("尚無上櫃交易日資料，請先執行 ingest tpex")
        return
    qfii_days = set(weekly_last_days(days))
    jobs = [(SRC_FLOW, d) for d in days if d.isoformat() not in done[SRC_FLOW]]
    jobs += [(SRC_QFII, d) for d in sorted(qfii_days) if d.isoformat() not in done[SRC_QFII]]
    jobs.sort(key=lambda j: j[1])
    log.info("上櫃法人與外資持股：待抓 %d 個請求", len(jobs))
    if not jobs:
        return
    progress = Progress("上櫃法人", len(jobs), every=50)
    failures = 0
    with HttpClient(settings.http_cache_dir) as http:
        for src, d in jobs:
            try:
                if src == SRC_FLOW:
                    form = {"type": "Daily", "sect": "EW", "date": _ymd(d), "response": "json"}
                    payload = http.get_json(f"{BASE}/insti/dailyTrade", form=form, should_cache=is_ok)
                    parser, model = parse_daily_trade, InstitutionalFlow
                else:
                    form = {"date": _ymd(d), "response": "json"}
                    payload = http.get_json(f"{BASE}/insti/qfii", form=form, should_cache=is_ok)
                    parser, model = parse_qfii, ForeignHolding
            except FetchError as e:
                failures += 1
                with session_scope(settings) as s:
                    mark(s, src, d.isoformat(), "error", note=str(e)[:200])
                log.warning("%s %s 抓取失敗（連續第 %d 次）：%s", src, d, failures, e)
                if failures >= 5:
                    raise
                progress.tick()
                continue
            failures = 0
            with session_scope(settings) as s:
                rows = parser(payload, d) if is_ok(payload) else []
                upsert(s, model, rows)
                mark(s, src, d.isoformat(), "ok" if rows else ("empty" if is_ok(payload) else "error"), len(rows))
            progress.tick()


# ── 公司基本資料 ──────────────────────────────────────────────────────────


def parse_company_otc(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for r in rows:
        symbol = clean_code(r.get("SecuritiesCompanyCode"))
        if not symbol:
            continue
        listed = str(r.get("DateOfListing") or "").strip()
        listed_on = (
            date(int(listed[:4]), int(listed[4:6]), int(listed[6:])) if len(listed) == 8 and listed.isdigit() else None
        )
        out[symbol] = {
            "industry": industry_name(r.get("SecuritiesIndustryCode")),
            "listed_on": listed_on,
            "city": parse_city(None, r.get("Address")),
        }
    return out


def ingest_tpex_company(settings: Settings) -> None:
    with HttpClient(settings.http_cache_dir) as http:
        rows = http.get_json(COMPANY_URL, use_cache=False)
    info = parse_company_otc(rows)
    n = 0
    with session_scope(settings) as s:
        for sec in s.execute(select(Security).where(Security.market == "TPEx")).scalars():
            meta = info.get(sec.symbol)
            if meta:
                sec.industry, sec.listed_on, sec.city = meta["industry"], meta["listed_on"], meta["city"]
                n += 1
        mark(s, "tpex_openapi_company", "latest", "ok", n)
    log.info("上櫃公司基本資料：%d 家，更新 %d 筆", len(info), n)


def ingest_tpex(settings: Settings) -> None:
    ingest_tpex_daily(settings)
    ingest_tpex_company(settings)
