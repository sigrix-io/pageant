"""Record a lesson as code: the real app in a real browser, with a voice, captions and chapters.

A lesson is a storyboard: a table of what it says, and its steps, each a highlight, a click or a
caption. The studio starts the lesson's app (``apps.py``), opens it in Chromium at 1280x720 CSS
pixels and a device scale of 1.5, so frames are 1920x1080 and text is sharp, draws the cursor,
spotlight, captions and cards over the page (``overlay.js``), and captures every painted frame over
CDP. It writes a folder of the lesson's own in the output folder, named by its page, which is the
lesson's bundle (``bundle.py``):

- ``video.mp4``: H.264 and AAC at 1080p and 30 fps, with its chapters as markers;
- ``cover.jpg``: the poster, which is the title card;
- ``captions.vtt``: the captions, every line spoken;
- ``chapters.vtt`` and ``chapters.txt``: the chapters, for a web page's player and for a
  YouTube description;
- ``lesson.json``: its page.

Every line is spoken before the recording starts (``narrate.py``), so each caption is held
exactly as long as its voice, and the sound is mixed in at the end (``mixdown.py``). A step the app
no longer has (a locator that finds nothing) stops the recording with an error, and the page is
kept as ``failure.png`` beside it, so an app that changed never ships a stale video.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import math
import mimetypes
import shutil
import tempfile
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import Locator, Page, async_playwright

from pageant import apps, bundle, mixdown, narrate, timeline
from pageant.apps import App, Running

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 1280, 720, 1.5
#: A voice starts a moment after its caption fades in, and the next line waits a breath after it.
VOICE_LEAD = 0.25
VOICE_GAP = 0.45


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


@dataclass
class Studio:
    """What a lesson's steps call. Times are seconds since the recording started."""

    page: Page
    lesson: Lesson
    clips: Mapping[str, narrate.Clip]
    work: Path
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
    #: The chapter label on screen, drawn again on a page the lesson goes to.
    label: str | None = None

    def clock(self) -> float:
        return time.time() - self.started

    async def sleep(self, ms: float) -> None:
        await asyncio.sleep(ms / 1000)

    async def card(self, spec: Mapping[str, str] | None, hold_ms: float = 0) -> None:
        """A title card over the page, with the product's mark unless ``spec`` names one; ``None`` lifts it."""

        if spec is not None and self.lesson.mark is not None and "mark" not in spec:
            spec = {**spec, "mark": self.lesson.mark.url}
        await self.page.evaluate("spec => window.__demo.card(spec)", spec)
        await self.sleep(hold_ms)

    async def chapter(self, title: str | None) -> None:
        """The label on screen, and a chapter of the video from here on."""

        if title:
            self.marks.append(timeline.Mark(self.clock(), title))
        self.label = title
        await self.page.evaluate("title => window.__demo.chapter(title)", title)

    async def _voice_free(self) -> None:
        """Never two voices at once: a line waits for the one before it, and a breath after."""

        busy = self.voice_until - time.time()
        if busy > 0:
            await asyncio.sleep(busy + VOICE_GAP)

    def _speak(self, clip: narrate.Clip) -> float:
        """Start a clip now; how long to wait for it, and the breath after."""

        self.spoken.append((self.clock() + VOICE_LEAD, clip.file))
        self.voice_until = time.time() + VOICE_LEAD + clip.seconds
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
        await self.page.evaluate("text => window.__demo.caption(text)", text)
        natural = self._speak(clip) if clip else max(2.4, len(text) * 0.06)
        await asyncio.sleep(natural if hold_ms is None else hold_ms / 1000)

    async def voice(self, key: str, extra_ms: float = 0) -> None:
        """A line spoken over a card, with no caption on screen; the captions file still has it."""

        clip = self.clips.get(key)
        if clip:
            await self._voice_free()
            start = self.clock() + VOICE_LEAD
            self.spoken_only.append(timeline.Cue(start, start + clip.seconds + 0.3, self.lesson.narration[key]["text"]))
            await asyncio.sleep(self._speak(clip))
        await self.sleep(extra_ms)

    async def quiet(self) -> None:
        self._close_caption()
        await self.page.evaluate("() => window.__demo.caption(null)")

    async def spot(self, locator: Locator | None, padding: float = 8) -> None:
        """Dim the page around ``locator``, scrolled into view; ``None`` lifts the spotlight."""

        if locator is None:
            await self.page.evaluate("() => window.__demo.spot(null)")
            return
        await locator.evaluate("el => el.scrollIntoView({ block: 'center', behavior: 'smooth' })")
        await self.sleep(550)
        await locator.evaluate("(el, padding) => window.__demo.spot(el, padding)", padding)
        await self.sleep(450)

    async def glide(self, locator: Locator) -> None:
        """Move the cursor to the middle of ``locator`` as a hand would, not in one jump."""

        await locator.evaluate("el => el.scrollIntoView({ block: 'center', behavior: 'smooth' })")
        await self.sleep(450)
        box = await locator.bounding_box()
        if box is None:
            raise RuntimeError(f"{locator} is not on the page")
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        steps = max(14, round(math.hypot(x - self.mouse[0], y - self.mouse[1]) / 14))
        await self.page.mouse.move(x, y, steps=steps)
        self.mouse = (x, y)
        await self.sleep(220)

    async def click(self, locator: Locator) -> None:
        await self.glide(locator)
        self.clicks.append(self.clock())
        await self.page.mouse.down()
        await self.sleep(70)
        await self.page.mouse.up()
        await self.sleep(350)

    async def terminal(self, title: str = "Terminal", where: str = "~") -> None:
        """Leave the app's page for the terminal, where shell() runs commands, and put the pointer away."""

        self.where = where
        await self.page.goto(self.terminal_url)
        await self.page.wait_for_function("() => window.__term && window.__demo && window.__demo.ready()")
        await self.page.evaluate(
            "([title, where, label]) => { window.__term.title(title); window.__term.prompt(where);"
            " window.__demo.pointer(false); window.__demo.chapter(label); }",
            [title, where, self.label],
        )

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
        for index, line in enumerate(text.split("\n")):
            if index:
                await self.page.keyboard.press("Shift+Enter")
            await locator.press_sequentially(line, delay=delay_ms)


async def _capture(
    lesson: Lesson, out: Path, work: Path, chromium: str | None
) -> tuple[Studio, list[tuple[Path, float]], float]:
    """Record the lesson's frames into its folder ``out``; the studio's log of it, each frame with when it
    was painted, and when it stopped."""

    clips = narrate.speak(lesson.narration, narrate.Voice(lesson.voice)) if lesson.narration else {}
    frames_folder = work / "frames"
    frames_folder.mkdir()
    frames: list[tuple[Path, float]] = []
    acks: set[asyncio.Future[Any]] = set()
    served = {"/": HERE / "terminal.html"}
    if lesson.mark is not None and lesson.mark.url.startswith("/"):
        served[lesson.mark.url] = lesson.mark.file
    running: Running = lesson.app.start(work, apps.environment(work, lesson.commands))
    files = ThreadingHTTPServer(("127.0.0.1", 0), _files(served))
    threading.Thread(target=files.serve_forever, daemon=True).start()
    try:
        async with async_playwright() as playwright:
            # The scale is the browser's own, not an emulated one: only then are screencast
            # frames painted at device pixels (1920x1080) rather than CSS pixels (1280x720).
            browser = await playwright.chromium.launch(
                executable_path=chromium,
                args=[f"--force-device-scale-factor={SCALE}", f"--window-size={WIDTH},{HEIGHT}"],
            )
            context = await browser.new_context(viewport=None, color_scheme=lesson.color_scheme)
            await context.add_init_script(path=HERE / "overlay.js")
            page = await context.new_page()
            studio = Studio(page, lesson, clips, work)
            studio.terminal_url = f"http://127.0.0.1:{files.server_address[1]}/"
            studio.shell_env = {**running.env, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color"}
            try:
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
                await page.mouse.move(*studio.mouse)
                await studio.card(lesson.title, 700)
                cdp = await context.new_cdp_session(page)
                # The poster is the title card, taken over CDP as the frames are, at 1920x1080.
                poster = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 92})
                (out / bundle.COVER).write_bytes(base64.b64decode(poster["data"]))

                def painted(frame: dict[str, Any]) -> None:
                    file = frames_folder / f"f{len(frames):06d}.jpg"
                    file.write_bytes(base64.b64decode(frame["data"]))
                    frames.append((file, time.time()))
                    ack = asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": frame["sessionId"]}))
                    acks.add(ack)
                    ack.add_done_callback(settled)

                def settled(ack: asyncio.Future[Any]) -> None:
                    # An ack still in flight when the page closes fails; that failure is expected.
                    acks.discard(ack)
                    if not ack.cancelled():
                        ack.exception()

                cdp.on("Page.screencastFrame", painted)
                studio.started = time.time()
                await cdp.send(
                    "Page.startScreencast",
                    {"format": "jpeg", "quality": 90, "maxWidth": int(WIDTH * SCALE), "maxHeight": int(HEIGHT * SCALE)},
                )
                await lesson.run(studio)
                await studio.quiet()
                await asyncio.sleep(max(0.4, studio.voice_until - time.time() + 0.4))
                stopped = time.time()
                await cdp.send("Page.stopScreencast")
            except Exception:
                with contextlib.suppress(Exception):
                    await page.screenshot(path=out / "failure.png")
                raise
            finally:
                await context.close()
                await browser.close()
    finally:
        files.shutdown()
        running.stop()
    return studio, frames, stopped


async def record(lesson: Lesson, out: Path, *, chromium: str | None = None, keep_work: bool = False) -> dict[str, Any]:
    """Record ``lesson`` into a folder of its own in ``out``, its bundle, and say what was made."""

    folder = out / lesson.slug
    folder.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{lesson.slug}-", dir=out))
    studio, frames, stopped = await _capture(lesson, folder, work, chromium)
    if not frames:
        raise RuntimeError("The browser painted no frames, so there is nothing to encode.")

    # The video's first instant is its first frame's, so every time recorded moves by that much.
    offset = frames[0][1] - studio.started
    seconds = stopped - frames[0][1]
    # Each frame lasts until the next was painted; ffmpeg turns that into a steady 30 fps.
    concat = []
    for (file, at), (_, after) in zip(frames, [*frames[1:], (None, stopped)], strict=True):
        concat += [f"file '{file.as_posix()}'", f"duration {after - at:.3f}"]
    concat.append(f"file '{frames[-1][0].as_posix()}'")
    (work / "frames.txt").write_text("\n".join(concat) + "\n", encoding="utf-8")
    mp4 = folder / bundle.VIDEO
    picture = work / "picture.mp4" if lesson.narration else mp4
    mixdown.ffmpeg(
        *("-f", "concat", "-safe", "0", "-i", str(work / "frames.txt"), "-fps_mode", "cfr", "-r", "30"),
        *("-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"),
        str(picture),
    )
    if lesson.narration:
        voice = [(at - offset, file) for at, file in studio.spoken]
        mixdown.mix(voice, [at - offset for at in studio.clicks], seconds, picture, mp4, work)

    captions = [
        timeline.Cue(
            caption.start - offset,
            (stopped - studio.started if caption.end is None else caption.end) - offset,
            caption.text,
        )
        for caption in studio.captions
    ]
    captions += [timeline.Cue(cue.start - offset, cue.end - offset, cue.text) for cue in studio.spoken_only]
    (folder / bundle.CAPTIONS).write_text(timeline.webvtt(captions), encoding="utf-8")

    parts = timeline.chapters([timeline.Mark(mark.start - offset, mark.title) for mark in studio.marks], seconds)
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
        "frames": len(frames),
        "captions": len(captions),
        "spoken": len(studio.spoken),
        "clicks": len(studio.clicks),
        "chapters": [f"{timeline.clock_time(part.start)} {part.text}" for part in parts],
    }


__all__ = ["Lesson", "Mark", "Studio", "record"]
