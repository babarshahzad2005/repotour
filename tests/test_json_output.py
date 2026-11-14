"""`--json FILE` writes the tour model as JSON next to the normal output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repotour.cli import app
from repotour.model.serde import from_data
from repotour.model.tour import Tour
from repotour.pipeline import build_tour
from repotour.render.json import SCHEMA_VERSION
from tests.conftest import GoldenCheck
from tests.fixtures.repos import graph_showcase, minimal

runner = CliRunner()


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


@pytest.fixture(scope="module")
def showcase_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return graph_showcase(tmp_path_factory.mktemp("json")).root


def test_json_is_written_alongside_the_tour(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "tour.json"

    result = invoke(str(repo.root), "--json", str(target))

    assert result.exit_code == 0, result.output
    assert (repo.root / "TOUR.md").exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["generator"] == "repotour"
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["tour"]["meta"]["repo_name"] == "minimal"
    assert str(target) in result.output


def test_json_matches_golden(showcase_root: Path, tmp_path: Path, golden: GoldenCheck) -> None:
    target = tmp_path / "tour.json"

    result = invoke(str(showcase_root), "--force", "--no-cache", "--json", str(target))

    assert result.exit_code == 0, result.output
    golden("graph-showcase.json", target.read_bytes().decode("utf-8"))


def test_json_round_trips_to_the_tour_model(showcase_root: Path, tmp_path: Path) -> None:
    target = tmp_path / "tour.json"
    invoke(str(showcase_root), "--force", "--no-cache", "--json", str(target))

    data = json.loads(target.read_text(encoding="utf-8"))

    assert from_data(Tour, data["tour"]) == build_tour(showcase_root, use_cache=False).tour


def test_json_is_byte_identical_utf8_with_lf(showcase_root: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    invoke(str(showcase_root), "--force", "--no-cache", "--json", str(first))
    invoke(str(showcase_root), "--force", "--no-cache", "--json", str(second))

    raw = first.read_bytes()
    assert raw == second.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"}\n")


def test_foreign_json_file_is_not_overwritten(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "data.json"
    target.write_text('{"mine": true}\n', encoding="utf-8")

    result = invoke(str(repo.root), "--json", str(target))

    assert result.exit_code == 4
    assert "--force" in result.output
    assert target.read_text(encoding="utf-8") == '{"mine": true}\n'
    assert not (repo.root / "TOUR.md").exists()


def test_unparseable_json_file_is_not_overwritten(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "notes.json"
    target.write_text("not json at all", encoding="utf-8")

    result = invoke(str(repo.root), "--json", str(target))

    assert result.exit_code == 4
    assert target.read_text(encoding="utf-8") == "not json at all"


def test_force_overwrites_foreign_json(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "data.json"
    target.write_text('{"mine": true}\n', encoding="utf-8")

    result = invoke(str(repo.root), "--json", str(target), "--force")

    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text(encoding="utf-8"))["generator"] == "repotour"


def test_regenerating_over_own_json_is_allowed(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "tour.json"
    invoke(str(repo.root), "--json", str(target))

    result = invoke(str(repo.root), "--json", str(target))

    assert result.exit_code == 0, result.output
