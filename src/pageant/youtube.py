"""Each lesson's YouTube upload, written from its page: its title, its description and its tags.

    pageant youtube-text lessons/pages.py

writes ``youtube.txt`` into each recorded lesson's folder (``--out`` names where they were recorded),
to paste into YouTube Studio beside the folder's ``video.mp4``, ``cover.jpg`` (the thumbnail) and
``captions.vtt``. The text is the lesson's page, so its title, summary and address are written once,
for the site and for YouTube alike, and the product's :class:`Product` says what every description
ends with.

The description opens with the summary and a link to the lesson's page: its address, or a tracked
link made for the video's post (``--link <slug>=<url>``), so the visits YouTube sends are counted as
YouTube's. Then come the chapters, from the recording's ``chapters.txt``, which YouTube turns into the
video's chapters; what in the lesson is scripted, as a lesson says wherever it is published; and
where to get the product.

A pages file may name ``SHORTS`` too: vertical videos for YouTube Shorts (:class:`Short`), each a
lesson of its own filmed on a phone's screen, whose ``youtube.txt`` sends its viewers to the lesson
of the path it is from, by its description and by YouTube Studio's Related video. A Short has no
chapters.

YouTube refuses a title or a description holding ``<`` or ``>``, a title over 100 characters, a
description over 5,000 bytes and tags over 500 characters, and makes no chapters of a list that does
not start at 0:00, holds fewer than three, or has one under ten seconds. Each is checked here, and a
lesson that breaks one stops the command, naming it, before anything is written: found here, not in
an upload that is refused or that shows no chapters. So does a tag holding a space: each tag is one
word, as the people who upload the lessons want them, so ``"ai marketplace"`` is written
``"aimarketplace"``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pageant import bundle, timeline

#: The file written into each lesson's folder.
UPLOAD = "youtube.txt"

TITLE_MAX = 100
DESCRIPTION_MAX_BYTES = 5000
TAGS_MAX = 500
CHAPTERS_MIN = 3
_REFUSED = re.compile(r"[<>]")
_CHAPTER = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2}) +(\S.*)")


@dataclass(frozen=True)
class Product:
    """What every lesson's description ends with: the product it teaches, and where to get it."""

    #: The product's name, as the description's last line gives it: "Get <name>: <link>".
    name: str
    #: One sentence saying what it is.
    about: str
    #: Where a viewer gets it.
    link: str
    #: Every lesson about it, on the site.
    all_lessons: str
    #: What in the lessons is scripted or a stand-in, as a lesson says wherever it is published;
    #: empty only for lessons with nothing scripted.
    scripted: str
    #: The video's tags, each one word: a tag holding a space stops the command.
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Short:
    """A vertical video for YouTube Shorts, from a lesson of the path: a lesson of its own, filmed on a
    phone's screen (``camera.PHONE``), and recorded into the folder its own page names."""

    #: Its own page: the folder it is recorded into, its title and its summary.
    page: bundle.Page
    #: The lesson of the path it is from, which its description links to, and which YouTube Studio's
    #: Related video, the link a Short's player shows, is the video of.
    lesson: bundle.Page


@dataclass(frozen=True)
class Upload:
    """What YouTube Studio asks for beside the files."""

    title: str
    description: str
    tags: tuple[str, ...]
    #: A Short's Related video: the lesson it is from.
    related: str = ""


def chapters(text: str) -> list[tuple[int, str]]:
    """``chapters.txt`` read back as (second, title), held to the rules YouTube makes chapters by."""

    found: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _CHAPTER.fullmatch(line.strip())
        if match is None:
            raise ValueError(f"a chapter line is not a time and a title: {line!r}")
        hours, minutes, seconds, title = match.groups()
        found.append((int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds), title))
    if len(found) < CHAPTERS_MIN:
        raise ValueError(f"YouTube makes chapters of {CHAPTERS_MIN} or more; this lesson has {len(found)}")
    if found[0][0] != 0:
        raise ValueError(f"the first chapter starts at {timeline.clock_time(found[0][0])}; YouTube wants 0:00")
    for (start, _), (after, title) in zip(found, found[1:], strict=False):
        if after - start < timeline.SHORTEST_CHAPTER:
            raise ValueError(
                f"the chapter before {title!r} is {after - start} s; YouTube wants each at least "
                f"{timeline.SHORTEST_CHAPTER:.0f} s"
            )
    return found


def _tags_length(tags: Sequence[str]) -> int:
    """How YouTube counts its 500: each tag and the commas between them. A tag holds no space, which
    YouTube would count with the quotes it puts round one."""

    return sum(len(tag) for tag in tags) + max(0, len(tags) - 1)


def upload_for(
    page: bundle.Page,
    *,
    number: int,
    path: bundle.LearningPath,
    product: Product,
    chapters_text: str,
    link: str = "",
) -> Upload:
    """A lesson's upload, the ``number``-th of ``path``, refused where YouTube would refuse it."""

    marks = chapters(chapters_text)
    lines = [
        page.summary,
        "",
        f"Watch it with its transcript on {path.site.split('://', 1)[-1].rstrip('/')}: {link or path.page_url(page)}",
        "",
        "Chapters",
        *(f"{timeline.clock_time(start)} {title}" for start, title in marks),
        "",
    ]
    if product.scripted:
        lines += [product.scripted, ""]
    lines += [
        f"Lesson {number} of {len(path.lessons)} in {path.title}. All of them: {product.all_lessons}",
        "",
        product.about,
        f"Get {product.name}: {product.link}",
    ]
    return _held(page, Upload(title=page.title, description="\n".join(lines), tags=product.tags))


def short_upload_for(short: Short, *, path: bundle.LearningPath, product: Product, link: str = "") -> Upload:
    """A Short's upload, refused where YouTube would refuse it: its summary, and the lesson it is from."""

    lesson = short.lesson
    lines = [
        short.page.summary,
        "",
        f"The whole lesson, {lesson.title}, on {path.site.split('://', 1)[-1].rstrip('/')}: "
        f"{link or path.page_url(lesson)}",
        "",
    ]
    if product.scripted:
        lines += [product.scripted, ""]
    lines += [product.about, f"Get {product.name}: {product.link}"]
    related = f"{lesson.title}: {lesson.youtube_url or 'its video, once it is on YouTube'}"
    return _held(
        short.page,
        Upload(title=short.page.title, description="\n".join(lines), tags=product.tags, related=related),
    )


def _held(page: bundle.Page, upload: Upload) -> Upload:
    """``upload``, held to the rules YouTube refuses an upload by, or ``ValueError`` naming the first broken."""

    if len(upload.title) > TITLE_MAX:
        raise ValueError(f"{page.slug}: its title is {len(upload.title)} characters; YouTube takes {TITLE_MAX}")
    for field, value in (("title", upload.title), ("description", upload.description)):
        if _REFUSED.search(value):
            raise ValueError(f"{page.slug}: its {field} holds < or >, which YouTube refuses")
    size = len(upload.description.encode("utf-8"))
    if size > DESCRIPTION_MAX_BYTES:
        raise ValueError(f"{page.slug}: its description is {size} bytes; YouTube takes {DESCRIPTION_MAX_BYTES}")
    for tag in upload.tags:
        if any(character.isspace() for character in tag):
            raise ValueError(f"the tag {tag!r} holds a space; each tag is one word: {''.join(tag.split())!r}")
    if _tags_length(upload.tags) > TAGS_MAX:
        raise ValueError(
            f"the tags are {_tags_length(upload.tags)} characters as YouTube counts them; it takes {TAGS_MAX}"
        )
    return upload


def text_of(upload: Upload) -> str:
    """``youtube.txt``: each field under the name YouTube Studio gives it, to copy as it stands."""

    text = f"TITLE\n{upload.title}\n\nDESCRIPTION\n{upload.description}\n\nTAGS\n{', '.join(upload.tags)}\n"
    return text + (f"\nRELATED VIDEO\n{upload.related}\n" if upload.related else "")


def recorded_for_youtube(out: Path, page: bundle.Page) -> Path:
    """The folder of ``page``'s recording that goes to YouTube: its YouTube cut where one was recorded."""

    cut = out / bundle.YOUTUBE_CUT / page.folder
    return cut if (cut / bundle.YOUTUBE_CHAPTERS).is_file() else out / page.folder


def write(
    out: Path,
    path: bundle.LearningPath,
    product: Product,
    links: Mapping[str, str] | None = None,
    shorts: Sequence[Short] = (),
) -> list[Path]:
    """Write ``youtube.txt`` into each recorded lesson of ``path`` in ``out``, and each of ``shorts``, or nothing.

    A lesson's YouTube cut (``pageant record --youtube``, in ``out/youtube/<folder>/``) is the one
    written for where it was recorded, as the video uploaded is that cut and its chapters are timed to
    it; otherwise the lesson's own recording is. ``links`` gives a lesson's or a Short's tracked link
    by its slug. Every lesson and Short is read and held to YouTube's rules before the first file is
    written, so one that breaks a rule leaves none half done.
    """

    links = dict(links or {})
    unknown = sorted(set(links) - {page.slug for page in path.lessons} - {short.page.slug for short in shorts})
    if unknown:
        raise ValueError("No lesson has this slug: " + ", ".join(unknown))
    strays = [short.page.slug for short in shorts if short.lesson not in path.lessons]
    if strays:
        raise ValueError("A Short is from a lesson of the path; these are not: " + ", ".join(strays))
    for slug, link in links.items():
        if not link.startswith("https://"):
            raise ValueError(f"{slug}: a link starts with https://")
    folders = {page.slug: recorded_for_youtube(out, page) for page in path.lessons}
    missing = [
        f"{page.folder}/{bundle.YOUTUBE_CHAPTERS}"
        for page in path.lessons
        if not (folders[page.slug] / bundle.YOUTUBE_CHAPTERS).is_file()
    ] + [
        f"{short.page.folder}/{bundle.VIDEO}"
        for short in shorts
        if not (out / short.page.folder / bundle.VIDEO).is_file()
    ]
    if missing:
        raise FileNotFoundError("Record these lessons first; missing: " + ", ".join(missing))
    uploads = [
        (
            folders[page.slug] / UPLOAD,
            upload_for(
                page,
                number=number,
                path=path,
                product=product,
                chapters_text=(folders[page.slug] / bundle.YOUTUBE_CHAPTERS).read_text(encoding="utf-8"),
                link=links.get(page.slug, ""),
            ),
        )
        for number, page in enumerate(path.lessons, start=1)
    ]
    uploads += [
        (
            out / short.page.folder / UPLOAD,
            short_upload_for(short, path=path, product=product, link=links.get(short.page.slug, "")),
        )
        for short in shorts
    ]
    for target, upload in uploads:
        target.write_text(text_of(upload), encoding="utf-8")
    return [target for target, _ in uploads]


__all__ = [
    "UPLOAD",
    "Product",
    "Short",
    "Upload",
    "chapters",
    "recorded_for_youtube",
    "short_upload_for",
    "text_of",
    "upload_for",
    "write",
]
