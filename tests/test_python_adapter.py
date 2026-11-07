from __future__ import annotations

import pytest

from repotour.languages.base import RawImport
from repotour.languages.python import PythonAdapter

ADAPTER = PythonAdapter()


def imports_of(source: str) -> list[RawImport]:
    result = ADAPTER.parse(source.encode("utf-8"))
    assert not result.has_error
    return list(result.imports)


def test_plain_and_aliased_imports() -> None:
    assert imports_of("import os, a.b as c\n") == [
        RawImport(module="os", names=(), line=1),
        RawImport(module="a.b", names=(), line=1),
    ]


def test_from_imports_keep_names_and_relative_dots() -> None:
    source = "from . import x\nfrom ..pkg.mod import y, z as zz\nfrom pkg import *\n"

    assert imports_of(source) == [
        RawImport(module=".", names=("x",), line=1),
        RawImport(module="..pkg.mod", names=("y", "z"), line=2),
        RawImport(module="pkg", names=(), line=3),
    ]


def test_nested_imports_are_static_too() -> None:
    source = "def f():\n    import late\n\nif True:\n    from x import y\n"

    assert [i.module for i in imports_of(source)] == ["late", "x"]


def test_dynamic_imports_are_ignored() -> None:
    source = "import importlib\nm = importlib.import_module('a.b')\nn = __import__('c')\n"

    assert [i.module for i in imports_of(source)] == ["importlib"]


def test_syntax_errors_are_reported() -> None:
    assert ADAPTER.parse(b"def broken(:\n    pass\n").has_error


@pytest.mark.parametrize("path", ["a.py", "pkg/types.pyi"])
def test_handles_python_extensions(path: str) -> None:
    assert ADAPTER.handles(path)
