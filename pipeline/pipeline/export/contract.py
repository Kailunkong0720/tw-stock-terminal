"""靜態資料契約（PLAN.md 第 8 節）。

網站讀的每一種 JSON 檔都在這裡用 Pydantic 定義；前端的 TypeScript 型別由
`python -m pipeline schema` 產生的 JSON Schema 再轉出，不要手寫兩份。

改變任何既有欄位的意義或移除欄位時，CONTRACT_VERSION 要加一。
"""

from __future__ import annotations

import datetime as _dt
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 1


class _Model(BaseModel):
    # 輸出時每個欄位都會寫出（包含有預設值的），所以在 schema 中標成必填，前端型別才不會多出 undefined
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class SourceHealth(_Model):
    """一個資料來源的狀態。"""

    id: str = Field(description="來源代號，例如 twse_daily")
    name: str = Field(description="顯示名稱")
    status: Literal["ok", "partial", "pending", "error"]
    last_date: date | None = Field(default=None, description="該來源最新一筆資料的日期")
    note: str | None = None


class Meta(_Model):
    """data/meta.json：網站啟動時第一個讀的檔案。"""

    contract_version: int = CONTRACT_VERSION
    generated_at: datetime = Field(description="輸出時間（含時區）")
    data_as_of: date | None = Field(description="資料截止日：最後一個有收盤資料的交易日")
    coverage_start: date = Field(description="資料起始日")
    sources: list[SourceHealth] = Field(default_factory=list)
    tracked: list[str] = Field(default_factory=list, description="追蹤池代號")
    build_notes: list[str] = Field(default_factory=list, description="建置時做的取捨，顯示在「關於」頁")


class Calendar(_Model):
    """data/calendar.json：資料期間的所有交易日（遞增）。

    其他檔案的日序列不重複寫日期，而是用 `start`（這份日曆的索引）對齊：
    陣列第 i 個值對應 `dates[start + i]`。
    """

    dates: list[date]


class SecurityInfo(_Model):
    symbol: str
    name: str
    kind: Literal["stock", "etf"]
    industry: str | None = Field(description="產業名稱；ETF 為 ETF")
    tracked: bool = Field(description="是否在追蹤池（有模型預測與事件分析）")
    first: date = Field(description="資料期間內第一個交易日")
    last: date = Field(description="資料期間內最後一個交易日")
    active: bool = Field(description="資料截止日仍有交易（未下市）")
    close: float | None = Field(description="最後一個有成交日的收盤價（原始價）")
    change_pct: float | None = Field(description="資料截止日的漲跌幅（%）；當日無成交或無法判斷時為 null")


class Securities(_Model):
    """data/securities.json：所有上市股票與 ETF（搜尋用，啟動時載入）。"""

    items: list[SecurityInfo]


class ActionInfo(_Model):
    ex_date: date
    type: str = Field(
        description="dividend_cash / dividend_stock / dividend_both / capital_reduction / par_change / "
        "etf_split / etf_reverse_split"
    )
    prev_close: float
    ref_price: float
    factor: float = Field(description="參考價 ÷ 前收。ex_date 之前每一天的價格乘以這個值即為還原價")
    affects_shares: bool = Field(description="是否改變股數（成交量也要還原）")
    detail: str | None


class Bars(_Model):
    """data/bars/{symbol}.json：原始（未還原）日線。

    陣列與 calendar.dates[start:] 對齊；沒有成交的日子價格為 null、量為 0。
    還原價由前端用 actions 計算：某日的累積因子 = 所有 ex_date 在該日之後的 factor 乘積。
    """

    symbol: str
    start: int = Field(description="第一個值在 calendar.dates 中的索引")
    open: list[float | None]
    high: list[float | None]
    low: list[float | None]
    close: list[float | None]
    volume: list[int] = Field(description="成交量（張，1 張 = 1,000 股）")
    value: list[int] = Field(description="成交金額（千元）")
    actions: list[ActionInfo]


class Flows(_Model):
    """data/flows/{symbol}.json：法人買賣超與外資持股。日序列與 calendar 對齊。"""

    symbol: str
    start: int
    foreign_net: list[int] = Field(description="外資（不含外資自營商）買賣超，張")
    trust_net: list[int] = Field(description="投信買賣超，張")
    dealer_net: list[int] = Field(description="自營商買賣超，張")
    foreign_value: list[float] = Field(description="外資買賣超估算金額（百萬元）= 股數 × 當日收盤價")
    holding_dates: list[date] = Field(description="外資持股比率的日期（每週最後一個交易日與資料截止日）")
    foreign_pct: list[float] = Field(description="外資持股比率（%）")


class MarketFlows(_Model):
    """data/flows/market.json：全市場各類法人每日買賣差額（億元，證交所實際金額）。"""

    start: int
    foreign: list[float | None]
    trust: list[float | None]
    dealer: list[float | None] = Field(description="自營商（自行買賣 + 避險）")
    total: list[float | None]


class IndustryFlowSeries(_Model):
    industry: str
    foreign_value: list[float] = Field(description="每週外資估算淨流入（億元）")


class IndustryFlows(_Model):
    """data/flows/industry.json：各產業每週的外資估算淨流入。"""

    weeks: list[date] = Field(description="每週最後一個交易日")
    industries: list[IndustryFlowSeries]


class IndexSeries(_Model):
    id: str
    name: str
    start: int
    close: list[float | None]


class SectorPerf(_Model):
    industry: str
    index_id: str
    close: float
    change_pct: float | None = Field(description="資料截止日的漲跌幅（%）")
    ret_1m: float | None = Field(description="近 21 個交易日報酬（%）")
    ret_ytd: float | None = Field(description="今年以來報酬（%）")
    ret_1y: float | None = Field(description="近 252 個交易日報酬（%）")


class Breadth(_Model):
    start: int
    up: list[int]
    down: list[int]
    flat: list[int]


class HeatItem(_Model):
    symbol: str
    name: str
    industry: str
    cap: float = Field(description="市值（億元）＝最新收盤 × 發行股數")


class Heatmap(_Model):
    """data/market/heatmap.json：市值前幾大上市股票的熱力圖。

    版面以最新市值固定，播放時只有顏色變化。ret 與 foreign 的第一維是週、第二維與 items 對齊。
    """

    as_of: date
    items: list[HeatItem]
    ret_1d: list[float | None] = Field(description="資料截止日的漲跌幅（%）")
    foreign_1d: list[float | None] = Field(description="資料截止日的外資估算買賣超（億元）")
    weeks: list[date] = Field(description="每週最後一個交易日")
    ret: list[list[float | None]] = Field(description="各週還原報酬（%）")
    foreign: list[list[float | None]] = Field(description="各週外資估算買賣超（億元）")


class Overview(_Model):
    """data/market/overview.json：大盤、類股表現、漲跌家數。"""

    taiex: IndexSeries
    sectors: list[SectorPerf]
    breadth: Breadth


class ForecastStepOut(_Model):
    step: int = Field(description="基準日之後第幾個交易日（1 起算）")
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float
    up_prob: float = Field(description="收盤高於基準日收盤的路徑比例")


class SignalOut(_Model):
    horizon: int = Field(description="交易日數：5、10、20")
    up_prob: float
    exp_ret: float = Field(description="期末報酬中位數")
    p10_ret: float = Field(description="期末報酬第 10 百分位（下檔風險）")
    mdd_p50: float = Field(description="途中最大回檔中位數（負值）")
    label: str = Field(description="偏多／略偏多／中性／略偏空／偏空")


class TrackRecord(_Model):
    """模型在回測中的方向命中率，與兩種單純基準比較。"""

    horizon: int
    n: int = Field(description="回測樣本數（不含平盤）")
    hit_rate: float | None = Field(description="方向命中率")
    baseline_rate: float | None = Field(description="較好的單純基準：一律看多數方向、或延續近 20 日趨勢")
    always_rate: float | None = Field(description="一律看多數方向的命中率")
    momentum_rate: float | None = Field(description="延續近 20 日趨勢的命中率")
    z: float | None
    has_edge: bool = Field(description="命中率明顯優於基準（單尾 p < 0.1，樣本至少 20）")


class Forecast(_Model):
    """data/forecast/{symbol}.json：最新預測。價格為基準日的還原價（＝基準日的原始收盤尺度）。"""

    symbol: str
    model: str
    base_date: date
    base_close: float
    future_dates: list[date] = Field(description="預測的各交易日（假日以平日估計）")
    steps: list[ForecastStepOut]
    paths: list[list[float]] = Field(description="各條取樣路徑的收盤價")
    signals: list[SignalOut]
    track: list[TrackRecord]


class BacktestPoint(_Model):
    base_date: date
    base_close: float = Field(description="以基準日當下已知的公司行動還原的收盤（＝當日原始收盤）")
    scale: float = Field(description="換算成目前還原價要乘上的因子（基準日之後的公司行動）")
    steps: list[ForecastStepOut]
    actual: dict[str, float | None] = Field(description="實際報酬，鍵為 5、10、20")
    exp: dict[str, float] = Field(description="模型預期報酬（中位數），鍵為 5、10、20")


class Backtest(_Model):
    """data/forecast/backtest/{symbol}.json：回測重播用。"""

    symbol: str
    model: str
    points: list[BacktestPoint]
    track: list[TrackRecord]


class RankIC(_Model):
    horizon: int
    mean: float | None = Field(description="各基準日橫斷面 Spearman 相關的平均")
    n_dates: int
    positive_share: float | None = Field(description="Rank IC 為正的基準日比例")


class RankingItem(_Model):
    symbol: str
    name: str
    industry: str | None
    base_date: date
    signals: list[SignalOut]
    track: list[TrackRecord]


class Ranking(_Model):
    """data/forecast/ranking.json：追蹤池的訊號排行與模型整體表現。"""

    model: str
    settings: dict[str, int] = Field(description="lookback、pred_len、n_paths、backtest_every、backtest_years")
    label_rules: list[str]
    items: list[RankingItem]
    pool: list[TrackRecord] = Field(description="整個追蹤池合計的命中率")
    rank_ic: list[RankIC]
    backtest_dates: list[date]


class EventOut(_Model):
    id: int
    at: datetime = Field(description="公告／發生時間（台北時間）")
    trade_date: date = Field(description="影響的交易日（盤後公告算下一個交易日）")
    level: Literal["official", "media", "market"]
    type: str
    type_name: str
    direction: int = Field(description="+1 利多、−1 利空、0 無法判斷")
    title: str
    source: str
    url: str | None


class Candidate(EventOut):
    """某個異常波動日的候選事件（可能相關，不是原因）。"""

    score: float
    components: dict[str, float] = Field(description="relevance、prior、direction、proximity、credibility")


class MoveOut(_Model):
    date: date
    ret: float = Field(description="還原後報酬")
    gap: int = Field(description="與前一個有成交日之間隔了幾個交易日")
    mkt: float | None = Field(description="大盤貢獻")
    sector: float | None = Field(description="類股（相對大盤）貢獻")
    overnight: float | None = Field(description="前一晚費半貢獻")
    idio: float | None = Field(description="個股特有")
    z: float | None
    vol_ratio: float | None = Field(description="成交量 ÷ 前 20 日均量")
    foreign_lots: int | None = Field(description="當日外資買賣超（張）")
    foreign_value: float | None = Field(description="當日外資買賣超估算金額（百萬元）")
    foreign_rank: float | None = Field(description="當日外資買賣超金額的絕對值在該股歷史中的百分位（0–1）")
    candidates: list[Candidate]


class Moves(_Model):
    """data/moves/{symbol}.json：異常波動日與可能相關的事件。"""

    symbol: str
    tracked: bool = Field(description="只有追蹤池有事件歸因")
    thresholds: dict[str, float]
    moves: list[MoveOut]


class Events(_Model):
    """data/events/{symbol}.json：個股的重大訊息（不含例行公告）。"""

    symbol: str
    events: list[EventOut]


class TimelineMove(_Model):
    symbol: str
    name: str
    date: date
    ret: float
    idio: float | None
    top: Candidate | None


class Timeline(_Model):
    """data/events/timeline.json：市場事件與追蹤池最大的異常波動。"""

    market: list[EventOut]
    moves: list[TimelineMove]


class GraphNode(_Model):
    id: str
    type: str = Field(
        description="company / industry / concept / global_company / organization / country / indicator / event / move"
    )
    name: str
    attrs: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


class GraphLink(_Model):
    source: str
    target: str
    rel: str
    rel_name: str
    confidence: float
    origin: Literal["seed", "data", "official", "market", "media", "llm"] = Field(
        description="seed：人工整理；data：由資料算出；official／market／media：事件；llm：模型從新聞抽取（虛線）"
    )
    # 欄位名稱與型別同名，型別寫成 _dt.date，否則預設值 None 會遮蔽 date 型別
    date: _dt.date | None = None
    note: str | None = None


class GraphPath(_Model):
    move: str = Field(description="異常波動節點 id")
    nodes: list[str] = Field(description="解釋路徑上的節點（依序），相鄰節點之間有連線")


class GraphCore(_Model):
    """data/graph/core.json：種子圖與由資料算出的靜態關係。"""

    nodes: list[GraphNode]
    links: list[GraphLink]


class GraphEgo(_Model):
    """data/graph/ego/{symbol}.json：以一檔股票為中心的子圖（含事件與異常波動，可依日期過濾）。"""

    center: str
    nodes: list[GraphNode]
    links: list[GraphLink]
    paths: list[GraphPath]


class PropagateItem(_Model):
    symbol: str
    name: str
    via: str = Field(description="傳導路徑的文字說明")
    rho: float | None = Field(description="與該指標的實測相關係數（近 500 個交易日）")


class GraphPropagate(_Model):
    """data/graph/propagate/{node}.json：一個全球實體或指標變動時，可能受影響的台股。"""

    node: GraphNode
    items: list[PropagateItem]


# 產生 JSON Schema / TypeScript 型別時要包含的頂層模型
EXPORTED_MODELS: list[type[BaseModel]] = [
    GraphCore,
    GraphEgo,
    GraphPropagate,
    Moves,
    Events,
    Timeline,
    Forecast,
    Backtest,
    Ranking,
    Meta,
    Calendar,
    Securities,
    Bars,
    Flows,
    MarketFlows,
    IndustryFlows,
    Overview,
    Heatmap,
]
