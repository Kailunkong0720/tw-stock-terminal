"""步驟鎖：防止同一個管線步驟同時跑兩份（例如兩個工作階段各自啟動回補）。"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class AlreadyRunning(RuntimeError):
    pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # 注意：Windows 上 os.kill(pid, 0) 會呼叫 TerminateProcess，不能用來檢查。
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


@contextmanager
def step_lock(run_dir: Path, name: str) -> Iterator[Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{name}.lock"
    existing = read_lock(path)
    if existing and pid_alive(int(existing.get("pid", 0))) and existing.get("pid") != os.getpid():
        raise AlreadyRunning(f"步驟「{name}」已在執行中（PID {existing['pid']}，開始於 {existing.get('started_at')}）")
    path.write_text(
        json.dumps({"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8",
    )
    try:
        yield path
    finally:
        current = read_lock(path)
        if current and current.get("pid") == os.getpid():
            path.unlink(missing_ok=True)


def list_locks(run_dir: Path) -> list[dict]:
    out = []
    if not run_dir.exists():
        return out
    for p in sorted(run_dir.glob("*.lock")):
        info = read_lock(p) or {}
        pid = int(info.get("pid", 0))
        out.append({"step": p.stem, "pid": pid, "started_at": info.get("started_at"), "alive": pid_alive(pid)})
    return out
