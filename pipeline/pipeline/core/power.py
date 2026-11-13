"""長時間執行期間避免系統閒置睡眠。

2026-11-12 夜間電腦在 22:58 進入睡眠，正在跑的回補與回測因此中斷或停滯。
Windows 上用 SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)：只在這個程序執行期間
阻止「閒置」睡眠，程序結束就自動失效；不修改任何電源設定，闔上筆電或手動睡眠仍然有效。
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def keep_awake() -> Iterator[None]:
    if sys.platform != "win32":
        yield
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)
