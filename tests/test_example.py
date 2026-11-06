"""The example lesson the package ships (``src/pageant/example``), read as a person starting from it reads it.

``pageant example`` writes it out, and CI's record job records it from a fresh install of the
wheel. These hold what can be held without recording it: its page and its path are ones the
format's schemas take, its lesson file names that page, every line its narration has is said and every
line it says is in its narration, the site it films holds every file its page asks for, and its
upload text is within what YouTube takes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import ModuleType

import pytest

from pageant import bundle, cli, schema, youtube


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The example as ``pageant example`` writes it out, so nothing is loaded from the package's own folder."""

    target = tmp_path_factory.mktemp("example") / "notebook"
    assert cli.main(["example", str(target)]) == 0
    return target


@pytest.fixture
def pages(written: Path) -> ModuleType:
    return cli.load(written / "pages.py")


def _lesson(written: Path) -> ast.Module:
    return ast.parse((written / "lesson.py").read_text(encoding="utf-8"))


def test_its_pages_and_its_path_are_ones_the_formats_schemas_take(pages: ModuleType) -> None:
    assert pages.PATH.lessons, "the example has a lesson"
    for page in pages.PATH.lessons:
        assert schema.problems(bundle.page_json(page), schema.load(schema.LESSON)) == [], page.slug
    assert schema.problems(bundle.path_json(pages.PATH), schema.load(schema.PATH)) == []
    bundle.check(pages.PATH)
    assert len({page.folder for page in pages.PATH.lessons}) == len(pages.PATH.lessons)


def test_its_lesson_file_names_a_page_of_its_path(written: Path, pages: ModuleType) -> None:
    named = [
        keyword.value
        for node in ast.walk(_lesson(written))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Lesson"
        for keyword in node.keywords
        if keyword.arg == "page"
    ]

    [page] = named
    assert isinstance(page, ast.Attribute) and isinstance(page.value, ast.Name) and page.value.id == "pages"
    assert getattr(pages, page.attr) in pages.PATH.lessons


def test_every_line_of_its_narration_is_said_and_it_says_nothing_else(written: Path) -> None:
    tree = _lesson(written)
    [narration] = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and [getattr(target, "id", "") for target in node.targets] == ["NARRATION"]
    ]
    assert isinstance(narration, ast.Dict)
    lines = {key.value for key in narration.keys if isinstance(key, ast.Constant)}
    said = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"say", "voice"}
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }

    assert len(lines) > 3, "the narration was read"
    assert said == lines


def test_the_site_it_films_holds_every_file_its_page_asks_for(written: Path) -> None:
    site = written / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    asked = set(re.findall(r'(?:src|href)="([^"]+)"', page))

    assert {"app.js", "style.css", "mark.svg"} <= asked
    assert [name for name in asked if not (site / name).is_file()] == []
    assert "Content-Security-Policy" in page, "filmed under a policy of its own, as a product's page is"


def test_its_upload_is_one_youtube_takes(pages: ModuleType) -> None:
    # The chapters as the recording on 2026-11-05 wrote them; CI's record job writes them afresh.
    chapters = "0:00 The page\n0:13 1 · Write a note\n0:27 2 · A terminal\n"
    for number, page in enumerate(pages.PATH.lessons, start=1):
        upload = youtube.upload_for(page, number=number, path=pages.PATH, product=pages.PRODUCT, chapters_text=chapters)
        assert upload.title == page.title
        assert pages.PATH.page_url(page) in upload.description
