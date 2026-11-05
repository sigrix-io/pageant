"""Pageant's example lesson: Notebook, a page the package ships, filmed with a voice, captions and chapters.

    pageant example notebook
    pageant record notebook/lesson.py

Its page is in ``pages.py``, beside it, and the app it films is the static site in ``site/``,
served on this computer's own address. Every line it says is in ``NARRATION``, and every step is
in ``run``: change either and record it again.
"""

from __future__ import annotations

from pathlib import Path

import pages

from pageant.apps import StaticSite
from pageant.studio import Lesson, Mark, Studio

SITE = Path(__file__).resolve().parent / "site"
NOTE = "Record the next lesson"

#: Every line, by key: ``text`` is the caption, and ``spoken`` what the voice says instead, if anything.
NARRATION = {
    "title": {"text": "Notebook, lesson one: your first note."},
    "page": {"text": "This is Notebook: a box to write a note in, and the notes you have kept."},
    "newest": {"text": "The newest note is always at the top of the list."},
    "write": {"text": "Write a note in the box."},
    "add": {"text": "Then add it."},
    "added": {"text": "There it is, at the top, and the count went up by one."},
    "terminal": {"text": "A lesson can film a terminal too. Each command is typed, then really run."},
    "printed": {"text": "And what it prints is shown as it prints it, line by line."},
    "end": {
        "text": "That's the example. Start your own from it with pageant example.",
        "spoken": "That's the example. Start your own from it, with pageant example.",
    },
}


async def run(s: Studio) -> None:
    page = s.page
    box = page.get_by_placeholder("Write a note")

    await s.sleep(600)
    await s.voice("title", 300)
    await s.card(None, 700)

    await s.chapter("The page")
    await s.say("page")
    await s.spot(page.locator("#notes"))
    await s.say("newest")
    await s.spot(None)

    await s.chapter("1 · Write a note")
    await s.say("write", 1800)
    await s.click(box)
    await s.type(box, NOTE)
    await s.say("add", 900)
    await s.click(page.get_by_role("button", name="Add note"))
    await s.spot(page.locator("#notes li", has_text=NOTE))
    await s.say("added")
    await s.spot(page.locator("#count"), 6)
    await s.sleep(1400)
    await s.spot(None)
    await s.quiet()

    await s.chapter("2 · A terminal")
    await s.terminal("Terminal", "~/notebook")
    await s.say("terminal", 2600)
    await s.shell('echo "Recorded by Pageant, from lesson.py"')
    await s.spot(page.locator("#screen .out .line", has_text="Recorded by Pageant").last, 6)
    await s.say("printed")
    await s.spot(None)
    await s.quiet()
    await s.chapter(None)
    await s.card(
        {"kicker": "Your turn", "title": "Write a lesson of your own", "sub": "pageant example, then pageant record"}
    )
    await s.voice("end", 900)


LESSON = Lesson(
    page=pages.FIRST_NOTE,
    title={"kicker": "Notebook · lesson 1", "title": "Your first note", "sub": "Pageant's example lesson"},
    narration=NARRATION,
    run=run,
    app=StaticSite(SITE, ready="#notes"),
    mark=Mark("/mark.svg", SITE / "mark.svg"),
)
