# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the versioning is
described in `VERSIONING.md`.

## [Unreleased]

### Added

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

### Changed, from Bailey's `lessons/`

- A YouTube description ends with the product's `Product`: its name, what it is, where to get
  it, where all its lessons are, and what in them is scripted, which were Bailey's constants.
- A lesson's pages name the site they are published on (`LearningPath.site`), `sigrix.io`
  unless they say otherwise.
- The voice and its lines are kept in `~/.cache/pageant/`, and `PAGEANT_CHROMIUM` names a
  Chromium already installed.
- A chapter's label stays on screen when a lesson goes to the terminal.
