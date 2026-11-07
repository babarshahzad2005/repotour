"""Path patterns with gitignore-style semantics, used for config globs.

- A pattern without an inner slash matches a name at any depth
  (`*.pb.go`, `vendor/`).
- A pattern with a leading or inner slash is anchored at the repository root
  (`/build/`, `docs/api/`).
- A trailing slash means "this directory and everything under it".
- `*` and `?` never cross a slash; `**` matches across directories.
"""

from __future__ import annotations

import re
from functools import lru_cache


def matches(pattern: str, path: str) -> bool:
    return _compile(pattern).match(path) is not None


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    directory = pattern.endswith("/")
    body = pattern.strip("/")
    anchored = pattern.startswith("/") or "/" in body
    regex = _translate(body)
    prefix = "" if anchored else "(?:.*/)?"
    suffix = "/.*" if directory else "(?:/.*)?"
    return re.compile(f"^{prefix}{regex}{suffix}$")


def _translate(glob: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return "".join(out)
