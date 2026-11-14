"""Rate limits: a 429 is waited out within a bounded total wait, then becomes
one warning. No test really sleeps: the clock is injected."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from repotour.model.tour import Tour
from repotour.pipeline import build_tour
from repotour.summarize.provider import Endpoint, HttpChatClient, RateLimitedError
from repotour.summarize.summarizer import (
    DEFAULT_RETRY_SECONDS,
    MAX_RATE_LIMIT_WAIT_SECONDS,
    SummaryOptions,
)
from tests.fixtures.repos import graph_showcase

KEY = {"GROQ_API_KEY": "test-key"}


@dataclass
class LimitedClient:
    """Rate-limits the first `limited` calls, then answers."""

    limited: int
    retry_after: float | None = 2.0
    calls: list[str] = field(default_factory=list)

    def complete(self, endpoint: Endpoint, system: str, user: str) -> str:
        path = user.splitlines()[0].removeprefix("File: ")
        self.calls.append(path)
        if len(self.calls) <= self.limited:
            raise RateLimitedError("HTTP 429", retry_after=self.retry_after)
        return f"Summary of {path}."


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return graph_showcase(tmp_path_factory.mktemp("limits")).root


def run(root: Path, client: LimitedClient, sleeps: list[float]) -> Tour:
    options = SummaryOptions(client=client, environ=KEY, sleep=sleeps.append)
    return build_tour(root, use_cache=False, summaries=options).tour


def test_rate_limited_call_is_retried_after_the_requested_delay(root: Path) -> None:
    sleeps: list[float] = []
    client = LimitedClient(limited=2, retry_after=3.5)

    tour = run(root, client, sleeps)

    assert sleeps == [3.5, 3.5]
    assert client.calls[0] == client.calls[1] == client.calls[2]
    assert len(tour.summaries) == len(client.calls) - 2
    assert not [w for w in tour.warnings if w.startswith("summaries")]


def test_missing_retry_after_uses_the_default_delay(root: Path) -> None:
    sleeps: list[float] = []

    run(root, LimitedClient(limited=1, retry_after=None), sleeps)

    assert sleeps == [DEFAULT_RETRY_SECONDS]


def test_total_wait_is_bounded_then_one_warning(root: Path) -> None:
    sleeps: list[float] = []
    client = LimitedClient(limited=10_000, retry_after=7.0)

    tour = run(root, client, sleeps)

    assert sum(sleeps) <= MAX_RATE_LIMIT_WAIT_SECONDS
    assert tour.summaries == ()
    warnings = [w for w in tour.warnings if w.startswith("summaries")]
    assert len(warnings) == 1
    assert "rate limit" in warnings[0]
    assert "left without a summary" in warnings[0]


def test_zero_retry_after_still_waits_a_moment(root: Path) -> None:
    sleeps: list[float] = []

    tour = run(root, LimitedClient(limited=10_000, retry_after=0.0), sleeps)

    assert set(sleeps) == {1.0}
    assert sum(sleeps) <= MAX_RATE_LIMIT_WAIT_SECONDS
    assert any("rate limit" in w for w in tour.warnings)


def test_a_delay_longer_than_the_budget_is_not_waited(root: Path) -> None:
    sleeps: list[float] = []

    tour = run(root, LimitedClient(limited=1, retry_after=3600.0), sleeps)

    assert sleeps == []
    assert any("rate limit" in w for w in tour.warnings)


def test_summaries_done_before_the_limit_are_kept(root: Path) -> None:
    @dataclass
    class LimitAfterTwo(LimitedClient):
        def complete(self, endpoint: Endpoint, system: str, user: str) -> str:
            path = user.splitlines()[0].removeprefix("File: ")
            self.calls.append(path)
            if len(self.calls) > 2:
                raise RateLimitedError("HTTP 429", retry_after=3600.0)
            return f"Summary of {path}."

    tour = run(root, LimitAfterTwo(limited=0), [])

    assert len(tour.summaries) == 2


# --- the HTTP client turns 429 into RateLimitedError -------------------------------


@pytest.fixture
def limited_server() -> Iterator[tuple[str, list[dict[str, str]]]]:
    header_sets: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(429)
            for name, value in header_sets.pop(0).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Rate limit reached"}}).encode())

        def log_message(self, *args: Any) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1", header_sets
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "12"}, 12.0),
        ({"Retry-After": "1.5"}, 1.5),
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, None),
        ({}, None),
    ],
)
def test_http_429_carries_retry_after(
    limited_server: tuple[str, list[dict[str, str]]],
    headers: dict[str, str],
    expected: float | None,
) -> None:
    url, header_sets = limited_server
    header_sets.append(headers)
    endpoint = Endpoint(provider="groq", base_url=url, model="m", api_key="k")

    with pytest.raises(RateLimitedError, match="Rate limit reached") as caught:
        HttpChatClient().complete(endpoint, "s", "u")

    assert caught.value.retry_after == expected
