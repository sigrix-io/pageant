"""How a recording starts the product it films: a start hook.

A lesson names its app (``Lesson.app``), and the studio asks it to start, in a work folder of the
recording's own, before the browser opens, with the environment :func:`environment` gives: this
process's, with the lesson's stand-in commands first on the PATH. What it answers is
:class:`Running`: the address the browser opens, the environment a command typed in the filmed
terminal runs with, a selector the page shows once it is ready to be filmed, and how to stop it.
Anything with a ``start`` method of that shape is an app; two ship here:

- :class:`Command` starts a process and reads its address from what it prints, as a development
  server or a command-line app that opens in the browser does;
- :class:`StaticSite` serves a folder of files on this computer's own address.

All of it is the standard library's, so a lesson file can name its app without Playwright or the
voice installed.
"""

from __future__ import annotations

import functools
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Running:
    """A started app, as the studio uses it."""

    #: What the browser opens.
    address: str
    #: What a command typed in the filmed terminal runs with.
    env: Mapping[str, str]
    #: A CSS selector the page shows once it is ready to be filmed; ``None`` when loading is enough.
    ready: str | None
    #: Stops the app and everything it started. Safe to call more than once.
    stop: Callable[[], None]


class App(Protocol):
    """Anything a lesson can film: it starts in ``work``, with ``env``, and says where it is."""

    def start(self, work: Path, env: Mapping[str, str]) -> Running: ...


def environment(work: Path, commands: Mapping[str, Sequence[str | os.PathLike[str]]]) -> dict[str, str]:
    """What an app starts with: this process's environment, the stand-in ``commands`` first on the PATH.

    Each stand-in is a name and what it runs with this Python, a script and its first arguments, such
    as a stand-in for a service the app calls. Each becomes a small launcher in ``work/bin``, ahead of
    everything else on the PATH, which a program the app starts inherits, as it would a command the
    person had installed. Nothing a lesson's app reaches is past this computer, so no proxy applies.
    """

    env = {key: value for key, value in os.environ.items() if not key.lower().endswith("_proxy")}
    if commands:
        folder = work / "bin"
        folder.mkdir()
        for name, runs in commands.items():
            parts = [sys.executable, *(os.fspath(part) for part in runs)]
            if os.name == "nt":
                line = " ".join(f'"{part}"' for part in parts)
                # Written as text, so the line ends as Windows ends one.
                (folder / f"{name}.cmd").write_text(f"@{line} %*\n", encoding="utf-8")
            else:
                launcher = folder / name
                launcher.write_text(f'#!/bin/sh\nexec {shlex.join(parts)} "$@"\n', encoding="utf-8")
                launcher.chmod(0o755)
        env["PATH"] = os.pathsep.join([str(folder), env.get("PATH", "")])
    return env


def _pattern(value: str | re.Pattern[str]) -> re.Pattern[str]:
    return value if isinstance(value, re.Pattern) else re.compile(value)


@dataclass(frozen=True)
class Command:
    """An app started as a process in the work folder, whose address is in a line it prints.

    ``address`` is a regular expression whose first group is the address to open, matched against
    each line the process prints until one matches. ``exports`` names more values to read the same
    way, each put in the filmed terminal's environment under its name, such as the address of a
    stand-in service the app started. ``files`` are written into the work folder before it starts,
    such as the answers a scripted service reads.
    """

    argv: Sequence[str | os.PathLike[str]]
    address: str | re.Pattern[str]
    env: Mapping[str, str] = field(default_factory=dict)
    files: Mapping[str, str] = field(default_factory=dict)
    exports: Mapping[str, str | re.Pattern[str]] = field(default_factory=dict)
    ready: str | None = None
    #: How long to wait for the address, in seconds.
    timeout: float = 60.0

    def start(self, work: Path, env: Mapping[str, str]) -> Running:
        for name, text in self.files.items():
            (work / name).write_text(text, encoding="utf-8")
        full = {**env, **self.env}
        process = subprocess.Popen(  # noqa: S603 -- the argv the lesson names, never a shell
            [os.fspath(part) for part in self.argv],
            cwd=work,
            env=full,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=_read, args=(process, lines), daemon=True).start()
        address = _pattern(self.address)
        exports = {name: _pattern(pattern) for name, pattern in self.exports.items()}
        found: dict[str, str] = {}
        printed: list[str] = []
        deadline = time.monotonic() + self.timeout

        def stop() -> None:
            _stop(process)

        while True:
            try:
                line = lines.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                stop()
                raise RuntimeError(
                    f"The app printed no address in {self.timeout:.0f} s:\n" + "".join(printed)
                ) from None
            if line is None:
                stop()
                raise RuntimeError("The app stopped before printing its address:\n" + "".join(printed))
            printed.append(line)
            for name, pattern in exports.items():
                if match := pattern.search(line):
                    found[name] = match.group(1)
            if match := address.search(line):
                return Running(address=match.group(1), env={**full, **found}, ready=self.ready, stop=stop)


def _read(process: subprocess.Popen[str], lines: queue.Queue[str | None]) -> None:
    # Read to the end, past the address too, so a chatty app never blocks on a full pipe.
    if process.stdout is not None:
        for line in process.stdout:
            lines.put(line)
    lines.put(None)


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class _QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


@dataclass(frozen=True)
class StaticSite:
    """A folder of files served on this computer's own address, as a static site or a page under test."""

    folder: Path
    #: The path the browser opens, under the site.
    path: str = "/"
    ready: str | None = None

    def start(self, work: Path, env: Mapping[str, str]) -> Running:
        if not self.folder.is_dir():
            raise FileNotFoundError(f"There is no folder at {self.folder} to serve.")
        handler = functools.partial(_QuietFiles, directory=str(self.folder))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        stopped = threading.Event()

        def stop() -> None:
            if not stopped.is_set():
                stopped.set()
                server.shutdown()
                server.server_close()

        return Running(
            address=f"http://127.0.0.1:{server.server_address[1]}{self.path}",
            env=dict(env),
            ready=self.ready,
            stop=stop,
        )


__all__ = ["App", "Command", "Running", "StaticSite", "environment"]
