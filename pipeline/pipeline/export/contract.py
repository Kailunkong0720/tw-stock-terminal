"""靜態資料契約（PLAN.md 第 8 節）。

網站讀的每一種 JSON 檔都在這裡用 Pydantic 定義；前端的 TypeScript 型別由
`python -m pipeline schema` 產生的 JSON Schema 再轉出，不要手寫兩份。

改變任何既有欄位的意義或移除欄位時，CONTRACT_VERSION 要加一。
"""

from __future__ import annotations

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


class Overview(_Model):
    """data/market/overview.json：大盤、類股表現、漲跌家數。"""

    taiex: IndexSeries
    sectors: list[SectorPerf]
    breadth: Breadth


# 產生 JSON Schema / TypeScript 型別時要包含的頂層模型
EXPORTED_MODELS: list[type[BaseModel]] = [
    Meta,
    Calendar,
    Securities,
    Bars,
    Flows,
    MarketFlows,
    IndustryFlows,
    Overview,
]
