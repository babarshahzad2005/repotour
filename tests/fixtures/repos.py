"""Named fixture repositories. Each function scripts one repository's full history."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.builder import FixtureRepo


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
        date="2024-01-01T12:00:00+00:00",
    )
    repo.commit(
        "Add a greeting helper",
        {"app/greet.py": 'def greet(name: str) -> str:\n    return f"hello {name}"\n'},
        author=("Grace Hopper", "grace@example.com"),
        date="2024-02-01T12:00:00+00:00",
    )
    return repo
