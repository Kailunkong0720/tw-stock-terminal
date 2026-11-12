"""行情、指數、公司行動、法人資金流向（PLAN.md 第 4 節）。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models.base import Base


class Security(Base):
    __tablename__ = "security"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    market: Mapped[str] = mapped_column(String(8), default="TWSE")  # TWSE（上市）/ TPEx（上櫃）
    # stock：普通股；etf；etn；preferred：特別股；tdr：存託憑證；other
    kind: Mapped[str] = mapped_column(String(16))
    industry: Mapped[str | None] = mapped_column(String(32), nullable=True)
    listed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_bar: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_bar: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracked: Mapped[bool] = mapped_column(Boolean, default=False)


class DailyBar(Base):
    """原始（未還原）日線。沒有成交的日子 OHLC 為 NULL。"""

    __tablename__ = "daily_bar"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)  # 漲跌價差（帶正負號）
    volume: Mapped[int] = mapped_column(Integer, default=0)  # 成交股數
    value: Mapped[int] = mapped_column(Integer, default=0)  # 成交金額（元）
    trades: Mapped[int] = mapped_column(Integer, default=0)  # 成交筆數
    pe: Mapped[float | None] = mapped_column(Float, nullable=True)


class IndexBar(Base):
    """指數收盤（大盤、類股、全球市場、匯率）。"""

    __tablename__ = "index_bar"

    index_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)


class CorporateAction(Base):
    """會讓價格出現非交易性跳動的事件。調整因子 = 參考價 ÷ 前收。"""

    __tablename__ = "corporate_action"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    ex_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # dividend_cash / dividend_stock / dividend_both / capital_reduction / par_change / etf_split / etf_reverse_split
    type: Mapped[str] = mapped_column(String(24), primary_key=True)
    prev_close: Mapped[float] = mapped_column(Float)
    ref_price: Mapped[float] = mapped_column(Float)
    factor: Mapped[float] = mapped_column(Float)
    affects_shares: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    # 該日的漲跌停價（報表提供）。含現增的除權日漲跌停不對稱，資料品質檢查用這兩個值
    limit_up: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_down: Mapped[float | None] = mapped_column(Float, nullable=True)


class InstitutionalFlow(Base):
    """三大法人買賣超（T86），單位：股。估算金額在輸出時用收盤價計算。"""

    __tablename__ = "institutional_flow"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    foreign_buy: Mapped[int] = mapped_column(Integer, default=0)  # 外資及陸資（不含外資自營商），證交所的定義
    foreign_sell: Mapped[int] = mapped_column(Integer, default=0)
    foreign_net: Mapped[int] = mapped_column(Integer, default=0)
    trust_buy: Mapped[int] = mapped_column(Integer, default=0)
    trust_sell: Mapped[int] = mapped_column(Integer, default=0)
    trust_net: Mapped[int] = mapped_column(Integer, default=0)
    dealer_net: Mapped[int] = mapped_column(Integer, default=0)
    total_net: Mapped[int] = mapped_column(Integer, default=0)


class MarketFlow(Base):
    """全市場各類法人買賣金額（BFI82U），單位：元。"""

    __tablename__ = "market_flow"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    investor: Mapped[str] = mapped_column(
        String(16), primary_key=True
    )  # foreign / foreign_dealer / trust / dealer_self / dealer_hedge / total
    buy: Mapped[int] = mapped_column(Integer)
    sell: Mapped[int] = mapped_column(Integer)
    net: Mapped[int] = mapped_column(Integer)


class ForeignHolding(Base):
    """外資及陸資持股（MI_QFIIS）。"""

    __tablename__ = "foreign_holding"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    shares_issued: Mapped[int] = mapped_column(Integer)
    foreign_shares: Mapped[int] = mapped_column(Integer)
    foreign_pct: Mapped[float] = mapped_column(Float)
    limit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
