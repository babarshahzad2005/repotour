"""`--format html` writes one self-contained page that works offline."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repotour.cli import app
from repotour.output import MARKER
from repotour.render.html import MERMAID_SHA256, MERMAID_VERSION, mermaid_bundle
from tests.conftest import GoldenCheck
from tests.fixtures.builder import FixtureRepo
from tests.fixtures.repos import graph_showcase, minimal

runner = CliRunner()
BUNDLE_PLACEHOLDER = f"/* mermaid {MERMAID_VERSION} bundle */"


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = graph_showcase(tmp_path_factory.mktemp("html")).root
    result = invoke(str(root), "--format", "html", "--no-cache")
    assert result.exit_code == 0, result.output
    return (root / "TOUR.html").read_bytes().decode("utf-8")


def test_html_matches_golden(page: str, golden: GoldenCheck) -> None:
    golden("graph-showcase.html", page.replace(mermaid_bundle(), BUNDLE_PLACEHOLDER))


def test_page_starts_with_marker_then_doctype(page: str) -> None:
    assert page.startswith(MARKER + "\n<!doctype html>\n")


def test_page_embeds_the_pinned_mermaid_bundle(page: str) -> None:
    bundle = mermaid_bundle()
    assert hashlib.sha256(bundle.encode("utf-8")).hexdigest() == MERMAID_SHA256
    assert page.count(bundle) == 1
    assert "</script" not in bundle


def test_page_loads_nothing_from_the_network(page: str) -> None:
    without_bundle = page.replace(mermaid_bundle(), "")
    assert re.search(r"<(script|link|img|iframe)[^>]*\s(src|href)=", without_bundle) is None
    assert "http://" not in without_bundle.split("<body>")[0]


def test_dependency_graph_is_left_for_mermaid_to_draw(page: str) -> None:
    assert '<pre class="mermaid">' in page
    assert "flowchart" in page
    assert '<code class="language-mermaid">' not in page


def test_every_markdown_section_appears(page: str) -> None:
    for heading in ("Overview", "Entry points", "Start here", "Dependency graph"):
        assert f"<h2>{heading}</h2>" in page


def test_repository_text_cannot_inject_markup(tmp_path: Path) -> None:
    repo = FixtureRepo.create(tmp_path, "hostile")
    repo.commit(
        "Initial commit",
        {
            "README.md": "# hostile\n",
            ".repotour.yml": (
                "version: 1\nnotes:\n"
                '  ui: "<script>alert(1)</script> <img src=x onerror=alert(2)> '
                '[x](javascript:alert(3))"\n'
            ),
            "ui/app.py": "print('hi')\n",
        },
    )

    result = invoke(str(repo.root), "--format", "html", "--no-cache")

    assert result.exit_code == 0, result.output
    page = (repo.root / "TOUR.html").read_text(encoding="utf-8").replace(mermaid_bundle(), "")
    assert "<script>alert" not in page
    assert "<img" not in page
    assert "&lt;img src=x onerror=alert(2)&gt;" in page
    assert 'href="javascript:' not in page


def test_default_path_follows_the_format(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    result = invoke(str(repo.root), "--format", "html")

    assert result.exit_code == 0, result.output
    assert (repo.root / "TOUR.html").exists()
    assert not (repo.root / "TOUR.md").exists()
    assert "TOUR.html" in result.output


def test_out_overrides_the_default_path(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    target = tmp_path / "site" / "index.html"

    result = invoke(str(repo.root), "--format", "html", "--out", str(target))

    assert result.exit_code == 0, result.output
    assert target.read_text(encoding="utf-8").startswith(MARKER)


def test_foreign_html_is_not_overwritten(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    existing = repo.root / "TOUR.html"
    existing.write_text("<!doctype html><p>mine</p>\n", encoding="utf-8")

    result = invoke(str(repo.root), "--format", "html")

    assert result.exit_code == 4
    assert existing.read_text(encoding="utf-8") == "<!doctype html><p>mine</p>\n"


def test_regenerating_own_html_is_allowed(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root), "--format", "html")

    result = invoke(str(repo.root), "--format", "html")

    assert result.exit_code == 0, result.output


def test_page_is_byte_identical_across_runs(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    invoke(str(repo.root), "--format", "html")
    first = (repo.root / "TOUR.html").read_bytes()

    invoke(str(repo.root), "--format", "html", "--no-cache")

    assert (repo.root / "TOUR.html").read_bytes() == first
    assert b"\r\n" not in first


def test_unknown_format_is_rejected(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    result = invoke(str(repo.root), "--format", "pdf")

    assert result.exit_code == 2
