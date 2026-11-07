"""Converts model dataclasses to JSON-compatible data and back.

Used for analyzer results, the cache, and `--json`. Supports the shapes the
model uses: nested frozen dataclasses, `tuple[X, ...]`, `X | None`, and
primitives.
"""

from __future__ import annotations

import dataclasses
import types
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


def to_data(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_data(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, tuple | list):
        return [to_data(item) for item in obj]
    return obj


def from_data(cls: type[T], data: Any) -> T:
    result: T = _convert(cls, data)
    return result


def _convert(tp: Any, data: Any) -> Any:
    origin, args = get_origin(tp), get_args(tp)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        hints = get_type_hints(tp)
        values = {
            f.name: _convert(hints[f.name], data[f.name])
            for f in dataclasses.fields(tp)
            if f.init and f.name in data
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
