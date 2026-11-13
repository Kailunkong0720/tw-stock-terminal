"""建立知識圖譜（PLAN.md 6.3）。

1. 種子：kg/seed/global.yaml（人工整理的全球實體與關係）
2. 由資料產生的靜態關係：公司 → 產業；公司 → 市場指標的「實測敏感度」
   （近兩年日報酬與指標前一晚報酬的相關係數，|ρ| ≥ 0.3 才建立關係；這是資料，不是推測）
3. 動態：異常波動日（move）、可能相關的事件（event）、事件 → 公司、事件 → 波動（帶歸因分數）、
   市場事件 → 市場指標
LLM 從新聞抽取的關係（Phase 5 後段）會以 source=llm 加入，網站以虛線顯示。
"""

from __future__ import annotations

import bisect
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sqlalchemy import delete

from pipeline.core.config import Settings
from pipeline.core.db import get_engine, session_scope
from pipeline.ingest.common import upsert
from pipeline.models import KgEdge, KgNode

log = logging.getLogger(__name__)

SEED = Path(__file__).parent / "seed" / "global.yaml"
SENSITIVITY_MIN = 0.3
SENSITIVITY_DAYS = 500
MAX_MOVES_PER_STOCK = 40


def load_seed() -> dict:
    return yaml.safe_load(SEED.read_text(encoding="utf-8"))


def _overnight_returns(series: pd.Series, tw_dates: list) -> np.ndarray:  # noqa: ANN001
    s = series.dropna().sort_index()
    us = list(s.index)
    out = np.full(len(tw_dates), np.nan)
    for i, d in enumerate(tw_dates):
        j = bisect.bisect_left(us, d) - 1  # 嚴格早於台股交易日的最後一個海外交易日
        if j >= 0:
            out[i] = s.iloc[j]
    return out


def build_graph(settings: Settings) -> None:
    from pipeline.core.provenance import now

    started = now()
    engine = get_engine(settings)
    seed = load_seed()
    src_tag = seed.get("source", "seed")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(id_: str, type_: str, name: str, aliases: list[str] | None = None, attrs: dict | None = None) -> None:
        nodes[id_] = {
            "id": id_,
            "type": type_,
            "name": name,
            "aliases": json.dumps(aliases or [], ensure_ascii=False),
            "attrs": json.dumps(attrs or {}, ensure_ascii=False),
        }

    def edge(
        src: str, rel: str, dst: str, source: str, conf: float = 1.0, note: str | None = None, frm=None, to=None
    ) -> None:  # noqa: ANN001
        edges.append(
            {
                "src": src,
                "dst": dst,
                "rel": rel,
                "confidence": conf,
                "valid_from": frm,
                "valid_to": to,
                "source": source,
                "note": note,
            }
        )

    for n in seed["nodes"]:
        attrs = {k: v for k, v in n.items() if k not in ("id", "type", "name", "aliases")}
        node(n["id"], n["type"], n["name"], n.get("aliases"), attrs)

    secs = pd.read_sql_query(
        "SELECT symbol, name, industry, tracked FROM security WHERE kind IN ('stock', 'etf')", engine
    )
    seed_companies = {
        e[k].split(":", 1)[1] for e in seed["edges"] for k in ("src", "dst") if e[k].startswith("company:")
    }
    for r in secs.itertuples():
        if r.tracked or r.symbol in seed_companies:
            node(f"company:{r.symbol}", "company", r.name, [r.symbol], {"symbol": r.symbol, "tracked": bool(r.tracked)})
            if isinstance(r.industry, str) and r.industry and r.industry != "ETF":
                node(f"industry:{r.industry}", "industry", r.industry)
                edge(f"company:{r.symbol}", "in_industry", f"industry:{r.industry}", "data")

    for e in seed["edges"]:
        for k in ("src", "dst"):
            if e[k].startswith("industry:") and e[k] not in nodes:
                node(e[k], "industry", e[k].split(":", 1)[1])
        if e["src"] in nodes and e["dst"] in nodes:
            edge(e["src"], e["rel"], e["dst"], src_tag, 0.9, note=e.get("note"))
        else:
            log.warning("種子關係的節點不存在，略過：%s %s %s", e["src"], e["rel"], e["dst"])

    # ── 實測敏感度：追蹤池日報酬 vs 指標前一晚（台股本身的指標用當日）報酬 ───────────
    idx = pd.read_sql_query("SELECT index_id, date, close FROM index_bar", engine)
    idx["date"] = pd.to_datetime(idx["date"]).dt.date
    series = {iid: g.set_index("date")["close"].sort_index().pct_change() for iid, g in idx.groupby("index_id")}
    moves = pd.read_sql_query(
        "SELECT p.symbol, p.date, p.ret FROM price_move p JOIN security s ON s.symbol = p.symbol "
        "WHERE s.tracked AND p.gap = 1",
        engine,
    )
    moves["date"] = pd.to_datetime(moves["date"]).dt.date
    indicators = [n for n in seed["nodes"] if n.get("series")]
    n_sens = 0
    for sym, g in moves.groupby("symbol"):
        g = g.sort_values("date").tail(SENSITIVITY_DAYS)
        dates = list(g["date"])
        y = g["ret"].to_numpy()
        for ind in indicators:
            s = series.get(ind["series"])
            if s is None:
                continue
            x = s.reindex(dates).to_numpy() if ind["series"].startswith("TWSE:") else _overnight_returns(s, dates)
            ok = ~(np.isnan(x) | np.isnan(y))
            if ok.sum() < 120:
                continue
            rho = float(np.corrcoef(x[ok], y[ok])[0, 1])
            if abs(rho) >= SENSITIVITY_MIN and ind["id"] != "indicator:taiex":
                edge(
                    f"company:{sym}",
                    "sensitive_to",
                    ind["id"],
                    "data",
                    round(abs(rho), 3),
                    f"近 {ok.sum()} 日相關係數 {rho:+.2f}",
                )
                n_sens += 1

    with session_scope(settings) as s:
        s.execute(delete(KgEdge))
        s.execute(delete(KgNode))
        upsert(s, KgNode, list(nodes.values()))
        s.add_all([KgEdge(**e) for e in edges])
    log.info("知識圖譜：%d 個節點、%d 條靜態關係（其中實測敏感度 %d 條）", len(nodes), len(edges), n_sens)
    from pipeline.core.provenance import save_run

    window = moves.groupby("symbol")["date"].apply(lambda d: sorted(d)[-SENSITIVITY_DAYS:][0]) if len(moves) else None
    save_run(
        settings,
        "graph",
        started,
        min(window) if window is not None and len(window) else None,
        max(moves["date"]) if len(moves) else None,
        {"sensitivity_min": SENSITIVITY_MIN, "sensitivity_days": SENSITIVITY_DAYS, "seed_source": src_tag},
        f"{len(nodes)} 個節點、{len(edges)} 條關係（人工整理 {len(seed['edges'])} 條、實測連動 {n_sens} 條）",
    )
