from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from repotour.cli import app
from repotour.config import CliOverrides, Config, load_config
from repotour.errors import ConfigError
from repotour.pipeline import build_tour
from tests.fixtures.repos import minimal

runner = CliRunner()


def write_config(root: Path, text: str) -> None:
    (root / ".repotour.yml").write_text(text, encoding="utf-8")


def invoke(*args: str) -> Result:
    return runner.invoke(app, list(args))


# --- loading -------------------------------------------------------------------


def test_no_config_file_means_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path) == Config()


def test_full_config_is_loaded(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        """\
version: 1
name: Demo Project
since: 3m
exclude: [generated/, "*.pb.go"]
pinned_entry_points: [app/main.py]
notes:
  app: Application code.
  scripts: Release helpers.
test_patterns: ["checks/**"]
bots: [release-robot]
ignore_revs: [0123456789abcdef0123456789abcdef01234567]
thresholds:
  bulk_commit_files: 500
  bus_factor_share: 0.9
caps:
  hotspots: 20
summaries:
  base_url: https://api.groq.com/openai/v1
  model: llama-3.1-8b-instant
""",
    )

    config = load_config(tmp_path)

    assert config.name == "Demo Project"
    assert config.since == "3m"
    assert config.exclude == ("generated/", "*.pb.go")
    assert config.pinned_entry_points == ("app/main.py",)
    assert config.notes == (("app", "Application code."), ("scripts", "Release helpers."))
    assert config.test_patterns == ("checks/**",)
    assert config.bots == ("release-robot",)
    assert config.thresholds.bulk_commit_files == 500
    assert config.thresholds.bus_factor_share == 0.9
    assert config.thresholds.bus_factor_min_files == 5
    assert config.caps.hotspots == 20
    assert config.summaries.model == "llama-3.1-8b-instant"


def test_config_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Config().since = "1y"  # type: ignore[misc]


# --- validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name: x\n", "'version: 1' is required"),
        ("", "'version: 1' is required"),
        ("version: 2\n", "unsupported config version 2"),
        ("version: '1'\n", "unsupported config version"),
        ("version: 1\nexlude: [a]\n", "unknown key 'exlude'"),
        (
            "version: 1\nthresholds:\n  bus_factor_shar: 0.5\n",
            "unknown key 'thresholds.bus_factor_shar'",
        ),
        ("version: 1\nexclude: vendor/\n", "'exclude' must be a list of strings"),
        ("version: 1\ncaps:\n  hotspots: ten\n", "'caps.hotspots' must be an integer"),
        ("version: 1\ncaps:\n  hotspots: true\n", "'caps.hotspots' must be an integer"),
        ("version: 1\ncaps:\n  reading_order: 0\n", "'caps.reading_order' must be at least 1"),
        ("version: 1\nthresholds:\n  bus_factor_share: 1.5\n", "'thresholds.bus_factor_share'"),
        ("version: 1\nsince: six months\n", "'since' must be a duration"),
        ("version: 1\nnotes: [a, b]\n", "'notes' must be a mapping"),
        ("version: 1\nnotes:\n  app: 3\n", "'notes.app' must be a string"),
        ("- version: 1\n", "must be a mapping"),
        ("version: 1\nexclude: [unclosed\n", "not valid YAML"),
    ],
)
def test_invalid_config_raises(tmp_path: Path, text: str, message: str) -> None:
    write_config(tmp_path, text)

    with pytest.raises(ConfigError, match=None) as excinfo:
        load_config(tmp_path)

    assert message in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_invalid_config_exits_2_naming_the_key(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    write_config(repo.root, "version: 1\nexlude: [vendor/]\n")

    result = invoke(str(repo.root))

    assert result.exit_code == 2
    assert "exlude" in result.output
    assert ".repotour.yml" in result.output
    assert not (repo.root / "TOUR.md").exists()


# --- CLI overrides -----------------------------------------------------------------


def test_cli_flag_overrides_config(tmp_path: Path) -> None:
    write_config(tmp_path, "version: 1\nsince: 3m\n")

    assert load_config(tmp_path, CliOverrides(since="1y")).since == "1y"
    assert load_config(tmp_path, CliOverrides()).since == "3m"


def test_invalid_since_flag_exits_2(tmp_path: Path) -> None:
    repo = minimal(tmp_path)

    result = invoke(str(repo.root), "--since", "forever")

    assert result.exit_code == 2
    assert "since" in result.output


# --- config hash -------------------------------------------------------------------


def test_hash_is_stable_and_changes_with_effective_settings(tmp_path: Path) -> None:
    default = Config().config_hash()

    assert default == Config().config_hash()
    assert len(default) == 64
    assert Config(since="1y").config_hash() != default
    assert dataclasses.replace(Config(), bots=("ci-bot",)).config_hash() != default


def test_explicit_defaults_hash_like_no_config(tmp_path: Path) -> None:
    write_config(tmp_path, "version: 1\nsince: 6m\ncaps:\n  hotspots: 10\n")

    assert load_config(tmp_path).config_hash() == Config().config_hash()


def test_cli_override_changes_hash(tmp_path: Path) -> None:
    assert load_config(tmp_path, CliOverrides(since="1y")).config_hash() != Config().config_hash()


def test_config_hash_appears_in_tour_meta(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    write_config(repo.root, "version: 1\nsince: 1y\n")

    tour = build_tour(repo.root).tour
    invoke(str(repo.root))

    expected = Config(since="1y").config_hash()
    assert tour.meta.config_hash == expected
    assert expected[:12] in (repo.root / "TOUR.md").read_text(encoding="utf-8")


def test_name_overrides_repository_name(tmp_path: Path) -> None:
    repo = minimal(tmp_path)
    write_config(repo.root, "version: 1\nname: Friendly Name\n")

    assert build_tour(repo.root).tour.meta.repo_name == "Friendly Name"
