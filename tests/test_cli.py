"""The ``pageant`` command (``pageant.cli``): what each command reads, writes and prints, and what stops it.

A lesson file and a pages file load as running them would: their own folder first on the import
path, so a lesson imports the pages beside it. Recording itself is CI's record job, which films the
example from a fresh install; here ``pageant record`` drives a stand-in studio, so what is held is
the command: which file it loads, where it records to, and what it says when recording's parts
are not installed.
"""

from __future__ import annotations

import json
import shutil
import sys
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest

import pageant
from pageant import cli

PAGES = """
from pageant.bundle import LearningPath, Page
from pageant.youtube import Product

FIRST = Page(
    folder="first-note",
    slug="notebook-lesson-1-your-first-note",
    title="Notebook lesson 1: your first note",
    summary="Write a note.",
    body="## What you will see\\n",
)
PATH = LearningPath(
    title="Notebook: getting started",
    audience="New to Notebook",
    description="One lesson.",
    lessons=(FIRST,),
    site="https://example.com",
)
PRODUCT = Product(
    name="Notebook",
    about="Notebook keeps notes.",
    link="https://example.com/notebook",
    all_lessons="https://example.com/learn",
    scripted="",
)
"""


def _project(tmp_path: Path) -> Path:
    pages = tmp_path / "lessons" / "pages.py"
    pages.parent.mkdir()
    pages.write_text(PAGES, encoding="utf-8")
    return pages


def _recorded(out: Path) -> None:
    folder = out / "first-note"
    folder.mkdir(parents=True)
    for name in ("video.mp4", "captions.vtt", "chapters.vtt", "cover.jpg"):
        (folder / name).write_bytes(name.encode())
    (folder / "chapters.txt").write_text("0:00 One\n0:15 Two\n0:30 Three\n", encoding="utf-8")


def test_pack_writes_the_pack_beside_the_recordings_or_says_what_to_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pages = _project(tmp_path)
    out = pages.parent / "out"

    assert cli.main(["pack", str(pages)]) == 1
    assert "Record these lessons first; missing: first-note/video.mp4" in capsys.readouterr().err

    _recorded(out)
    assert cli.main(["pack", str(pages)]) == 0
    made = out / cli.PACK
    assert capsys.readouterr().out == f"{made}\n"
    with zipfile.ZipFile(made) as archive:
        assert archive.namelist()[0] == "lessons/first-note/lesson.json"

    elsewhere = tmp_path / "notebook-lessons.zip"
    assert cli.main(["pack", str(pages), "--out", str(out), "--zip", str(elsewhere)]) == 0
    with zipfile.ZipFile(elsewhere) as archive:
        assert archive.namelist()[-1] == "notebook-lessons/path.json"


def test_youtube_text_writes_each_upload_or_says_what_stops_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pages = _project(tmp_path)
    out = tmp_path / "recorded"

    assert cli.main(["youtube-text", str(pages), "--out", str(out)]) == 1
    assert "Record these lessons first" in capsys.readouterr().err

    _recorded(out)
    link = "notebook-lesson-1-your-first-note=https://example.com/go/abc"
    assert cli.main(["youtube-text", str(pages), "--out", str(out), "--link", link]) == 0
    written = out / "first-note" / "youtube.txt"
    assert capsys.readouterr().out == f"{written}\n"
    assert "on example.com: https://example.com/go/abc\n" in written.read_text(encoding="utf-8")

    plain = "notebook-lesson-1-your-first-note=http://example.com/go/abc"
    assert cli.main(["youtube-text", str(pages), "--out", str(out), "--link", plain]) == 1
    assert "a link starts with https://" in capsys.readouterr().err


@pytest.mark.parametrize("given", ["https://example.com/go/abc", "=https://example.com/go/abc", "first-note= "])
def test_a_link_is_a_slug_and_an_address(tmp_path: Path, capsys: pytest.CaptureFixture[str], given: str) -> None:
    pages = _project(tmp_path)

    with pytest.raises(SystemExit) as stopped:
        cli.main(["youtube-text", str(pages), "--link", given])
    assert stopped.value.code == 2
    assert "give a link as <slug>=<link>" in capsys.readouterr().err


def test_a_file_that_is_not_there_or_names_nothing_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["pack", str(tmp_path / "pages.py")]) == 1
    assert "There is no file at" in capsys.readouterr().err

    pages = tmp_path / "pages.py"
    pages.write_text("FIRST = 1\n", encoding="utf-8")
    assert cli.main(["pack", str(pages)]) == 1
    assert capsys.readouterr().err == f"{pages} names no PATH: a pageant.bundle.LearningPath.\n"

    pages.write_text(PAGES.replace("PRODUCT = Product(", "OTHER = Product("), encoding="utf-8")
    assert cli.main(["youtube-text", str(pages)]) == 1
    assert "names no PRODUCT: a pageant.youtube.Product." in capsys.readouterr().err


class _Lesson:
    """What the stand-in studio's lessons are: the page they name."""

    def __init__(self, page: Any) -> None:
        self.page = page


@pytest.fixture
def stand_in_studio(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """``pageant.studio`` as a stand-in that records and rehearses nothing, and says what it was asked to."""

    asked: list[dict[str, Any]] = []

    async def record(
        lesson: _Lesson, out: Path, *, chromium: str | None = None, keep_work: bool = False, youtube: bool = False
    ) -> dict[str, str]:
        asked.append(
            {
                "to": "record",
                "lesson": lesson,
                "out": out,
                "chromium": chromium,
                "keep_work": keep_work,
                "youtube": youtube,
            }
        )
        return {"bundle": str(out / lesson.page.folder)}

    async def rehearse(
        lesson: _Lesson, out: Path, *, chromium: str | None = None, keep_work: bool = False
    ) -> dict[str, str]:
        asked.append({"to": "rehearse", "lesson": lesson, "out": out, "chromium": chromium, "keep_work": keep_work})
        return {"rehearsed": lesson.page.folder}

    studio = types.ModuleType("pageant.studio")
    studio.Lesson = _Lesson  # type: ignore[attr-defined]
    studio.record = record  # type: ignore[attr-defined]
    studio.rehearse = rehearse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pageant.studio", studio)
    monkeypatch.setattr(pageant, "studio", studio, raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("PAGEANT_CHROMIUM", raising=False)
    return asked


def test_record_loads_the_lesson_beside_its_pages_and_records_it_into_out_beside_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stand_in_studio: list[dict[str, Any]],
) -> None:
    pages = _project(tmp_path)
    lesson = pages.parent / "first_note.py"
    lesson.write_text(
        "import pages\nfrom pageant.studio import Lesson\n\nLESSON = Lesson(pages.FIRST)\n", encoding="utf-8"
    )

    assert cli.main(["record", str(lesson), "--chromium", "/opt/chromium", "--keep-work"]) == 0

    [asked] = stand_in_studio
    assert asked["lesson"].page.slug == "notebook-lesson-1-your-first-note", "it imported the pages beside it"
    assert asked["out"] == pages.parent.resolve() / "out"
    assert (asked["chromium"], asked["keep_work"], asked["youtube"]) == ("/opt/chromium", True, False)
    assert json.loads(capsys.readouterr().out) == {"bundle": str(asked["out"] / "first-note")}

    monkeypatch.setenv("PAGEANT_CHROMIUM", "/from/the/environment")
    assert cli.main(["record", str(lesson), "--out", str(tmp_path / "elsewhere")]) == 0
    assert stand_in_studio[1]["out"] == tmp_path / "elsewhere"
    assert (stand_in_studio[1]["chromium"], stand_in_studio[1]["keep_work"]) == ("/from/the/environment", False)

    # The YouTube cut is the same lesson, recorded into the same out, which the studio files under youtube/.
    assert cli.main(["record", str(lesson), "--youtube"]) == 0
    assert (stand_in_studio[2]["out"], stand_in_studio[2]["youtube"]) == (pages.parent.resolve() / "out", True)


def test_rehearse_runs_the_lesson_beside_its_pages_with_no_ffmpeg_and_says_what_it_went_through(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stand_in_studio: list[dict[str, Any]],
) -> None:
    pages = _project(tmp_path)
    lesson = pages.parent / "first_note.py"
    lesson.write_text(
        "import pages\nfrom pageant.studio import Lesson\n\nLESSON = Lesson(pages.FIRST)\n", encoding="utf-8"
    )
    # A rehearsal encodes nothing, so a computer without ffmpeg rehearses.
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert cli.main(["rehearse", str(lesson), "--chromium", "/opt/chromium", "--keep-work"]) == 0

    [asked] = stand_in_studio
    assert asked["to"] == "rehearse"
    assert asked["lesson"].page.slug == "notebook-lesson-1-your-first-note", "it imported the pages beside it"
    assert asked["out"] == pages.parent.resolve() / "out"
    assert (asked["chromium"], asked["keep_work"]) == ("/opt/chromium", True)
    assert json.loads(capsys.readouterr().out) == {"rehearsed": "first-note"}

    monkeypatch.setenv("PAGEANT_CHROMIUM", "/from/the/environment")
    assert cli.main(["rehearse", str(lesson), "--out", str(tmp_path / "elsewhere")]) == 0
    assert stand_in_studio[1]["out"] == tmp_path / "elsewhere"
    assert (stand_in_studio[1]["chromium"], stand_in_studio[1]["keep_work"]) == ("/from/the/environment", False)


@pytest.mark.parametrize("command", ["record", "rehearse"])
def test_record_and_rehearse_name_a_file_without_a_lesson(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stand_in_studio: list[dict[str, Any]], command: str
) -> None:
    lesson = tmp_path / "lesson.py"
    lesson.write_text("LESSONS = []\n", encoding="utf-8")

    assert cli.main([command, str(lesson)]) == 1
    assert "names no LESSON" in capsys.readouterr().err
    assert stand_in_studio == []


@pytest.mark.parametrize("command", ["record", "rehearse"])
def test_record_and_rehearse_stop_on_a_page_the_import_would_refuse_before_anything_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stand_in_studio: list[dict[str, Any]], command: str
) -> None:
    pages = _project(tmp_path)
    pages.write_text(
        PAGES.replace('slug="notebook-lesson-1-your-first-note"', 'slug="Notebook Lesson 1"'), encoding="utf-8"
    )
    lesson = pages.parent / "first_note.py"
    lesson.write_text(
        "import pages\nfrom pageant.studio import Lesson\n\nLESSON = Lesson(pages.FIRST)\n", encoding="utf-8"
    )

    assert cli.main([command, str(lesson)]) == 1
    said = capsys.readouterr().err
    assert said.startswith("A learning site's import would refuse what these would write:\n")
    assert '- first-note/lesson.json, /slug: "Notebook Lesson 1" is not of its form.' in said
    assert stand_in_studio == [], "nothing was filmed or rehearsed"


def test_pack_says_every_reason_a_page_is_refused_and_writes_no_pack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pages = _project(tmp_path)
    pages.write_text(
        PAGES.replace('slug="notebook-lesson-1-your-first-note"', 'slug="Notebook Lesson 1"').replace(
            'title="Notebook: getting started"', 'title="  "'
        ),
        encoding="utf-8",
    )
    out = pages.parent / "out"
    _recorded(out)

    assert cli.main(["pack", str(pages)]) == 1
    said = capsys.readouterr().err
    assert "- first-note/lesson.json, /slug: " in said
    assert "- path.json, /title: " in said
    assert "- path.json, /lessons/0: " in said
    assert not (out / cli.PACK).exists()


def _as_if_the_record_extra_were_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Playwright, and every part of it already imported, as an import finds a package that is not
    there: where the record extra is installed, tests/test_studio.py has imported them first."""

    for name in [name for name in sys.modules if name.split(".")[0] == "playwright"] + ["playwright"]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, "pageant.studio", raising=False)
    monkeypatch.delattr(pageant, "studio", raising=False)


def test_record_says_what_recording_takes_that_is_not_here(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lesson = tmp_path / "lesson.py"
    lesson.write_text("raise AssertionError('the lesson is not loaded before recording can run')\n", encoding="utf-8")
    # As if neither the record extra nor ffmpeg were installed.
    _as_if_the_record_extra_were_not_installed(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert cli.main(["record", str(lesson)]) == 1
    said = capsys.readouterr().err
    assert said.startswith("Recording takes what is not here:\n")
    assert '- the record extra, which installs playwright: pip install "pageant[record]"\n' in said
    assert "- ffmpeg on the PATH, which encodes the video and mixes its sound\n" in said


def test_rehearse_says_it_takes_the_record_extra_and_not_ffmpeg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lesson = tmp_path / "lesson.py"
    lesson.write_text("raise AssertionError('the lesson is not loaded before rehearsing can run')\n", encoding="utf-8")
    _as_if_the_record_extra_were_not_installed(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert cli.main(["rehearse", str(lesson)]) == 1
    assert capsys.readouterr().err == (
        'Rehearsing takes what is not here:\n- the record extra, which installs playwright: pip install "pageant[record]"\n'
    )


def test_example_writes_the_example_lesson_into_a_new_folder_and_nowhere_else(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "notebook"

    assert cli.main(["example", str(target)]) == 0

    def files(root: Path) -> list[str]:
        return sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and "out" not in path.relative_to(root).parts
        )

    assert files(target) == files(cli.EXAMPLE)
    assert {"lesson.py", "pages.py", "site/index.html"} <= set(files(target))
    assert capsys.readouterr().out == f"{target}\nRecord it with: pageant record {target / 'lesson.py'}\n"

    assert cli.main(["example", str(target)]) == 1
    assert "is not an empty folder" in capsys.readouterr().err


def test_the_version_is_the_packages(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out == f"pageant {pageant.__version__}\n"
