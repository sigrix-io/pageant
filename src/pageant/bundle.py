"""A recorded lesson as a bundle Sigrix's Learn console imports in one step, and a pack of them.

Sigrix's Learn console imports a lesson from a **bundle**: a folder holding its page (``lesson.json``)
and its media under fixed names (``video.mp4``, ``captions.vtt``, ``chapters.vtt``, ``cover.jpg``).
A **pack** is a zip of bundles with the learning path that lists them (``path.json``), and its
Import lessons page checks every lesson, shows what importing them will do, and saves them. The
format is Sigrix's (``sigrix-lesson/1`` and ``sigrix-learning-path/1``), written down in
``SPEC.md`` and in a JSON Schema for each of its two documents (``schema.py``); this module
writes it, and holds every page and path it writes to its schema, so a page the import would
refuse is refused here, with every reason, before anything is written.

A lesson records into a folder of its own (``studio.record``), named by its page's ``folder``, which
is its bundle: the files above, and ``chapters.txt`` for a YouTube description, which an import
passes over (``youtube.py`` writes the rest of that upload). Its page is written as ``lesson.json``
when it is recorded and again when it is packed, so a corrected summary reaches the site with a pack
and an import, and no recording.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pageant import schema

LESSON_FORMAT = "sigrix-lesson/1"
PATH_FORMAT = "sigrix-learning-path/1"
#: Where an import publishes a lesson's page: ``<site>/learn/<slug>``.
DEFAULT_SITE = "https://sigrix.io"
PAGE = "lesson.json"
PATH_PAGE = "path.json"
VIDEO = "video.mp4"
CAPTIONS = "captions.vtt"
CHAPTERS = "chapters.vtt"
COVER = "cover.jpg"
#: The chapters as lines for a YouTube description: in the folder, never in a pack.
YOUTUBE_CHAPTERS = "chapters.txt"
#: The folder in ``out`` that a lesson's YouTube cut is recorded into, as ``youtube/<folder>/``: the
#: lesson with no captions drawn into the picture, for YouTube to show its ``captions.vtt`` itself.
YOUTUBE_CUT = "youtube"
#: What a lesson's folder must hold before it is packed, and what a pack carries of it.
RECORDED = (VIDEO, CAPTIONS, CHAPTERS, COVER)
PACKED = (PAGE, *RECORDED)
#: The media is compressed already; the text is not.
_STORED = frozenset({VIDEO, COVER})
_PAGE_SCHEMA = schema.load(schema.LESSON)
_PATH_SCHEMA = schema.load(schema.PATH)


class ManifestRefused(ValueError):
    """Pages or a path the format's schemas refuse, as the import would: each file, and every reason."""

    def __init__(self, found: Sequence[tuple[str, schema.Problem]]) -> None:
        self.problems = tuple(found)
        reasons = "\n".join(f"- {file}, {problem}" for file, problem in self.problems)
        super().__init__(f"A learning site's import would refuse what these would write:\n{reasons}")


@dataclass(frozen=True)
class Page:
    """A lesson's page on Learn, and the folder it is recorded into."""

    #: Where the recorder writes the lesson, which is also its name for a YouTube upload.
    folder: str
    #: Its address on the site, ``/learn/<slug>``: the one thing an import matches it by.
    slug: str
    title: str
    summary: str
    body: str
    category: str = "tutorials"
    tags: tuple[str, ...] = ()
    #: The same video on YouTube, once it is uploaded there: its page links to it, and never embeds
    #: it. Left out of ``lesson.json`` until then, so an import keeps a link the page already has.
    youtube_url: str = ""


@dataclass(frozen=True)
class LearningPath:
    """The path that lists the lessons on Learn, in their order."""

    title: str
    audience: str
    description: str
    lessons: tuple[Page, ...]
    #: The site an import publishes the lessons on, which a YouTube description links back to.
    site: str = DEFAULT_SITE

    def page_url(self, page: Page) -> str:
        """Where an import publishes ``page``."""

        return f"{self.site.rstrip('/')}/learn/{page.slug}"


def page_json(page: Page) -> dict[str, Any]:
    """``page`` as ``lesson.json``, or ``ManifestRefused`` with every reason its schema gives."""

    data = _page_data(page)
    _hold([(f"{page.folder}/{PAGE}", data, _PAGE_SCHEMA)])
    return data


def path_json(path: LearningPath) -> dict[str, Any]:
    """``path`` as ``path.json``, or ``ManifestRefused`` with every reason its schema gives."""

    data = _path_data(path)
    _hold([(PATH_PAGE, data, _PATH_SCHEMA)])
    return data


def check(path: LearningPath) -> None:
    """Refuse, with every reason at once, a path that its schema, or any of its pages' schema, refuses."""

    _hold(
        [(f"{page.folder}/{PAGE}", _page_data(page), _PAGE_SCHEMA) for page in path.lessons]
        + [(PATH_PAGE, _path_data(path), _PATH_SCHEMA)]
    )


def _hold(documents: Iterable[tuple[str, Any, dict[str, Any]]]) -> None:
    found = [(file, problem) for file, data, rules in documents for problem in schema.problems(data, rules)]
    if found:
        raise ManifestRefused(found)


def _page_data(page: Page) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": LESSON_FORMAT,
        "slug": page.slug,
        "title": page.title,
        "summary": page.summary,
        "category": page.category,
        "tags": list(page.tags),
        "body_markdown": page.body,
    }
    if page.youtube_url:
        data["youtube_url"] = page.youtube_url
    return data


def _path_data(path: LearningPath) -> dict[str, Any]:
    return {
        "format": PATH_FORMAT,
        "title": path.title,
        "audience": path.audience,
        "description": path.description,
        "lessons": [page.slug for page in path.lessons],
    }


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def write_page(page: Page, folder: Path) -> Path:
    """Write ``lesson.json`` into a lesson's folder."""

    target = folder / PAGE
    target.write_text(_json(page_json(page)), encoding="utf-8")
    return target


def pack(out: Path, path: LearningPath, target: Path) -> Path:
    """Zip each lesson of ``path`` recorded in ``out``, its page written afresh, with the path itself.

    Refuses, with every reason, a path or a page the format's schemas refuse; and, naming every
    file missing, a lesson not recorded whole, since a pack that leaves one out would import a
    path naming a lesson that is not there.
    """

    check(path)
    missing = [
        f"{page.folder}/{name}"
        for page in path.lessons
        for name in RECORDED
        if not (out / page.folder / name).is_file()
    ]
    if missing:
        raise FileNotFoundError("Record these lessons first; missing: " + ", ".join(missing))
    root = target.stem
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for page in path.lessons:
            folder = out / page.folder
            write_page(page, folder)
            for name in PACKED:
                kind = zipfile.ZIP_STORED if name in _STORED else zipfile.ZIP_DEFLATED
                archive.write(folder / name, f"{root}/{page.folder}/{name}", compress_type=kind)
        archive.writestr(f"{root}/{PATH_PAGE}", _json(path_json(path)), compress_type=zipfile.ZIP_DEFLATED)
    return target


__all__ = [
    "CAPTIONS",
    "CHAPTERS",
    "COVER",
    "DEFAULT_SITE",
    "LESSON_FORMAT",
    "PAGE",
    "PATH_FORMAT",
    "PATH_PAGE",
    "VIDEO",
    "YOUTUBE_CHAPTERS",
    "LearningPath",
    "ManifestRefused",
    "Page",
    "check",
    "pack",
    "page_json",
    "path_json",
    "write_page",
]
