"""Named fixture repositories. Each function scripts one repository's full history."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.builder import Author, FixtureRepo


def minimal(parent: Path) -> FixtureRepo:
    """A tiny Python project with a two-commit history."""
    repo = FixtureRepo.create(parent, "minimal")
    repo.commit(
        "Initial commit",
        {
            "README.md": "# minimal\n\nA tiny example project.\n",
            "app/__init__.py": "",
            "app/main.py": 'def main() -> None:\n    print("hello")\n',
        },
    )
    repo.commit(
        "Add a greeting helper",
        {"app/greet.py": 'def greet(name: str) -> str:\n    return f"hello {name}"\n'},
        author=Author("Grace Hopper", "grace@example.com"),
        date="2024-02-01T12:00:00+00:00",
    )
    return repo


def polyglot(parent: Path) -> FixtureRepo:
    """Several languages plus line-counting edge cases."""
    repo = FixtureRepo.create(parent, "polyglot")
    repo.commit(
        "Add a small multi-language project",
        {
            "README.md": "# polyglot\n",
            "config.yml": "debug: false\n",
            "server/main.go": "package main\n\nfunc main() {\n}\n",
            "server/util.go": "package main\n",
            "web/app.ts": "export const a = 1;\nexport const b = 2;\n",
            "web/legacy.js": "var x = 1;\r\nvar y = 2;\r\nvar z = 3;\r\n",
            "tools/build.py": "print('build')",
            "tools/empty.py": "",
            "LICENSE": "MIT\n",
        },
    )
    return repo
