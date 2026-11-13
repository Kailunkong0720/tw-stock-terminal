"""知識圖譜的輸出：核心圖、個股子圖（含解釋路徑）、傳導預覽（PLAN.md 6.3、第 8 節）。"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict

import pandas as pd
from sqlalchemy import Engine

from pipeline.events.classify import TYPE_NAMES
from pipeline.export.contract import (
    GraphCore,
    GraphEgo,
    GraphLink,
    GraphNode,
    GraphPath,
    GraphPropagate,
    PropagateItem,
)
from pipeline.export.writer import ExportWriter

log = logging.getLogger(__name__)

REL_NAMES = {
    "supplies_to": "供應給",
    "competes": "競爭",
    "partners": "合作",
    "member_of": "屬於題材",
    "in_industry": "屬於產業",
    "sensitive_to": "連動",
    "influences": "影響",
    "regulates": "管制",
    "part_of": "屬於",
    "component_of": "成分股",
    "involves": "涉及",
    "may_affect": "可能相關",
    "origin": "來源",
}
MAX_PEERS = 8
MAX_MOVES = 40
TOP_CANDIDATES = 3
MARKET_SOURCE = {"market:sox": "indicator:sox", "market:taiex": "indicator:taiex"}


def _origin(source: str) -> str:
    if source == "data":
        return "data"
    if source == "llm":
        return "llm"
    return "seed"


def _safe(v):  # noqa: ANN001, ANN202
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def export_graph(engine: Engine, writer: ExportWriter, calendar_end) -> None:  # noqa: ANN001
    nodes_df = pd.read_sql_query("SELECT * FROM kg_node", engine)
    if nodes_df.empty:
        log.info("尚無知識圖譜，略過圖譜輸出")
        return
    edges_df = pd.read_sql_query("SELECT * FROM kg_edge", engine)

    nodes: dict[str, GraphNode] = {}
    for r in nodes_df.itertuples():
        attrs = {k: v for k, v in json.loads(r.attrs or "{}").items() if isinstance(v, str | int | float | bool)}
        attrs["aliases"] = "、".join(json.loads(r.aliases or "[]"))
        nodes[r.id] = GraphNode(id=r.id, type=r.type, name=r.name, attrs=attrs)

    static: list[GraphLink] = [
        GraphLink(
            source=r.src,
            target=r.dst,
            rel=r.rel,
            rel_name=REL_NAMES.get(r.rel, r.rel),
            confidence=round(float(r.confidence), 3),
            origin=_origin(r.source),
            note=_safe(r.note),
        )
        for r in edges_df.itertuples()
        if r.src in nodes and r.dst in nodes
    ]
    writer.write("graph/core.json", GraphCore(nodes=list(nodes.values()), links=static))

    out_adj: dict[str, list[GraphLink]] = defaultdict(list)
    in_adj: dict[str, list[GraphLink]] = defaultdict(list)
    for lk in static:
        out_adj[lk.source].append(lk)
        in_adj[lk.target].append(lk)

    # 市值（排序同業用）：最新收盤 × 發行股數
    cap = pd.read_sql_query(
        "SELECT h.symbol, h.shares_issued * b.close AS cap FROM foreign_holding h "
        "JOIN (SELECT symbol, MAX(date) AS d FROM foreign_holding GROUP BY symbol) m ON m.symbol = h.symbol AND m.d = h.date "
        "JOIN daily_bar b ON b.symbol = h.symbol AND b.date = h.date",
        engine,
    )
    cap_by = dict(zip(cap["symbol"], cap["cap"], strict=True))

    def company_cap(nid: str) -> float:
        return float(cap_by.get(nid.split(":", 1)[1], 0) or 0)

    # 動態：異常波動與歸因
    end = calendar_end.isoformat()
    moves = pd.read_sql_query(
        "SELECT p.symbol, p.date, p.ret, p.idio FROM price_move p JOIN security s ON s.symbol = p.symbol "
        "WHERE s.tracked AND p.anomaly AND p.date <= :end",
        engine,
        params={"end": end},
    )
    attr = pd.read_sql_query(
        "SELECT a.symbol, a.date, a.rank, a.score, e.id, e.uid, e.level, e.type, e.title, e.at, e.url, e.direction "
        "FROM attribution a JOIN event e ON e.id = a.event_id WHERE a.rank <= :k AND a.date <= :end",
        engine,
        params={"k": TOP_CANDIDATES, "end": end},
    )
    attr_by = {k: g for k, g in attr.groupby(["symbol", "date"])}

    tracked = [nid for nid, n in nodes.items() if n.type == "company" and n.attrs.get("tracked")]
    for cid in tracked:
        sym = cid.split(":", 1)[1]
        keep: set[str] = {cid}
        links: list[GraphLink] = []

        def add(lk: GraphLink, links: list[GraphLink] = links, keep: set[str] = keep) -> None:
            links.append(lk)
            keep.add(lk.source)
            keep.add(lk.target)

        for lk in out_adj[cid] + in_adj[cid]:
            add(lk)
        # 第二層：題材與產業的同業（依市值取前幾名）、海外公司連到的指標、題材／產業連到的指標
        for nid in list(keep):
            n = nodes[nid]
            if n.type in ("concept", "industry"):
                peers = sorted(
                    (lk for lk in in_adj[nid] if lk.source != cid and nodes[lk.source].type == "company"),
                    key=lambda lk: -company_cap(lk.source),
                )[:MAX_PEERS]
                for lk in peers:
                    add(lk)
                for lk in out_adj[nid]:
                    add(lk)
            elif n.type in ("global_company", "organization"):
                for lk in out_adj[nid]:
                    if nodes[lk.target].type in ("indicator", "country"):
                        add(lk)

        ego_nodes = {nid: nodes[nid] for nid in keep}
        paths: list[GraphPath] = []
        g = moves[moves["symbol"] == sym].copy()
        g["mag"] = g["idio"].abs()
        g = g.sort_values("mag", ascending=False).head(MAX_MOVES)
        for m in g.itertuples():
            mid = f"move:{sym}:{m.date}"
            ego_nodes[mid] = GraphNode(
                id=mid,
                type="move",
                name=f"{m.date} {m.ret * 100:+.1f}%",
                attrs={"date": m.date, "ret": round(m.ret, 5), "symbol": sym},
            )
            cands = attr_by.get((sym, m.date))
            if cands is None:
                continue
            for c in cands.itertuples():
                eid = f"event:{c.id}"
                if eid not in ego_nodes:
                    ego_nodes[eid] = GraphNode(
                        id=eid,
                        type="event",
                        name=c.title if len(c.title) <= 28 else c.title[:27] + "…",
                        attrs={
                            "date": str(pd.Timestamp(c.at).date()),
                            "level": c.level,
                            "type_name": TYPE_NAMES.get(c.type, c.type),
                            "title": c.title,
                            "url": _safe(c.url),
                            "direction": int(c.direction),
                        },
                    )
                links.append(
                    GraphLink(
                        source=eid,
                        target=mid,
                        rel="may_affect",
                        rel_name=REL_NAMES["may_affect"],
                        confidence=round(float(c.score), 3),
                        origin=c.level,
                        date=m.date,
                    )
                )
                if c.level == "official":
                    links.append(
                        GraphLink(
                            source=cid,
                            target=eid,
                            rel="involves",
                            rel_name="公告",
                            confidence=1.0,
                            origin="official",
                            date=m.date,
                        )
                    )
                    path = [cid, eid, mid]
                else:
                    ind = next((v for k, v in MARKET_SOURCE.items() if str(c.uid).startswith(k)), None)
                    if ind and ind in nodes:
                        ego_nodes[ind] = nodes[ind]
                        links.append(
                            GraphLink(
                                source=ind,
                                target=eid,
                                rel="origin",
                                rel_name=REL_NAMES["origin"],
                                confidence=1.0,
                                origin="market",
                                date=m.date,
                            )
                        )
                        # 若本公司與該指標有實測連動，從公司出發：公司 → 指標 → 事件 → 波動
                        linked = any(lk.source == cid and lk.target == ind for lk in links)
                        path = ([cid] if linked else []) + [ind, eid, mid]
                    else:
                        path = [eid, mid]
                if c.rank == 1:
                    paths.append(GraphPath(move=mid, nodes=path))
        # 去除重複連線
        seen, uniq = set(), []
        for lk in links:
            key = (lk.source, lk.target, lk.rel, lk.date)
            if key not in seen and lk.source in ego_nodes and lk.target in ego_nodes:
                seen.add(key)
                uniq.append(lk)
        writer.write(
            f"graph/ego/{sym}.json", GraphEgo(center=cid, nodes=list(ego_nodes.values()), links=uniq, paths=paths)
        )

    # 傳導預覽：指標、海外公司、題材、機構
    for nid, n in nodes.items():
        if n.type not in ("indicator", "global_company", "concept", "organization"):
            continue
        items: dict[str, PropagateItem] = {}

        def put(company_id: str, via: str, rho: float | None, items: dict[str, PropagateItem] = items) -> None:
            if nodes.get(company_id) is None or nodes[company_id].type != "company":
                return
            sym = company_id.split(":", 1)[1]
            old = items.get(sym)
            if old is None or (rho or 0) > (old.rho or 0):
                items[sym] = PropagateItem(symbol=sym, name=nodes[company_id].name, via=via, rho=rho)

        def rho_of(lk: GraphLink) -> float | None:
            return lk.confidence if lk.origin == "data" else None

        for lk in in_adj[nid]:
            src = nodes[lk.source]
            if src.type == "company":
                put(lk.source, f"{src.name} {lk.rel_name} {n.name}", rho_of(lk))
            elif src.type in ("industry", "concept"):
                for lk2 in in_adj[lk.source]:
                    put(
                        lk2.source,
                        f"{nodes[lk2.source].name} {lk2.rel_name} {src.name}，{src.name} {lk.rel_name} {n.name}",
                        None,
                    )
            elif src.type == "global_company" and lk.rel == "component_of":
                pass
        for lk in out_adj[nid]:
            dst = nodes[lk.target]
            if dst.type == "company":
                put(lk.target, f"{n.name} {lk.rel_name} {dst.name}", None)
            if dst.type == "indicator" and n.type == "global_company":
                for lk2 in in_adj[lk.target]:
                    if nodes[lk2.source].type == "company":
                        put(
                            lk2.source,
                            f"{n.name} 是 {dst.name} 成分股；{nodes[lk2.source].name} 與 {dst.name} 連動",
                            rho_of(lk2),
                        )
        if items:
            ranked = sorted(items.values(), key=lambda x: (-(x.rho or 0), x.symbol))
            writer.write(f"graph/propagate/{nid.replace(':', '_')}.json", GraphPropagate(node=n, items=ranked))
    log.info("圖譜輸出：核心 %d 節點、%d 關係；個股子圖 %d 檔", len(nodes), len(static), len(tracked))
