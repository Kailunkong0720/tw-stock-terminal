"""export 步驟：把資料庫內容輸出成第 8 節定義的 JSON。"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter
from sqlalchemy import func, select

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.export.contract import CONTRACT_VERSION, EXPORTED_MODELS, Meta, SourceHealth
from pipeline.export.writer import ExportWriter
from pipeline.models import DailyBar, Security

log = logging.getLogger(__name__)
TPE = ZoneInfo("Asia/Taipei")

# 對外顯示的資料來源（多個抓取來源可合併成一個顯示項目）
DISPLAY_SOURCES: list[tuple[str, str, list[str]]] = [
    ("twse_daily", "每日收盤行情", ["twse_mi_index"]),
    ("twse_institutional", "三大法人買賣超", ["twse_t86", "twse_bfi82u"]),
    ("twse_foreign_holding", "外資持股", ["twse_mi_qfiis"]),
    ("twse_corporate_actions", "除權息與分割", ["twse_twt49u", "twse_twtauu", "twse_twtb8u", "twse_twtcau"]),
    ("twse_company", "公司基本資料", ["twse_openapi_company"]),
]

BUILD_NOTES = [
    "價格為證交所公布的原始價；還原價依除權息、減資、變更面額、ETF 分割的參考價計算。",
    "「外資」採證交所定義：外資及陸資（不含外資自營商）。外資自營商已計入自營商。",
    "外資買賣超金額為估算值：買賣超股數 × 當日收盤價。法人實際成交價不一定是收盤價。",
    "外資買賣超是交易所內的買賣淨額，不是跨境資金的匯入匯出；也包含透過境外帳戶下單的本國資金。",
    "外資持股比率取每週最後一個交易日與資料截止日。",
    "追蹤池：資料截止日市值前 150 大的上市普通股，加上 0050、0056、00878、006208。",
]


def build_meta(settings: Settings) -> Meta:
    from pipeline.export.market import source_status

    engine = get_engine(settings)
    with session_scope(settings) as s:
        as_of = s.execute(select(func.max(DailyBar.date))).scalar_one_or_none()
        tracked = sorted(s.execute(select(Security.symbol).where(Security.tracked.is_(True))).scalars())

    status = source_status(engine) if as_of else {}
    sources = []
    for sid, name, parts in DISPLAY_SOURCES:
        got = [status[p] for p in parts if p in status]
        if not got:
            sources.append(SourceHealth(id=sid, name=name, status="pending"))
            continue
        n_err = sum(g[2] for g in got)
        dates = [g[0] for g in got if g[0] and len(g[0]) == 10]
        sources.append(
            SourceHealth(
                id=sid,
                name=name,
                status="partial" if n_err or len(got) < len(parts) else "ok",
                last_date=date.fromisoformat(max(dates)) if dates else None,
                note=f"{n_err} 筆抓取失敗待重試" if n_err else None,
            )
        )

    return Meta(
        generated_at=datetime.now(TPE).replace(microsecond=0),
        data_as_of=as_of,
        coverage_start=COVERAGE_START,
        sources=sources,
        tracked=tracked,
        build_notes=BUILD_NOTES if as_of else [],
    )


def run_export(settings: Settings) -> ExportWriter:
    from pipeline.core.db import migrate
    from pipeline.export.market import MarketExporter

    migrate(settings)
    writer = ExportWriter(settings.export_dir)
    MarketExporter(get_engine(settings), writer).run()
    writer.write("meta.json", build_meta(settings))
    total = writer.check_budget()
    log.info("輸出 %d 個檔案到 %s，總大小 %.1f MB", writer.file_count(), settings.export_dir, total / 1e6)
    return writer


def _strip_property_titles(node: object) -> None:
    """拿掉欄位層級的 title，避免 json2ts 為每個欄位產生一個型別別名。模型層級的 title 保留。"""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for prop in props.values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        for v in node.values():
            _strip_property_titles(v)
    elif isinstance(node, list):
        for v in node:
            _strip_property_titles(v)


def json_schema() -> dict:
    """所有頂層模型合併成一份 JSON Schema（給前端產生型別用）。"""
    defs: dict = {}
    for model in EXPORTED_MODELS:
        schema = TypeAdapter(model).json_schema(ref_template="#/$defs/{model}", mode="serialization")
        defs.update(schema.pop("$defs", {}))
        defs[model.__name__] = schema
    _strip_property_titles(defs)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Contract",
        "description": "tw-stock-terminal 靜態資料契約（由 pipeline 自動產生，請勿手改）",
        "x-contract-version": CONTRACT_VERSION,
        "type": "object",
        "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in EXPORTED_MODELS},
        "additionalProperties": False,
        "$defs": defs,
    }


def dump_schema(path) -> None:  # noqa: ANN001
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n"：Windows 上不轉成 CRLF，否則與 CI（Linux）產生的檔案不一致
    path.write_text(json.dumps(json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
