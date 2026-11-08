# Pageant

Record a product's video lessons from the app itself, as code.

A lesson is a Python file: a table of everything it says, and its steps, each a highlight, a click,
a line typed or a command run. `pageant record` starts the product, drives its real page in
Chromium with a cursor, a spotlight and captions drawn over it, paints every frame of the video
itself, 60 a second, zooming in on what a step points at if the lesson asks, speaks every line with
a voice that runs on your computer over music made there, and writes a folder of the lesson's own:

| File | What it is |
| --- | --- |
| `video.mp4` | the video: 1080p, 60 fps, H.264 and AAC, with its chapters as markers desktop players show |
| `cover.jpg` | its poster, which is the title card |
| `captions.vtt` | its captions: every line spoken, including those over a card |
| `chapters.vtt` | its chapters, for a web page's video player |
| `chapters.txt` | its chapters as lines for a YouTube description, which YouTube turns into chapters |
| `lesson.json` | its page on a learning site |

Because a lesson is code, it is recorded again in a few minutes when the product changes, and a
step the product no longer has (a button that moved, a label that changed) stops the recording
with an error, and a screenshot of the page, rather than letting a stale video out.

Pageant came out of [Bailey](https://github.com/sigrix-io/bailey)'s `lessons/`, which recorded
Bailey's four video lessons on [sigrix.io](https://sigrix.io/learn/tag/bailey) with this engine.

## Try it

You need Python 3.11 or later and ffmpeg on the `PATH`.

```bash
pip install "pageant[record]"
```

```bash
playwright install chromium
```

(which installs Chromium's headless shell too, what Pageant records with)

```bash
pageant example notebook
```

```bash
pageant record notebook/lesson.py
```

`pageant example` writes the example lesson into `notebook/`: Notebook, a one-page app the package
ships, filmed in three chapters. Recording it takes a minute or two and writes
`notebook/out/first-note/`. The first recording fetches the voice,
[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (Apache-2.0, about 120 MB), from that
project's release on GitHub, checks it against the SHA-256 in `narrate.py`, and keeps it in
`~/.cache/pageant/` with every line it speaks, so a lesson recorded again speaks nothing it has
spoken before.

`import pageant` needs only the standard library: a project that packs its lessons or writes
their YouTube text installs `pageant` alone, and only recording takes the `record` extra
(Playwright, Kokoro and numpy).

## A lesson

```python
from pathlib import Path

import pages

from pageant.apps import StaticSite
from pageant.studio import Lesson, Mark, Studio

SITE = Path(__file__).resolve().parent / "site"

NARRATION = {
    "title": {"text": "Notebook, lesson one: your first note."},
    "page": {"text": "This is Notebook: a box to write a note in, and the notes you have kept."},
    "add": {"text": "Then add it."},
}


async def run(s: Studio) -> None:
    await s.voice("title", 300)  # spoken over the title card
    await s.card(None, 700)  # lift it
    await s.chapter("The page")  # a label on screen, and a chapter of the video
    await s.say("page")  # a caption, held as long as its voice
    await s.spot(s.page.locator("#notes"))  # dim everything else
    await s.click(s.page.get_by_role("button", name="Add note"))


LESSON = Lesson(
    page=pages.FIRST_NOTE,
    title={"kicker": "Notebook · lesson 1", "title": "Your first note", "sub": "Pageant's example lesson"},
    narration=NARRATION,
    run=run,
    app=StaticSite(SITE, ready="#notes"),
    mark=Mark("/mark.svg", SITE / "mark.svg"),
)
```

`pageant record` loads the file as running it would, with its own folder first on the import
path, so a lesson imports the pages beside it, and records the lesson it names as `LESSON`.

A `Lesson` holds:

| Field | What it is |
| --- | --- |
| `page` | its page (below), which names the folder it records into |
| `title` | the title card, which is also the poster: `kicker`, `title` and `sub` |
| `narration` | every line, by key: `text` is the caption, and `spoken` what the voice says instead, if anything |
| `run` | its steps |
| `app` | the product it films, and how to start it (below) |
| `voice` | Kokoro's voice, `af_heart` unless it says |
| `color_scheme` | `light` or `dark`, as the browser asks the page for |
| `setup` | steps on the page before the recording starts, so a lesson starts where the one before left off |
| `commands` | stand-in programs put first on the app's `PATH` and the terminal's, each a name and the script this Python runs |
| `mark` | the product's mark on the title cards: the address its app serves it at, and the file |
| `label_corner` | where the chapter label sits: `top-right`, or `top-left` for an app whose controls are on the right |
| `label_seconds` | how long the chapter label shows after its chapter starts; unset, it stays up until the next one |
| `pronounce` | words the voice says differently from how they are written, respelled in every line it speaks while the captions keep the written form: `{"example.io": "example dot eye oh"}` |
| `loudness` | the mix's loudness in LUFS, set in two passes: -16 unless it says, the level web players expect, or -14, what YouTube plays every video at |
| `zoom` | how far the camera may zoom in on what a spotlight shows: 1, the default, never zooms; 2 shows it up to twice as large (below) |

A lesson's steps call the studio, `s`:

| Step | What it does |
| --- | --- |
| `s.card(spec, ms)`, `s.card(None)` | a title card over the page, with the product's mark; `None` lifts it. `spec`'s `points` are a short list under the title, numbered, or ticked with `"checks": True` for a recap; `"mark": ""` draws it with no mark |
| `s.tell(spec, key, ms, at)` | a card whose points come up one at a time while the line `key` is spoken over it: the first as the voice starts, each next at its share of the line in `at` (evenly, if none), so a line that names them in order shows each as it is said |
| `s.chapter(title)` | the label on screen, and a chapter of the video from here on |
| `s.say(key_or_text, ms)` | a caption, held as long as its voice, or long enough to read; a shorter `ms` lets the voice run on under the steps that follow |
| `s.voice(key, ms)` | a line spoken with no caption on screen, as over a card; the captions file still has it |
| `s.quiet()` | takes the caption down |
| `s.spot(locator)`, `s.spot(None)` | dims the page around an element, once a scroll to it has stopped; the spotlight comes up where the element is, and one already up is taken down while the page scrolls there. With the lesson's `zoom`, or `zoom=` for this one, the camera moves in on it |
| `s.glide(locator)`, `s.click(locator)` | moves the cursor there as a hand would, along a gently curved path that speeds up and slows down, a point a frame, once the page has stopped scrolling to it and once a view transition it is in is over, and clicks, with a sound, where the element is when the mouse goes down |
| `s.arrive(url)` | waits for the page a step went to, loaded: `url` is its address, a glob such as `"**/checkout/done"`, a regular expression, or a function of the address |
| `s.type(locator, text)` | types as a person does, a key every frame or more |
| `s.paste(locator, text)` | puts text in at once, as a paste does, for words too long to watch being typed |
| `s.terminal(title, where)` | leaves the page for a terminal |
| `s.shell(command)` | types a command at the terminal's prompt, runs it for real, and shows what it prints as it prints it |
| `s.sleep(ms)` | waits |
| `s.page` | the Playwright page itself, for anything else |

A step that goes to another page (a link, a form post, a server redirect such as a checkout's)
loads a new document, and the overlay starts afresh in each one. So the studio keeps the chapter
label, the caption, the title card and where the pointer is, and hands them to every page the
lesson goes to as that page starts, so its first frame has them; what a step changes while the
page loads is drawn on it too. `s.arrive(url)` is for the step after such a click, so that it does
not start on the page before, as it could with a button both pages have:

```python
await s.click(s.page.get_by_role("button", name="Pay"))
await s.arrive("**/checkout/done")
await s.say("paid")
```

Before the pointer moves to an element, the studio scrolls it to the middle of the page and waits
for the scroll to stop, until two reads of the element's box 120 ms apart agree, since a long
smooth scroll is still moving after a short one is over. It waits three seconds from the scroll's
start at most, for an element that never holds still. An element already in view is not scrolled
to: all of it on screen, and either in a bar that stays put as the page scrolls (fixed or sticky)
or clear of the captions at the foot of the screen with nothing drawn over its middle. Chromium
scrolls the page under a sticky top bar to bring a control in it nearer, so a lesson pointing at
an app's cart or account menu would otherwise move the page under the bar.

### Every frame, painted

Pageant does not film the screen as it goes; it paints the video a frame at a time
(`pageant.film`). Chromium's headless shell paints a frame only when asked, and the page's own
time, its timers, transitions, animations and smooth scrolls, moves on only when the film moves it,
1/60 of a second a frame. So every motion in the video is as even as the clock, on a slow computer
as on a fast one: a pointer's move, a scroll, a fade. The pointer is drawn along its path a point
a frame, and the page sees one mouse move, at its end, so a menu that opens on hover does not
flicker open on the way.

While a page fetches, its time waits for the answer, so a page loads in the video in the frames its
scripts take, not the seconds its server does; a fetch that never ends (a stream, a long poll) is
let run past after two seconds of waiting. A page on another site (a payment provider's checkout,
and the app it sends the buyer back to) gets a renderer of its own, whose clock Chromium starts at
the machine's time, far ahead of a recording's frames; the film moves its frames' times on to a
tenth of a second short of that page's, so its fades and menus run as they do anywhere else. A
frame the same as the one before is not written again.
Recording takes the headless shell, `chrome-headless-shell`, which `playwright install chromium`
installs beside Chromium; `--chromium` names one already installed. A Chromium that is not one
stops the recording with that said.

### The camera

A lesson with `zoom` above 1 has a camera (`pageant.camera`). When a step puts the spotlight on
an element, the camera moves in on it, over 0.7 s, until it fills as much of the room above the
captions as fits, no more than `zoom` times larger and never past the screen's edges; a zoom of
less than 1.18 times is not made. The page is painted at that size, not stretched: its text is as
sharp as at full screen. The captions, the chapter label and the cards keep their size and place.
The camera moves back out when the spotlight lifts, before the page scrolls, before the pointer
goes to something outside the view, and at once on a page change, the terminal or a card.
`s.spot(locator, zoom=1)` keeps one spotlight on the whole screen in a lesson that zooms.

The video's chapters follow YouTube's rules, since a video that breaks them shows none: the first
starts at 0:00 whenever the lesson marked it, and a chapter shorter than ten seconds runs on into
the one before it.

### Rehearsing

```bash
pageant rehearse notebook/lesson.py
```

runs a lesson through as `pageant record` does, on the same page in the same Chromium, with
nothing spoken, no frame kept and no wait longer than a quarter of a second: the time a
caption is held, a pause the lesson asks for, a pause after a click. A scroll is still waited for
until it stops. A step the app no longer has stops it as it stops a recording, with the page kept
as `failure.png` in the lesson's folder, and nothing else is written there. It takes the `record`
extra, but not ffmpeg, and runs in a fraction of a recording's time.

## Starting the product: the start hook

The studio holds no product's name. A lesson names its app, and the studio asks it to start, in a
work folder of the recording's own, before the browser opens:

```python
class App(Protocol):
    def start(self, work: Path, env: Mapping[str, str]) -> Running: ...
```

`Running` says the address the browser opens, the environment a command typed in the filmed
terminal runs with, a CSS selector the page shows once it is ready to be filmed, and how to stop
the app and everything it started. Two apps ship:

- `Command(argv, address=...)` starts a process in the work folder and reads its address from a
  line it prints, as a development server or a command-line app that opens in the browser does.
  `env` adds variables, `files` writes files into the work folder first (such as the answers a
  scripted service reads), and `exports` reads more values from what it prints into the
  terminal's environment, such as the address of a stand-in service it started.
- `StaticSite(folder)` serves a folder of files on this computer's own address, as the example does.

Anything with a `start` method of that shape is an app, so a product whose start takes more (a
data folder made first, a scripted model beside it) writes a hook of its own.

## Publishing

### Pages, and a pack a learning site imports

A product's pages are written once, in a file of their own that needs only the standard library,
for every place a lesson is published:

```python
from pageant.bundle import LearningPath, Page
from pageant.youtube import Product

FIRST_NOTE = Page(folder="first-note", slug="notebook-lesson-1-your-first-note", title="...", summary="...", body="...")
PATH = LearningPath(
    title="Notebook: getting started", audience="New to Notebook", description="...", lessons=(FIRST_NOTE,)
)
PRODUCT = Product(name="Notebook", about="...", link="...", all_lessons="...", scripted="")
```

`pageant record` writes a lesson's page beside its video as `lesson.json`, and

```bash
pageant pack notebook/pages.py
```

zips each recorded lesson of `PATH`, its page written afresh, with the path that lists them, as
`out/lessons.zip`. The format is Sigrix's, `sigrix-lesson/1` and `sigrix-learning-path/1`:
[Sigrix](https://sigrix.io)'s Learn console imports the pack in one step, checking every lesson
and showing what the import will do before it saves anything, and publishes each page at
`<site>/learn/<slug>`. A lesson not recorded whole stops the pack, naming what is missing.

[`SPEC.md`](SPEC.md) is the format: a bundle's files, each member of `lesson.json` and
`path.json` and its limits, and what a reader does. Each document has a JSON Schema, published
at the address its `$id` names, and a case table of documents a reader takes and documents it
refuses, each with its reason (`src/pageant/schemas/1/`). Every page and path Pageant writes is
held to its schema, so one the import would refuse stops `pageant record` before anything is
filmed, and `pageant pack` before anything is zipped, with every reason at once.

### YouTube

```bash
pageant youtube-text notebook/pages.py --link notebook-lesson-1-your-first-note=https://example.com/go/abc
```

writes `youtube.txt` into each recorded lesson's folder: its title, description and tags, to paste
into YouTube Studio beside the folder's `video.mp4`, `cover.jpg` (the thumbnail) and
`captions.vtt`. The description is the lesson's summary, a link to its page (or the tracked link
`--link` gives), its chapters, what in it is scripted, where it sits in its path, and the
product's `PRODUCT` lines. YouTube refuses a title over 100 characters, `<` or `>`, a description
over 5,000 bytes and tags over 500 characters, and shows no chapters that break its rules, so each
is checked first, and a lesson that breaks one stops the command before anything is written.

## What is real, and what is scripted

A lesson films the real product, and says what in it is not real wherever it is published. The
page, the clicks and what the product shows are its own. Whatever is scripted or a stand-in (a
model's answers, a service the product calls, a command on the `PATH`) is said on the lesson's
page and, through `Product.scripted`, in every YouTube description. The example has nothing
scripted: its page is the one it films, and its command really runs.

## The command line

| Command | What it does |
| --- | --- |
| `pageant record LESSON.py [--out DIR] [--chromium PATH] [--keep-work]` | records the lesson the file names as `LESSON` into `out/` beside it; `--chromium` (or `PAGEANT_CHROMIUM`) drives a Chromium headless shell already installed (`chrome-headless-shell`) rather than Playwright's, and `--keep-work` keeps the frames, the audio and the app's work folder |
| `pageant rehearse LESSON.py [--out DIR] [--chromium PATH] [--keep-work]` | runs the lesson through as `record` would, with nothing spoken or filmed and its long waits cut short, and stops where `record` would, keeping the page as `failure.png` in its folder in `out/`; `--keep-work` keeps the app's work folder |
| `pageant pack PAGES.py [--out DIR] [--zip FILE]` | zips the recorded lessons of `PATH`, as `out/lessons.zip` unless `--zip` names another |
| `pageant youtube-text PAGES.py [--out DIR] [--link SLUG=URL ...]` | writes each recorded lesson's `youtube.txt` from `PATH` and `PRODUCT` |
| `pageant example FOLDER` | writes the example lesson into a new folder, to record and change |

To hear how the voice says a line, and see the phonemes it reads, before a lesson says it:

```bash
python -m pageant.narrate "Install one from a zip file."
```

## Developing

```bash
pip install -e ".[dev,record]"
```

```bash
ruff check . && ruff format --check . && mypy && pytest
```

The tests need neither Playwright nor the voice, and run on Linux, macOS and Windows, except
`tests/test_studio.py`, which drives the studio in Chromium's headless shell: a lesson that goes
from page to page, a click after a long scroll, the chapter label and the spotlight, what is
scrolled to and what is not, a paste, the film's clock, the pointer's path, the camera, a rehearsal.
It is skipped without the `record` extra and a headless shell (`playwright install chromium`, or
one `PAGEANT_CHROMIUM` names), and CI's studio job runs it,
where `PAGEANT_STUDIO_TESTS=required` fails a skip. CI's record job rehearses and films the
example lesson from a fresh install of the wheel, on Linux, and keeps the video as an artifact of
the run. `tests/test_boundary.py` fails if the engine names a product it films, and
`tests/test_schemas.py` holds the schemas and their case tables to Pageant's checker, to a
reference implementation of JSON Schema, to the writer and to `SPEC.md`.

## License

Apache-2.0: see `LICENSE` and `NOTICE`.
