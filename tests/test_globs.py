from __future__ import annotations

import pytest

from repotour.scan.globs import matches


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # no slash: matches the name at any depth
        ("*.pb.go", "src/api.pb.go", True),
        ("*.pb.go", "api.pb.go", True),
        ("*.pb.go", "src/api.go", False),
        # trailing slash: a directory at any depth
        ("vendor/", "vendor/lib.go", True),
        ("vendor/", "a/vendor/lib.go", True),
        ("vendor/", "vendored/lib.go", False),
        # inner slash: anchored at the repository root
        ("docs/api/", "docs/api/index.html", True),
        ("docs/api/", "x/docs/api/index.html", False),
        ("docs/*.md", "docs/guide.md", True),
        ("docs/*.md", "docs/sub/guide.md", False),
        # double star
        ("checks/**", "checks/a/b.py", True),
        ("**/fixtures/**", "tests/fixtures/x.py", True),
        ("**/fixtures/**", "fixtures/x.py", True),
        ("src/**/*.ts", "src/a/b/c.ts", True),
        ("src/**/*.ts", "src/c.ts", True),
        # leading slash anchors too
        ("/build/", "build/out.js", True),
        ("/build/", "x/build/out.js", False),
        # exact file
        ("legacy/old.py", "legacy/old.py", True),
        ("?.py", "a.py", True),
        ("?.py", "ab.py", False),
    ],
)
def test_matches(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected
