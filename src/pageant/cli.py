"""The ``pageant`` command: record a lesson or rehearse it, pack a path's lessons, and write their YouTube uploads.

    pageant example notebook                 # a lesson to start from, written into notebook/
    pageant rehearse notebook/lesson.py      # its steps run through quickly, nothing spoken or filmed
    pageant record notebook/lesson.py        # the lesson the file names as LESSON, into notebook/out/
    pageant pack notebook/pages.py           # the path the file names as PATH, as notebook/out/lessons.zip
    pageant youtube-text notebook/pages.py   # each lesson's youtube.txt, from PATH and PRODUCT (and SHORTS)

A lesson file and a pages file are Python, loaded as running them would load them: their own
folder first on the import path, so a lesson imports the pages beside it. The recordings go into
``out/`` beside the file unless ``--out`` names another folder. Recording and rehearsing take the
``record`` extra, which nothing here imports until one of them runs.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, TypeVar

from pageant import __version__, bundle, youtube

if TYPE_CHECKING:
    from pageant.studio import Lesson

#: The lesson the package ships: a lesson file, its pages, and the static site it films.
EXAMPLE = Path(__file__).resolve().parent / "example"
#: The pack ``pageant pack`` writes into the recordings' folder unless ``--zip`` names another.
PACK = "lessons.zip"
RECORD_EXTRA = 'pip install "pageant[record]"'

T = TypeVar("T")


class Refused(Exception):
    """A command that cannot go on, with the sentence that says why."""


def load(file: Path) -> ModuleType:
    """The Python file's module, loaded as running it loads it: its own folder first on the import path."""

    path = file.resolve()
    if not path.is_file():
        raise Refused(f"There is no file at {file}.")
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    name = f"_pageant_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise Refused(f"{file} is not a Python file.")
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs, as an import is, so the dataclasses it defines find their module.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _named(module: ModuleType, file: Path, name: str, kind: type[T]) -> T:
    value = getattr(module, name, None)
    if not isinstance(value, kind):
        raise Refused(f"{file} names no {name}: a {kind.__module__}.{kind.__qualname__}.")
    return value


def _out(args: argparse.Namespace, file: Path) -> Path:
    out: Path | None = args.out
    return out if out is not None else file.resolve().parent / "out"


def _takes(doing: str, *, ffmpeg: bool) -> None:
    """Refuse, naming each, what ``doing`` takes that is not here: the record extra, and ffmpeg if it encodes.

    Asked before the lesson is loaded, since a lesson file imports the studio.
    """

    needs = []
    if ffmpeg and not shutil.which("ffmpeg"):
        needs.append("ffmpeg on the PATH, which encodes the video and mixes its sound")
    try:
        importlib.import_module("pageant.studio")
    except ModuleNotFoundError as missing:
        package = (missing.name or "").split(".")[0]
        needs.insert(0, f"the record extra, which installs {package}: {RECORD_EXTRA}")
    if needs:
        raise Refused(f"{doing} takes what is not here:\n" + "\n".join(f"- {need}" for need in needs))


def _lesson(file: Path) -> Lesson:
    """The lesson ``file`` names as ``LESSON``, whose page an import takes."""

    from pageant import studio

    lesson = _named(load(file), file, "LESSON", studio.Lesson)
    # The page is written once the lesson is filmed; one the import would refuse stops it first.
    try:
        bundle.page_json(lesson.page)
    except bundle.ManifestRefused as refused:
        raise Refused(str(refused)) from None
    return lesson


def _record(args: argparse.Namespace) -> int:
    _takes("Recording", ffmpeg=True)
    from pageant import studio

    lesson = _lesson(args.lesson)
    made = asyncio.run(
        studio.record(
            lesson, _out(args, args.lesson), chromium=args.chromium, keep_work=args.keep_work, youtube=args.youtube
        )
    )
    sys.stdout.write(json.dumps(made, indent=2, ensure_ascii=False) + "\n")
    return 0


def _rehearse(args: argparse.Namespace) -> int:
    # Nothing is encoded, so ffmpeg is not asked for.
    _takes("Rehearsing", ffmpeg=False)
    from pageant import studio

    lesson = _lesson(args.lesson)
    made = asyncio.run(
        studio.rehearse(lesson, _out(args, args.lesson), chromium=args.chromium, keep_work=args.keep_work)
    )
    sys.stdout.write(json.dumps(made, indent=2, ensure_ascii=False) + "\n")
    return 0


def _pack(args: argparse.Namespace) -> int:
    path = _named(load(args.pages), args.pages, "PATH", bundle.LearningPath)
    out = _out(args, args.pages)
    try:
        made = bundle.pack(out, path, args.zip or out / PACK)
    except (FileNotFoundError, bundle.ManifestRefused) as refused:
        raise Refused(str(refused)) from None
    sys.stdout.write(f"{made}\n")
    return 0


def _youtube_text(args: argparse.Namespace) -> int:
    module = load(args.pages)
    path = _named(module, args.pages, "PATH", bundle.LearningPath)
    product = _named(module, args.pages, "PRODUCT", youtube.Product)
    shorts = getattr(module, "SHORTS", ())
    if not isinstance(shorts, tuple) or not all(isinstance(short, youtube.Short) for short in shorts):
        raise Refused(f"{args.pages}: SHORTS is a tuple of pageant.youtube.Short")
    try:
        written = youtube.write(_out(args, args.pages), path, product, dict(args.link), shorts)
    except (FileNotFoundError, ValueError) as refused:
        raise Refused(str(refused)) from None
    for target in written:
        sys.stdout.write(f"{target}\n")
    return 0


def _example(args: argparse.Namespace) -> int:
    folder: Path = args.folder
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise Refused(f"{folder} is not an empty folder; name a new one for the example.")
    shutil.copytree(EXAMPLE, folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "out"))
    sys.stdout.write(f"{folder}\nRecord it with: pageant record {folder / 'lesson.py'}\n")
    return 0


def _link(value: str) -> tuple[str, str]:
    slug, sep, link = value.partition("=")
    if not sep or not slug.strip() or not link.strip():
        raise argparse.ArgumentTypeError(f"give a link as <slug>=<link>, not {value!r}")
    return slug.strip(), link.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pageant", description="Record a product's video lessons from the app itself, and publish them."
    )
    parser.add_argument("--version", action="version", version=f"pageant {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    out = "where the lessons are recorded (default: out/ beside the file)"

    record = commands.add_parser("record", help="record the lesson a lesson file names as LESSON")
    record.add_argument("lesson", type=Path, help="the lesson file")
    record.add_argument("--out", type=Path, help=out)
    record.add_argument(
        "--chromium",
        default=os.environ.get("PAGEANT_CHROMIUM"),
        help="a Chromium headless shell (chrome-headless-shell) to drive instead of Playwright's (or PAGEANT_CHROMIUM)",
    )
    record.add_argument("--keep-work", action="store_true", help="keep the frames, the audio and the app's work folder")
    record.add_argument(
        "--youtube",
        action="store_true",
        help=f"record the YouTube cut, with no captions drawn into the picture, into {bundle.YOUTUBE_CUT}/ in --out",
    )
    record.set_defaults(run=_record)

    rehearse = commands.add_parser(
        "rehearse",
        help="run the lesson a lesson file names as LESSON through, quickly, with nothing spoken or filmed",
    )
    rehearse.add_argument("lesson", type=Path, help="the lesson file")
    rehearse.add_argument(
        "--out",
        type=Path,
        help="where a page a step stopped on is kept, as failure.png (default: out/ beside the file)",
    )
    rehearse.add_argument(
        "--chromium",
        default=os.environ.get("PAGEANT_CHROMIUM"),
        help="a Chromium headless shell (chrome-headless-shell) to drive instead of Playwright's (or PAGEANT_CHROMIUM)",
    )
    rehearse.add_argument("--keep-work", action="store_true", help="keep the app's work folder")
    rehearse.set_defaults(run=_rehearse)

    pack = commands.add_parser("pack", help="zip the recorded lessons of the path a pages file names as PATH")
    pack.add_argument("pages", type=Path, help="the pages file")
    pack.add_argument("--out", type=Path, help=out)
    pack.add_argument("--zip", type=Path, help=f"the pack to write (default: {PACK} in --out)")
    pack.set_defaults(run=_pack)

    text = commands.add_parser(
        "youtube-text", help="write each recorded lesson's YouTube title, description and tags as youtube.txt"
    )
    text.add_argument("pages", type=Path, help="the pages file, which names PATH and PRODUCT, and may name SHORTS")
    text.add_argument("--out", type=Path, help=out)
    text.add_argument(
        "--link",
        type=_link,
        action="append",
        default=[],
        metavar="SLUG=URL",
        help="a lesson's tracked link, for its description in place of its page's address (once per lesson)",
    )
    text.set_defaults(run=_youtube_text)

    example = commands.add_parser("example", help="write the example lesson into a new folder, to record and change")
    example.add_argument("folder", type=Path, help="the folder to write it into")
    example.set_defaults(run=_example)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run: Callable[[argparse.Namespace], int] = args.run
    try:
        return run(args)
    except Refused as refused:
        sys.stderr.write(f"{refused}\n")
        return 1


__all__ = ["EXAMPLE", "PACK", "Refused", "load", "main"]
