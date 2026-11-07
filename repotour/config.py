"""Loads and validates `.repotour.yml`, then applies CLI flags on top.

The result is a frozen `Config`. Its hash is part of every cache key and of
the tour's meta section, so equal effective settings always hash equally.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import types
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

import yaml

from repotour.errors import ConfigError

CONFIG_FILE = ".repotour.yml"
SUPPORTED_VERSION = 1
_DURATION = re.compile(r"^[1-9]\d*[dwmy]$")


@dataclass(frozen=True)
class Thresholds:
    bulk_commit_files: int = 200
    bus_factor_share: float = 0.8
    bus_factor_min_files: int = 5
    bus_factor_min_commits: int = 10
    ownership_max_depth: int = 2
    ownership_min_files: int = 5
    contact_window: str = "12m"
    stable_window: str = "12m"
    graph_max_nodes: int = 60
    core_module_share: float = 0.1


@dataclass(frozen=True)
class Caps:
    hotspots: int = 10
    authors_per_directory: int = 3
    entry_points_per_kind: int = 10
    reading_order: int = 5


@dataclass(frozen=True)
class Summaries:
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:3b"
    max_files: int = 15


@dataclass(frozen=True)
class Config:
    name: str | None = None
    since: str = "6m"
    exclude: tuple[str, ...] = ()
    pinned_entry_points: tuple[str, ...] = ()
    notes: tuple[tuple[str, str], ...] = ()
    test_patterns: tuple[str, ...] = ()
    bots: tuple[str, ...] = ()
    ignore_revs: tuple[str, ...] = ()
    thresholds: Thresholds = field(default_factory=Thresholds)
    caps: Caps = field(default_factory=Caps)
    summaries: Summaries = field(default_factory=Summaries)

    def config_hash(self) -> str:
        canonical = json.dumps(dataclasses.asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CliOverrides:
    """CLI flags that override config values. None means "not given"."""

    since: str | None = None


def load_config(root: Path, overrides: CliOverrides | None = None) -> Config:
    path = root / CONFIG_FILE
    config = _parse(path.read_text(encoding="utf-8")) if path.exists() else Config()
    if overrides is not None and overrides.since is not None:
        config = dataclasses.replace(config, since=overrides.since)
    _check_ranges(config)
    return config


def _parse(text: str) -> Config:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{CONFIG_FILE} is not valid YAML: {exc}") from None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_FILE} must be a mapping of settings")
    if "version" not in raw:
        raise ConfigError(f"{CONFIG_FILE}: 'version: 1' is required")
    version = raw.pop("version")
    if type(version) is not int or version != SUPPORTED_VERSION:
        raise ConfigError(
            f"{CONFIG_FILE}: unsupported config version {version!r}; this Repotour reads version 1"
        )
    built: Config = _build(Config, raw, "")
    return built


def _build(cls: type[Any], raw: object, where: str) -> Any:
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_FILE}: '{where}' must be a mapping")
    known = {f.name for f in fields(cls)}
    for key in raw:
        if key not in known:
            raise ConfigError(f"{CONFIG_FILE}: unknown key '{_join(where, str(key))}'")
    hints = get_type_hints(cls)
    values = {
        f.name: _convert(hints[f.name], raw[f.name], _join(where, f.name))
        for f in fields(cls)
        if f.name in raw
    }
    return cls(**values)


def _convert(tp: Any, value: object, where: str) -> Any:
    origin, args = get_origin(tp), get_args(tp)
    if isinstance(tp, type) and is_dataclass(tp):
        return _build(tp, value, where)
    if origin in (Union, types.UnionType) and type(None) in args:
        if value is None:
            return None
        (inner,) = (a for a in args if a is not type(None))
        return _convert(inner, value, where)
    if origin is tuple and args == (tuple[str, str], ...):
        if not isinstance(value, dict):
            raise ConfigError(f"{CONFIG_FILE}: '{where}' must be a mapping of path to text")
        pairs = []
        for key, text in value.items():
            if not isinstance(text, str):
                raise ConfigError(f"{CONFIG_FILE}: '{_join(where, str(key))}' must be a string")
            pairs.append((str(key), text))
        return tuple(sorted(pairs))
    if origin is tuple:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{CONFIG_FILE}: '{where}' must be a list of strings")
        return tuple(value)
    if tp is bool or isinstance(value, bool):
        raise ConfigError(f"{CONFIG_FILE}: '{where}' must be {_describe(tp)}")
    if tp is float and isinstance(value, int | float):
        return float(value)
    if isinstance(value, tp):
        return value
    raise ConfigError(f"{CONFIG_FILE}: '{where}' must be {_describe(tp)}")


def _check_ranges(config: Config) -> None:
    for where, duration in (
        ("since", config.since),
        ("thresholds.contact_window", config.thresholds.contact_window),
        ("thresholds.stable_window", config.thresholds.stable_window),
    ):
        if not _DURATION.match(duration):
            raise ConfigError(
                f"'{where}' must be a duration like 6m (units: d, w, m, y), got {duration!r}"
            )
    for section_name, section in (("thresholds", config.thresholds), ("caps", config.caps)):
        for f in fields(section):
            value = getattr(section, f.name)
            where = f"{section_name}.{f.name}"
            if isinstance(value, int) and value < 1:
                raise ConfigError(f"{CONFIG_FILE}: '{where}' must be at least 1")
            if isinstance(value, float) and not 0 < value <= 1:
                raise ConfigError(f"{CONFIG_FILE}: '{where}' must be between 0 and 1")
    if config.summaries.max_files < 1:
        raise ConfigError(f"{CONFIG_FILE}: 'summaries.max_files' must be at least 1")


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _describe(tp: Any) -> str:
    return {int: "an integer", float: "a number", str: "a string"}.get(tp, str(tp))
