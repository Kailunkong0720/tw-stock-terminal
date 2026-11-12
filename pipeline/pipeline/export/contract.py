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


# 產生 JSON Schema / TypeScript 型別時要包含的頂層模型
EXPORTED_MODELS: list[type[BaseModel]] = [Meta]
