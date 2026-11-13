"""網站「分析說明」：每一項分析的方法、參數、使用的資料期間與計算時間。

方法說明寫在這裡（單一來源），數字（期間、時間、樣本數）一律從資料庫讀，不手寫。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import Engine

from pipeline.core.config import Settings
from pipeline.export.contract import AnalysisInfo

TPE = ZoneInfo("Asia/Taipei")
UTC = ZoneInfo("UTC")


def date_range(engine: Engine, sql: str, cap: date | None = None) -> tuple[date | None, date | None]:
    with engine.connect() as c:
        lo, hi = c.exec_driver_sql(sql).one()
    lo = pd.Timestamp(lo).date() if lo else None
    hi = pd.Timestamp(hi).date() if hi else None
    if cap and hi and hi > cap:
        hi = cap
    return lo, hi


def _fmt(d: date | None) -> str:
    return d.isoformat() if d else "—"


def _last_run(engine: Engine, step: str) -> dict | None:
    df = pd.read_sql_query(
        "SELECT * FROM analysis_run WHERE step = :s ORDER BY id DESC LIMIT 1", engine, params={"s": step}
    )
    if df.empty:
        return None
    r = df.iloc[0].to_dict()
    r["params"] = json.loads(r["params"] or "{}")
    for k in ("data_from", "data_to"):
        r[k] = pd.Timestamp(r[k]).date() if r[k] else None
    r["finished_at"] = datetime.fromisoformat(r["finished_at"])
    return r


def _utc_to_tpe(v) -> datetime | None:  # noqa: ANN001
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return pd.Timestamp(v).to_pydatetime().replace(tzinfo=UTC).astimezone(TPE).replace(microsecond=0)


def model_revision(settings: Settings, repo: str) -> str | None:
    """Hugging Face 快取中實際使用的權重版本（commit）。"""
    ref = Path(settings.data_dir) / "hf" / "hub" / f"models--{repo.replace('/', '--')}" / "refs" / "main"
    try:
        return ref.read_text(encoding="utf-8").strip()[:7]
    except OSError:
        return None


def build_analyses(
    settings: Settings, engine: Engine, calendar: list[date], generated_at: datetime
) -> list[AnalysisInfo]:
    from pipeline.events.attribution import MIN_SCORE, PROXIMITY, SOX_BIG, TAIEX_BIG, WEIGHTS
    from pipeline.events.factor_model import MIN_IDIO, VOL_MIN_RET, VOL_RATIO, WINDOW, Z_THRESHOLD
    from pipeline.forecast.kronos_runner import (
        BACKTEST_EVERY,
        BACKTEST_YEARS,
        LOOKBACK,
        MODEL_NAME,
        MODEL_REPO,
        N_PATHS,
        PRED_LEN,
        TOKENIZER_REPO,
    )
    from pipeline.kg.build import SENSITIVITY_DAYS, SENSITIVITY_MIN

    if not calendar:
        return []
    end = calendar[-1]
    cal_idx = {d: i for i, d in enumerate(calendar)}
    out: list[AnalysisInfo] = []

    bars = date_range(engine, "SELECT MIN(date), MAX(date) FROM daily_bar", end)
    acts = date_range(engine, "SELECT MIN(ex_date), MAX(ex_date) FROM corporate_action", end)
    out.append(
        AnalysisInfo(
            id="adjust",
            name="還原價（除權息、減資、分割調整）",
            method=(
                "以證交所公布的參考價計算調整因子：因子 = 參考價 ÷ 前一日收盤價；某一天之前的所有價格乘上之後各次因子的累積乘積。"
                "含現金增資的除權採「減除股利參考價」，因為證交所以它作為開盤基準。"
                "還原後每一天的報酬都要通過不變量檢查（超過漲跌幅限制必須能被事件解釋），確保沒有遺漏的公司行動。"
            ),
            params=[
                "調整事件：除權息、減資、變更面額、ETF 分割與反分割",
                "不變量門檻：單日 ±10.5%（多日未交易時依天數累積），新上市前 5 個交易日不設限",
                "還原在瀏覽器端依公司行動即時計算，原始價格不改動",
            ],
            inputs=[
                f"證交所每日收盤行情（MI_INDEX）：{_fmt(bars[0])} 至 {_fmt(bars[1])}",
                f"證交所除權息、減資、變更面額、ETF 分割報表（TWT49U、TWTAUU、TWTB8U、TWTCAU）：除權日 {_fmt(acts[0])} 至 {_fmt(acts[1])}",
                "櫃買中心（上櫃）每日收盤行情與除權除息、減資、變更面額參考價（afterTrading/otc、bulletin/exDailyQ、"
                "bulletin/revivt、bulletin/pvChgRslt），規則與上市相同",
            ],
            data_from=bars[0],
            data_to=bars[1],
            run_last=generated_at,
            page="/stock/2330",
        )
    )

    flows = date_range(engine, "SELECT MIN(date), MAX(date) FROM institutional_flow", end)
    holds = date_range(engine, "SELECT MIN(date), MAX(date) FROM foreign_holding", end)
    out.append(
        AnalysisInfo(
            id="flows",
            name="外資與法人資金流向",
            method=(
                "外資採證交所定義：外資及陸資（不含外資自營商，外資自營商已計入自營商）。"
                "個股金額以買賣超股數 × 當日收盤價估算；產業流向是同產業個股估算金額的加總；"
                "外資持股比率取每週最後一個交易日。這是交易所內的買賣淨額，不是跨境資金的匯入匯出。"
            ),
            params=[
                "金額為估算值：法人實際成交價不一定是收盤價",
                "全市場數字直接採用證交所 BFI82U 的實際金額（只有上市；資金流向頁的全市場圖表不含上櫃）",
                "上櫃個股的外資同樣採不含外資自營商",
            ],
            inputs=[
                f"證交所三大法人買賣超（T86 個股、BFI82U 全市場）：{_fmt(flows[0])} 至 {_fmt(flows[1])}",
                f"證交所外資持股（MI_QFIIS）：{_fmt(holds[0])} 至 {_fmt(holds[1])}",
                "櫃買中心（上櫃）三大法人買賣明細（insti/dailyTrade）與僑外資持股（insti/qfii）",
            ],
            data_from=flows[0],
            data_to=flows[1],
            run_last=generated_at,
            summary=None if flows[1] == end else f"法人資料目前到 {_fmt(flows[1])}，之後的日期仍在回補",
            page="/flows",
        )
    )

    f = _last_run(engine, "factor")
    out.append(
        AnalysisInfo(
            id="factor",
            name="漲跌拆解與大波動日",
            method=(
                f"每檔股票每天的報酬，以前 {WINDOW} 個交易日（不含當天）的最小平方法迴歸拆成四部分："
                "大盤（上市用加權報酬指數、上櫃用櫃買報酬指數）、類股（類股報酬指數相對大盤；上櫃股票暫用上市同產業的指數）、"
                "前一晚費城半導體指數、個股特有。"
                "個股特有部分除以同一段期間的殘差標準差得到 z 分數。大盤與類股使用含息的報酬指數，避免除息日被誤判為下跌。"
            ),
            params=[
                f"迴歸視窗：{WINDOW} 個交易日（滾動，不含當天，不會用到未來資料）",
                f"大波動日：|z| ≥ {Z_THRESHOLD} 且 |個股特有報酬| ≥ {MIN_IDIO:.0%}；"
                f"或成交量 ≥ 前 20 日均量 {VOL_RATIO:g} 倍且 |報酬| ≥ {VOL_MIN_RET:.0%}",
            ],
            inputs=[
                f"還原日報酬：{_fmt(bars[0])} 至 {_fmt(bars[1])}",
                "證交所加權指數與各類股的價格指數、報酬指數",
                "Yahoo Finance 費城半導體指數日線（只用於計算）",
            ],
            data_from=f["data_from"] if f else None,
            data_to=f["data_to"] if f else None,
            run_last=f["finished_at"] if f else None,
            summary=f["summary"] if f else "尚無執行紀錄（下次執行 moves 步驟後產生）",
            page="/explain",
        )
    )

    a = _last_run(engine, "attribution")
    nw = _last_run(engine, "news")
    news = date_range(engine, "SELECT MIN(trade_date), MAX(trade_date) FROM event WHERE uid LIKE 'gdelt:%'", end)
    n_news = pd.read_sql_query("SELECT COUNT(*) AS n FROM event WHERE uid LIKE 'gdelt:%'", engine)["n"].iloc[0]
    news_line = (
        f"GDELT 媒體新聞標題：{n_news:,} 則，{_fmt(news[0])} 至 {_fmt(news[1])}（只涵蓋最近三個月）"
        if nw
        else "媒體新聞：尚未加入（使用 GDELT，只涵蓋最近三個月）"
    )
    mops = date_range(engine, "SELECT MIN(trade_date), MAX(trade_date) FROM event WHERE uid LIKE 'mops:%'", end)
    n_mops = pd.read_sql_query("SELECT COUNT(*) AS n FROM event WHERE uid LIKE 'mops:%'", engine)["n"].iloc[0]
    w = "＋".join(
        f"{v:.2f} {k}"
        for k, v in zip(
            ["相關性", "類型先驗", "方向一致", "時間接近", "來源可信度"],
            [WEIGHTS[k] for k in ("relevance", "prior", "direction", "proximity", "credibility")],
            strict=True,
        )
    )
    out.append(
        AnalysisInfo(
            id="attribution",
            name="大波動日的可能相關事件",
            method=(
                "針對追蹤池的每個大波動日，從同一天與前兩個交易日的事件中找候選："
                "公開資訊觀測站的重大訊息（依標題規則分類）、證交所的分割與減資資料、由資料產生的市場事件。"
                f"分數 = {w}；達門檻才列出，每天最多 5 個。市場事件的方向必須與當天漲跌一致。"
                "這些是「可能相關」，時間相近不代表因果；找不到就顯示未找到，不硬湊。"
            ),
            params=[
                f"門檻：{MIN_SCORE}",
                "時間接近度：" + "、".join(f"前 {k} 天 {v:g}" if k else f"當天 {v:g}" for k, v in PROXIMITY.items()),
                "類型先驗：該類事件當天的平均 |個股特有報酬| ÷ 全部日子的平均（由本站資料統計，不是人工設定）",
                f"市場事件：費半前一晚漲跌 ≥ {SOX_BIG:.0%}、加權指數當日漲跌 ≥ {TAIEX_BIG:.1%}",
                "例行性公告（股東會、董事會開會通知等）不列入",
            ],
            inputs=[
                f"公開資訊觀測站重大訊息（追蹤池 150 家）：{n_mops:,} 則，{_fmt(mops[0])} 至 {_fmt(mops[1])}",
                "證交所分割、面額變更、減資報表",
                news_line,
            ],
            data_from=a["data_from"] if a else None,
            data_to=a["data_to"] if a else None,
            run_last=a["finished_at"] if a else None,
            summary=a["summary"] if a else "尚無執行紀錄（下次執行 moves 步驟後產生）",
            page="/explain",
        )
    )
    if nw:
        out.append(
            AnalysisInfo(
                id="news",
                name="媒體新聞（GDELT）",
                method=(
                    "只針對追蹤池最近三個月的大波動日查詢 GDELT DOC 2.0："
                    "以公司英文簡稱搜尋台灣媒體，時間窗是前一個交易日 13:30 到當天 13:30（台北），也就是可能影響當天股價的消息。"
                    "只保存標題、來源網域、連結與時間，不轉載內文；標題依與重大訊息相同的規則分類，再進入事件歸因。"
                ),
                params=[
                    f"查詢：{nw['params'].get('query', '')}（以公司名稱代入）",
                    f"每次最多 {nw['params'].get('max_records', '')} 則；請求間隔 30 秒",
                    "GDELT 只保留最近三個月，所以更早的大波動日只有官方公告與市場事件",
                ],
                inputs=[news_line],
                data_from=news[0],
                data_to=news[1],
                run_last=nw["finished_at"],
                summary=nw["summary"],
                page="/explain",
            )
        )

    runs = pd.read_sql_query(
        "SELECT kind, symbol, base_date, created_at FROM forecast_run WHERE model = :m",
        engine,
        params={"m": MODEL_NAME},
    )
    runs["base_date"] = pd.to_datetime(runs["base_date"]).dt.date
    rev_m = model_revision(settings, MODEL_REPO)
    rev_t = model_revision(settings, TOKENIZER_REPO)
    model_params = [
        f"模型：{MODEL_REPO}" + (f"（權重版本 {rev_m}）" if rev_m else ""),
        f"Tokenizer：{TOKENIZER_REPO}" + (f"（版本 {rev_t}）" if rev_t else ""),
        f"輸入：基準日（含）之前 {LOOKBACK} 根還原日 K 線（開、高、低、收、量）",
        f"輸出：{N_PATHS} 條取樣路徑，各 {PRED_LEN} 個交易日；在一般電腦的 CPU 上推論",
    ]

    def lookback_start(base: date) -> date | None:
        i = cal_idx.get(base)
        return calendar[max(0, i - LOOKBACK + 1)] if i is not None else None

    latest = runs[runs["kind"] == "latest"]
    if not latest.empty:
        base = max(latest["base_date"])
        out.append(
            AnalysisInfo(
                id="forecast",
                name="K 線模型：最新預測",
                method=(
                    "Kronos（開源 K 線基礎模型，MIT 授權）的 mini 版本，未針對台股微調。"
                    "每檔股票一次取樣多條未來走勢：上漲機率 = 期末收盤高於基準日收盤的路徑比例，"
                    "預期報酬取路徑的中位數，下檔取第 10 百分位。"
                    "偏多／中性／偏空的標籤依上漲機率與預期報酬決定；回測沒有顯著優勢時以灰色顯示。"
                ),
                params=model_params + ["預測期間：5、10、20 個交易日"],
                inputs=[
                    f"還原日線：每檔基準日之前 {LOOKBACK} 個交易日（{_fmt(lookback_start(base))} 至 {_fmt(base)}）"
                ],
                data_from=lookback_start(base),
                data_to=base,
                run_first=_utc_to_tpe(latest["created_at"].min()),
                run_last=_utc_to_tpe(latest["created_at"].max()),
                summary=f"{latest['symbol'].nunique()} 檔，基準日 {_fmt(base)}",
                page="/forecast",
            )
        )

    bt = runs[runs["kind"] == "backtest"]
    if not bt.empty:
        from pipeline.forecast.kronos_runner import backtest_dates

        planned = backtest_dates(calendar)
        n_sym = latest["symbol"].nunique() if not latest.empty else bt["symbol"].nunique()
        done = len(bt)
        total = len(planned) * n_sym
        first_base, last_base = min(bt["base_date"]), max(bt["base_date"])
        j = cal_idx.get(last_base)
        realized_to = calendar[min(len(calendar) - 1, j + PRED_LEN)] if j is not None else None
        out.append(
            AnalysisInfo(
                id="backtest",
                name="K 線模型：回測",
                method=(
                    f"最近 {BACKTEST_YEARS} 年內每隔 {BACKTEST_EVERY} 個交易日取一個基準日，"
                    "每次只用基準日當天以前的資料（包含當時已知的還原因子），預測之後 5、10、20 個交易日，再與實際走勢比較。"
                    "命中率與兩種不需要模型的基準比較：一律猜多數方向、延續近 20 日趨勢；"
                    "命中率顯著高於基準（單尾 z 檢定，信心水準 90%）才算有優勢。另計算 Rank IC（預期報酬與實際報酬的等級相關）。"
                ),
                params=model_params
                + [f"基準日：{len(planned)} 個（每隔 {BACKTEST_EVERY} 個交易日），追蹤池 {n_sym} 檔"],
                inputs=[
                    f"還原日線：最早基準日之前 {LOOKBACK} 個交易日起（{_fmt(lookback_start(first_base))}），"
                    f"到最後基準日之後 {PRED_LEN} 個交易日的實際走勢（{_fmt(realized_to)}）"
                ],
                data_from=lookback_start(first_base),
                data_to=realized_to,
                run_first=_utc_to_tpe(bt["created_at"].min()),
                run_last=_utc_to_tpe(bt["created_at"].max()),
                summary=(
                    f"已完成 {done:,} / {total:,} 次（基準日 {_fmt(first_base)} 至 {_fmt(last_base)}）"
                    + ("；仍在計算中" if done < total else "")
                ),
                page="/forecast",
            )
        )

    g = _last_run(engine, "graph")
    out.append(
        AnalysisInfo(
            id="graph",
            name="知識圖譜與全球供應鏈",
            method=(
                "兩種關係：人工整理的公開、長期廣泛報導的關係（客戶、供應商、競爭、合作、題材、主管機關），"
                "以及由股價資料算出的連動：追蹤池每檔股票的日報酬與市場指標前一晚報酬（台股指標用當天）的相關係數。"
                "全球供應鏈地圖上，台股公司依證交所公司基本資料的登記地址放在所在縣市（新竹科學園區單獨一區）。"
            ),
            params=[
                f"連動視窗：每檔最近 {SENSITIVITY_DAYS} 個交易日；門檻 |相關係數| ≥ {SENSITIVITY_MIN}",
                f"人工整理的關係：{(g or {}).get('params', {}).get('seed_source', '—')}",
                "人工整理的關係不代表完整的客戶或供應商名單",
            ],
            inputs=[
                "證交所日線（追蹤池）",
                "Yahoo Finance 費城半導體指數、那斯達克、美國十年期公債殖利率、美元兌台幣日線",
                "證交所 OpenAPI 公司基本資料（登記地址）",
            ],
            data_from=g["data_from"] if g else None,
            data_to=g["data_to"] if g else None,
            run_last=g["finished_at"] if g else None,
            summary=g["summary"] if g else "尚無執行紀錄（下次執行 moves 步驟後產生）",
            page="/graph",
        )
    )

    glob = date_range(engine, "SELECT MIN(date), MAX(date) FROM index_bar WHERE index_id = 'GLOBAL:SOX'", end)
    out.append(
        AnalysisInfo(
            id="overnight",
            name="隔夜傳導（美股前一晚 → 台股當天）",
            method=(
                "把美股每個交易日的變動對齊到下一個台股交易日：台股第 t 天受到「前一個台股交易日（含，因為美股收盤在台股收盤之後）"
                "到第 t 天之前」的美股交易日影響，連假期間的多日變動累積計算。"
                "β 與相關係數用截至所選日期的最近 250 個交易日，在瀏覽器即時計算。"
            ),
            params=[
                "序列：費城半導體指數、台積電 ADR、那斯達克、標普 500（報酬率）；美國十年期公債殖利率（基點）",
                "不含美元兌台幣：新台幣匯率主要在台北時段決定，不是前一晚的訊號",
                "弧線粗細與流速依變動大小，以各序列自身的標準差衡量",
            ],
            inputs=[
                f"Yahoo Finance 日線：{_fmt(glob[0])} 至 {_fmt(glob[1])}",
                "證交所加權指數、台積電還原日報酬",
            ],
            data_from=max(glob[0], calendar[0]) if glob[0] else None,
            data_to=glob[1],
            run_last=generated_at,
            page="/globe",
        )
    )
    return out


__all__ = ["build_analyses", "date_range", "model_revision"]
