"""The example lesson's page, the path that lists it, and what its YouTube description ends with.

A product's pages are written once, here, for every place a lesson is published: ``pageant
record`` writes each lesson's page beside its video as ``lesson.json``, ``pageant pack pages.py``
zips the recorded lessons with ``PATH``, and ``pageant youtube-text pages.py`` writes each one's
YouTube upload from its page and ``PRODUCT``. Nothing here needs more than the standard library.
"""

from __future__ import annotations

from pageant.bundle import LearningPath, Page
from pageant.youtube import Product

FIRST_NOTE = Page(
    folder="first-note",
    slug="notebook-lesson-1-your-first-note",
    title="Notebook lesson 1: your first note",
    summary=(
        "Write a note and add it, see where it goes, and run a command in a terminal: "
        "Pageant's example lesson, filmed from a page the package ships."
    ),
    body=(
        "## What you will see\n\n"
        "- Notebook's one page: the box to write in, and the notes it keeps.\n"
        "- A note written and added, and where it goes.\n"
        "- A command typed in a terminal, run for real, and what it prints.\n\n"
        "## How it was made\n\n"
        "This is Pageant's example lesson. Its file, `lesson.py`, says every line and every step, "
        "and `pageant record` filmed it from the page in `site/`, in a real browser, with nothing "
        "scripted. `pageant example` writes a copy of it to start your own from.\n"
    ),
    tags=("notebook", "video"),
)

PATH = LearningPath(
    title="Notebook: getting started",
    audience="New to Notebook",
    description="One short lesson, filmed by Pageant from the page it ships with: Pageant's own example.",
    lessons=(FIRST_NOTE,),
    # Where the example would be published. A product's own site goes here; left out, it is the
    # site the bundle format is for.
    site="https://example.com",
)

PRODUCT = Product(
    name="Notebook",
    about="Notebook is the one-page app Pageant's example lesson films. Pageant records a product's lessons from the app itself.",
    link="https://github.com/sigrix-io/pageant",
    all_lessons="https://example.com/learn",
    # Nothing in this lesson is scripted: the page is the one it films, and the command really runs.
    scripted="",
    tags=("pageant", "example", "video lesson"),
)
