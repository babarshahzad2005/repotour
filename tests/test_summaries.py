"""AI summaries: provider presets, keys, caching, labelling, and failure
handling. Tests never touch the network: they use a fake client, or a local
HTTP server for the real client."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.errors import ConfigError
from repotour.model.tour import find_unevidenced_claims
from repotour.pipeline import PipelineResult, build_tour
from repotour.render.html import render_html
from repotour.render.json import render_json
from repotour.render.markdown import render_markdown
from repotour.summarize import provider
from repotour.summarize.provider import (
    Endpoint,
    HttpChatClient,
    MissingKeyError,
    ProviderError,
    UnreachableError,
    resolve_endpoint,
)
from repotour.summarize.summarizer import MAX_SUMMARY_CHARS, SummaryOptions
from tests.fixtures.repos import graph_showcase, minimal

KEY = {"GROQ_API_KEY": "test-key"}


@dataclass
class FakeClient:
    """Answers from a script; records every call and the notice order."""

    events: list[str] = field(default_factory=list)
    calls: list[tuple[Endpoint, str]] = field(default_factory=list)
    fail: dict[str, Exception] = field(default_factory=dict)
    answer: str = "Summary of {path}."

    def complete(self, endpoint: Endpoint, system: str, user: str) -> str:
        path = user.splitlines()[0].removeprefix("File: ")
        self.calls.append((endpoint, path))
        self.events.append(f"call {path}")
        if path in self.fail:
            raise self.fail[path]
        return self.answer.format(path=path)

    def options(self, environ: dict[str, str] | None = None) -> SummaryOptions:
        return SummaryOptions(
            client=self,
            environ=KEY if environ is None else environ,
            notify=lambda message: self.events.append(f"notice {message}"),
        )


@pytest.fixture(scope="module")
def showcase_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return graph_showcase(tmp_path_factory.mktemp("summaries")).root


def tour_with(root: Path, client: FakeClient, **kwargs: Any) -> PipelineResult:
    return build_tour(root, use_cache=False, summaries=client.options(**kwargs))


def write_config(root: Path, text: str) -> None:
    (root / ".repotour.yml").write_text("version: 1\n" + text, encoding="utf-8")


# --- presets and keys -----------------------------------------------------------


def test_groq_is_the_default_preset() -> None:
    endpoint = resolve_endpoint("groq", None, None, KEY)

    assert endpoint.base_url == "https://api.groq.com/openai/v1"
    assert endpoint.model
    assert endpoint.api_key == "test-key"


def test_generic_key_variable_wins_over_the_provider_variable() -> None:
    environ = {"GROQ_API_KEY": "groq", "REPOTOUR_LLM_API_KEY": "generic"}

    assert resolve_endpoint("groq", None, None, environ).api_key == "generic"


def test_missing_key_names_both_variables() -> None:
    with pytest.raises(MissingKeyError, match=r"GROQ_API_KEY.*REPOTOUR_LLM_API_KEY"):
        resolve_endpoint("groq", None, None, {})


def test_ollama_needs_no_key() -> None:
    endpoint = resolve_endpoint("ollama", None, None, {})

    assert endpoint.base_url == "http://localhost:11434/v1"
    assert endpoint.api_key is None


def test_config_overrides_the_preset() -> None:
    endpoint = resolve_endpoint("custom", "http://box:8080/v1/", "my-model", {})

    assert endpoint.base_url == "http://box:8080/v1"
    assert endpoint.model == "my-model"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ("summaries:\n  provider: openai\n", "'summaries.provider' must be one of"),
        ("summaries:\n  provider: custom\n  model: m\n", "'summaries.base_url' is required"),
        ("summaries:\n  provider: openrouter\n", "'summaries.model' is required"),
    ],
)
def test_invalid_summaries_config_exits_2(tmp_path: Path, config: str, message: str) -> None:
    repo = minimal(tmp_path)
    write_config(repo.root, config)

    with pytest.raises(ConfigError, match=message):
        build_tour(repo.root, use_cache=False)
    result = CliRunner().invoke(app, [str(repo.root)])
    assert result.exit_code == 2


# --- what is summarized and how it renders ----------------------------------------


def test_reading_order_then_core_modules_are_summarized(showcase_root: Path) -> None:
    client = FakeClient()

    tour = tour_with(showcase_root, client).tour

    assert tour.reading_order is not None
    assert tour.dependency_graph is not None
    expected = list(
        dict.fromkeys(
            [s.path for s in tour.reading_order.steps]
            + [c.path for c in tour.dependency_graph.core]
        )
    )
    assert [s.path for s in tour.summaries] == expected
    assert [path for _, path in client.calls] == expected
    assert tour.summaries[0].text == f"Summary of {expected[0]}."
    assert find_unevidenced_claims(tour) == []


def test_max_files_caps_the_summaries(showcase_root: Path, tmp_path: Path) -> None:
    repo = graph_showcase(tmp_path)
    write_config(repo.root, "summaries:\n  max_files: 2\n")
    repo.commit("Limit summaries", {".repotour.yml": (repo.root / ".repotour.yml").read_text()})
    client = FakeClient()

    tour = tour_with(repo.root, client).tour

    assert len(tour.summaries) == 2
    assert len(client.calls) == 2


def test_notice_names_files_endpoint_and_model_before_sending(showcase_root: Path) -> None:
    client = FakeClient()

    tour_with(showcase_root, client)

    notice = client.events[0]
    assert notice.startswith("notice Sending ")
    assert "https://api.groq.com/openai/v1" in notice
    assert client.calls[0][0].model in notice
    for _, path in client.calls:
        assert path in notice
    assert all(e.startswith("call ") for e in client.events[1:])


def test_summaries_are_labelled_in_every_format(showcase_root: Path) -> None:
    tour = tour_with(showcase_root, FakeClient()).tour
    model = tour.summaries[0].model

    markdown = render_markdown(tour)
    assert "## Key files, summarized by AI" in markdown
    assert f"AI model ({model})" in markdown
    assert f"`{tour.summaries[0].path}`: {tour.summaries[0].text}" in markdown
    assert "summarized by AI</h2>" in render_html(tour)
    data = json.loads(render_json(tour))["tour"]["summaries"]
    assert data[0]["model"] == model


def test_model_output_is_one_bounded_plain_paragraph(showcase_root: Path) -> None:
    client = FakeClient(answer="First line.\n\n  Second   line.\n" + "word " * 400)

    summary = tour_with(showcase_root, client).tour.summaries[0]

    assert "\n" not in summary.text
    assert summary.text.startswith("First line. Second line. word")
    assert len(summary.text) <= MAX_SUMMARY_CHARS + 3
    assert summary.text.endswith("...")


def test_without_summaries_flag_no_section_and_no_client(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    tour = build_tour(repo.root, use_cache=False).tour

    assert tour.summaries == ()
    assert "summarized by AI" not in render_markdown(tour)


# --- caching ------------------------------------------------------------------------


def test_cached_summaries_cost_no_second_call(tmp_path: Path) -> None:
    repo = graph_showcase(tmp_path)
    first = FakeClient()
    build_tour(repo.root, summaries=first.options())

    second = FakeClient()
    tour = build_tour(repo.root, summaries=second.options()).tour

    assert first.calls
    assert second.calls == []
    assert not any(e.startswith("notice") for e in second.events)
    assert [s.text for s in tour.summaries] == [f"Summary of {p}." for _, p in first.calls]


def test_changing_the_model_summarizes_again(tmp_path: Path) -> None:
    repo = graph_showcase(tmp_path)
    build_tour(repo.root, summaries=FakeClient().options())
    write_config(repo.root, "summaries:\n  model: another-model\n")
    repo.commit("Switch model", {".repotour.yml": (repo.root / ".repotour.yml").read_text()})

    client = FakeClient()
    build_tour(repo.root, summaries=client.options())

    assert client.calls
    assert all(endpoint.model == "another-model" for endpoint, _ in client.calls)


# --- failures never stop the tour -----------------------------------------------------


def test_missing_key_is_a_warning_and_nothing_is_sent(showcase_root: Path) -> None:
    client = FakeClient()

    tour = tour_with(showcase_root, client, environ={}).tour

    assert client.calls == []
    assert tour.summaries == ()
    assert any("summaries skipped" in w and "GROQ_API_KEY" in w for w in tour.warnings)


def test_provider_error_on_one_file_keeps_the_others(showcase_root: Path) -> None:
    probe = FakeClient()
    paths = [p for _, p in (tour_with(showcase_root, probe), probe.calls)[1]]
    client = FakeClient(fail={paths[0]: ProviderError("HTTP 500")})

    tour = tour_with(showcase_root, client).tour

    assert [s.path for s in tour.summaries] == paths[1:]
    assert any(paths[0] in w and "HTTP 500" in w for w in tour.warnings)


def test_unreachable_endpoint_stops_after_one_warning(showcase_root: Path) -> None:
    probe = FakeClient()
    tour_with(showcase_root, probe)
    paths = [p for _, p in probe.calls]
    client = FakeClient(fail={paths[0]: UnreachableError("cannot reach http://x")})

    tour = tour_with(showcase_root, client).tour

    assert len(client.calls) == 1
    assert tour.summaries == ()
    summary_warnings = [w for w in tour.warnings if w.startswith("summaries")]
    assert summary_warnings == [
        f"summaries: cannot reach http://x; {len(paths)} files left without a summary"
    ]


def test_cli_with_summaries_but_no_key_still_writes_the_tour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = minimal(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("REPOTOUR_LLM_API_KEY", raising=False)

    result = CliRunner().invoke(app, [str(repo.root), "--summaries"])

    assert result.exit_code == 0, result.output
    assert "1 warning" in result.output or "warnings" in result.output
    assert "GROQ_API_KEY" in (repo.root / "TOUR.md").read_text(encoding="utf-8")


# --- the HTTP client, against a local server ----------------------------------------------


@dataclass
class Recorded:
    path: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def server() -> Iterator[tuple[str, Recorded, list[tuple[int, bytes]]]]:
    recorded = Recorded()
    replies: list[tuple[int, bytes]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            recorded.path = self.path
            recorded.headers = {k.lower(): v for k, v in self.headers.items()}
            length = int(self.headers["Content-Length"])
            recorded.body = json.loads(self.rfile.read(length))
            status, payload = replies.pop(0)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1", recorded, replies
    finally:
        httpd.shutdown()
        httpd.server_close()


def endpoint(base_url: str, key: str | None = "secret") -> Endpoint:
    return Endpoint(provider="custom", base_url=base_url, model="m1", api_key=key)


def test_http_client_sends_an_openai_compatible_request(
    server: tuple[str, Recorded, list[tuple[int, bytes]]],
) -> None:
    url, recorded, replies = server
    replies.append((200, json.dumps({"choices": [{"message": {"content": "Hi."}}]}).encode()))

    text = HttpChatClient().complete(endpoint(url), "system text", "user text")

    assert text == "Hi."
    assert recorded.path == "/v1/chat/completions"
    assert recorded.headers["authorization"] == "Bearer secret"
    assert recorded.body["model"] == "m1"
    assert [m["role"] for m in recorded.body["messages"]] == ["system", "user"]


def test_http_client_sends_no_authorization_without_a_key(
    server: tuple[str, Recorded, list[tuple[int, bytes]]],
) -> None:
    url, recorded, replies = server
    replies.append((200, json.dumps({"choices": [{"message": {"content": "Hi."}}]}).encode()))

    HttpChatClient().complete(endpoint(url, key=None), "s", "u")

    assert "authorization" not in recorded.headers


def test_http_error_carries_the_provider_message(
    server: tuple[str, Recorded, list[tuple[int, bytes]]],
) -> None:
    url, _, replies = server
    replies.append((401, json.dumps({"error": {"message": "Invalid API Key"}}).encode()))

    with pytest.raises(ProviderError, match=r"HTTP 401 \(Invalid API Key\)"):
        HttpChatClient().complete(endpoint(url), "s", "u")


def test_response_without_content_is_an_error(
    server: tuple[str, Recorded, list[tuple[int, bytes]]],
) -> None:
    url, _, replies = server
    replies.append((200, b'{"choices": []}'))

    with pytest.raises(ProviderError, match="no message content"):
        HttpChatClient().complete(endpoint(url), "s", "u")


def test_a_slow_answer_fails_only_that_request(monkeypatch: pytest.MonkeyPatch) -> None:
    class Slow(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            time.sleep(2)

        def log_message(self, *args: Any) -> None:
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(provider, "REQUEST_TIMEOUT_SECONDS", 0.3)
    try:
        with pytest.raises(ProviderError, match="no answer within") as caught:
            HttpChatClient().complete(
                endpoint(f"http://127.0.0.1:{httpd.server_port}/v1"), "s", "u"
            )
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert not isinstance(caught.value, UnreachableError)


def test_closed_port_is_unreachable() -> None:
    httpd = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = httpd.server_port
    httpd.server_close()

    with pytest.raises(UnreachableError, match="cannot reach"):
        HttpChatClient().complete(endpoint(f"http://127.0.0.1:{port}/v1"), "s", "u")
