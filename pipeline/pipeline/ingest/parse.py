"""證交所回應的共用解析工具。

證交所的 JSON 有幾個固定的坑：
- 數字是帶千分位逗號的字串，沒有成交時是 "--"、"---" 或空字串
- 漲跌符號包在 HTML 裡：<p style= color:red>+</p>
- 日期是民國年：「109年01月02日」或「109/01/20」
- 表格位置會因日期不同而變，要用標題或欄位名稱找，不能用索引
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_EMPTY = {"", "--", "---", "----", "-", "X", "x", "N/A"}
_ROC_RE = re.compile(r"^\s*(\d{2,3})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?\s*$")
_TAG_RE = re.compile(r"<[^>]+>")


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    s = _TAG_RE.sub("", str(v)).strip().replace(",", "")
    if s in _EMPTY:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_int(v: Any) -> int | None:
    f = to_float(v)
    return None if f is None else int(round(f))


def sign_of(html: Any) -> int:
    """「漲跌(+/-)」欄位：+ → 1、- → -1、其他（平盤、除權息的 X）→ 0。"""
    s = _TAG_RE.sub("", str(html or "")).strip()
    if s == "+":
        return 1
    if s == "-":
        return -1
    return 0


def roc_date(s: str) -> date:
    """「109年01月02日」、「109/01/20」、「1090120」（櫃買中心）→ date(2020, 1, 2)。"""
    m = _ROC_RE.match(str(s)) or re.fullmatch(r"\s*(\d{2,3})(\d{2})(\d{2})\s*", str(s))
    if not m:
        raise ValueError(f"無法解析民國日期：{s!r}")
    y, mo, d = (int(x) for x in m.groups())
    return date(y + 1911, mo, d)


def clean_code(s: Any) -> str:
    return str(s or "").strip()


def clean_name(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def find_table(payload: dict, *, title_contains: str) -> dict | None:
    for t in payload.get("tables") or []:
        if title_contains in (t.get("title") or ""):
            return t
    return None


def rows_as_dicts(fields: list[str], data: list[list[Any]]) -> list[dict[str, Any]]:
    return [dict(zip(fields, row, strict=False)) for row in data]


def is_ok(payload: Any) -> bool:
    # 證交所回 "OK"，櫃買中心回小寫 "ok"
    return isinstance(payload, dict) and str(payload.get("stat", "")).lower() == "ok"


def is_no_data(payload: Any) -> bool:
    """休市日或查無資料。證交所回 stat 為「很抱歉，沒有符合條件的資料!」。"""
    return isinstance(payload, dict) and "沒有符合條件的資料" in str(payload.get("stat", ""))
