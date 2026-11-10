"""A recording's frames, each one painted when the film asks for it, on a clock the film keeps.

Chromium's headless shell, started with ``FLAGS``, paints a frame only when asked
(``HeadlessExperimental.beginFrame``), and the page's own time (its timers, its CSS transitions and
animations, a smooth scroll) moves on only when the film moves it, by a frame's worth, 1/``FPS`` of a
second, at a time (``Emulation.setVirtualTimePolicy``). Each frame is stamped with the film's clock,
so every motion in it is as even as the clock, whatever the machine takes over painting it: a
recording made on a slow computer moves exactly as one made on a fast one, only later.

While a page fetches, its time waits for the answer, so a page loads in the film in the frames
its scripts take rather than in the seconds its server does; a fetch that never ends (a stream, a
long poll) is let run past after ``STUCK`` seconds of waiting, so it cannot hold the film for ever,
and while a fetch that has been open that long is still open, the page's time runs on without
waiting for fetches at all, so it costs the film one wait rather than one a frame.

A page on another site is drawn by a renderer of its own, which Chromium starts with the page's
time set to the machine's clock, ahead of the frames' by however much longer than the film the
recording has taken to paint so far (seconds, or a minute); and a page whose time is ahead of its
frames' holds its CSS animations at their first keyframe until the frames catch up, which they may
never do: a menu that fades in stays invisible. So the frames keep the time of the renderer drawing
the page: each answer to the film's ``setVirtualTimePolicy`` says when that renderer's time began
(``virtualTimeTicksBase``), and the film, having moved it on by every frame's worth since, times the
next frame no more than ``BEHIND`` before the page's time. The frames' times only ever move on; the
film's own clock, its frames counted, is not changed.

The film paints from before the first page loads to the end of the recording: a page's scripts,
its loads and Playwright's own waits all need frames. It writes them to its folder only while it
is ``rolling``, and a frame the same as the one before (nothing on the page moved) is not written
again: the last file is held a frame longer. A frame can show the screen through a camera
(``view``), a rectangle of it painted larger, crisply, through a clipped screenshot that rides
on the next frame.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import CDPSession

from pageant.camera import WIDTH

#: Frames a second.
FPS = 60
#: What Chromium's headless shell is started with, so it paints only when asked and keeps the page's time.
FLAGS = ("--enable-begin-frame-control", "--deterministic-mode")
#: Seconds the film waits for a fetch before it lets the page's time run past it.
STUCK = 2.0
#: How many times the film asks again, ``STUCK`` seconds apart, for the page's time to move on a frame
#: when no answer says it has, before it paints the frame anyway (``Film._expired``).
ASKS = 3
#: Real seconds a frame's painting may take before the film stops with that said, rather than wait for ever.
PAINT_SECONDS = 60.0
#: Seconds behind the page's time a frame is timed, at least, when the frames catch up with it
#: (``Film._next_time``). In a browser a frame always began a little before the page's now, and the
#: film holds the page's clock still until a frame is drawn: timed level with it, a frame on Stripe's
#: Checkout page was never drawn. What waits instead is a page's first tenth of a second of CSS
#: animation.
BEHIND = 0.1
#: How the frames are kept: JPEG, at this quality.
QUALITY = 90
#: How many times the same moment is painted again for a zoomed frame's screenshot that missed its
#: frame, and how long, in real seconds, its answer is waited for after each.
REPAINTS = 4
TAKEN = 0.03
#: A frame's pixels: the screen at the device scale the browser paints it at.
FRAME_WIDTH, FRAME_HEIGHT = 1920, 1080
#: A pixel's colour changed where no one can see it, so the next frame has something new to paint and so
#: a picture to give: Chromium gives none of a frame in which nothing changed.
NUDGE = """(() => {
  let dot = document.getElementById("__pageant_nudge");
  if (!dot) {
    dot = document.createElement("div");
    dot.id = "__pageant_nudge";
    Object.assign(dot.style, { position: "fixed", left: "0", top: "0", width: "1px", height: "1px",
      pointerEvents: "none", zIndex: "2147483647" });
    (document.body || document.documentElement).append(dot);
  }
  dot.style.background = dot.style.background === "rgba(0, 0, 0, 0.01)" ? "rgba(0, 0, 0, 0.02)" : "rgba(0, 0, 0, 0.01)";
})()"""
#: How many of the frame's pixels a zoomed frame's screenshot is taken larger than the frame, right and below.
SPARE = 3
#: What the encoder keeps of each frame: its top-left FRAME_WIDTH x FRAME_HEIGHT (``crop``'s filter).
CROP = f"crop={FRAME_WIDTH}:{FRAME_HEIGHT}:0:0"


class NoBeginFrame(RuntimeError):
    """The browser cannot paint a frame when asked: it is not Chromium's headless shell."""


@dataclass
class Shot:
    """A file of the film, and how many frames in a row it is."""

    file: Path
    frames: int = 1


@dataclass
class Film:
    """The frames of a recording, and the clock they keep. Times are seconds of film."""

    cdp: CDPSession
    #: Where frames are written while rolling; ``None`` paints them without keeping any, as a rehearsal does.
    folder: Path | None = None
    #: How many frames have been painted since the film started.
    count: int = 0
    #: The number of the last frame ``before`` was called for: a change a step makes now shows from
    #: the frame after it, whatever frame is being painted as it makes it.
    hooked: int = 0
    #: Whether painted frames are kept.
    rolling: bool = False
    #: Whether the video leaves out the frames painted now, as an edit cuts a wait (``Studio.cut``): the
    #: page's time runs on, and the film's clock, which is the video's, does not.
    cutting: bool = False
    #: How many frames were painted while cutting: the frames the video goes without.
    skipped: int = 0
    #: What the next frame shows: the whole screen (``None``), or a rectangle of the page, in its own
    #: (document) CSS pixels, painted to fill the frame.
    clip: dict[str, float] | None = None
    #: Called before each frame is painted, with the frame's number, so a camera can move.
    before: Callable[[int], Awaitable[None]] | None = None
    shots: list[Shot] = field(default_factory=list)
    _base: float = field(default=0.0, init=False, repr=False)
    _tick: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _stopping: bool = field(default=False, init=False, repr=False)
    _failure: BaseException | None = field(default=None, init=False, repr=False)
    #: The last picture Chromium gave of the whole screen, and the last one kept.
    _latest: bytes = field(default=b"", init=False, repr=False)
    #: A picture of the screen asked for (``picture``), and the one the next frame gave.
    _asked: bool = field(default=False, init=False, repr=False)
    _picture: bytes = field(default=b"", init=False, repr=False)
    _kept: bytes = field(default=b"", init=False, repr=False)
    #: The page's requests not yet answered, by id, with the machine's time each was sent at.
    _open: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    #: When the time of the renderer drawing the page began, in the milliseconds of the machine's clock
    #: that frames are timed in, and how much of it the film has moved on since: the page's time now.
    _began: float | None = field(default=None, init=False, repr=False)
    _moved: float = field(default=0.0, init=False, repr=False)
    #: How far the frames' times have been moved on to keep up with a renderer started after the film.
    _caught_up: float = field(default=0.0, init=False, repr=False)

    def clock(self) -> float:
        """Seconds of the video's frames painted so far: the frames left out by a cut are not counted."""

        return (self.count - self.skipped) / FPS

    async def start(self) -> None:
        """Hold the page's time, and start painting a frame for each frame's worth of it."""

        self._renderer(await self.cdp.send("Emulation.setVirtualTimePolicy", {"policy": "pause"}))
        self.cdp.on("Network.requestWillBeSent", self._sent)
        self.cdp.on("Network.loadingFinished", self._answered)
        self.cdp.on("Network.loadingFailed", self._answered)
        await self.cdp.send("Network.enable")
        # Chromium's frame times are milliseconds of the machine's monotonic clock, as Python's are.
        self._base = time.monotonic() * 1000
        await self._paint_one()
        self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        if self._failure is not None:
            raise self._failure

    def roll(self) -> None:
        """Keep the frames painted from now on."""

        self.rolling = True

    async def until(self, frame: int) -> None:
        """Wait until ``frame`` frames have been painted."""

        while self.count < frame:
            if self._failure is not None:
                raise self._failure
            if self._task is None or self._task.done():
                raise RuntimeError("The film stopped before the frame a step waited for.")
            tick = self._tick
            await tick.wait()

    async def frames(self, count: int) -> None:
        """Wait ``count`` frames."""

        await self.until(self.count + count)

    async def seconds(self, seconds: float) -> None:
        """Wait ``seconds`` of film, to the nearest frame; a wait of under half a frame waits none."""

        await self.until(self.count + round(seconds * FPS))

    async def _run(self) -> None:
        try:
            while not self._stopping:
                await self._paint_one()
        except BaseException as error:
            self._failure = error
        finally:
            tick, self._tick = self._tick, asyncio.Event()
            tick.set()

    def _sent(self, event: dict[str, Any]) -> None:
        # A redirect is sent again under the same id: it is still the one request, open since the first.
        self._open.setdefault(str(event.get("requestId")), time.monotonic())

    def _answered(self, event: dict[str, Any]) -> None:
        self._open.pop(str(event.get("requestId")), None)

    def stuck(self) -> bool:
        """Whether a request the page made has been open longer than ``STUCK``: a stream, a long poll."""

        now = time.monotonic()
        return any(now - sent > STUCK for sent in self._open.values())

    async def _advance(self) -> None:
        """Move the page's time on by a frame, waiting for what it is fetching, but not for ever.

        While a request is stuck (``stuck``), the time runs on without waiting for fetches at all:
        Chromium waits for every fetch or none, and one that never ends would cost every frame
        ``STUCK`` seconds.
        """

        loop = asyncio.get_running_loop()
        expired: asyncio.Future[None] = loop.create_future()

        def done(_: Any) -> None:
            if not expired.done():
                expired.set_result(None)

        self.cdp.once("Emulation.virtualTimeBudgetExpired", done)
        budget = 1000 / FPS
        if self.stuck():
            await self._policy("advance", budget)
            await self._expired(expired, budget)
        else:
            await self._policy("pauseIfNetworkFetchesPending", budget)
            try:
                await asyncio.wait_for(asyncio.shield(expired), STUCK)
            except TimeoutError:
                await self._policy("advance", budget)
                await self._expired(expired, budget)
        self._moved += budget

    async def _expired(self, expired: asyncio.Future[None], budget: float) -> None:
        """Wait for the page's time to have moved on, asking again every ``STUCK`` seconds it has not.

        The answer can be lost: a page that goes to another while its time moves on can take with it
        the renderer that would have given it, and the one that replaced it was asked for nothing. A
        frame asked for ``ASKS`` times with no answer is painted anyway, rather than the film waiting
        for ever.
        """

        for _ in range(ASKS):
            try:
                await asyncio.wait_for(asyncio.shield(expired), STUCK)
                return
            except TimeoutError:
                await self._policy("advance", budget)

    async def _policy(self, policy: str, budget: float) -> None:
        self._renderer(await self.cdp.send("Emulation.setVirtualTimePolicy", {"policy": policy, "budget": budget}))

    def _renderer(self, answer: dict[str, Any] | None) -> None:
        """Note when the time of the renderer drawing the page began: a renderer new since the last
        answer (the page went to another site) began its own, which the film has not moved on yet."""

        began = (answer or {}).get("virtualTimeTicksBase")
        if began and began != self._began:
            self._began, self._moved = float(began), 0.0

    def _next_time(self) -> float:
        """When the next frame is: a frame after the last, or ``BEHIND`` the page's time if that is later.

        The page's time is that far ahead only where a renderer started since the film did: it began
        on the machine's clock, which a recording's frames fall behind, and a frame far behind its
        page's time leaves the page's CSS animations at their first keyframe. The frames' times catch
        up with it there, and only ever move on.
        """

        at = self._base + self._caught_up + (self.count + 1) * 1000 / FPS
        if self._began is not None:
            page = self._began + self._moved - BEHIND * 1000
            if page > at:
                self._caught_up += page - at
                at = page
        return at

    async def _paint_one(self) -> None:
        """Paint the next frame, and keep it if the film is rolling.

        A film with a folder asks every frame for its picture, which Chromium gives only when
        something on the screen changed; the last one it gave is the screen as it is. A zoomed
        frame is a clipped screenshot as well, asked for first, as it is taken in the frame painted
        after it is asked for.
        """

        self.hooked = self.count + 1
        if self.before is not None:
            await self.before(self.hooked)
        # Its time is set once the page's time has moved on to it (``_next_time``).
        begin: dict[str, Any] = {"interval": 1000 / FPS}
        shooting = self.folder is not None
        asked = self._asked
        if asked:
            begin["screenshot"] = {"format": "png"}
        elif shooting:
            begin["screenshot"] = {"format": "jpeg", "quality": QUALITY}
        clipped: bytes | None = None
        if shooting and self.rolling and self.clip is not None:
            # The clip's corner on the frame's own pixel grid, so Chromium's rounding of it moves
            # nothing; and the clip a few of the frame's pixels larger than the frame, as Chromium also
            # rounds its size, sometimes down. The encoder keeps the frame's top-left FRAME_WIDTH x
            # FRAME_HEIGHT (``CROP``): exact pixels, never resampled.
            scale = WIDTH / self.clip["width"]
            unit = WIDTH / FRAME_WIDTH / scale
            spare = SPARE * unit
            clip = {
                "x": round(self.clip["x"] / unit) * unit,
                "y": round(self.clip["y"] / unit) * unit,
                "width": self.clip["width"] + spare,
                "height": self.clip["height"] + spare,
                "scale": scale,
            }
            params = {"format": "jpeg", "quality": QUALITY, "clip": clip}
            shot = asyncio.ensure_future(self.cdp.send("Page.captureScreenshot", params))
            try:
                # The request has to reach Chromium before the frame it rides on is asked for: the
                # page's time moves on in between, which takes a few round trips.
                await self._advance()
                begin["frameTimeTicks"] = self._next_time()
                painted = await self._begin(begin)
                for again in range(1, REPAINTS + 1):
                    if (await asyncio.wait({shot}, timeout=TAKEN))[0]:
                        break
                    # Not taken in that frame (a scaled screenshot often waits for the frame after
                    # the one it was asked before): paint the same moment again, a hair later, for it.
                    repainted = await self._begin({**begin, "frameTimeTicks": begin["frameTimeTicks"] + 0.01 * again})
                    painted = repainted if repainted.get("screenshotData") else painted
                else:
                    await asyncio.wait({shot}, timeout=1.0)
                if shot.done() and not shot.cancelled() and shot.exception() is None:
                    clipped = base64.b64decode(shot.result()["data"])
                # A screenshot not taken (the page went to another while it waited) leaves the frame
                # whole: a page that changes is a cut to the whole screen in any case.
            finally:
                if not shot.done():
                    shot.cancel()
        else:
            await self._advance()
            begin["frameTimeTicks"] = self._next_time()
            painted = await self._begin(begin)
        if painted.get("screenshotData") and asked:
            self._picture, self._asked = base64.b64decode(painted["screenshotData"]), False
        elif painted.get("screenshotData"):
            self._latest = base64.b64decode(painted["screenshotData"])
        self.count += 1
        if self.cutting:
            self.skipped += 1
        elif shooting and self.rolling:
            self._keep(clipped if clipped is not None else self._latest)
        tick, self._tick = self._tick, asyncio.Event()
        tick.set()

    async def picture(self, tries: int = 10) -> bytes | None:
        """The screen as it is, painted fresh, as a PNG: what a failed step keeps of its page.

        Taken with the film's own frames, as Chromium's screenshot (``Page.captureScreenshot``) waits for
        a frame with something new in it, which a still page may never paint. A pixel no one can see is
        changed first (``NUDGE``), as a frame gives its picture only when something on it changed.
        ``None`` when no frame gave one in ``tries``.
        """

        for _ in range(tries):
            self._asked, self._picture = True, b""
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.cdp.send("Runtime.evaluate", {"expression": NUDGE}), 2)
            await self.frames(2)
            if self._picture:
                return self._picture
        self._asked = False
        return None

    async def _begin(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(self.cdp.send("HeadlessExperimental.beginFrame", params), PAINT_SECONDS)
        except TimeoutError:
            raise RuntimeError(
                f"Chromium painted no frame in {PAINT_SECONDS:g} s of asking (frame {self.count + 1}): the browser "
                "has stopped drawing the page."
            ) from None
        except Exception as error:
            if "wasn't found" in str(error):
                raise NoBeginFrame(
                    "Recording paints each frame itself, which takes Chromium's headless shell "
                    "(chrome-headless-shell); this browser cannot. Leave --chromium and PAGEANT_CHROMIUM "
                    "unset to use Playwright's, or point them at a chrome-headless-shell."
                ) from error
            raise

    def _keep(self, picture: bytes) -> None:
        """Keep a frame: a new file, or the last one held a frame longer when the picture is the same."""

        if self.folder is None:
            return
        if not picture:
            raise RuntimeError("The film has no picture of the screen to keep: Chromium painted none yet.")
        if self.shots and picture == self._kept:
            self.shots[-1].frames += 1
            return
        file = self.folder / f"f{len(self.shots):06d}.jpg"
        file.write_bytes(picture)
        self._kept = picture
        self.shots.append(Shot(file))

    @property
    def last_file(self) -> Path | None:
        return self.shots[-1].file if self.shots else None


def concat(shots: list[Shot]) -> str:
    """The shots as ffmpeg's concat demuxer reads them: each file, held for its frames."""

    lines = []
    for shot in shots:
        lines += [f"file '{shot.file.as_posix()}'", f"duration {shot.frames / FPS:.6f}"]
    if shots:
        # The demuxer takes the last file's duration only from a file after it.
        lines.append(f"file '{shots[-1].file.as_posix()}'")
    return "\n".join(lines) + "\n"


__all__ = [
    "CROP",
    "FLAGS",
    "FPS",
    "FRAME_HEIGHT",
    "FRAME_WIDTH",
    "QUALITY",
    "SPARE",
    "STUCK",
    "ASKS",
    "PAINT_SECONDS",
    "Film",
    "NoBeginFrame",
    "Shot",
    "concat",
]
