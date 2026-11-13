"""命令列進入點：python -m pipeline <指令>

build     從頭跑完整個管線（可中斷續跑；已完成的部分自動跳過）
refresh   只補上次之後的新資料
ingest    只執行指定的抓取步驟，例如 ingest daily
export    把資料庫輸出成 site/public/data/ 下的 JSON
publish   把輸出的 JSON 推到 data 分支並觸發部署
status    顯示正在執行的步驟與資料狀態
migrate   把資料庫升級到最新結構
schema    產生前端用的 JSON Schema
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from pipeline.core.config import REPO_ROOT, Settings, get_settings
from pipeline.core.locks import AlreadyRunning, list_locks, step_lock

log = logging.getLogger("pipeline")

# 管線步驟依序執行。Phase 1 之後在這裡加入 ingest、forecast 等步驟。
Step = Callable[[Settings], None]


def _step_migrate(s: Settings) -> None:
    from pipeline.core.db import migrate

    migrate(s)


def _step_export(s: Settings) -> None:
    from pipeline.export.run import run_export

    run_export(s)


def _step_daily(s: Settings) -> None:
    from pipeline.ingest.twse_daily import ingest_daily

    ingest_daily(s)


def _step_actions(s: Settings) -> None:
    from pipeline.ingest.corporate_actions import ingest_corporate_actions

    ingest_corporate_actions(s)


def _step_company(s: Settings) -> None:
    from pipeline.ingest.company import ingest_company

    ingest_company(s)


def _step_flows(s: Settings) -> None:
    from pipeline.ingest.institutional import ingest_institutional

    ingest_institutional(s)


def _step_global(s: Settings) -> None:
    from pipeline.ingest.global_markets import ingest_global

    ingest_global(s)


def _step_mops(s: Settings) -> None:
    from pipeline.ingest.mops import ingest_mops

    ingest_mops(s)


def _step_news(s: Settings) -> None:
    from pipeline.ingest.news import ingest_news

    ingest_news(s)


def _step_moves(s: Settings) -> None:
    from pipeline.events.attribution import attribute
    from pipeline.events.factor_model import compute_moves
    from pipeline.kg.build import build_graph

    compute_moves(s)
    attribute(s)
    build_graph(s)


def _step_attribution(s: Settings) -> None:
    from pipeline.events.attribution import attribute

    attribute(s)


# 會對外發請求的步驟，依序執行。
INGEST_STEPS: dict[str, Step] = {
    "daily": _step_daily,
    "actions": _step_actions,
    "company": _step_company,
    "flows": _step_flows,
    "global": _step_global,
    "mops": _step_mops,
    # 媒體新聞要用到大波動日（moves），所以 build/refresh 的順序裡排在 moves 之後（見 BUILD_STEPS）
    "news": _step_news,
}

# 每個步驟執行時持有的鎖。「net」保證同一時間只有一個程序在對證交所發請求
# （兩個程序各自限速 3 秒，合起來就變成 1.5 秒，等於違反限速）；其他主機各自一把；
# 吃 CPU 的模型推論用「cpu」。
STEP_LOCKS: dict[str, str] = {
    "daily": "net",
    "actions": "net",
    "company": "net",
    "flows": "net",
    "global": "net-yahoo",
    "mops": "net-mops",
    "news": "net-gdelt",
    "forecast": "cpu",
}


def _step_forecast(s: Settings) -> None:
    from pipeline.forecast.kronos_runner import run_latest

    run_latest(s)


BUILD_STEPS: list[tuple[str, Step]] = [
    ("migrate", _step_migrate),
    *((k, v) for k, v in INGEST_STEPS.items() if k != "news"),
    ("moves", _step_moves),
    # 新聞查的是大波動日，所以在 moves 之後；查完再重算一次歸因，讓新聞進入候選事件
    ("news", _step_news),
    ("attribution", _step_attribution),
    ("forecast", _step_forecast),
    ("export", _step_export),
]
REFRESH_STEPS: list[tuple[str, Step]] = BUILD_STEPS


def _setup_logging(settings: Settings, verbose: bool) -> None:
    settings.ensure_dirs()
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    file = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    file.setFormatter(fmt)
    root.handlers[:] = [console, file]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)
    for noisy in ("httpx2", "huggingface_hub", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _run_steps(settings: Settings, name: str, steps: list[tuple[str, Step]]) -> None:
    from contextlib import nullcontext

    with step_lock(settings.run_dir, name):
        for step_name, fn in steps:
            lock = STEP_LOCKS.get(step_name)
            log.info("── %s", step_name)
            with step_lock(settings.run_dir, lock) if lock else nullcontext():
                fn(settings)


def cmd_status(settings: Settings) -> None:
    import json

    print("執行中的步驟：")
    locks = list_locks(settings.run_dir)
    if not locks:
        print("  （無）")
    for lk in locks:
        state = "執行中" if lk["alive"] else "已結束（殘留鎖檔）"
        print(f"  {lk['step']}: PID {lk['pid']}，開始於 {lk['started_at']}，{state}")

    print(f"\n資料庫：{settings.db_path}")
    if settings.db_path.exists():
        from sqlalchemy import text

        from pipeline.core.db import get_engine

        with get_engine(settings).connect() as conn:
            tables = (
                conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
                )
                .scalars()
                .all()
            )
            for t in tables:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one()
                print(f"  {t}: {n:,} 列")
            if "ingest_log" in tables:
                rows = conn.execute(
                    text(
                        "SELECT source, status, COUNT(*), MAX(key) FROM ingest_log "
                        "GROUP BY source, status ORDER BY source, status"
                    )
                ).all()
                if rows:
                    print("\n抓取紀錄：")
                    for src, st, n, last in rows:
                        print(f"  {src} [{st}] {n:,} 筆，最新鍵 {last}")
    else:
        print("  （尚未建立）")

    meta = settings.export_dir / "meta.json"
    print(f"\n輸出：{settings.export_dir}")
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        print(f"  資料截至 {m.get('data_as_of')}，產生於 {m.get('generated_at')}")
    else:
        print("  （尚未輸出）")


def cmd_check(settings: Settings) -> int:
    """資料品質不變量：還原後日報酬超過 ±10.5% 的普通股（PLAN.md 3.2）。"""
    from pipeline.analytics.checks import find_violations
    from pipeline.core.config import COVERAGE_START
    from pipeline.core.db import get_engine

    vs = find_violations(get_engine(settings), COVERAGE_START)
    unexplained = [v for v in vs if v.reason is None]
    explained = [v for v in vs if v.reason is not None]
    print(f"還原後日報酬超過 ±10.5%：共 {len(vs)} 筆；已知例外 {len(explained)} 筆；無法解釋 {len(unexplained)} 筆")
    for v in explained[:20]:
        print(f"  [例外] {v.symbol} {v.prev_date}→{v.date} 還原 {v.ret:+.1%}（原始 {v.raw_ret:+.1%}）：{v.reason}")
    if len(explained) > 20:
        print(f"  …另有 {len(explained) - 20} 筆已知例外")
    for v in unexplained:
        print(f"  [待查] {v.symbol} {v.prev_date}→{v.date} 還原 {v.ret:+.1%}（原始 {v.raw_ret:+.1%}）")
    return 1 if unexplained else 0


def main(argv: list[str] | None = None) -> int:
    # Windows 的主控台預設編碼可能不是 UTF-8，中文輸出會出錯
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="python -m pipeline", description="台股終端資料管線")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="從頭跑完整個管線（可續跑）")
    sub.add_parser("refresh", help="只補新資料")
    sub.add_parser("export", help="輸出 JSON")
    p_pub = sub.add_parser("publish", help="推送 data 分支並觸發部署")
    p_pub.add_argument("--no-push", action="store_true", help="只在本機建立 data 分支的 commit")
    p_pub.add_argument("--no-deploy", action="store_true", help="推送後不觸發部署")
    p_ing = sub.add_parser("ingest", help="只執行指定的抓取步驟（可續跑）")
    p_ing.add_argument("steps", nargs="+", choices=sorted(INGEST_STEPS), help="步驟名稱")
    p_fc = sub.add_parser("forecast", help="Kronos 最新預測（追蹤池）")
    p_fc.add_argument("symbols", nargs="*", help="只跑指定代號（預設：追蹤池）")
    p_bt = sub.add_parser("backtest", help="Kronos 滾動回測（可續跑，耗時數小時）")
    p_bt.add_argument("symbols", nargs="*", help="只跑指定代號（預設：追蹤池）")
    sub.add_parser("moves", help="因子拆解與異常波動日偵測")
    sub.add_parser("status", help="顯示狀態")
    sub.add_parser("check", help="資料品質檢查（還原後漲跌幅不變量）")
    sub.add_parser("migrate", help="升級資料庫結構")
    p_schema = sub.add_parser("schema", help="產生前端用的 JSON Schema")
    p_schema.add_argument("--out", type=Path, default=REPO_ROOT / "site" / "src" / "lib" / "contract" / "schema.json")
    args = parser.parse_args(argv)

    settings = get_settings()
    _setup_logging(settings, args.verbose)

    # 長時間的指令執行期間避免系統閒置睡眠（只在本程序執行期間有效）
    from contextlib import nullcontext

    from pipeline.core.power import keep_awake

    long_running = args.cmd in ("build", "refresh", "ingest", "forecast", "backtest", "moves", "export")
    with keep_awake() if long_running else nullcontext():
        return _dispatch(args, settings)


def _dispatch(args: argparse.Namespace, settings: Settings) -> int:
    try:
        if args.cmd == "build":
            _run_steps(settings, "build", BUILD_STEPS)
        elif args.cmd == "refresh":
            _run_steps(settings, "refresh", REFRESH_STEPS)
        elif args.cmd == "ingest":
            _step_migrate(settings)
            _run_steps(settings, "ingest-" + "-".join(args.steps), [(n, INGEST_STEPS[n]) for n in args.steps])
        elif args.cmd == "export":
            with step_lock(settings.run_dir, "export"):
                _step_export(settings)
        elif args.cmd == "publish":
            from pipeline.publish import publish

            publish(settings, push=not args.no_push, trigger_deploy=not args.no_deploy)
        elif args.cmd in ("forecast", "backtest"):
            from pipeline.core.db import migrate
            from pipeline.forecast.kronos_runner import run_backtest, run_latest

            migrate(settings)
            # 模型推論吃 CPU，不碰網路（權重第一次下載後就有快取）：用 cpu 鎖，可與 net 回補同時進行
            with step_lock(settings.run_dir, "cpu"):
                (run_latest if args.cmd == "forecast" else run_backtest)(settings, args.symbols or None)
        elif args.cmd == "moves":
            _step_migrate(settings)
            with step_lock(settings.run_dir, "moves"):
                _step_moves(settings)
        elif args.cmd == "status":
            cmd_status(settings)
        elif args.cmd == "check":
            return cmd_check(settings)
        elif args.cmd == "migrate":
            _step_migrate(settings)
        elif args.cmd == "schema":
            from pipeline.export.run import dump_schema

            dump_schema(args.out)
            log.info("已寫入 %s", args.out)
    except AlreadyRunning as e:
        log.error("%s", e)
        return 3
    except KeyboardInterrupt:
        log.warning("已中斷。重新執行同一指令會從中斷處繼續。")
        return 130
    return 0
