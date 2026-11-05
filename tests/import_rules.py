"""What Sigrix's lesson import refuses a page or a path for, restated where the tests hold a page to it.

Sigrix's Learn console imports a pack on its Import lessons page, and refuses a ``lesson.json``
whose format is not ``sigrix-lesson/1``, whose slug is not lowercase words joined by hyphens or is
over 120 characters, whose title (200) or summary (600) is missing or too long, whose tags are not a
list of words, or whose YouTube link is over 300 characters; the Learn editor it saves through
takes only the categories the Learn index has. A ``path.json`` must say ``sigrix-learning-path/1``,
have a title, and list each lesson's slug once. A pack holds at most 20 lessons.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 120
TITLE_MAX = 200
SUMMARY_MAX = 600
YOUTUBE_URL_MAX = 300
CATEGORIES = frozenset({"foundations", "tutorials", "patterns", "seller", "buyer", "case"})
LESSONS_MAX = 20


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= limit


def page_refusals(page: Mapping[str, Any]) -> list[str]:
    """Why the import would refuse this ``lesson.json``; empty when it takes it."""

    found = []
    if page.get("format") != "sigrix-lesson/1":
        found.append("format")
    slug = page.get("slug")
    if not (_text(slug, SLUG_MAX) and SLUG.match(str(slug).strip())):
        found.append("slug")
    if not _text(page.get("title"), TITLE_MAX):
        found.append("title")
    if not _text(page.get("summary"), SUMMARY_MAX):
        found.append("summary")
    if page.get("category") not in CATEGORIES:
        found.append("category")
    tags = page.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        found.append("tags")
    if not isinstance(page.get("body_markdown", ""), str):
        found.append("body_markdown")
    if "youtube_url" in page and not _text(page["youtube_url"], YOUTUBE_URL_MAX):
        found.append("youtube_url")
    return found


def path_refusals(path: Mapping[str, Any]) -> list[str]:
    """Why the import would refuse this ``path.json``; empty when it takes it."""

    found = []
    if path.get("format") != "sigrix-learning-path/1":
        found.append("format")
    if not _text(path.get("title"), TITLE_MAX):
        found.append("title")
    lessons = path.get("lessons")
    if (
        not isinstance(lessons, list)
        or not lessons
        or len(lessons) > LESSONS_MAX
        or not all(isinstance(slug, str) for slug in lessons)
        or len({slug.strip().lower() for slug in lessons}) != len(lessons)
    ):
        found.append("lessons")
    return found
