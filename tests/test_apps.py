"""The start hooks a recording films an app through (``pageant.apps``), each started for real.

A :class:`~pageant.apps.Command` is a stand-in app here (``stand_ins/fake_app.py``) that prints its
address as a development server does and listens until it is stopped, so a test tells it is running
by connecting to it. A :class:`~pageant.apps.StaticSite` is fetched over HTTP. The stand-in commands
a lesson puts on the PATH are run through the shell, as the filmed terminal runs them, on each
system CI runs on.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from pageant import apps

STAND_INS = Path(__file__).resolve().parent / "stand_ins"
FAKE_APP = STAND_INS / "fake_app.py"


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            return True
    except OSError:
        return False


def _started(work: Path) -> dict[str, object]:
    return dict(json.loads((work / "started.json").read_text(encoding="utf-8")))


def _fetch(address: str) -> bytes:
    # This computer's own address, never through a proxy the environment names.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(address, timeout=10) as response:
        return bytes(response.read())


def test_a_command_starts_in_the_work_folder_and_its_address_is_read_from_what_it_prints(tmp_path: Path) -> None:
    app = apps.Command(
        argv=[sys.executable, FAKE_APP],
        address=r"Open it at (http://\S+)",
        env={"FAKE_APP_GREETING": "hello"},
        files={"given.txt": "the answers a scripted service reads"},
        exports={"SERVICE_URL": r"Scripted service at (\S+)"},
        ready="#chat",
    )

    running = app.start(tmp_path, {**os.environ, "FROM_THE_STUDIO": "1"})
    try:
        started = _started(tmp_path)
        port = int(str(started["port"]))
        assert running.address == f"http://127.0.0.1:{port}/#token=abc"
        assert running.ready == "#chat"
        assert running.env["SERVICE_URL"] == f"http://127.0.0.1:{port}/service", "an export, for the terminal"
        assert running.env["FAKE_APP_GREETING"] == "hello" and running.env["FROM_THE_STUDIO"] == "1"
        assert Path(str(started["cwd"])).resolve() == tmp_path.resolve()
        assert started["greeting"] == "hello", "the app's own variables reach it"
        assert started["given"] == "the answers a scripted service reads", "its files are written before it starts"
        assert _listening(port)
    finally:
        running.stop()
    assert not _listening(port), "stopping it stops the process"
    running.stop()


def test_a_command_that_stops_before_its_address_says_what_it_printed(tmp_path: Path) -> None:
    app = apps.Command(argv=[sys.executable, FAKE_APP, "--fail"], address=r"Open it at (http://\S+)")

    with pytest.raises(RuntimeError, match="stopped before printing its address") as refused:
        app.start(tmp_path, dict(os.environ))
    assert "Cannot start: the data folder is locked." in str(refused.value)


def test_a_command_that_prints_no_address_in_time_is_stopped(tmp_path: Path) -> None:
    app = apps.Command(argv=[sys.executable, FAKE_APP, "--silent"], address=r"Open it at (http://\S+)", timeout=3)

    with pytest.raises(RuntimeError, match=re.escape("printed no address in 3 s")):
        app.start(tmp_path, dict(os.environ))
    assert not _listening(int(str(_started(tmp_path)["port"]))), "the process is not left running"


def test_a_static_site_is_served_on_this_computers_own_address(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>Notebook</h1>", encoding="utf-8")
    (site / "mark.svg").write_text("<svg/>", encoding="utf-8")

    running = apps.StaticSite(site, path="/index.html", ready="h1").start(tmp_path, {"FROM_THE_STUDIO": "1"})
    try:
        assert running.address.startswith("http://127.0.0.1:") and running.address.endswith("/index.html")
        assert running.ready == "h1"
        assert running.env == {"FROM_THE_STUDIO": "1"}
        assert _fetch(running.address) == b"<h1>Notebook</h1>"
        assert _fetch(running.address.replace("/index.html", "/mark.svg")) == b"<svg/>"
    finally:
        running.stop()
    running.stop()
    with pytest.raises(OSError):
        _fetch(running.address)


def test_a_static_site_needs_its_folder(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no folder"):
        apps.StaticSite(tmp_path / "nowhere").start(tmp_path, {})


def test_a_lessons_stand_in_commands_run_first_on_the_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("no_proxy", "localhost")

    env = apps.environment(tmp_path, {"say-args": [STAND_INS / "say_args.py", "--from-the-lesson"]})

    assert env["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin")
    assert not [name for name in env if name.lower().endswith("_proxy")], "nothing a lesson's app reaches is past here"
    # Through the shell, as the filmed terminal runs a command.
    printed = subprocess.run(  # noqa: S602
        "say-args 'two words'" if os.name != "nt" else 'say-args "two words"',
        shell=True,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(printed.stdout) == ["--from-the-lesson", "two words"]


def test_no_stand_ins_leaves_the_path_as_it_is(tmp_path: Path) -> None:
    env = apps.environment(tmp_path, {})

    assert env["PATH"] == os.environ["PATH"]
    assert not (tmp_path / "bin").exists()
