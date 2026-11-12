"""export 步驟：把資料庫內容輸出成第 8 節定義的 JSON。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from pipeline.core.config import COVERAGE_START, Settings
from pipeline.export.contract import EXPORTED_MODELS, Meta, SourceHealth
from pipeline.export.writer import ExportWriter

log = logging.getLogger(__name__)
TPE = ZoneInfo("Asia/Taipei")


def build_meta(settings: Settings) -> Meta:
    # Phase 1 之後由各資料來源的實際狀態填入
    return Meta(
        generated_at=datetime.now(TPE).replace(microsecond=0),
        data_as_of=None,
        coverage_start=COVERAGE_START,
        sources=[
            SourceHealth(id="twse_daily", name="證交所每日收盤行情", status="pending"),
        ],
        tracked=[],
        build_notes=[],
    )


def run_export(settings: Settings) -> ExportWriter:
    writer = ExportWriter(settings.export_dir)
    writer.write("meta.json", build_meta(settings))
    total = writer.check_budget()
    log.info("輸出 %d 個檔案到 %s，總大小 %.2f MB", writer.file_count(), settings.export_dir, total / 1e6)
    return writer


def json_schema() -> dict:
    """所有頂層模型合併成一份 JSON Schema（給前端產生型別用）。"""
    defs: dict = {}
    for model in EXPORTED_MODELS:
        schema = TypeAdapter(model).json_schema(ref_template="#/$defs/{model}")
        defs.update(schema.pop("$defs", {}))
        defs[model.__name__] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Contract",
        "description": "tw-stock-terminal 靜態資料契約（由 pipeline 自動產生，請勿手改）",
        "type": "object",
        "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in EXPORTED_MODELS},
        "$defs": defs,
    }


def dump_schema(path) -> None:  # noqa: ANN001
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
