"""Record a lesson as code: the real app in a real browser, with a voice, captions and chapters.

A lesson is a storyboard: a table of what it says, and its steps, each a highlight, a click or a
caption. The studio starts the lesson's app (``apps.py``), opens it in Chromium's headless shell at
1280x720 CSS pixels and a device scale of 1.5, so frames are 1920x1080 and text is sharp, draws the
cursor, spotlight, captions and cards over the page (``overlay.js``), and paints every frame of the
video itself, 60 a second, on a clock it keeps (``film.py``): every motion in it, the pointer's, a
scroll's, a fade's, is as even on a slow machine as on a fast one. A lesson that lets it zooms
in on what each spotlight shows (``Lesson.zoom``, ``camera.py``). It writes a folder of the
lesson's own in the output folder, named by its page, which is the lesson's bundle (``bundle.py``):

- ``video.mp4``: H.264 and AAC at 1080p and 60 fps, with its chapters as markers;
- ``cover.jpg``: the poster, which is the title card;
- ``captions.vtt``: the captions, every line spoken;
- ``chapters.vtt`` and ``chapters.txt``: the chapters, for a web page's player and for a
  YouTube description;
- ``lesson.json``: its page.

Every line is spoken before the recording starts (``narrate.py``), so each caption is held
exactly as long as its voice, and the sound is mixed in at the end (``mixdown.py``). A step the app
no longer has (a locator that finds nothing) stops the recording with an error, and the page is
kept as ``failure.png`` beside it, so an app that changed never ships a stale video.

A step that goes to another page (a link, a form post, a redirect such as a checkout's) starts a
new document, and the overlay starts afresh in each, so the studio keeps what is on screen (the
chapter label, the caption, the title card and where the pointer is) and draws it on every page
the lesson goes to as that page loads. ``rehearse`` runs a lesson as ``record`` does, with nothing
spoken or filmed and every long wait cut short, to find a step the app no longer has before a
recording spends its minutes on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import mimetypes
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from re import Pattern
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import FloatRect, Frame, Locator, Page, async_playwright

from pageant import apps, bundle, camera, loudness, mixdown, narrate, timeline
from pageant.apps import App, Running
from pageant.camera import HEIGHT, WHOLE, WIDTH, View
from pageant.film import CROP, FLAGS, FPS, Film, concat

HERE = Path(__file__).resolve().parent
SCALE = 1.5
#: A voice starts a moment after its caption fades in, and the next line waits a breath after it.
VOICE_LEAD = 0.25
VOICE_GAP = 0.45
#: A step that scrolls to an element reads its box this often, in seconds, until two reads agree,
#: and moves on this long after the scroll began at most. Chromium's smooth scroll takes longer the
#: further it goes: about 450 ms for 500 px, and 1.5 s for the longest.
SETTLE_POLL = 0.12
SETTLE_CAP = 3.0
#: A draw that a page load cuts off is made again on the page that replaced it, up to this many
#: pages in a row.
DRAW_ATTEMPTS = 3
#: In a rehearsal, no wait is longer than this, in seconds.
REHEARSAL_WAIT = 0.25
#: How long the spotlight takes to fade out, in seconds (``overlay.js``).
SPOT_FADE = 0.35
#: How long, in real seconds, a frame waits for the page to draw the pointer and the camera before it
#: is painted without them.
HOOK_WAIT = 1.0
#: The foot of the screen a caption of two lines covers, in CSS pixels.
CAPTION_BAND = 125
#: How far, in CSS pixels, an element may have moved by the time the mouse goes down before the
#: pointer goes after it (``Studio.click``).
AIM = 3.0
#: How many frames a step waits for a view transition to end before it skips it (``Studio.glide``):
#: a page change's fades last a fraction of a second, and Chromium gives up on one after four.
TRANSITION_FRAMES = 90
#: How long a step's own waits for the page (Playwright's) may take, in the machine's seconds: the
#: page moves only as frames are painted, which a busy machine paints more slowly, so the 30 s
#: Playwright's waits default to is the machine's time, not the film's, and too short.
WAIT_SECONDS = 180
#: Whether an element is in view already, so a step that points at it does not scroll there: all of
#: it on screen, and either in a bar that stays put as the page scrolls (fixed, or sticky, which
#: Chromium scrolls the page under rather than bring it nearer) or above the captions with nothing
#: over its middle, such as a sticky top bar.
IN_VIEW = f"""el => {{
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height || r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) {{
    return false;
  }}
  for (let at = el; at; at = at.parentElement) {{
    if (["fixed", "sticky"].includes(getComputedStyle(at).position)) return true;
  }}
  const over = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return r.bottom <= innerHeight - {CAPTION_BAND} && !!over && el.contains(over);
}}"""


@dataclass(frozen=True)
class Mark:
    """A product's mark, drawn on the title cards: the address its app serves it at, and the file.

    The card loads it from the page's own origin, so an app's CSP allows it; the filmed terminal's
    page serves the same file at the same address.
    """

    url: str
    file: Path


@dataclass(frozen=True)
class Lesson:
    #: Its page on the site, which names the folder it is recorded into.
    page: bundle.Page
    #: The title card, which is also the poster: ``kicker``, ``title`` and ``sub``.
    title: Mapping[str, str]
    #: Every line, by key: ``text`` is the caption, and ``spoken`` what the voice says instead, if anything.
    narration: Mapping[str, Mapping[str, str]]
    run: Callable[[Studio], Awaitable[None]]
    #: The app the lesson films, and how to start it (``apps.py``).
    app: App
    voice: str = "af_heart"
    color_scheme: Literal["light", "dark"] = "light"
    #: Steps before the recording starts, on the page itself (``studio.page``): what an
    #: earlier lesson showed, so this one starts where it left off.
    setup: Callable[[Studio], Awaitable[None]] | None = None
    #: Stand-in programs on the app's PATH and the terminal's, each a name and what it runs with this
    #: Python: a script and its first arguments, such as a stand-in for a service the app calls.
    commands: Mapping[str, Sequence[str | Path]] = field(default_factory=dict)
    mark: Mark | None = None
    #: Where the chapter label sits: ``top-right``, or ``top-left`` for an app whose controls are on the right.
    label_corner: Literal["top-right", "top-left"] = "top-right"
    #: How long the label shows after its chapter starts, in seconds; ``None`` keeps it up until the next one.
    label_seconds: float | None = None
    #: Words the voice says differently from how they are written, each respelled in every line it speaks
    #: (``pronounce.py``): ``{"example.io": "example dot eye oh"}``. The captions keep the written form.
    pronounce: Mapping[str, str] = field(default_factory=dict)
    #: The mix's loudness in LUFS (``loudness.py``): -16, what web players expect, or -14, what YouTube
    #: plays every video at.
    loudness: float = loudness.WEB
    #: How far the camera may zoom in on what a spotlight shows: 1, the default, never zooms; 2 shows
    #: it up to twice as large (``camera.py``). The captions, the label and the cards keep their size.
    zoom: float = 1.0

    @property
    def slug(self) -> str:
        """The folder the lesson is recorded into, and its name for a YouTube upload."""

        return self.page.folder


def _files(served: Mapping[str, Path]) -> type[BaseHTTPRequestHandler]:
    """A server for the filmed terminal's page, and the product's mark at its address: nothing else."""

    class Files(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = served.get(self.path.split("?", 1)[0])
            if path is None:
                self.send_error(404)
                return
            body = path.read_bytes()
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{kind}; charset=utf-8" if kind == "text/html" else kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Files


@dataclass
class _Caption:
    start: float
    text: str
    end: float | None = None


def _middle(box: FloatRect | None) -> tuple[float, float] | None:
    return None if box is None else (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _held(before: FloatRect | None, after: FloatRect | None) -> bool:
    """Whether an element held still between two reads of its box: its middle, where the pointer
    goes, within half a pixel of where it was, or the element not shown at either."""

    was, now = _middle(before), _middle(after)
    if was is None or now is None:
        return was is None and now is None
    return math.dist(was, now) < 0.5


@dataclass
class Studio:
    """What a lesson's steps call. Times are seconds since the recording started."""

    page: Page
    lesson: Lesson
    clips: Mapping[str, narrate.Clip]
    work: Path
    #: The frames, and the clock the studio keeps by them (``film.py``).
    film: Film
    #: When the video starts, in seconds of film.
    started: float = 0.0
    captions: list[_Caption] = field(default_factory=list)
    spoken_only: list[timeline.Cue] = field(default_factory=list)
    spoken: list[tuple[float, Path]] = field(default_factory=list)
    clicks: list[float] = field(default_factory=list)
    marks: list[timeline.Mark] = field(default_factory=list)
    voice_until: float = 0.0
    mouse: tuple[float, float] = (WIDTH / 2, HEIGHT / 2)
    #: The terminal page's address, and what a command typed there runs with.
    terminal_url: str = ""
    shell_env: Mapping[str, str] = field(default_factory=dict)
    where: str = "~"
    #: The chapter label on screen. It, the caption and the title card on screen, and the pointer at
    #: ``mouse``, are drawn again on every page the lesson goes to, as that page loads.
    label: str | None = None
    #: A rehearsal (``rehearse``): nothing is spoken or filmed, and no wait is longer than
    #: ``REHEARSAL_WAIT``.
    rehearsal: bool = False
    _caption: str | None = field(default=None, init=False, repr=False)
    _card: Mapping[str, Any] | None = field(default=None, init=False, repr=False)
    #: Takes away the script that hands what is on screen to the next document (``_carry``).
    _uncarry: Callable[[], Awaitable[None]] | None = field(default=None, init=False, repr=False)
    #: Takes the label down ``Lesson.label_seconds`` after its chapter started (``_label_after``).
    _label_down: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _carrying: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _drawing: set[asyncio.Task[None]] = field(default_factory=set, init=False, repr=False)
    #: The pointer on its way somewhere: its points, a frame each, from the frame after this one.
    _reaching: tuple[list[tuple[float, float]], int] | None = field(default=None, init=False, repr=False)
    #: Where the camera looks, and its move: from one view to another, from a frame, over so many frames.
    _view: View = field(default=WHOLE, init=False, repr=False)
    _move: tuple[View, View, int, int] | None = field(default=None, init=False, repr=False)
    #: The view the overlay was last drawn for, so a still camera on the whole screen costs no call a
    #: frame; ``None`` when a draw went unanswered, so the next frame draws again.
    _drawn_for: View | None = field(default=WHOLE, init=False, repr=False)

    def __post_init__(self) -> None:
        self.page.on("framenavigated", self._went)

    def clock(self) -> float:
        """Seconds since the video started, on the film's clock."""

        return self.film.clock() - self.started

    async def sleep(self, ms: float) -> None:
        await self._wait(ms / 1000)

    async def _wait(self, seconds: float) -> None:
        """Wait, as a recording does, in frames; a rehearsal waits ``REHEARSAL_WAIT`` at most."""

        await self.film.seconds(min(seconds, REHEARSAL_WAIT) if self.rehearsal else seconds)

    async def _frame(self, number: int) -> None:
        """Before frame ``number`` is painted: the pointer's next point on its way, and where the camera looks.

        Run by the film before every frame, so a pointer moves a point a frame and a camera a step a
        frame, however long the steps around them take. It talks to the page over the film's own
        connection, which waits for no page to load, so a frame is never held up by one.
        """

        point = None
        if self._reaching is not None:
            points, first = self._reaching
            index = number - first - 1
            if 0 <= index < len(points):
                point = points[index]
        view = self._view_at(number)
        if point is None and view == WHOLE and self._drawn_for == WHOLE:
            self.film.clip = None
            return
        script = (
            "(() => { const demo = window.__demo; if (!demo) return null;"
            + (f" demo.point({point[0]}, {point[1]});" if point else "")
            + f" return demo.camera({view.x}, {view.y}, {view.scale}); }})()"
        )
        try:
            # A page between documents can leave the call unanswered until a frame is painted, which
            # this call is holding up: that frame is painted whole instead.
            answer = await asyncio.wait_for(
                self.film.cdp.send("Runtime.evaluate", {"expression": script, "returnByValue": True}), HOOK_WAIT
            )
            scroll = answer.get("result", {}).get("value")
        except (PlaywrightError, TimeoutError):
            scroll = None
        self._drawn_for = view if scroll is not None else None
        if view == WHOLE or scroll is None:
            self.film.clip = None
        else:
            left, top = scroll
            self.film.clip = {"x": view.x + left, "y": view.y + top, "width": view.width, "height": view.height}

    def _view_at(self, number: int) -> View:
        """Where the camera looks in frame ``number``: still, or part of the way through a move."""

        if self._move is not None:
            start, end, first, frames = self._move
            if number >= first + frames:
                self._view, self._move = end, None
            else:
                return camera.between(start, end, (number - first) / frames)
        return self._view

    async def _look(self, view: View, *, wait: bool = False) -> None:
        """Move the camera to ``view`` over ``camera.MOVE_SECONDS``, from wherever it is; ``wait`` for it to get there."""

        first = self.film.hooked
        now = self._view_at(first + 1)
        if now == view and self._move is None:
            return
        frames = camera.frames_for(camera.MOVE_SECONDS, FPS)
        self._move = (now, view, first, frames)
        if wait:
            await self.film.until(first + frames)

    def _cut(self, view: View) -> None:
        """Show ``view`` from the next frame, with no move: a page that changed, a card, the terminal."""

        self._view, self._move = view, None

    def _screen(self) -> dict[str, Any]:
        """What is on screen, as ``overlay.js`` draws it: the label, the caption, the card, and the pointer."""

        card = None if self._card is None else dict(self._card)
        return {
            "label": self.label,
            "corner": self.lesson.label_corner,
            "caption": self._caption,
            "card": card,
            "at": list(self.mouse),
        }

    async def _on_page(self, expression: str, arg: Callable[[], Any] = lambda: None) -> None:
        """Evaluate ``expression`` with ``arg()`` on the page as it is now.

        A page load can cut it off: a click that went to another page, or a redirect, replaces the
        document it was sent to while it runs. Then it is made again, ``arg()`` read afresh, on the
        document that replaced it, up to ``DRAW_ATTEMPTS`` in a row; anything else fails each time,
        and the last failure is raised.
        """

        for attempt in range(1, DRAW_ATTEMPTS + 1):
            try:
                await self.page.evaluate(expression, arg())
                return
            except PlaywrightError:
                if attempt == DRAW_ATTEMPTS or self.page.is_closed():
                    raise

    async def _carry(self) -> None:
        """Hand what is on screen to the next document the page loads, to draw before its first frame.

        A script of the page's own, which runs as each new document starts, after the overlay's and
        before the page's scripts, in the page itself and not the frames in it; it is replaced each
        time what is on screen changes.
        """

        async with self._carrying:
            script = f"window === window.top && window.__demo && window.__demo.show({json.dumps(self._screen())});"
            carried = await self.page.add_init_script(script=script)
            if self._uncarry is not None:
                await self._uncarry()
            self._uncarry = carried.close

    async def _show(self) -> None:
        """Draw what is on screen on the page as it is now, and on the next page from its first frame."""

        await self._carry()
        await self._on_page("screen => window.__demo.show(screen)", self._screen)

    def _went(self, frame: Frame) -> None:
        """A page the lesson went to, as it starts to load: draw on it what the last page had.

        The next document drew what was on screen as it started (``_carry``), but a step that ran
        while it loaded may have changed that, so it is drawn again now.
        """

        if frame.parent_frame is not None:
            return
        # A new page is a cut: it starts on the whole screen, whatever the last one was zoomed to.
        self._cut(WHOLE)
        drawing = asyncio.ensure_future(self._show_quietly())
        self._drawing.add(drawing)
        drawing.add_done_callback(self._drawing.discard)

    async def _show_quietly(self) -> None:
        # A page that is gone before it is drawn needs drawing no more: the one that replaced it is
        # drawn in its turn. A page that cannot be drawn on fails the next step that draws.
        with contextlib.suppress(PlaywrightError):
            await self._on_page("screen => window.__demo.show(screen)", self._screen)

    async def _drawn(self) -> None:
        """Wait for the pages the lesson went to to be drawn."""

        await asyncio.gather(*self._drawing, return_exceptions=True)

    async def card(self, spec: Mapping[str, Any] | None, hold_ms: float = 0) -> None:
        """A title card over the page, with the product's mark unless ``spec`` names one; ``None`` lifts it.

        ``spec`` holds a ``kicker``, ``title`` and ``sub``, and may hold ``points``: a short list drawn
        under them, numbered, or ticked with ``checks``. ``"mark": ""`` draws the card with no mark.
        """

        if spec is not None and self.lesson.mark is not None and "mark" not in spec:
            spec = {**spec, "mark": self.lesson.mark.url}
        if spec is not None:
            self._cut(WHOLE)
        self._card = spec
        await self._show()
        await self.sleep(hold_ms)

    async def tell(self, spec: Mapping[str, Any], key: str, extra_ms: float = 0, at: Sequence[float] = ()) -> None:
        """A card whose points come up one at a time while ``key`` is spoken over it, as a list is read out.

        The first point is up as the line starts, and each next one at ``at``'s share of the line (by
        default, an equal share apart), so a line that names the points in order shows each as it is
        said. With no voice (a rehearsal, or an unspoken line) every point is up at once.
        """

        points = list(spec.get("points") or [])
        clip = self.clips.get(key)
        if clip is None or len(points) < 2:
            await self.card(spec)
            await self.voice(key, extra_ms)
            return
        shares = list(at) or [index / len(points) for index in range(len(points))]
        if len(shares) != len(points):
            raise ValueError(f"tell({key!r}): {len(points)} points, but {len(shares)} shares of the line in at")
        await self._voice_free()
        start = self.clock() + VOICE_LEAD
        self.spoken_only.append(timeline.Cue(start, start + clip.seconds + 0.3, self.lesson.narration[key]["text"]))
        length = self._speak(clip)
        shown = 0.0
        for count, share in enumerate(shares, start=1):
            moment = VOICE_LEAD + share * clip.seconds
            if moment > shown:
                await self._wait(moment - shown)
                shown = moment
            await self.card({**spec, "points": points[:count]})
        await self._wait(max(0.0, length - shown))
        await self.sleep(extra_ms)

    async def chapter(self, title: str | None) -> None:
        """The label on screen, and a chapter of the video from here on.

        With ``Lesson.label_seconds``, the label comes down that long after, on whatever page the
        lesson is on by then, unless the next chapter has started.
        """

        if title:
            self.marks.append(timeline.Mark(self.clock(), title))
        self.label = title
        await self._show()
        if self._label_down is not None:
            self._label_down.cancel()
            self._label_down = None
        if title and self.lesson.label_seconds:
            self._label_down = asyncio.ensure_future(self._label_after(title, self.lesson.label_seconds))

    async def _label_after(self, title: str, seconds: float) -> None:
        """Take the label ``title`` down after ``seconds``, from this page and every page after.

        In seconds of film, in a rehearsal too: no step waits for it.
        """

        await self.film.seconds(seconds)
        if self.label != title:
            return
        self.label = None
        # As for a page drawn as it loads: a page that cannot be drawn on fails the next step that draws.
        with contextlib.suppress(PlaywrightError):
            await self._show()

    async def _voice_free(self) -> None:
        """Never two voices at once: a line waits for the one before it, and a breath after."""

        busy = self.voice_until - self.clock()
        if busy > 0:
            await self._wait(busy + VOICE_GAP)

    def _speak(self, clip: narrate.Clip) -> float:
        """Start a clip now; how long to wait for it, and the breath after."""

        self.spoken.append((self.clock() + VOICE_LEAD, clip.file))
        self.voice_until = self.clock() + VOICE_LEAD + clip.seconds
        return VOICE_LEAD + clip.seconds + VOICE_GAP

    def _close_caption(self) -> None:
        if self.captions and self.captions[-1].end is None:
            self.captions[-1].end = self.clock()

    async def say(self, key_or_text: str, hold_ms: float | None = None) -> None:
        """A caption, by its narration key or as text.

        Spoken, it is held as long as its voice; unspoken, long enough to read, about 60 ms a
        character and never under 2.4 s. A shorter ``hold_ms`` lets the voice run on under
        the steps that follow.
        """

        line = self.lesson.narration.get(key_or_text)
        text = line["text"] if line else key_or_text
        clip = self.clips.get(key_or_text) if line else None
        if clip:
            await self._voice_free()
        self._close_caption()
        self.captions.append(_Caption(self.clock(), text))
        self._caption = text
        await self._show()
        natural = self._speak(clip) if clip else max(2.4, len(text) * 0.06)
        await self._wait(natural if hold_ms is None else hold_ms / 1000)

    async def voice(self, key: str, extra_ms: float = 0) -> None:
        """A line spoken over a card, with no caption on screen; the captions file still has it."""

        clip = self.clips.get(key)
        if clip:
            await self._voice_free()
            start = self.clock() + VOICE_LEAD
            self.spoken_only.append(timeline.Cue(start, start + clip.seconds + 0.3, self.lesson.narration[key]["text"]))
            await self._wait(self._speak(clip))
        await self.sleep(extra_ms)

    async def quiet(self) -> None:
        self._close_caption()
        self._caption = None
        await self._show()

    async def _scroll_to(self, locator: Locator, pause_ms: float) -> FloatRect | None:
        """Scroll smoothly until ``locator`` is in the middle of the page, unless it is in view
        already (``IN_VIEW``); its box once it is still.

        A smooth scroll takes longer the further it goes, so once ``pause_ms`` has passed, its box
        is read every ``SETTLE_POLL`` until two reads in a row agree, and at most until
        ``SETTLE_CAP`` after the scroll began: a short scroll is over by the pause, and the pointer
        goes to where a long one ends, not to where the element was on its way there. An element in
        view is not scrolled to: the page would move under the pointer for nothing, and a control
        in a sticky top bar would scroll the page under the bar.
        """

        if not await locator.evaluate(IN_VIEW):
            await locator.evaluate("el => el.scrollIntoView({ block: 'center', behavior: 'smooth' })")
        until = self.film.clock() + SETTLE_CAP
        await self.sleep(pause_ms - SETTLE_POLL * 1000)
        box = await locator.bounding_box()
        while True:
            await self.film.seconds(SETTLE_POLL)
            then, box = box, await locator.bounding_box()
            if _held(then, box) or self.film.clock() >= until:
                return box

    async def spot(self, locator: Locator | None, padding: float = 8, zoom: float | None = None) -> None:
        """Dim the page around ``locator``, scrolled into view; ``None`` lifts the spotlight.

        A spotlight already up on another element is taken down before the page scrolls to one out
        of view, rather than trailing its element off the screen and sliding across to the new one;
        the new one comes up where it lands. With ``Lesson.zoom``, or ``zoom`` for this one, the
        camera moves in on it (``camera.framing``), and it moves back out when the spotlight lifts
        or the page has to scroll to the next.
        """

        if locator is None:
            await self._on_page("() => window.__demo.spot(null)")
            await self._look(WHOLE)
            return
        if not await locator.evaluate(IN_VIEW):
            await self._look(WHOLE, wait=True)
            if await self.page.evaluate("() => window.__demo.spot(null)"):
                await self.sleep(SPOT_FADE * 1000)
        box = await self._scroll_to(locator, 550)
        await locator.evaluate("(el, padding) => window.__demo.spot(el, padding)", padding)
        most = self.lesson.zoom if zoom is None else zoom
        if box is not None and most > 1:
            framed = (box["x"] - padding, box["y"] - padding, box["width"] + 2 * padding, box["height"] + 2 * padding)
            await self._look(camera.framing(framed, most, band=CAPTION_BAND))
        await self.sleep(450)

    async def _transitioned(self) -> None:
        """Wait out a view transition the page is in, as a person does: until it ends, the page takes
        no clicks (it hit-tests as ``<html>``). One still running after ``TRANSITION_FRAMES`` is skipped."""

        for _ in range(TRANSITION_FRAMES):
            if not await self.page.evaluate("() => !!(window.__demo && window.__demo.transitioning())"):
                return
            await self.film.frames(1)
        await self.page.evaluate("() => window.__demo && window.__demo.skipTransition()")

    async def glide(self, locator: Locator) -> None:
        """Move the cursor to the middle of ``locator`` as a hand would, not in one jump, once the
        page has stopped scrolling to it, and once a view transition the page is in is over."""

        await self._transitioned()
        if not await locator.evaluate(IN_VIEW):
            # The page is about to scroll under the camera: back out to the whole screen first.
            await self._look(WHOLE, wait=True)
        box = await self._scroll_to(locator, 450)
        if box is None:
            raise RuntimeError(f"{locator} is not on the page")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        if not self._view_at(self.film.hooked + 1).holds(x, y, margin=24):
            await self._look(WHOLE, wait=True)
        await self._reach((x, y))
        # A click here may go to another page, which draws the pointer here from its first frame.
        await self._carry()
        await self.sleep(220)

    async def _reach(self, end: tuple[float, float]) -> None:
        """Move the pointer to ``end`` along ``camera.path``, a point a frame, then the mouse itself.

        The points are drawn by the overlay, frame by frame (``_frame``); the page sees one mouse
        move, at the end, so a menu that opens on hover does not flicker open on the pointer's way.
        """

        points = camera.path(self.mouse, end, FPS)
        # The first point is drawn in the first frame whose drawing has not begun.
        first = self.film.hooked
        self._reaching = (points, first)
        try:
            await self.film.until(first + len(points))
        finally:
            self._reaching = None
        await self.page.mouse.move(*end)
        self.mouse = end

    async def click(self, locator: Locator) -> None:
        """Glide to ``locator`` and click it, where it is when the mouse goes down.

        A page can move an element while the pointer is on its way to it (a banner coming in
        above it, a list laid out again), and a press at the middle it had when the pointer set
        off lands on whatever is there now. So its box is read again before the press, and the
        pointer goes on to its middle first if it moved, as a hand corrects its aim.
        """

        await self.glide(locator)
        box = await locator.bounding_box()
        if box is not None:
            aim = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            if math.dist(aim, self.mouse) > AIM:
                if not self._view_at(self.film.hooked + 1).holds(*aim, margin=24):
                    await self._look(WHOLE, wait=True)
                await self._reach(aim)
                await self.sleep(120)
        self.clicks.append(self.clock())
        await self.page.mouse.down()
        await self.sleep(70)
        await self.page.mouse.up()
        await self.sleep(350)

    async def arrive(self, url: str | Pattern[str] | Callable[[str], bool]) -> None:
        """Wait for the page a step went to, loaded, with what was on screen drawn on it.

        ``url`` is where the step goes, as Playwright's ``wait_for_url`` takes it: the address, a
        glob such as ``"**/checkout/done"``, a regular expression, or a function of the address.
        Every page the lesson goes to is drawn as it loads, whether a lesson arrives there or not;
        this is for the step after, so it does not start on the page before.
        """

        await self.page.wait_for_url(url)
        await self._show()

    async def terminal(self, title: str = "Terminal", where: str = "~") -> None:
        """Leave the app's page for the terminal, where shell() runs commands, and put the pointer away."""

        self.where = where
        # Whole before the page changes: a zoomed frame's screenshot cannot be taken of a page going away.
        self._cut(WHOLE)
        await self.film.frames(1)
        await self.page.goto(self.terminal_url)
        await self.page.wait_for_function("() => window.__term && window.__demo && window.__demo.ready()")
        await self.page.evaluate(
            "([title, where]) => { window.__term.title(title); window.__term.prompt(where);"
            " window.__demo.pointer(false); }",
            [title, where],
        )
        await self._show()

    async def shell(self, command: str, delay_ms: float = 45) -> int:
        """Type a command at the prompt, run it for real in a shell of its own, and show what it prints as it prints it.

        It runs in the work folder, with the app's environment and the lesson's stand-in commands on
        the PATH. Its exit status is returned.
        """

        await self.page.evaluate("([text, delay]) => window.__term.type(text, delay)", [command, delay_ms])
        await self.sleep(400)
        await self.page.evaluate("() => window.__term.enter()")
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=self.work,
            env=dict(self.shell_env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if process.stdout is not None:
            while line := await process.stdout.readline():
                await self.page.evaluate(
                    "text => window.__term.write(text)", line.decode("utf-8", "replace").rstrip("\n")
                )
        status = await process.wait()
        await self.page.evaluate("where => window.__term.prompt(where)", self.where)
        return status

    async def type(self, locator: Locator, text: str, delay_ms: float = 28) -> None:
        """Type as a person does. A new line is Shift+Enter, since Enter often sends."""

        await locator.focus()
        each = max(1, round(delay_ms / 1000 * FPS))
        first, typed = self.film.count, 0
        for index, line in enumerate(text.split("\n")):
            for key in (["Shift+Enter"] if index else []) + list(line):
                if key == "Shift+Enter":
                    await self.page.keyboard.press(key)
                else:
                    await self.page.keyboard.type(key)
                typed += 1
                await self.film.until(first + typed * each)

    async def paste(self, locator: Locator, text: str) -> None:
        """Put ``text`` in at once, as a paste does: for words too long to watch being typed.

        The page hears it as typing (an ``input`` event), so a form that saves or counts as you type
        does so; a new line is a new line, in a box that keeps one.
        """

        await locator.focus()
        await self.page.keyboard.insert_text(text)
        await self.sleep(300)


@contextlib.asynccontextmanager
async def _staged(
    lesson: Lesson,
    out: Path,
    work: Path,
    chromium: str | None,
    clips: Mapping[str, narrate.Clip],
    *,
    frames: Path | None = None,
    rehearsal: bool = False,
) -> AsyncIterator[Studio]:
    """The lesson's app started, its page open in Chromium's headless shell under the overlay, the
    film painting its frames (into ``frames`` once it rolls, if given), the lesson's setup run on it,
    and the studio that drives it.

    A step that fails, in the setup or in what the caller runs, keeps the page as ``failure.png`` in
    ``out``; one an earlier run left there is removed first.
    """

    failure = out / "failure.png"
    failure.unlink(missing_ok=True)
    served = {"/": HERE / "terminal.html"}
    if lesson.mark is not None and lesson.mark.url.startswith("/"):
        served[lesson.mark.url] = lesson.mark.file
    running: Running = lesson.app.start(work, apps.environment(work, lesson.commands))
    files = ThreadingHTTPServer(("127.0.0.1", 0), _files(served))
    threading.Thread(target=files.serve_forever, daemon=True).start()
    try:
        async with async_playwright() as playwright:
            # The scale is the browser's own, not an emulated one: only then are frames painted at
            # device pixels (1920x1080) rather than CSS pixels (1280x720).
            browser = await playwright.chromium.launch(
                executable_path=chromium,
                args=[*FLAGS, f"--force-device-scale-factor={SCALE}", f"--window-size={WIDTH},{HEIGHT}"],
            )
            context = await browser.new_context(viewport=None, color_scheme=lesson.color_scheme)
            await context.add_init_script(path=HERE / "overlay.js")
            page = await context.new_page()
            page.set_default_timeout(WAIT_SECONDS * 1000)
            # The film paints from before the first page loads: a page loads only as frames are painted.
            film = Film(await context.new_cdp_session(page), frames)
            studio = Studio(page, lesson, clips, work, film, rehearsal=rehearsal)
            film.before = studio._frame
            studio.terminal_url = f"http://127.0.0.1:{files.server_address[1]}/"
            studio.shell_env = {**running.env, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color"}
            try:
                await film.start()
                await page.goto(running.address)
                await page.wait_for_function("() => window.__demo && window.__demo.ready()")
                if running.ready:
                    await page.locator(running.ready).wait_for(state="visible")
                if lesson.setup is not None:
                    await lesson.setup(studio)
                    # Setup is not part of the video: nothing it did is on its timeline.
                    studio.captions.clear()
                    studio.clicks.clear()
                    studio.marks.clear()
                    studio.spoken.clear()
                    studio.spoken_only.clear()
                yield studio
            except Exception:
                # The page as the step that failed left it, painted by the film (Chromium's own screenshot
                # can wait for ever on a page with nothing moving), unless the film has stopped too.
                with contextlib.suppress(Exception):
                    picture = await asyncio.wait_for(film.picture(), 30)
                    if picture:
                        failure.write_bytes(picture)
                raise
            finally:
                if studio._label_down is not None:
                    # A label still to come down when the lesson ends comes down with the page.
                    studio._label_down.cancel()
                    await asyncio.gather(studio._label_down, return_exceptions=True)
                await studio._drawn()
                # A failure of the film's own fails the step that waited on it, which is what is raised.
                with contextlib.suppress(Exception):
                    await film.stop()
                await context.close()
                await browser.close()
    finally:
        files.shutdown()
        running.stop()


async def _capture(lesson: Lesson, out: Path, work: Path, chromium: str | None) -> tuple[Studio, float]:
    """Record the lesson's frames into its work folder, and its poster into its folder ``out``; the
    studio's log of it, and how long the video is, in seconds."""

    clips = narrate.speak(lesson.narration, narrate.Voice(lesson.voice), lesson.pronounce) if lesson.narration else {}
    frames = work / "frames"
    frames.mkdir()
    async with _staged(lesson, out, work, chromium, clips, frames=frames) as studio:
        film = studio.film
        await studio.page.mouse.move(*studio.mouse)
        await studio.card(lesson.title, 700)
        film.roll()
        studio.started = film.clock()
        await film.frames(1)
        # The poster is the title card: the first frame the film keeps.
        if film.last_file is None:
            raise RuntimeError("The film kept no first frame, so there is no poster.")
        shutil.copyfile(film.last_file, out / bundle.COVER)
        await lesson.run(studio)
        await studio.quiet()
        await film.seconds(max(0.4, studio.voice_until - studio.clock() + 0.4))
        film.rolling = False
        stopped = studio.clock()
    return studio, stopped


async def record(lesson: Lesson, out: Path, *, chromium: str | None = None, keep_work: bool = False) -> dict[str, Any]:
    """Record ``lesson`` into a folder of its own in ``out``, its bundle, and say what was made."""

    folder = out / lesson.slug
    folder.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{lesson.slug}-", dir=out))
    studio, stopped = await _capture(lesson, folder, work, chromium)
    shots = studio.film.shots
    if not shots:
        raise RuntimeError("The film kept no frames, so there is nothing to encode.")

    # The film's clock is the video's: each kept frame is 1/FPS of a second, and the studio's times
    # are counted from the first of them.
    seconds = sum(shot.frames for shot in shots) / FPS
    (work / "frames.txt").write_text(concat(shots), encoding="utf-8")
    mp4 = folder / bundle.VIDEO
    picture = work / "picture.mp4" if lesson.narration else mp4
    mixdown.ffmpeg(
        *("-f", "concat", "-safe", "0", "-i", str(work / "frames.txt")),
        # A zoomed frame is taken a few pixels larger than the frame (``film.SPARE``): its top-left is the frame.
        *("-vf", CROP, "-fps_mode", "cfr", "-r", str(FPS)),
        *("-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"),
        str(picture),
    )
    if lesson.narration:
        mixdown.mix(list(studio.spoken), list(studio.clicks), seconds, picture, mp4, work, lesson.loudness)

    captions = [
        timeline.Cue(caption.start, stopped if caption.end is None else caption.end, caption.text)
        for caption in studio.captions
    ]
    captions += list(studio.spoken_only)
    (folder / bundle.CAPTIONS).write_text(timeline.webvtt(captions), encoding="utf-8")

    parts = timeline.chapters(list(studio.marks), seconds)
    if parts:
        (folder / bundle.CHAPTERS).write_text(timeline.webvtt(parts), encoding="utf-8")
        (folder / bundle.YOUTUBE_CHAPTERS).write_text(timeline.youtube_chapters(parts), encoding="utf-8")
        metadata = work / "chapters.ffmeta"
        metadata.write_text(timeline.ffmetadata(f"{lesson.title['kicker']}: {lesson.title['title']}", parts), "utf-8")
        marked = work / "marked.mp4"
        language = ("-metadata:s:a:0", "language=eng") if lesson.narration else ()
        mixdown.ffmpeg(
            *("-i", str(mp4), "-i", str(metadata), "-map", "0", "-map_metadata", "1", "-map_chapters", "1"),
            *("-c", "copy", *language, "-movflags", "+faststart", str(marked)),
        )
        marked.replace(mp4)
    bundle.write_page(lesson.page, folder)
    if not keep_work:
        shutil.rmtree(work)
    return {
        "bundle": str(folder),
        "video": str(mp4),
        "seconds": round(seconds, 1),
        "frames": round(seconds * FPS),
        "captions": len(captions),
        "spoken": len(studio.spoken),
        "clicks": len(studio.clicks),
        "chapters": [f"{timeline.clock_time(part.start)} {part.text}" for part in parts],
    }


async def rehearse(
    lesson: Lesson, out: Path, *, chromium: str | None = None, keep_work: bool = False
) -> dict[str, Any]:
    """Run ``lesson`` as ``record`` does, as a rehearsal, and say what it went through.

    Its app starts, and its setup and its steps run on its page in Chromium as a recording's do, but
    nothing is spoken and no frame is kept, and no wait is longer than ``REHEARSAL_WAIT``: a caption
    held as long as it takes to read, a pause the lesson asks for, a pause after a click. A scroll is
    still waited for until it stops, and a pointer moves its whole way, as a recording's do. A step
    the app no longer has stops it as it stops a recording, with the page kept as ``failure.png`` in
    the lesson's folder in ``out``, and nothing else is written there.
    """

    folder = out / lesson.slug
    folder.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{lesson.slug}-", dir=out))
    began = time.monotonic()
    async with _staged(lesson, folder, work, chromium, {}, rehearsal=True) as studio:
        await studio.page.mouse.move(*studio.mouse)
        await studio.card(lesson.title, 700)
        studio.started = studio.film.clock()
        await lesson.run(studio)
        await studio.quiet()
    if not keep_work:
        shutil.rmtree(work)
    return {
        "rehearsed": lesson.slug,
        "seconds": round(time.monotonic() - began, 1),
        "captions": len(studio.captions),
        "clicks": len(studio.clicks),
        "chapters": [mark.title for mark in studio.marks],
    }


__all__ = ["Lesson", "Mark", "Studio", "record", "rehearse"]
