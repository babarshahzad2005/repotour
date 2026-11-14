"""Converts model dataclasses to JSON-compatible data and back.

Used for analyzer results, the cache, and `--json`. Supports the shapes the
model uses: nested frozen dataclasses, `tuple[X, ...]`, `X | None`, and
primitives.
"""

from __future__ import annotations

import dataclasses
import types
from functools import cache
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


def to_data(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {name: to_data(getattr(obj, name)) for name in _field_names(type(obj))}
    if isinstance(obj, tuple | list):
        return [to_data(item) for item in obj]
    return obj


def from_data(cls: type[T], data: Any) -> T:
    result: T = _convert(cls, data)
    return result


def _convert(tp: Any, data: Any) -> Any:
    origin, args = get_origin(tp), get_args(tp)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        values = {
            name: _convert(hint, data[name]) for name, hint in _init_fields(tp) if name in data
        }
        return tp(**values)
    if origin in (Union, types.UnionType):
        if data is None:
            return None
        (inner,) = (a for a in args if a is not type(None))
        return _convert(inner, data)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_convert(args[0], item) for item in data)
        return tuple(_convert(a, item) for a, item in zip(args, data, strict=True))
    return data


def clear_caches() -> None:
    """Forget resolved field types (for tests that patch type resolution)."""
    _field_names.cache_clear()
    _init_fields.cache_clear()


@cache
def _field_names(cls: type) -> tuple[str, ...]:
    return tuple(f.name for f in dataclasses.fields(cls))


@cache
def _init_fields(cls: type) -> tuple[tuple[str, Any], ...]:
    """(name, resolved type) for each init field. Resolving type hints is slow,
    so it happens once per class rather than once per object."""
    hints = get_type_hints(cls)
    return tuple((f.name, hints[f.name]) for f in dataclasses.fields(cls) if f.init)
