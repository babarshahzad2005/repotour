from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"

GoldenCheck = Callable[[str, str], None]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Rewrite golden tours from the current output instead of comparing.",
    )


@pytest.fixture
def golden(request: pytest.FixtureRequest) -> GoldenCheck:
    """Compare rendered output with tests/golden/<name>.md, byte for byte."""
    update = bool(request.config.getoption("--update-goldens"))

    def check(name: str, actual: str) -> None:
        path = GOLDEN_DIR / f"{name}.md"
        if update:
            path.write_bytes(actual.encode("utf-8"))
            return
        assert path.exists(), f"Missing golden {path.name}; run `pytest --update-goldens`."
        expected = path.read_bytes().decode("utf-8")
        assert actual == expected, f"Output differs from golden {path.name}."

    return check
