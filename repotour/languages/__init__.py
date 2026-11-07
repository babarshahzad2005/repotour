"""Language adapters: per-language parsing and import resolution.

Adding a language means adding one adapter to `ADAPTERS`, nothing else.
"""

from __future__ import annotations

from repotour.languages.base import LanguageAdapter
from repotour.languages.go import GoAdapter
from repotour.languages.javascript import JavaScriptAdapter
from repotour.languages.python import PythonAdapter

ADAPTERS: tuple[LanguageAdapter, ...] = (PythonAdapter(), JavaScriptAdapter(), GoAdapter())
