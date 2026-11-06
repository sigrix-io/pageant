"""A recorded lesson's bundle and a pack of them (``pageant.bundle``), as Sigrix's Learn import reads them.

Moved from sigrix-io/bailey's ``tests/test_lesson_bundles.py`` with the module, and held to a path
of the tests' own rather than Bailey's lessons: a page is written as the import reads it, its
YouTube link only once it has one; a pack carries exactly the files the import reads, its pages
written afresh, in the path's order; and a lesson not recorded whole stops the pack, naming what is
missing.
"""

from __future__ import annotations

import dataclasses
import json
import re
import zipfile
from pathlib import Path

import pytest

from pageant import bundle, schema

FIRST = bundle.Page(
    folder="first-note",
    slug="notebook-lesson-1-your-first-note",
    title="Notebook lesson 1: your first note",
    summary="Write a note and add it.",
    body="## What you will see\n\n- A note.\n",
    tags=("notebook", "video"),
)
SECOND = bundle.Page(
    folder="find-a-note",
    slug="notebook-lesson-2-find-a-note",
    title="Notebook lesson 2: find a note",
    summary="Search the notes.",
    body="## What you will see\n\n- A search.\n",
    category="patterns",
)
PATH = bundle.LearningPath(
    title="Notebook: getting started",
    audience="New to Notebook",
    description="Two short lessons.",
    lessons=(FIRST, SECOND),
)
RECORDED = ("video.mp4", "captions.vtt", "chapters.vtt", "cover.jpg", "chapters.txt")


def _recorded(out: Path, *, leave_out: str | None = None) -> None:
    """The folders a recording leaves: media under the bundle's names, an old page, YouTube's chapters."""

    for page in PATH.lessons:
        folder = out / page.folder
        folder.mkdir(parents=True)
        for name in RECORDED:
            if f"{page.folder}/{name}" != leave_out:
                (folder / name).write_bytes(f"{page.folder}/{name}".encode())
        (folder / "lesson.json").write_text('{"title": "an old page"}', encoding="utf-8")


def test_a_page_is_written_as_the_import_reads_it(tmp_path: Path) -> None:
    written = bundle.write_page(FIRST, tmp_path)

    assert written == tmp_path / "lesson.json"
    data = json.loads(written.read_text(encoding="utf-8"))
    assert data == {
        "format": "sigrix-lesson/1",
        "slug": "notebook-lesson-1-your-first-note",
        "title": "Notebook lesson 1: your first note",
        "summary": "Write a note and add it.",
        "category": "tutorials",
        "tags": ["notebook", "video"],
        "body_markdown": "## What you will see\n\n- A note.\n",
    }
    assert schema.problems(data, schema.load(schema.LESSON)) == []


def test_a_youtube_link_is_written_once_a_page_has_one() -> None:
    assert "youtube_url" not in bundle.page_json(FIRST), "left out, so an import keeps the page's link"
    uploaded = dataclasses.replace(FIRST, youtube_url="https://www.youtube.com/watch?v=abcdefghijk")
    assert bundle.page_json(uploaded)["youtube_url"] == "https://www.youtube.com/watch?v=abcdefghijk"


def test_a_page_is_published_at_its_slug_on_the_paths_site() -> None:
    assert PATH.page_url(FIRST) == "https://sigrix.io/learn/notebook-lesson-1-your-first-note"
    elsewhere = dataclasses.replace(PATH, site="https://learn.example.com/")
    assert elsewhere.page_url(FIRST) == "https://learn.example.com/learn/notebook-lesson-1-your-first-note"


def test_a_pack_holds_each_lesson_the_import_reads_and_the_path_in_order(tmp_path: Path) -> None:
    _recorded(tmp_path)

    made = bundle.pack(tmp_path, PATH, tmp_path / "packs" / "notebook-lessons.zip")

    assert made == tmp_path / "packs" / "notebook-lessons.zip"
    with zipfile.ZipFile(made) as archive:
        expected = [
            f"notebook-lessons/{page.folder}/{name}"
            for page in PATH.lessons
            for name in ("lesson.json", "video.mp4", "captions.vtt", "chapters.vtt", "cover.jpg")
        ]
        assert archive.namelist() == [*expected, "notebook-lessons/path.json"], (
            "nothing the import does not read, YouTube's chapters left out"
        )
        page = json.loads(archive.read("notebook-lessons/first-note/lesson.json"))
        assert page["slug"] == FIRST.slug, "the page is written afresh, not the one left on disk"
        assert schema.problems(page, schema.load(schema.LESSON)) == []
        assert archive.read("notebook-lessons/first-note/video.mp4") == b"first-note/video.mp4"
        assert archive.getinfo("notebook-lessons/first-note/video.mp4").compress_type == zipfile.ZIP_STORED
        assert archive.getinfo("notebook-lessons/first-note/cover.jpg").compress_type == zipfile.ZIP_STORED
        assert archive.getinfo("notebook-lessons/first-note/captions.vtt").compress_type == zipfile.ZIP_DEFLATED
        path = json.loads(archive.read("notebook-lessons/path.json"))
        assert path == {
            "format": "sigrix-learning-path/1",
            "title": "Notebook: getting started",
            "audience": "New to Notebook",
            "description": "Two short lessons.",
            "lessons": [FIRST.slug, SECOND.slug],
        }
        assert schema.problems(path, schema.load(schema.PATH)) == []
    assert json.loads((tmp_path / "first-note" / "lesson.json").read_text(encoding="utf-8"))["slug"] == FIRST.slug


def test_a_lesson_not_recorded_whole_stops_the_pack_and_names_what_is_missing(tmp_path: Path) -> None:
    gone = f"{SECOND.folder}/chapters.vtt"
    _recorded(tmp_path, leave_out=gone)

    with pytest.raises(FileNotFoundError, match=re.escape(f"missing: {gone}")):
        bundle.pack(tmp_path, PATH, tmp_path / "notebook-lessons.zip")
    assert not (tmp_path / "notebook-lessons.zip").exists()
