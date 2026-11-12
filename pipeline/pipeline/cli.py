"""命令列進入點：python -m pipeline <指令>

build     從頭跑完整個管線（可中斷續跑；已完成的部分自動跳過）
refresh   只補上次之後的新資料
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


BUILD_STEPS: list[tuple[str, Step]] = [
    ("migrate", _step_migrate),
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


def _run_steps(settings: Settings, name: str, steps: list[tuple[str, Step]]) -> None:
    with step_lock(settings.run_dir, name):
        for step_name, fn in steps:
            log.info("── %s", step_name)
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
    sub.add_parser("status", help="顯示狀態")
    sub.add_parser("migrate", help="升級資料庫結構")
    p_schema = sub.add_parser("schema", help="產生前端用的 JSON Schema")
    p_schema.add_argument("--out", type=Path, default=REPO_ROOT / "site" / "src" / "lib" / "contract" / "schema.json")
    args = parser.parse_args(argv)

    settings = get_settings()
    _setup_logging(settings, args.verbose)

    try:
        if args.cmd == "build":
            _run_steps(settings, "build", BUILD_STEPS)
        elif args.cmd == "refresh":
            _run_steps(settings, "refresh", REFRESH_STEPS)
        elif args.cmd == "export":
            with step_lock(settings.run_dir, "export"):
                _step_export(settings)
        elif args.cmd == "publish":
            from pipeline.publish import publish

            publish(settings, push=not args.no_push, trigger_deploy=not args.no_deploy)
        elif args.cmd == "status":
            cmd_status(settings)
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
