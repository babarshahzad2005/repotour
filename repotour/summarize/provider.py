"""Where summaries come from: provider presets, API keys, and the HTTP client.

Every provider speaks the OpenAI-compatible chat completions API, so one small
client covers them all. It uses only the standard library.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

KEY_VARIABLE = "REPOTOUR_LLM_API_KEY"
REQUEST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Preset:
    base_url: str | None  # None: the user must configure one
    model: str | None  # None: the user must configure one
    key_variable: str | None  # the provider's own variable; None: no key needed


PRESETS: dict[str, Preset] = {
    "groq": Preset("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "openrouter": Preset("https://openrouter.ai/api/v1", None, "OPENROUTER_API_KEY"),
    "ollama": Preset("http://localhost:11434/v1", "qwen2.5-coder:3b", None),
    "custom": Preset(None, None, None),
}


@dataclass(frozen=True)
class Endpoint:
    provider: str
    base_url: str
    model: str
    api_key: str | None


class MissingKeyError(Exception):
    """The provider needs an API key and none is set."""


class ProviderError(Exception):
    """The provider answered with an error, or with something unusable."""


class UnreachableError(ProviderError):
    """The endpoint could not be reached at all; later calls would fail too."""


class ChatClient(Protocol):
    def complete(self, endpoint: Endpoint, system: str, user: str) -> str: ...


def resolve_endpoint(
    provider: str, base_url: str | None, model: str | None, environ: Mapping[str, str]
) -> Endpoint:
    """Apply config overrides to the preset and find the API key.

    The config loader has already checked that the provider exists and that
    `custom` has a base URL and every preset without a model has one.
    """
    preset = PRESETS[provider]
    url = base_url or preset.base_url
    name = model or preset.model
    assert url is not None
    assert name is not None
    key = environ.get(KEY_VARIABLE) or (
        environ.get(preset.key_variable) if preset.key_variable else None
    )
    if preset.key_variable and not key:
        raise MissingKeyError(
            f"set {preset.key_variable} (or {KEY_VARIABLE}) to your {provider} API key"
        )
    return Endpoint(provider=provider, base_url=url.rstrip("/"), model=name, api_key=key or None)


class HttpChatClient:
    """Calls `<base_url>/chat/completions` with the standard library."""

    def complete(self, endpoint: Endpoint, system: str, user: str) -> str:
        body = {
            "model": endpoint.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json", "User-Agent": "repotour"}
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"
        request = urllib.request.Request(
            f"{endpoint.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                payload: Any = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"HTTP {exc.code} {_error_message(exc)}".rstrip()) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            raise UnreachableError(f"cannot reach {endpoint.base_url} ({reason})") from None
        except (UnicodeDecodeError, ValueError):
            raise ProviderError("the response was not JSON") from None
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("the response had no message content") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("the response was empty")
        return content


def _error_message(exc: urllib.error.HTTPError) -> str:
    """The provider's own error message, if the body carries one."""
    try:
        data = json.loads(exc.read().decode("utf-8"))
        message = data["error"]["message"] if isinstance(data["error"], dict) else data["error"]
    except Exception:
        return ""
    return f"({str(message)[:200]})"
