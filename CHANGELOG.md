# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the versioning is
described in `VERSIONING.md`.

## [Unreleased]

### Added

- A lesson's YouTube cut: `pageant record LESSON --youtube` records the same lesson with no captions
  drawn into the picture, into `out/youtube/<folder>/` (`bundle.YOUTUBE_CUT`), for YouTube to show
  the `captions.vtt` written beside it, which a viewer can turn off or have translated. The lesson's
  own recording keeps its captions in the picture for a learning site, and the pack takes it.
  `pageant youtube-text` writes each lesson's upload from its YouTube cut where one was recorded,
  as its chapters are timed to that video.
- A YouTube thumbnail: the YouTube cut composes `thumbnail.jpg` (1920×1080, under YouTube's 2 MB)
  from the lesson's `thumbnail` words (a short title, a `*starred*` part in the accent colour, an
  optional kicker and brand) beside its mark, and the frame it chose with `Studio.thumbnail()`, which
  is zoomed where the camera was. It is drawn on a page of Pageant's own once the film stops rolling,
  in Inter where the fonts answer.
- A phone's screen (`Lesson.screen`, `camera.PHONE`): a lesson filmed on a 360×640 screen painted at 3,
  for a vertical video of 1080×1920, its page laid out for the phone and the overlay too, with the
  caption above the foot a vertical video's player covers, and a fingertip for the pointer. The
  camera stays still on it, so it takes no `zoom` and no thumbnail, and it keeps its captions in the
  picture rather than having a YouTube cut. The report holds a vertical video to a Short's rules: three
  minutes at most, no end screen and no chapters, and three seconds after its last line at most.
- `Studio.cut()`: what the steps inside take is left out of the video, as an edit cuts a wait (a payment
  processing, a slow page). The page's time runs on; the film's clock, which is the video's, does not,
  so captions, voice and clicks stay where they were.
- YouTube Shorts' uploads (`youtube.Short`): a pages file's `SHORTS`, each a lesson of its own on a
  phone's screen, from a lesson of the path, whose `youtube.txt` links to that lesson's page and names
  it as its Related video.
- A recording's report (`pageant.report`): `report.md` and `report.json` beside the video, and what
  they found worth a look in what `pageant record` prints. It holds the checks made by hand before
  publishing, read off the recording's own log: the loudness and true peak against the lesson's
  target, a caption up long after its voice, the longest stretch with nothing said and the longest
  with no frame changing (title and end cards aside), the distinct frames of the busiest second of
  motion, the seconds after the last line that YouTube's end screen takes, and the chapters YouTube
  makes. A finding never stops a recording.
- A card's `points`: a short list under its title, numbered, or ticked for a recap (`"checks": True`),
  and `Studio.tell`, which brings them up one at a time as a line read over the card names them, so a
  lesson can open on what it covers and close on what it showed. A point added to a card on screen
  fades up into place; the rest stay as they are.
- The lesson engine, moved out of [Bailey](https://github.com/sigrix-io/bailey)'s `lessons/` with
  its tests: the studio that drives a product's page in Chromium and captures every frame, the
  filmed terminal, the voice (Kokoro, on the recording machine), the music made there, the mix,
  the captions and chapters, the lesson bundle and its pack, and each lesson's YouTube text.
- The start hook: a lesson names the app it films, and the studio asks it to start. `Command`
  starts a process and reads its address from what it prints, and `StaticSite` serves a folder.
  The engine names no product it films, which `tests/test_boundary.py` keeps so.
- The `pageant` command: `record`, `pack`, `youtube-text`, and `example`, which writes the
  example lesson into a folder to record and change.
- The example lesson, Notebook: a one-page app the package ships, filmed in three chapters, with
  a terminal. CI records it from a fresh install of the wheel.
- `import pageant` needs only the standard library. Recording takes the `record` extra.
- The format written down: `SPEC.md`, and a JSON Schema for `lesson.json` (`sigrix-lesson/1`)
  and for `path.json` (`sigrix-learning-path/1`), each with a case table of documents a reader
  takes and documents it refuses with the reason (`src/pageant/schemas/1/`, read through
  `pageant.schema`). Each schema's `$id` is the address it is published at,
  `https://sigrix.io/schemas/pageant/1/`.
- Every page and path the writer writes is held to its schema: `bundle.page_json`,
  `bundle.path_json` and `bundle.pack` refuse one the import would refuse, with every reason
  (`bundle.ManifestRefused`), and `pageant record` stops on such a page before anything is
  filmed.
- `pageant rehearse LESSON.py` (`studio.rehearse`): the lesson run through as `record` runs it, its
  app started and its setup and steps run on its page in Chromium, with nothing spoken, no frame
  captured and no wait longer than a quarter of a second, so a step the app no longer has is found
  in a fraction of a recording's time. It stops where `record` would, keeping the page as
  `failure.png` in the lesson's folder, and writes nothing else there. It takes the record extra,
  and not ffmpeg. CI's record job rehearses the example before recording it.
- `s.arrive(url)`: waits for the page a step went to, loaded, with what was on screen drawn on it,
  so the step after a click that goes to another page does not start on the page before.
- `tests/test_studio.py` drives the studio in Chromium, and CI's studio job runs it with the
  record extra installed; elsewhere it is skipped.
- `Lesson.pronounce`: words the voice says differently from how they are written, respelled in
  every line it speaks, the captions keeping the written form (`pageant.pronounce`). A domain's
  `.io` was read as one syllable ("dot ee-oh") until a lesson could respell it once.
- `Lesson.label_corner` and `Lesson.label_seconds`: the chapter label can sit top left, and come
  down a few seconds after its chapter starts, on whatever page the lesson is on by then, rather
  than staying over an app's own controls at the top right. Unset, it stays where and as long as
  it did.
- `Lesson.loudness`: the mix's target in LUFS, -16 unless a lesson says, the level web players
  expect, or -14, the level YouTube plays every video at and the one it turns nothing up to.
- `s.paste(locator, text)`: puts long text in at once, as a paste does, rather than typing it a
  key at a time.
- Every frame of the video painted, 60 a second, on a clock the film keeps (`pageant.film`):
  Chromium's headless shell paints a frame only when asked, and the page's own time (its timers,
  CSS transitions and animations, smooth scrolls) moves on a frame's worth at a time, so motion is
  as even on a slow computer as on a fast one. A page's time waits for what it fetches, so it loads
  in the video in the frames its scripts take; a fetch that never ends is let run past after two
  seconds. A frame the same as the one before is held rather than written again.
- The camera (`Lesson.zoom`, `pageant.camera`): a spotlight is zoomed in on, as large as fits above
  the captions and no more than `zoom` times, painted at that size rather than stretched, while the
  captions, the label and the cards keep their size; it moves back out when the spotlight lifts,
  before a scroll, before the pointer goes outside the view, and at once on a page change, the
  terminal or a card. `s.spot(..., zoom=)` sets it for one spotlight.
- The pointer moves along a gently curved path that speeds up and slows down as a hand does, a
  point a frame, and the page sees one mouse move, at its end, so a hover menu does not flicker open
  on its way. `s.type` types a key every frame or more.

### Fixed

- A frame whose answer is lost no longer holds the film for ever. A page that went to another while its
  time moved on a frame could take with it the renderer that would have said so, and the film waited,
  idle, until the recording was killed. It asks again every `STUCK` seconds, and paints the frame
  after `ASKS` asks; and a frame Chromium does not paint in `PAINT_SECONDS` (60) stops the recording
  with that said.
- The screen a lesson is filmed on is set on its page (`Emulation.setDeviceMetricsOverride`, keeping the
  browser's own scale). Chromium's headless shell opens every page at 1280×720 whatever `--window-size`
  says, which the studio passed it and which only ever matched by chance.
- A page on another site than the one before it (a payment provider's checkout, and the app it sends
  the buyer back to) held its CSS animations at their first keyframe: a menu that fades in was open,
  and took clicks, but never showed, and a title card never came up. Chromium draws such a page with a
  renderer of its own, whose clock starts at the machine's time, which a recording's frames had fallen
  tens of seconds behind; frames timed before a page's time leave its animations waiting for them. The
  film reads where each renderer's clock began (`virtualTimeTicksBase`, in every answer to its
  `setVirtualTimePolicy`) and moves the frames' times on to `BEHIND` (0.1 s) short of the page's time:
  a frame level with it was never drawn on Stripe's Checkout page.
- A step on a page still in its view transition (an app's CSS `@view-transition`) was swallowed: until
  the transition ends, the page hit-tests as `<html>`. A step now waits for it, as a person does, and
  skips one still running after `TRANSITION_FRAMES` (1.5 s), through the handle the page was
  revealed with. A step's own waits for the page (Playwright's) take up to `WAIT_SECONDS` (180) of the
  machine's time, not 30: the page moves only as frames are painted, which a busy machine paints slower.
- A request a page keeps open (a stream, a long poll) cost the film `STUCK` seconds on every frame, so a
  page change's view transition could take half a minute and a click land on a page still in it. The film
  now watches its page's requests (CDP `Network`), and while one has been open longer than `STUCK`, the
  page's time runs on without waiting for fetches, so it costs one wait.
- A click pressed where its element was when the pointer set off, so one the page moved on the way (a
  banner coming in above it) was missed. It is pressed where the element is when the mouse goes down.
- A lesson that goes from page to page keeps what is on screen. The overlay starts afresh in each
  document a page loads, so after a click on a link, a form post or a server redirect, the next
  page had no chapter label and no caption, and drew the pointer at the middle of the screen until
  the mouse next moved, though the captions file had the caption on. The studio now keeps the
  label, the caption, the title card and where the pointer is, and hands them to each new document
  in a script that runs as it starts, so its first frame has them; it draws them again as the page
  loads, for a step that ran meanwhile, and an overlay call a page load cuts off is made again on
  the page that replaced it. The overlay is built as soon as a page has a body, rather than once
  it has loaded, and draws no pointer until something places it.
- A click after a long scroll lands on its target. `glide`, and so `click`, read where the target
  was 450 ms into its smooth scroll, which Chromium runs for up to 1.5 s, so after a long one the
  pointer went where the target had been on the way. It now waits, after the same pause, until two
  reads of the target's box 120 ms apart put its middle in the same place, for three seconds from
  the scroll's start at most; `spot` waits the same way before drawing the spotlight.
- A `failure.png` left by an earlier run is removed when a lesson is recorded or rehearsed again,
  so one in a lesson's folder is from the last run.
- The mix is set to its loudness in two passes (`pageant.loudness`): one pass of `loudnorm` left
  a lesson mixed for -16 LUFS at -16.6 LUFS, measured.
- The spotlight comes up where its element is, rather than sliding there from where it last was:
  on a page just opened, from the screen's corner. Moving to an element out of view, it is taken
  down before the page scrolls there, rather than trailing the last element off the screen.
- A step that fails keeps its page as `failure.png` at the video's own 1920x1080, painted by the
  film, and on a page with nothing moving too: Chromium's own screenshot, which it used, waits for a
  frame with something new in it, which a still page under the film never paints.
- `spot` and `glide` do not scroll to an element in view: all of it on screen, and either in a
  bar that stays put as the page scrolls or clear of the captions with nothing over it. Chromium
  scrolls the page under a sticky top bar to bring a control in it nearer, so pointing at an
  app's cart or account menu moved the page under the bar; and a page moved under the pointer
  for nothing.

### Changed

- Recording takes Chromium's headless shell (`chrome-headless-shell`), which `playwright install
  chromium` installs beside Chromium: `--chromium` and `PAGEANT_CHROMIUM` name one. A Chromium
  that cannot paint a frame when asked stops the recording with that said.
- The video is 60 frames a second, rather than 30.
- A product's YouTube tags are one word each, as the people uploading the lessons want them:
  `pageant youtube-text` stops on a tag holding a space, naming it and its joined spelling
  (`ai marketplace` is `aimarketplace`), before anything is written. Tags were phrases, and the
  example's `video lesson` is `videolesson` now.

### Changed, from Bailey's `lessons/`

- A YouTube description ends with the product's `Product`: its name, what it is, where to get
  it, where all its lessons are, and what in them is scripted, which were Bailey's constants.
- A lesson's pages name the site they are published on (`LearningPath.site`), `sigrix.io`
  unless they say otherwise.
- The voice and its lines are kept in `~/.cache/pageant/`, and `PAGEANT_CHROMIUM` names a
  Chromium already installed.
- A chapter's label stays on screen when a lesson goes to the terminal.
