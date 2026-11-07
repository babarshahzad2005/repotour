from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from repotour.cli import app
from repotour.languages.python import PythonAdapter
from tests.fixtures.builder import FixtureRepo

runner = CliRunner()


class Parses:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        original = PythonAdapter.parse

        def counting(adapter: PythonAdapter, source: bytes, path: str = ""):  # type: ignore[no-untyped-def]
            self.count += 1
            return original(adapter, source, path)

        monkeypatch.setattr(PythonAdapter, "parse", counting)


def project(tmp_path: Path) -> FixtureRepo:
    repo = FixtureRepo.create(tmp_path, "parsecache")
    repo.commit(
        "Add",
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from pkg import b\n",
            "pkg/b.py": "import os\n",
            "pkg/cli.py": "if __name__ == '__main__':\n    pass\n",
        },
        date="2024-01-01T00:00:00+00:00",
    )
    return repo


def tour(root: Path, *args: str) -> bytes:
    result = runner.invoke(app, [str(root), "--force", *args])
    assert result.exit_code == 0, result.output
    return (root / "TOUR.md").read_bytes()


def test_each_file_is_parsed_once_per_run_even_without_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = project(tmp_path)
    parses = Parses(monkeypatch)

    tour(repo.root, "--no-cache")

    assert parses.count == 4  # shared by the dependency and entry point analyzers


def test_only_changed_files_are_reparsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = project(tmp_path)
    tour(repo.root)
    repo.commit("Edit b", {"pkg/b.py": "import json\n"}, date="2024-01-02T00:00:00+00:00")

    parses = Parses(monkeypatch)
    tour(repo.root)

    assert parses.count == 1


def test_moved_unchanged_file_is_not_reparsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = project(tmp_path)
    tour(repo.root)
    repo.commit(
        "Move cli",
        {"pkg/cli.py": None, "pkg/main.py": "if __name__ == '__main__':\n    pass\n"},
        date="2024-01-02T00:00:00+00:00",
    )

    parses = Parses(monkeypatch)
    tour(repo.root)

    assert parses.count == 0


def test_adapter_version_bump_invalidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = project(tmp_path)
    tour(repo.root)
    repo.commit("Touch docs", {"README.md": "hi\n"}, date="2024-01-02T00:00:00+00:00")
    monkeypatch.setattr(PythonAdapter, "version", 999)

    parses = Parses(monkeypatch)
    tour(repo.root)

    assert parses.count == 4


def test_cached_output_matches_a_cold_run(tmp_path: Path) -> None:
    repo = project(tmp_path)
    tour(repo.root)
    repo.commit("Edit b", {"pkg/b.py": "from pkg import a\n"}, date="2024-01-02T00:00:00+00:00")

    assert tour(repo.root) == tour(repo.root, "--no-cache")
