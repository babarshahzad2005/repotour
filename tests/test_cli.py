from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repotour import __version__
from repotour.cli import app
from tests.conftest import GoldenCheck
from tests.fixtures.repos import minimal

runner = CliRunner()


def run_repotour(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_tour_matches_golden(tmp_path: Path, golden: GoldenCheck) -> None:
    repo = minimal(tmp_path)

    run_repotour(str(repo.root))

    golden("minimal", (repo.root / "TOUR.md").read_bytes().decode("utf-8"))


def test_meta_names_repo_commit_and_version(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    head = repo.commit("Touch", {"app/main.py": "def main() -> None:\n    pass\n"})

    run_repotour(str(repo.root))

    text = (repo.root / "TOUR.md").read_text(encoding="utf-8")
    assert "minimal" in text
    assert head in text
    assert __version__ in text


def test_output_is_byte_identical_across_runs(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    tour = repo.root / "TOUR.md"

    run_repotour(str(repo.root))
    first = tour.read_bytes()
    run_repotour(str(repo.root))

    assert tour.read_bytes() == first


def test_output_is_utf8_with_lf_line_endings(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    run_repotour(str(repo.root))

    data = (repo.root / "TOUR.md").read_bytes()
    assert b"\r" not in data
    data.decode("utf-8")
    assert data.endswith(b"\n")


def test_out_option_writes_to_given_path(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "elsewhere" / "tour.md"

    output = run_repotour(str(repo.root), "--out", str(target))

    assert target.exists()
    assert not (repo.root / "TOUR.md").exists()
    assert str(target) in output


def test_summary_reports_output_and_warning_count(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    output = run_repotour(str(repo.root))

    assert "TOUR.md" in output
    assert "0 warnings" in output
