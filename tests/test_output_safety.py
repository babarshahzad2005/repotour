from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner, Result

from repotour.cli import app
from repotour.output import MARKER
from tests.conftest import GoldenCheck
from tests.fixtures.repos import minimal

runner = CliRunner()


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


def test_generated_tour_starts_with_marker(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    invoke(str(repo.root))

    assert (repo.root / "TOUR.md").read_text(encoding="utf-8").startswith(MARKER + "\n")


def test_regenerating_over_own_output_is_allowed(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root))

    result = invoke(str(repo.root))

    assert result.exit_code == 0, result.output


def test_existing_hand_written_file_is_not_overwritten(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    hand_written = repo.root / "TOUR.md"
    hand_written.write_text("# My own tour\n", encoding="utf-8")

    result = invoke(str(repo.root))

    assert result.exit_code == 4
    assert "--force" in result.output
    assert "--out" in result.output
    assert hand_written.read_text(encoding="utf-8") == "# My own tour\n"


def test_force_overwrites_hand_written_file(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    (repo.root / "TOUR.md").write_text("# My own tour\n", encoding="utf-8")

    result = invoke(str(repo.root), "--force")

    assert result.exit_code == 0, result.output
    assert (repo.root / "TOUR.md").read_text(encoding="utf-8").startswith(MARKER)


def test_out_avoids_the_conflict(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    (repo.root / "TOUR.md").write_text("# My own tour\n", encoding="utf-8")
    other = repo.root / "docs" / "TOUR.md"

    result = invoke(str(repo.root), "--out", str(other))

    assert result.exit_code == 0, result.output
    assert other.exists()


def test_warnings_render_in_closing_section(tmp_path: Path, golden: GoldenCheck) -> None:
    clone = minimal(tmp_path).shallow_clone("shallow")

    invoke(str(clone.root))

    text = (clone.root / "TOUR.md").read_text(encoding="utf-8")
    assert text.rstrip().splitlines()[-1].startswith("- History truncated")
    golden("shallow", text)


def test_no_warnings_section_without_warnings(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    invoke(str(repo.root))

    assert "## Warnings" not in (repo.root / "TOUR.md").read_text(encoding="utf-8")


def test_strict_with_warnings_exits_3_but_still_writes(tmp_path: Path) -> None:
    clone = minimal(tmp_path).shallow_clone("shallow")

    result = invoke(str(clone.root), "--strict")

    assert result.exit_code == 3
    assert "1 warning" in result.output
    assert (clone.root / "TOUR.md").exists()


def test_strict_without_warnings_exits_0(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    result = invoke(str(repo.root), "--strict")

    assert result.exit_code == 0, result.output


def test_every_documented_exit_code(tmp_path: Path) -> None:
    """Exit codes 0-4, as documented in the CLI surface."""
    repo = minimal(tmp_path)
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    assert invoke(str(repo.root)).exit_code == 0
    assert invoke(str(not_a_repo)).exit_code == 1
    assert invoke(str(repo.root), "--since", "soon").exit_code == 2
    assert invoke(str(repo.root.parent / "plain-clone-missing")).exit_code == 1
    assert invoke(str(minimal_shallow(tmp_path)), "--strict").exit_code == 3
    (repo.root / "TOUR.md").write_text("hand-written\n", encoding="utf-8")
    assert invoke(str(repo.root)).exit_code == 4


def minimal_shallow(tmp_path: Path) -> Path:
    return minimal(tmp_path / "for-shallow").shallow_clone("shallow").root
