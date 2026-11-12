"""所有對外 HTTP 請求都經過這裡：限速、磁碟快取、失敗退避。

PLAN.md 第 0 節第 4 點：被封 IP 會卡住整個專案，所以限速是硬性規定，不是建議。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

log = logging.getLogger(__name__)

# 不帶任何個人資訊的 User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) tw-stock-terminal/0.1"

# 各來源的最小請求間隔（秒）。PLAN.md 第 3 節。
DEFAULT_INTERVALS: dict[str, float] = {
    "www.twse.com.tw": 3.0,
    "openapi.twse.com.tw": 3.0,
    "www.tpex.org.tw": 3.0,
    "mops.twse.com.tw": 5.0,
    "mopsov.twse.com.tw": 5.0,
}
FALLBACK_INTERVAL = 2.0


class Blocked(RuntimeError):
    """來源回應 403 或明顯的封鎖頁面。不要重試，停下來處理。"""


class FetchError(RuntimeError):
    pass


def cache_key(url: str, params: dict[str, Any] | None) -> str:
    query = urlencode(sorted((params or {}).items()))
    return hashlib.sha256(f"{url}?{query}".encode()).hexdigest()


class HttpClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        intervals: dict[str, float] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_attempts: int = 5,
        base_backoff: float = 5.0,
        timeout: float = 30.0,
    ) -> None:
        self.cache_dir = cache_dir
        self.intervals = {**DEFAULT_INTERVALS, **(intervals or {})}
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.stats = {"network": 0, "cache_hit": 0}
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- 快取 -------------------------------------------------------------
    def _cache_path(self, host: str, key: str) -> Path:
        return self.cache_dir / host / key[:2] / f"{key}.gz"

    def _cache_read(self, path: Path) -> bytes | None:
        try:
            return gzip.decompress(path.read_bytes())
        except FileNotFoundError:
            return None

    def _cache_write(self, path: Path, body: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body))
        tmp.replace(path)

    # ---- 限速 -------------------------------------------------------------
    def _throttle(self, host: str) -> None:
        interval = self.intervals.get(host, FALLBACK_INTERVAL)
        last = self._last.get(host)
        if last is not None:
            wait = interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()

    # ---- 主要介面 ---------------------------------------------------------
    def get_bytes(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
        should_cache: Callable[[bytes], bool] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> bytes:
        """GET（或給了 json_body 時 POST）。快取鍵包含網址、參數與請求本文。"""
        host = urlsplit(url).netloc
        key_params = dict(params or {})
        if json_body is not None:
            key_params["__body__"] = json.dumps(json_body, sort_keys=True, ensure_ascii=False)
        path = self._cache_path(host, cache_key(url, key_params))
        if use_cache:
            cached = self._cache_read(path)
            if cached is not None:
                self.stats["cache_hit"] += 1
                return cached

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._throttle(host)
            self.stats["network"] += 1
            try:
                if json_body is not None:
                    resp = self._client.post(url, params=params, json=json_body)
                else:
                    resp = self._client.get(url, params=params)
            except httpx.TransportError as e:
                last_error = e
                log.warning("連線失敗 %s（第 %d 次）：%s", url, attempt, e)
            else:
                if resp.status_code == 403:
                    raise Blocked(f"{host} 回應 403，可能已被封鎖。請停止所有對 {host} 的請求並檢查。")
                if resp.status_code == 200:
                    body = resp.content
                    if use_cache and (should_cache is None or should_cache(body)):
                        self._cache_write(path, body)
                    return body
                last_error = FetchError(f"HTTP {resp.status_code}: {url}")
                if resp.status_code < 500 and resp.status_code != 429:
                    raise last_error
                log.warning("HTTP %d %s（第 %d 次）", resp.status_code, url, attempt)
            if attempt < self.max_attempts:
                backoff = self.base_backoff * 2 ** (attempt - 1)
                self._sleep(backoff + random.uniform(0, backoff * 0.2))
        raise FetchError(f"重試 {self.max_attempts} 次仍失敗：{url}") from last_error

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
        should_cache: Callable[[Any], bool] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        def _ok(body: bytes) -> bool:
            try:
                data = json.loads(body)
            except ValueError:
                return False
            return should_cache(data) if should_cache else True

        body = self.get_bytes(url, params, use_cache=use_cache, should_cache=_ok, json_body=json_body)
        try:
            return json.loads(body)
        except ValueError as e:
            snippet = body[:200].decode("utf-8", "replace")
            if "<html" in snippet.lower():
                raise Blocked(f"預期 JSON 卻收到 HTML（可能是封鎖或維護頁）：{url}\n{snippet}") from e
            raise FetchError(f"回應不是 JSON：{url}\n{snippet}") from e
