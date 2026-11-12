from __future__ import annotations

import httpx
import pytest

from pipeline.core.http import Blocked, FetchError, HttpClient


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def make(tmp_path, handler, **kw):  # noqa: ANN001
    fc = FakeClock()
    client = HttpClient(
        tmp_path / "cache",
        transport=httpx.MockTransport(handler),
        sleep=fc.sleep,
        clock=fc.clock,
        intervals={"example.test": 3.0},
        **kw,
    )
    return client, fc


def test_rate_limit_waits_between_requests(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(200, json={"ok": True})

    client, fc = make(tmp_path, handler)
    client.get_json("https://example.test/a", use_cache=False)
    client.get_json("https://example.test/b", use_cache=False)
    client.get_json("https://example.test/c", use_cache=False)
    assert len(calls) == 3
    assert fc.sleeps == [3.0, 3.0]


def test_cache_hit_skips_network(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"stat": "OK", "n": 1})

    client, _ = make(tmp_path, handler)
    a = client.get_json("https://example.test/x", {"date": "20200102"})
    b = client.get_json("https://example.test/x", {"date": "20200102"})
    assert a == b == {"stat": "OK", "n": 1}
    assert len(calls) == 1
    assert client.stats == {"network": 1, "cache_hit": 1}


def test_should_cache_predicate_prevents_caching(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"stat": "很抱歉，沒有符合條件的資料!"})

    client, _ = make(tmp_path, handler)
    for _ in range(2):
        client.get_json("https://example.test/today", should_cache=lambda d: d.get("stat") == "OK")
    assert len(calls) == 2


def test_retries_on_503_then_succeeds(tmp_path):
    responses = iter([httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    client, fc = make(tmp_path, lambda req: next(responses), base_backoff=1.0)
    assert client.get_json("https://example.test/r", use_cache=False) == {"ok": 1}
    assert client.stats["network"] == 3


def test_403_raises_blocked_without_retry(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403)

    client, _ = make(tmp_path, handler)
    with pytest.raises(Blocked):
        client.get_json("https://example.test/blocked")
    assert len(calls) == 1


def test_html_instead_of_json_raises_blocked(tmp_path):
    client, _ = make(tmp_path, lambda req: httpx.Response(200, text="<html><body>請稍後再試</body></html>"))
    with pytest.raises(Blocked):
        client.get_json("https://example.test/html")


def test_gives_up_after_max_attempts(tmp_path):
    client, _ = make(tmp_path, lambda req: httpx.Response(500), max_attempts=3, base_backoff=0.1)
    with pytest.raises(FetchError):
        client.get_json("https://example.test/down", use_cache=False)
    assert client.stats["network"] == 3
