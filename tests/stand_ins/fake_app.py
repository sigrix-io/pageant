"""A stand-in app for tests/test_apps.py: it starts, says where it is, and waits to be stopped.

    fake_app.py [--fail | --silent]

It writes what it was started with into ``started.json`` in its working folder: the folder, the
variable ``FAKE_APP_GREETING``, the file ``given.txt`` if it was given one, and the port it listens
on. Then it prints a line of chatter, the address of a stand-in service and its own, as a
development server does, and listens on its port until it is stopped, so a test can tell it is
running by connecting. ``--fail`` exits before the addresses; ``--silent`` prints nothing at all.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

args = sys.argv[1:]
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen()
port = server.getsockname()[1]
given = Path("given.txt")
started = {
    "cwd": os.getcwd(),
    "greeting": os.environ.get("FAKE_APP_GREETING"),
    "given": given.read_text(encoding="utf-8") if given.exists() else None,
    "port": port,
}
Path("started.json").write_text(json.dumps(started), encoding="utf-8")
if "--silent" not in args:
    print("Starting the app ...", flush=True)
    if "--fail" in args:
        print("Cannot start: the data folder is locked.", flush=True)
        sys.exit(3)
    print(f"Scripted service at http://127.0.0.1:{port}/service", flush=True)
    print(f"Open it at http://127.0.0.1:{port}/#token=abc", flush=True)
time.sleep(120)
