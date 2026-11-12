"""把契約模型寫成 JSON 檔，並統計大小。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from pipeline.core.config import EXPORT_BUDGET_BYTES


class OverBudget(RuntimeError):
    pass


@dataclass
class ExportWriter:
    root: Path
    written: dict[str, int] = field(default_factory=dict)

    def reset(self) -> int:
        """刪除上次輸出的 JSON（輸出目錄完全由 export 擁有），避免已下市標的的舊檔殘留。"""
        n = 0
        if self.root.exists():
            for p in self.root.rglob("*.json"):
                p.unlink()
                n += 1
        return n

    def write(self, rel_path: str, model: BaseModel) -> Path:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        text = model.model_dump_json(exclude_none=False)
        # 驗證輸出可以被讀回（避免寫出無法解析的檔案）
        json.loads(text)
        data = text.encode("utf-8")
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        self.written[rel_path] = len(data)
        return path

    def total_bytes(self) -> int:
        """整個輸出目錄的大小（不只這次寫的檔）。"""
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def file_count(self) -> int:
        return sum(1 for p in self.root.rglob("*") if p.is_file())

    def check_budget(self, budget: int = EXPORT_BUDGET_BYTES) -> int:
        total = self.total_bytes()
        if total > budget:
            raise OverBudget(f"輸出總大小 {total / 1e6:.1f} MB 超過預算 {budget / 1e6:.0f} MB")
        return total
