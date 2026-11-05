from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def fresh_lesson_imports() -> Iterator[None]:
    """A lesson or pages file loaded in one test is not the one the next test imports by name.

    ``pageant.cli.load`` puts a file's folder first on the import path and registers its module, as
    running the file would; a command runs once, but a test suite loads many folders' ``pages.py``.
    """

    path = list(sys.path)
    before = set(sys.modules)
    yield
    sys.path[:] = path
    for name in set(sys.modules) - before:
        if name.startswith("_pageant_") or name in {"pages", "lesson"}:
            del sys.modules[name]
