from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from pipeline.core.locks import AlreadyRunning, list_locks, pid_alive, step_lock


def test_pid_alive_for_self_and_dead_process():
    assert pid_alive(os.getpid())
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not pid_alive(proc.pid)


def test_lock_blocks_second_holder_and_is_released(tmp_path):
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / "build.lock").write_text(json.dumps({"pid": other.pid, "started_at": "x"}))
        with pytest.raises(AlreadyRunning), step_lock(tmp_path, "build"):
            pass
    finally:
        other.kill()
        other.wait()

    # 持有者已結束 → 殘留的鎖檔可以被接手，結束後自動移除
    with step_lock(tmp_path, "build") as path:
        assert path.exists()
        assert list_locks(tmp_path)[0]["alive"]
    assert not (tmp_path / "build.lock").exists()
