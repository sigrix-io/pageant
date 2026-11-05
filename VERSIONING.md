# Versioning

Semantic versioning, `MAJOR.MINOR.PATCH`, released from a `vX.Y.Z` tag.

Before 1.0, a MINOR release may change or remove what an earlier one offered, and the changelog
says so when it does. From 1.0:

- **PATCH**: a fix that changes no command, option, step or file, and no recording.
- **MINOR**: a new command, option, step or app; a change to how a recording looks or sounds (the
  overlay, the voice, the music, the mix), since recording a lesson again then changes its video;
  a new version of the record extra's pins.
- **MAJOR**: a removed or renamed command, option, step or field of a lesson; a lesson file or a
  pages file that stops loading; a bundle or a pack that a learning site's import stops reading.

The bundle and pack formats are Sigrix's, and each file says its own version (`"format":
"sigrix-lesson/1"`, `"sigrix-learning-path/1"`). Pageant writes the versions Sigrix's import reads,
and moves to a new one only once that import reads it.

## The record extra

`pageant[record]` pins Playwright and Kokoro exactly, at the versions the lessons were last
recorded with: a bump can change how a page renders or how a line is said, so it is a change of
its own, made in a pull request where CI's record job films the example lesson with it.

## Releasing

The version lives in `src/pageant/__init__.py`, which the build reads. Date the version's
section in `CHANGELOG.md` the day the tag goes out. A release publishes to PyPI from the tag,
through a trusted publisher rather than a stored token; the workflow that does so arrives with
the first release.
