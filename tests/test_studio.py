"""The studio's steps in a real Chromium: a lesson that goes from page to page keeps what is on
screen, and a click after a long scroll lands where it aims.

Each document a page loads starts the overlay afresh, so a click that goes to another page (a link,
a form post, a server redirect) used to leave the next page with no chapter label, no caption and
the pointer drawn at the middle of the screen; and ``glide`` read where its target was 450 ms into a
smooth scroll, which a long one is still in, so the click went where the target had been. These
hold that neither happens, by running lessons through ``studio.rehearse``, the studio ``record``
uses with nothing spoken or filmed, against a small app of their own.

They drive the browser, so they take the record extra and a Chromium: Playwright's own
(``playwright install chromium``) or the one ``PAGEANT_CHROMIUM`` names. Where either is missing
they are skipped, unless ``PAGEANT_STUDIO_TESTS=required``, as CI's studio job sets it.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from pageant import bundle
from pageant.apps import Running

REQUIRED = os.environ.get("PAGEANT_STUDIO_TESTS") == "required"

try:
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    from pageant import studio
    from pageant.studio import Lesson, Studio
except ModuleNotFoundError as missing:
    if REQUIRED:
        raise
    pytest.skip(f"the studio's tests take the record extra; {missing.name} is not installed", allow_module_level=True)

#: What the overlay shows, read from the page: what a frame painted now would have on it.
READ = """() => {
  const root = [...document.documentElement.children].find((el) => el.style.zIndex === "2147483000");
  if (!root) return null;
  const [, , caption, label, card, pointer] = root.children;
  const seen = (el) => {
    const style = getComputedStyle(el);
    return style.opacity === "1" && style.visibility !== "hidden" && style.display !== "none";
  };
  return {
    label: seen(label) ? label.textContent : null,
    caption: seen(caption) ? caption.textContent : null,
    card: seen(card) ? card.children[2].textContent : null,
    pointer: seen(pointer) ? pointer.style.transform : null,
    fading: document.getAnimations().filter((a) => a.effect && root.contains(a.effect.target)).length,
  };
}"""
#: Waits until nothing the overlay shows is fading in or out.
STILL = f"() => ({READ})().fading === 0"
#: Waits until the page has kept what its first frame showed, which can be after its load event.
PAINTED = "() => window.firstFrame !== undefined"

HOME = """<!doctype html>
<html><head><meta charset="utf-8"><title>Home</title>
<style>@keyframes drift { from { transform: translateX(0) } to { transform: translateX(100px) } }</style>
</head>
<body style="margin:0;font:16px/1.4 sans-serif">
  <header style="height:240px;padding:24px">
    <a id="to-b" href="/b">To page B</a>
    <a id="to-stalled" href="/stalled">To a page still loading its script</a>
    <a id="through" href="/redirect">Through a redirect</a>
    <a id="slow" href="/slow">To a slow page</a>
    <form method="post" action="/post"><button id="post">Post the form</button></form>
    <button id="hero" type="button" onclick="window.clicked = (window.clicked || 0) + 1">Start selling</button>
    <button id="drifting" type="button" style="animation:drift 1s linear infinite">Never still</button>
  </header>
  <div style="height:6000px"></div>
  <section style="padding:24px"><button id="far" type="button">Work out the earnings</button></section>
</body></html>
"""


def _other(title: str, head: str = "") -> str:
    """A page other than the first, which keeps what the overlay showed in its first frame, read just
    before that frame was painted."""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>{head}</head>
<body style="margin:0;padding:24px;font:16px/1.4 sans-serif">
  <h1>{title}</h1><a id="home" href="/">Home</a>
  <script>requestAnimationFrame(() => {{ window.firstFrame = ({READ})(); window.scriptBefore = !!window.stalled; }});</script>
</body></html>
"""


PAGES = {
    "/": HOME,
    "/b": _other("Page B"),
    "/slow": _other("A slow page"),
    "/done": _other("Posted"),
    # Painted well before its DOMContentLoaded, which waits for a deferred script that is slow to come.
    "/stalled": _other("A page still loading its script", '<script src="/stall.js" defer></script>'),
}


class _Pages(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/redirect":
            self._redirect(302, "/b")
            return
        if path in {"/slow", "/stall.js"}:
            # Long enough for the steps after the click to run while it loads.
            time.sleep(0.6)
        body = "window.stalled = true;\n" if path == "/stall.js" else PAGES.get(path)
        if body is None:
            self.send_error(404)
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript" if path.endswith(".js") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._redirect(303, "/done")

    def _redirect(self, status: int, to: str) -> None:
        self.send_response(status)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


class _Site:
    """The app these lessons film: pages, a form that posts, and redirects, as a product has."""

    def start(self, work: Path, env: Mapping[str, str]) -> Running:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Pages)
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def stop() -> None:
            server.shutdown()
            server.server_close()

        return Running(address=f"http://127.0.0.1:{server.server_address[1]}/", env=dict(env), ready=None, stop=stop)


FOLDER = "studio-steps"
PAGE = bundle.Page(
    folder=FOLDER, slug="studio-steps", title="The studio's steps", summary="Steps in Chromium.", body="## Steps\n"
)


@pytest.fixture(scope="module")
def chromium() -> Iterator[str | None]:
    """The Chromium the studio drives here, once it is known to start."""

    path = os.environ.get("PAGEANT_CHROMIUM")

    async def starts() -> None:
        async with async_playwright() as playwright:
            await (await playwright.chromium.launch(executable_path=path)).close()

    try:
        asyncio.run(starts())
    except PlaywrightError as missing:
        if REQUIRED:
            raise
        pytest.skip(f"no Chromium to drive: {missing.message.splitlines()[0]}")
    yield path


def _rehearse(out: Path, run: Callable[[Studio], Awaitable[None]], chromium: str | None) -> dict[str, Any]:
    lesson = Lesson(
        page=PAGE,
        title={"kicker": "Pageant", "title": "The studio's steps", "sub": ""},
        narration={},
        run=run,
        app=_Site(),
    )
    return asyncio.run(studio.rehearse(lesson, out, chromium=chromium))


def _pointer(shown: Mapping[str, Any]) -> tuple[float, float] | None:
    """Where the drawn pointer points: its tip is drawn 4 px left of the mouse and 2 px above it."""

    if shown["pointer"] is None:
        return None
    x, y = re.findall(r"-?\d+(?:\.\d+)?", shown["pointer"])
    return float(x) + 4, float(y) + 2


def _first_frame(tmp_path: Path, chromium: str | None) -> dict[str, Any]:
    """What a page's first frame showed, painted before its DOMContentLoaded, after a click on the
    link to it with a label and a caption up."""

    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        await s.card(None)
        await s.chapter("1 · Sell")
        await s.say("Open the next page.", 0)
        await s.click(s.page.locator("#to-stalled"))
        # Not arrive(), which draws: this is what the page drew as it loaded.
        await s.page.wait_for_url("**/stalled")
        await s.page.wait_for_function(PAINTED)
        seen.update(await s.page.evaluate("window.firstFrame"), mouse=s.mouse)
        seen["its script had run"] = await s.page.evaluate("window.scriptBefore")

    _rehearse(tmp_path, run, chromium)
    return seen


def test_the_page_a_link_goes_to_has_the_label_the_caption_and_the_pointer_in_its_first_frame(
    tmp_path: Path, chromium: str | None
) -> None:
    first = _first_frame(tmp_path, chromium)

    assert first["its script had run"] is False, "the frame was painted before the page's DOMContentLoaded"
    assert (first["label"], first["caption"]) == ("1 · Sell", "Open the next page.")
    assert _pointer(first) == pytest.approx(first["mouse"], abs=0.5), "where the click was, not the middle"
    assert first["fading"] == 0, "drawn at once, with no fade in"


def test_the_next_document_draws_what_was_on_screen_as_it_starts_by_itself(
    tmp_path: Path, chromium: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With no drawing as the page loads, only the script that starts each document draws it.
    monkeypatch.setattr(Studio, "_went", lambda self, frame: None)

    first = _first_frame(tmp_path, chromium)

    assert (first["label"], first["caption"]) == ("1 · Sell", "Open the next page.")
    assert _pointer(first) == pytest.approx(first["mouse"], abs=0.5)
    assert first["fading"] == 0


def test_a_page_given_nothing_draws_no_pointer_and_what_is_shown_later_comes_at_once(
    tmp_path: Path, chromium: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(self: Studio) -> None:
        return None

    # Nothing handed to the next document, and nothing drawn as it loads.
    monkeypatch.setattr(Studio, "_carry", nothing)
    monkeypatch.setattr(Studio, "_went", lambda self, frame: None)
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        await s.card(None)
        await s.chapter("5 · Later")
        await s.say("Shown once the page has loaded.", 0)
        await s.click(s.page.locator("#to-b"))
        await s.page.wait_for_url("**/b")
        seen["loaded"] = await s.page.evaluate(READ)
        await s.arrive("**/b")
        seen["arrived"] = await s.page.evaluate(READ)

    _rehearse(tmp_path, run, chromium)

    loaded = seen["loaded"]
    assert (loaded["label"], loaded["caption"], loaded["pointer"]) == (None, None, None), "not a pointer at the middle"
    arrived = seen["arrived"]
    assert (arrived["label"], arrived["caption"], arrived["fading"]) == (
        "5 · Later",
        "Shown once the page has loaded.",
        0,
    )
    assert arrived["pointer"] is not None


def test_a_form_post_a_redirect_and_a_title_card_keep_what_is_on_screen(tmp_path: Path, chromium: str | None) -> None:
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        home = s.page.url
        await s.card(None)
        await s.chapter("2 · Pay")
        await s.say("Post the form.", 0)
        await s.click(s.page.locator("#post"))
        await s.arrive("**/done")
        seen["after a post and a 303"] = await s.page.evaluate(READ)
        seen["mouse there"] = s.mouse

        await s.page.goto(home)
        await s.say("Go through a redirect.", 0)
        await s.click(s.page.locator("#through"))
        await s.arrive(re.compile(r"/b$"))
        seen["after a 302"] = await s.page.evaluate(READ)

        await s.card({"kicker": "Next", "title": "A page loaded under the card", "sub": ""})
        await s.page.goto(home)
        seen["under the card"] = await s.page.evaluate(READ)
        await s.card(None)
        await s.sleep(600)
        seen["the card lifted"] = await s.page.evaluate(READ)

    _rehearse(tmp_path, run, chromium)

    posted = seen["after a post and a 303"]
    assert (posted["label"], posted["caption"]) == ("2 · Pay", "Post the form.")
    assert _pointer(posted) == pytest.approx(seen["mouse there"], abs=0.5)
    redirected = seen["after a 302"]
    assert (redirected["label"], redirected["caption"]) == ("2 · Pay", "Go through a redirect.")
    under = seen["under the card"]
    assert (under["card"], under["pointer"]) == ("A page loaded under the card", None), "the pointer is under the card"
    lifted = seen["the card lifted"]
    assert (lifted["card"], lifted["label"]) == (None, "2 · Pay")
    assert lifted["pointer"] is not None


def test_a_step_that_runs_while_the_next_page_loads_ends_up_on_it(tmp_path: Path, chromium: str | None) -> None:
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        await s.card(None)
        await s.chapter("Before")
        # The app answers 0.6 s later. Chromium runs nothing on the page being left until the next
        # one starts, and then fails what it held, so these are drawn on the next page instead.
        await s.click(s.page.locator("#slow"))
        await s.chapter("3 · Wait")
        await s.say("Still loading.", 0)
        await s.arrive("**/slow")
        await s.page.wait_for_function(STILL)
        seen["arrived"] = await s.page.evaluate(READ)

    _rehearse(tmp_path, run, chromium)

    assert (seen["arrived"]["label"], seen["arrived"]["caption"]) == ("3 · Wait", "Still loading.")


def test_a_page_is_drawn_again_as_it_loads_for_a_change_its_first_frame_missed(
    tmp_path: Path, chromium: str | None
) -> None:
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        home = s.page.url
        await s.card(None)
        await s.chapter("Before")
        # As if a step changed what is on screen as the next document started, too late for the
        # script that hands it over: that script still says "Before".
        s.label = "After"
        await s.page.goto(home + "b")
        await s._drawn()
        await s.page.wait_for_function(STILL)
        seen["loaded"] = await s.page.evaluate(READ)

    _rehearse(tmp_path, run, chromium)

    assert seen["loaded"]["label"] == "After", "drawn again as it loaded"


def test_a_draw_a_page_load_cuts_off_is_made_again_on_the_page_that_replaced_it(
    tmp_path: Path, chromium: str | None
) -> None:
    seen: dict[str, Any] = {}
    # On the first page it goes to page B and never answers, so only a second try on page B returns.
    goes_and_hangs = (
        "() => location.pathname === '/' ? (location.assign('/b'), new Promise(() => {}))"
        " : (window.drawnOn = location.pathname)"
    )

    async def run(s: Studio) -> None:
        await s.card(None)
        await s._on_page(goes_and_hangs)
        seen["drawn on"] = await s.page.evaluate("window.drawnOn")

    _rehearse(tmp_path, run, chromium)

    assert seen["drawn on"] == "/b"


def test_a_draw_that_fails_on_a_page_that_stays_fails_its_step(tmp_path: Path, chromium: str | None) -> None:
    async def run(s: Studio) -> None:
        await s.card(None)
        await s._on_page("() => { throw new Error('the overlay broke'); }")

    with pytest.raises(PlaywrightError, match="the overlay broke"):
        _rehearse(tmp_path, run, chromium)


def test_the_terminal_keeps_the_label_and_the_caption_and_puts_the_pointer_away(
    tmp_path: Path, chromium: str | None
) -> None:
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        await s.card(None)
        await s.chapter("4 · A terminal")
        await s.say("Now a terminal.", 0)
        await s.terminal("Terminal", "~/work")
        seen["terminal"] = await s.page.evaluate(READ)

    _rehearse(tmp_path, run, chromium)

    shown = seen["terminal"]
    assert (shown["label"], shown["caption"], shown["pointer"]) == ("4 · A terminal", "Now a terminal.", None)


def test_a_click_after_a_long_scroll_lands_on_its_target(tmp_path: Path, chromium: str | None) -> None:
    seen: dict[str, Any] = {}
    under = "([x, y]) => { const el = document.elementFromPoint(x, y); return el && el.id; }"

    async def run(s: Studio) -> None:
        await s.card(None)
        # Down 6000 px to the calculator, then all the way back up to the button at the top: a
        # smooth scroll that long is still moving after the 450 ms glide used to wait.
        await s.glide(s.page.locator("#far"))
        seen["down there"] = await s.page.evaluate(under, list(s.mouse))
        await s.click(s.page.locator("#hero"))
        seen["back up"] = await s.page.evaluate(under, list(s.mouse))
        seen["clicked"] = await s.page.evaluate("window.clicked")
        seen["drawn at"] = _pointer(await s.page.evaluate(READ))
        seen["mouse"] = s.mouse

    _rehearse(tmp_path, run, chromium)

    assert (seen["down there"], seen["back up"], seen["clicked"]) == ("far", "hero", 1)
    # Drawn where the page saw the mouse move, which Chromium gives in whole pixels.
    assert seen["drawn at"] == pytest.approx(seen["mouse"], abs=1)


def test_glide_moves_on_from_a_target_that_never_holds_still(
    tmp_path: Path, chromium: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio, "SETTLE_CAP", 0.8)
    seen: dict[str, Any] = {}

    async def run(s: Studio) -> None:
        await s.card(None)
        began = time.monotonic()
        # Bounded here, so a glide that waits for ever fails this rather than stalling the suite.
        await asyncio.wait_for(s.glide(s.page.locator("#drifting")), timeout=10)
        seen["took"] = time.monotonic() - began

    _rehearse(tmp_path, run, chromium)

    assert 0.8 <= seen["took"] < 2.5


def test_a_rehearsal_cuts_its_waits_short_writes_nothing_and_says_what_it_went_through(
    tmp_path: Path, chromium: str | None
) -> None:
    folder = tmp_path / FOLDER
    folder.mkdir()
    (folder / "failure.png").write_bytes(b"where an earlier run stopped")

    async def run(s: Studio) -> None:
        await s.card(None, 5000)
        await s.chapter("Waiting")
        # Held about 5 s in a recording: 60 ms a character.
        await s.say("A line long enough to take a while to read, held as long as reading it takes, in a recording.")
        await s.sleep(10_000)
        await s.click(s.page.locator("#hero"))
        await s.quiet()

    made = _rehearse(tmp_path, run, chromium)

    # A recording would wait over 20 s in those steps alone.
    assert made.pop("seconds") < 10
    assert made == {"rehearsed": FOLDER, "captions": 1, "clicks": 1, "chapters": ["Waiting"]}
    assert [path.name for path in tmp_path.iterdir()] == [FOLDER], "its work folder is gone"
    assert list(folder.iterdir()) == [], "nothing is written, and an earlier run's failure.png is gone"


def test_a_rehearsal_stops_at_a_step_the_app_no_longer_has_and_keeps_the_page(
    tmp_path: Path, chromium: str | None
) -> None:
    async def run(s: Studio) -> None:
        await s.card(None)
        s.page.set_default_timeout(1000)
        await s.click(s.page.get_by_role("button", name="A button the app no longer has"))

    with pytest.raises(PlaywrightTimeoutError):
        _rehearse(tmp_path, run, chromium)

    assert (tmp_path / FOLDER / "failure.png").stat().st_size > 0
