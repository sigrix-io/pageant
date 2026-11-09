"""Each lesson's YouTube upload (``pageant.youtube``): written from its page, and held to what YouTube refuses.

Moved from sigrix-io/bailey's ``tests/test_lesson_bundles.py`` with the module. What every
description ends with is a product's :class:`~pageant.youtube.Product` now, where Bailey's were
constants of its own; the rules are YouTube's and stay as they were: a title of 100 characters at
most, no ``<`` or ``>``, a description of 5,000 bytes at most, tags of 500 characters as YouTube
counts them, and chapters YouTube shows. So is each tag, which is one word. A lesson that breaks one
leaves no upload written.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from pageant import bundle, timeline, youtube

FIRST = bundle.Page(
    folder="first-note",
    slug="notebook-lesson-1-your-first-note",
    title="Notebook lesson 1: your first note",
    summary="Write a note and add it, and see where it goes.",
    body="## What you will see\n",
)
SECOND = bundle.Page(
    folder="find-a-note",
    slug="notebook-lesson-2-find-a-note",
    title="Notebook lesson 2: find a note",
    summary="Search the notes.",
    body="## What you will see\n",
)
PATH = bundle.LearningPath(
    title="Notebook: getting started",
    audience="New to Notebook",
    description="Two short lessons.",
    lessons=(FIRST, SECOND),
    site="https://learn.example.com/",
)
PRODUCT = youtube.Product(
    name="Notebook",
    about="Notebook keeps your notes on one page.",
    link="https://example.com/notebook",
    all_lessons="https://learn.example.com/learn/tag/notebook",
    scripted="Its answers are scripted, so the lesson is the same every time it is recorded.",
    tags=("notebook", "notesapp", "tutorial"),
)

#: A recording's chapters as ``timeline.youtube_chapters`` writes them.
CHAPTERS = "0:00 Finding your way\n0:19 1 · Write a note\n0:38 2 · Add it\n1:20 3 · Find it again\n"


def _recorded(out: Path, text: str = CHAPTERS) -> None:
    for page in PATH.lessons:
        (out / page.folder).mkdir(parents=True, exist_ok=True)
        (out / page.folder / "chapters.txt").write_text(text, encoding="utf-8")


def test_each_lesson_gets_its_youtube_upload_written_from_its_page(tmp_path: Path) -> None:
    _recorded(tmp_path)
    link = "https://learn.example.com/go/abc123"

    written = youtube.write(tmp_path, PATH, PRODUCT, {SECOND.slug: link})

    assert written == [tmp_path / page.folder / "youtube.txt" for page in PATH.lessons]
    first = written[0].read_text(encoding="utf-8")
    assert first == (
        f"TITLE\n{FIRST.title}\n\n"
        "DESCRIPTION\n"
        f"{FIRST.summary}\n\n"
        f"Watch it with its transcript on learn.example.com: https://learn.example.com/learn/{FIRST.slug}\n\n"
        "Chapters\n"
        "0:00 Finding your way\n0:19 1 · Write a note\n0:38 2 · Add it\n1:20 3 · Find it again\n\n"
        f"{PRODUCT.scripted}\n\n"
        "Lesson 1 of 2 in Notebook: getting started. All of them: https://learn.example.com/learn/tag/notebook\n\n"
        "Notebook keeps your notes on one page.\n"
        "Get Notebook: https://example.com/notebook\n\n"
        "TAGS\nnotebook, notesapp, tutorial\n"
    )
    second = written[1].read_text(encoding="utf-8")
    assert f"on learn.example.com: {link}\n" in second, "the tracked link made for its post"
    assert f"/learn/{SECOND.slug}" not in second
    assert "Lesson 2 of 2 in Notebook: getting started." in second


def test_a_product_with_nothing_scripted_says_nothing_of_it(tmp_path: Path) -> None:
    upload = youtube.upload_for(
        FIRST, number=1, path=PATH, product=dataclasses.replace(PRODUCT, scripted=""), chapters_text=CHAPTERS
    )

    assert "1:20 3 · Find it again\n\nLesson 1 of 2" in upload.description


def test_the_chapters_the_recorder_writes_are_ones_youtube_shows() -> None:
    marks = [
        timeline.Mark(0.4, "Finding your way"),
        timeline.Mark(19.2, "1 · Choose your AI"),
        timeline.Mark(38.0, "2 · Install a solution"),
        timeline.Mark(80.5, "3 · Give it documents"),
    ]
    written = timeline.youtube_chapters(timeline.chapters(marks, 133.0))

    assert youtube.chapters(written) == [
        (0, "Finding your way"),
        (19, "1 · Choose your AI"),
        (38, "2 · Install a solution"),
        (80, "3 · Give it documents"),
    ]
    assert youtube.chapters("0:00 One\n0:30 Two\n1:02:05 Three\n") == [(0, "One"), (30, "Two"), (3725, "Three")]


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("0:00 One\n0:30 Two\n", "3 or more"),
        ("0:05 One\n0:30 Two\n1:00 Three\n", "YouTube wants 0:00"),
        ("0:00 One\n0:30 Two\n0:35 Three\n", "at least 10 s"),
        ("0:00 One\n0:30 Two\nlater Three\n", "not a time and a title"),
    ],
)
def test_chapters_youtube_would_not_show_stop_the_command(text: str, says: str) -> None:
    with pytest.raises(ValueError, match=re.escape(says)):
        youtube.chapters(text)


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"title": "x" * 101}, "YouTube takes 100"),
        ({"title": "Notebook <lesson>"}, "its title holds < or >"),
        ({"summary": "a > b"}, "its description holds < or >"),
        ({"summary": "é" * 2600}, "YouTube takes 5000"),
    ],
)
def test_what_youtube_refuses_stops_the_command(change: dict[str, str], says: str) -> None:
    page = dataclasses.replace(FIRST, **change)

    with pytest.raises(ValueError, match=re.escape(says)):
        youtube.upload_for(page, number=1, path=PATH, product=PRODUCT, chapters_text=CHAPTERS)


def test_the_tags_are_held_to_youtubes_count() -> None:
    assert youtube._tags_length(("ab", "cd")) == len("ab,cd")
    assert youtube._tags_length(()) == 0
    too_many = dataclasses.replace(PRODUCT, tags=tuple(f"tagnumber{n}" for n in range(60)))
    with pytest.raises(ValueError, match="it takes 500"):
        youtube.upload_for(FIRST, number=1, path=PATH, product=too_many, chapters_text=CHAPTERS)


@pytest.mark.parametrize("tag", ["notes app", "notes\tapp", " notes app"])
def test_a_tag_holding_a_space_stops_the_command_and_says_how_to_write_it(tmp_path: Path, tag: str) -> None:
    _recorded(tmp_path)
    spaced = dataclasses.replace(PRODUCT, tags=("notebook", tag))

    with pytest.raises(ValueError, match=re.escape(f"the tag {tag!r} holds a space; each tag is one word: 'notesapp'")):
        youtube.write(tmp_path, PATH, spaced)
    assert not list(tmp_path.rglob("youtube.txt")), "no upload is written"


def test_a_lessons_youtube_cut_is_the_recording_its_upload_is_written_for(tmp_path: Path) -> None:
    _recorded(tmp_path)
    # The first lesson's YouTube cut, recorded since: its chapters are timed to that video.
    cut = tmp_path / bundle.YOUTUBE_CUT / FIRST.folder
    cut.mkdir(parents=True)
    (cut / "chapters.txt").write_text(
        "0:00 Finding your way\n0:21 1 · Write a note\n0:40 2 · Add it\n1:22 3 · Find it again\n", encoding="utf-8"
    )

    written = youtube.write(tmp_path, PATH, PRODUCT)

    assert written == [cut / youtube.UPLOAD, tmp_path / SECOND.folder / youtube.UPLOAD]
    assert "0:21 1 · Write a note" in (cut / youtube.UPLOAD).read_text(encoding="utf-8")
    assert not (tmp_path / FIRST.folder / youtube.UPLOAD).exists(), "the lesson's own recording is not the upload"


def test_a_lesson_that_breaks_a_rule_leaves_no_upload_written(tmp_path: Path) -> None:
    _recorded(tmp_path)
    (tmp_path / SECOND.folder / "chapters.txt").write_text("0:00 Only\n", encoding="utf-8")

    with pytest.raises(ValueError, match="3 or more"):
        youtube.write(tmp_path, PATH, PRODUCT)
    assert not list(tmp_path.rglob("youtube.txt")), "the first one is not written either"


def test_a_link_names_a_lesson_and_is_an_https_one(tmp_path: Path) -> None:
    _recorded(tmp_path)

    with pytest.raises(ValueError, match="No lesson has this slug: notebook-lesson-9"):
        youtube.write(tmp_path, PATH, PRODUCT, {"notebook-lesson-9": "https://learn.example.com/go/x"})
    with pytest.raises(ValueError, match="starts with https://"):
        youtube.write(tmp_path, PATH, PRODUCT, {FIRST.slug: "learn.example.com/go/x"})


def test_a_lesson_not_recorded_yet_is_named(tmp_path: Path) -> None:
    _recorded(tmp_path)
    (tmp_path / FIRST.folder / "chapters.txt").unlink()

    with pytest.raises(FileNotFoundError, match=re.escape(f"Record these lessons first; missing: {FIRST.folder}/")):
        youtube.write(tmp_path, PATH, PRODUCT)
