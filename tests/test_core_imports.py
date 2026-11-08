"""``import pageant`` needs nothing but Python: recording's heavy parts load only when a lesson is recorded.

The ``record`` extra brings Playwright, Kokoro and onnxruntime, and numpy with them: hundreds of
megabytes a project that only packs its lessons or writes their YouTube text never needs. So the
core modules, and the command line until ``pageant record`` runs, import none of them, nor the
modules of the package that do. Checked in a fresh interpreter, where nothing else has imported
them first; CI's test job runs it without the extra installed, where an import would fail, and the
studio job with it, where one would succeed.
"""

from __future__ import annotations

import json
import subprocess
import sys

HEAVY = ("playwright", "kokoro_onnx", "onnxruntime", "numpy")
RECORDING = ("pageant.studio", "pageant.narrate", "pageant.mixdown", "pageant.music")

PROBE = """
import json, sys
import pageant
import pageant.apps, pageant.bundle, pageant.cli, pageant.timeline, pageant.youtube
import pageant.camera, pageant.loudness, pageant.pronounce
pageant.cli._parser().parse_args(["pack", "pages.py"])
print(json.dumps(sorted(sys.modules)))
"""


def test_the_core_and_the_command_line_import_nothing_recording_needs() -> None:
    done = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, check=True)
    loaded = json.loads(done.stdout)

    assert "pageant.cli" in loaded, "the probe imported what it says it did"
    assert [name for name in loaded if name.split(".")[0] in HEAVY] == []
    assert [name for name in loaded if name in RECORDING] == []
