"""The engine names no product it films: every product reaches it through a start hook and its own files.

Pageant came out of Bailey's ``lessons/``, where the studio knew how to start Bailey. That became
a start hook a lesson names (``pageant.apps``), and Bailey's own hook stays in Bailey. This scan
keeps it so, as Causeway's boundary scan keeps Sigrix out of Causeway: no file the package ships,
the example included, says the name of a product that films its lessons with Pageant. A product
that comes to Pageant is added to ``FILMED``. (Sigrix is named where the bundle format is, since the
format is Sigrix's, as YouTube is named where its upload is written.)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "src" / "pageant"
#: The products whose lessons Pageant films, none of which the engine may name.
FILMED = ("bailey",)


def named_products(root: Path) -> list[str]:
    """Each place under ``root`` that names a product in ``FILMED``: ``path:line: name``."""

    pattern = re.compile("|".join(FILMED), re.IGNORECASE)
    found = []
    for file in sorted(root.rglob("*")):
        if not file.is_file() or "__pycache__" in file.parts:
            continue
        text = file.read_bytes().decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                found.append(f"{file.relative_to(root).as_posix()}:{number}: {match.group(0)}")
        if pattern.search(file.name):
            found.append(f"{file.relative_to(root).as_posix()}: its name")
    return found


def test_the_engine_names_no_product_it_films() -> None:
    files = [file for file in ENGINE.rglob("*") if file.is_file() and "__pycache__" not in file.parts]
    # The canary for the scan's reach: it reads the Python, the overlay, the terminal page and the
    # example's site, so a sweep that finds nothing found nothing in all of them.
    assert {file.suffix for file in files} >= {".py", ".js", ".html", ".css", ".svg"}

    assert named_products(ENGINE) == []


def test_a_product_planted_in_the_engine_is_found(tmp_path: Path) -> None:
    copy = tmp_path / "pageant"
    shutil.copytree(ENGINE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    studio = copy / "studio.py"
    studio.write_text(studio.read_text(encoding="utf-8") + "\n# Start Bailey for the recording.\n", encoding="utf-8")
    (copy / "example" / "site" / "BAILEY.txt").write_text("a page\n", encoding="utf-8")

    found = named_products(copy)

    assert "example/site/BAILEY.txt: its name" in found
    assert any(place.startswith("studio.py:") and place.endswith(": Bailey") for place in found)
