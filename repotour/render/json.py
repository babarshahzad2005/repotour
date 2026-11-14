"""JSON renderer: the Tour model as data, for tools rather than people.

The format is experimental (see docs/json.md). JSON has no comments, so a
`generator` field marks files Repotour wrote, the way the Markdown marker does.
"""

from __future__ import annotations

import json
from pathlib import Path

from repotour.model.serde import to_data
from repotour.model.tour import Tour

GENERATOR = "repotour"
SCHEMA_VERSION = 1


def render_json(tour: Tour) -> str:
    document = {"generator": GENERATOR, "schema_version": SCHEMA_VERSION, "tour": to_data(tour)}
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def is_generated_json(path: Path) -> bool:
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return isinstance(data, dict) and data.get("generator") == GENERATOR
