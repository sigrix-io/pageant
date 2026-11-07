"""A lesson's loudness in two passes: what ffmpeg's ``loudnorm`` measures of a mix, then the level it is set to.

One pass of ``loudnorm`` estimates as it goes and lands near its target, often half a decibel or more
under it. A second pass, handed what the first measured, lands on it: linearly, by one gain, when the
mix's peaks leave room, and through loudnorm's limiter when they do not. ``mixdown.py`` runs both;
what each says is here, in the standard library alone, so it is tested without ffmpeg.

-16 LUFS is the level web players expect, and the default. YouTube plays every video at -14 LUFS and
turns nothing up, so a lesson made for it says ``loudness=-14``, or it plays quieter than the videos
around it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping

#: The loudness a lesson's mix is set to unless it says otherwise: what web players expect.
WEB = -16.0
#: The level YouTube plays every video at.
YOUTUBE = -14.0
#: The loudness range loudnorm aims for, and the true peak it keeps the mix under, in dB.
RANGE = 11.0
TRUE_PEAK = -2.0
#: What the first pass prints, by name, that the second is handed.
MEASURED = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def first_pass(target: float) -> str:
    """The filter that measures a mix against ``target`` and prints what it found as JSON."""

    return f"loudnorm=I={target:g}:TP={TRUE_PEAK:g}:LRA={RANGE:g}:print_format=json"


def measured(report: str) -> dict[str, float]:
    """What the first pass measured, read from the end of ffmpeg's report.

    Raises ``ValueError`` when the report holds no such figures, which is a first pass that never ran.
    """

    start = report.rfind("{")
    end = report.find("}", start)
    if start < 0 or end < 0:
        raise ValueError("ffmpeg's report holds no loudness figures: the first pass printed none.")
    data = json.loads(report[start : end + 1])
    missing = [name for name in MEASURED if name not in data]
    if missing:
        raise ValueError(f"ffmpeg's loudness figures lack {', '.join(missing)}.")
    return {name: float(data[name]) for name in MEASURED}


def second_pass(target: float, figures: Mapping[str, float]) -> str:
    """The filter that sets the mix to ``target`` from what the first pass measured.

    A mix with nothing to measure (silence reads ``-inf``) is set by one pass, as it would have been.
    """

    if not all(math.isfinite(figures[name]) for name in MEASURED):
        return f"loudnorm=I={target:g}:TP={TRUE_PEAK:g}:LRA={RANGE:g}"
    return (
        f"loudnorm=I={target:g}:TP={TRUE_PEAK:g}:LRA={RANGE:g}"
        f":measured_I={figures['input_i']:g}:measured_TP={figures['input_tp']:g}"
        f":measured_LRA={figures['input_lra']:g}:measured_thresh={figures['input_thresh']:g}"
        f":offset={figures['target_offset']:g}:linear=true:print_format=none"
    )


__all__ = ["MEASURED", "RANGE", "TRUE_PEAK", "WEB", "YOUTUBE", "first_pass", "measured", "second_pass"]
