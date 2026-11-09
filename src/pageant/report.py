"""A recording's report: the checks a person makes by hand before publishing a lesson.

``pageant record`` writes it beside the video, as ``report.json`` and ``report.md``, and prints what
it found worth a look. It is read off the recording's own log, not guessed from the video: a
caption's time past its voice is measured against the clip the voice spoke, and the picture's motion
against the frames the film kept.

- **Loudness**: the mix's integrated loudness and its true peak, against the lesson's target
  (``LOUDNESS_TOLERANCE``) and the ceiling a player's own processing leaves room under
  (``TRUE_PEAK_MAX``).
- **A caption held past its voice**: a line still on screen ``PAST_VOICE`` seconds after its voice
  and the breath after it have ended, which a viewer sits through as dead air.
- **No voice**: the longest stretch between the first line and the end of the last with nothing
  spoken (``SILENCE``).
- **A still picture**: the longest stretch over the same span in which no frame changed (``STILL``),
  which a page that stopped moving shows as well as a page with nothing to do.
- **Motion**: how many of a second's frames differ from the frame before, in the busiest second
  (``SMOOTH``): a pointer's move or a scroll changes every frame.
- **The end**: the seconds after the last line, which YouTube's end screen takes (``END_MIN`` to
  ``END_MAX``).
- **Chapters**: what YouTube makes chapters of (``youtube.chapters``' rules).
- **A vertical video**, a phone's (``camera.PHONE``), is a Short on YouTube if it is ``SHORT_MAX``
  seconds or less. A Short has no end screen and no chapters, and plays again from the start, so
  its end is the seconds after its last line, ``SHORT_TAIL`` at most, and its chapters are not held
  to YouTube's rules.

A finding is something to look at, not a refusal: the video is written whatever the report says.
Everything here but ``measure_loudness`` is the standard library's arithmetic, so it is tested without
ffmpeg.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pageant import timeline

#: The files written beside the video.
JSON = "report.json"
MARKDOWN = "report.md"

#: LU either side of the lesson's target that its integrated loudness may land.
LOUDNESS_TOLERANCE = 1.0
#: dBTP a mix's true peak stays under.
TRUE_PEAK_MAX = -1.0
#: Seconds a caption may stay up after its voice and breath before it is dead air.
PAST_VOICE = 4.0
#: Seconds with no voice, between the first line and the end of the last, worth a look.
SILENCE = 6.0
#: Seconds without a changed frame, over the same span, worth a look.
STILL = 8.0
#: Distinct frames the busiest second of motion has at least, of the video's frames a second.
SMOOTH = 45
#: The seconds after the last line that YouTube's end screen takes: at least 5, at most 20.
END_MIN = 5.0
END_MAX = 20.0
#: What YouTube makes chapters of: the first at 0:00, at least three, each at least ten seconds.
CHAPTERS_MIN = 3
#: The longest vertical video YouTube shows as a Short, in seconds.
SHORT_MAX = 180.0
#: The seconds a Short may run after its last line before it plays again from the start.
SHORT_TAIL = 3.0


@dataclass(frozen=True)
class Line:
    """A caption as it was on screen, and how long its voice took with the lead before it and the
    breath after, which is 0 for a line nothing spoke."""

    start: float
    end: float
    text: str
    spoken: float = 0.0


@dataclass(frozen=True)
class Loudness:
    """The mix's integrated loudness, in LUFS, and its true peak, in dBTP."""

    integrated: float
    true_peak: float


def loudness_of(report: str) -> Loudness:
    """What ffmpeg's ``ebur128=peak=true`` filter measured, read from the summary it ends its report with.

    Raises ``ValueError`` when the report holds no summary, which is a measurement that never ran.
    """

    at = report.rfind("Summary:")
    if at < 0:
        raise ValueError("ffmpeg's report holds no loudness summary")
    summary = report[at:]
    integrated = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    peak = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if integrated is None or peak is None:
        raise ValueError("ffmpeg's loudness summary holds no integrated loudness or true peak")
    return Loudness(float(integrated.group(1)), float(peak.group(1)))


def measure_loudness(video: Path) -> Loudness:
    """The finished video's loudness, as ``ebur128`` measures its audio."""

    done = subprocess.run(  # noqa: S603 -- ffmpeg, with arguments this module spells
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"ffmpeg could not measure {video}: {done.stderr.strip()[-400:]}")
    return loudness_of(done.stderr)


def _clock(seconds: float) -> str:
    """A time in the video to the tenth of a second: ``1:32.8``."""

    whole, tenth = divmod(round(seconds * 10), 10)
    return f"{timeline.clock_time(whole)}.{tenth}"


def _merged(spans: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def build(
    *,
    seconds: float,
    fps: int,
    size: tuple[int, int],
    lines: Sequence[Line],
    voiced: Sequence[tuple[float, float]],
    runs: Sequence[int],
    chapters: Sequence[tuple[float, str]],
    loudness: Loudness | None = None,
    target: float | None = None,
) -> dict[str, Any]:
    """The report on a recording ``seconds`` long, from its log.

    ``voiced`` is when the voice spoke, ``runs`` how many frames in a row each kept picture is, in
    order (the film's shots), and ``chapters`` each chapter's start and title. A ``size`` taller than
    it is wide is a vertical video, held to a Short's rules.
    """

    found: list[str] = []
    vertical = size[1] > size[0]
    report: dict[str, Any] = {
        "seconds": round(seconds, 1),
        "size": f"{size[0]}x{size[1]}",
        "fps": fps,
        "vertical": vertical,
    }
    if vertical and seconds > SHORT_MAX:
        found.append(f"The video is {seconds:.1f} s; YouTube shows a vertical video as a Short up to {SHORT_MAX:g}.")

    if loudness is not None:
        report["loudness"] = {"integrated": loudness.integrated, "true_peak": loudness.true_peak, "target": target}
        if target is not None and abs(loudness.integrated - target) > LOUDNESS_TOLERANCE:
            found.append(
                f"The mix is {loudness.integrated:g} LUFS, not within {LOUDNESS_TOLERANCE:g} LU of {target:g}."
            )
        if loudness.true_peak > TRUE_PEAK_MAX:
            found.append(f"The mix's true peak is {loudness.true_peak:g} dBTP, over {TRUE_PEAK_MAX:g}.")

    past = sorted(
        ((line.end - line.start - line.spoken, line) for line in lines if line.spoken > 0), key=lambda pair: -pair[0]
    )
    report["captions"] = {
        "on_screen": len(lines),
        "longest_past_voice": [
            {
                "at": round(line.start, 1),
                "text": line.text,
                "held": round(line.end - line.start, 1),
                "spoken": round(line.spoken, 1),
                "past": round(extra, 1),
            }
            for extra, line in past[:5]
        ],
    }
    for extra, line in past:
        if extra > PAST_VOICE:
            found.append(f"A caption stays up {extra:.1f} s after its voice at {_clock(line.start)}: “{line.text}”")

    spoken = _merged(voiced)
    first = spoken[0][0] if spoken else 0.0
    last = spoken[-1][1] if spoken else 0.0
    gaps = sorted(
        ((after - before, before) for (_, before), (after, _) in zip(spoken, spoken[1:], strict=False)), reverse=True
    )
    report["voice"] = {
        "first": round(first, 1),
        "last_ends": round(last, 1),
        "longest_silence": {"seconds": round(gaps[0][0], 1), "at": round(gaps[0][1], 1)} if gaps else None,
    }
    for gap, at in gaps:
        if gap > SILENCE:
            found.append(f"Nothing is said for {gap:.1f} s from {_clock(at)}.")

    starts: list[int] = []
    frame = 0
    for run in runs:
        starts.append(frame)
        frame += run
    distinct: dict[int, int] = {}
    for start in starts:
        distinct[start // fps] = distinct.get(start // fps, 0) + 1
    moving = [count for count in distinct.values() if count > 1]
    still = (0.0, 0.0)
    for start, run in zip(starts, runs, strict=True):
        a, b = max(start / fps, first), min((start + run) / fps, last)
        if b - a > still[0]:
            still = (b - a, a)
    report["picture"] = {
        "distinct_frames": len(runs),
        "busiest_second": max(moving, default=1),
        "moving_second_median": round(statistics.median(moving), 1) if moving else 1,
        "longest_still": {"seconds": round(still[0], 1), "at": round(still[1], 1)},
    }
    if moving and max(moving) < SMOOTH:
        found.append(
            f"The busiest second of motion has {max(moving)} distinct frames of {fps}: motion will look choppy."
        )
    if still[0] > STILL:
        found.append(f"The picture does not change for {still[0]:.1f} s from {_clock(still[1])}.")

    after = seconds - last
    report["end"] = {"after_last_line": round(after, 1)}
    if spoken and vertical and after > SHORT_TAIL:
        found.append(
            f"The video runs {after:.1f} s after its last line; a Short has no end screen and plays again "
            f"from the start, so {SHORT_TAIL:g} at most."
        )
    elif spoken and not vertical and not END_MIN <= after <= END_MAX:
        found.append(
            f"The video runs {after:.1f} s after its last line; YouTube's end screen takes {END_MIN:g} to {END_MAX:g}."
        )

    report["chapters"] = [{"at": round(start, 1), "title": title} for start, title in chapters]
    if chapters and not vertical:
        if chapters[0][0] > 0:
            found.append(f"The first chapter starts at {_clock(chapters[0][0])}; YouTube wants 0:00.")
        if len(chapters) < CHAPTERS_MIN:
            found.append(f"YouTube makes chapters of {CHAPTERS_MIN} or more; this has {len(chapters)}.")
        ends = [begins for begins, _ in chapters[1:]] + [seconds]
        for (begins, title), stops in zip(chapters, ends, strict=True):
            if stops - begins < timeline.SHORTEST_CHAPTER:
                found.append(
                    f"The chapter “{title}” is {stops - begins:.1f} s; YouTube wants each {timeline.SHORTEST_CHAPTER:g} s or more."
                )

    report["findings"] = found
    return report


def markdown(report: dict[str, Any], title: str) -> str:
    """``report.md``: the numbers a person reads first, and what to look at."""

    rows = [
        (
            "Length",
            f"{_clock(report['seconds'])} ({report['seconds']:g} s), {report['size'].replace('x', '×')} at {report['fps']} fps"
            + (", vertical" if report.get("vertical") else ""),
        )
    ]
    sound = report.get("loudness")
    if sound:
        target = f" (target {sound['target']:g})" if sound["target"] is not None else ""
        rows.append(("Loudness", f"{sound['integrated']:g} LUFS{target}, true peak {sound['true_peak']:g} dBTP"))
    captions = report["captions"]
    worst = captions["longest_past_voice"][0] if captions["longest_past_voice"] else None
    rows.append(
        (
            "Captions",
            f"{captions['on_screen']} on screen"
            + (f"; the longest past its voice: {worst['past']:g} s at {_clock(worst['at'])}" if worst else ""),
        )
    )
    silence = report["voice"]["longest_silence"]
    rows.append(
        (
            "Voice",
            f"the longest stretch with none: {silence['seconds']:g} s at {_clock(silence['at'])}"
            if silence
            else "one line, or none",
        )
    )
    picture = report["picture"]
    rows.append(
        (
            "Picture",
            f"{picture['busiest_second']} distinct frames in the busiest second, "
            f"{picture['moving_second_median']:g} in a moving second's median; the longest still: "
            f"{picture['longest_still']['seconds']:g} s at {_clock(picture['longest_still']['at'])}",
        )
    )
    rows.append(("End", f"{report['end']['after_last_line']:g} s after the last line"))
    if report["chapters"]:
        rows.append(("Chapters", ", ".join(f"{_clock(c['at'])} {c['title']}" for c in report["chapters"])))
    lines = [
        f"# {title}",
        "",
        "| | |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in rows),
        "",
        "## To look at",
        "",
    ]
    lines += [f"- {finding}" for finding in report["findings"]] or ["Nothing."]
    return "\n".join(lines) + "\n"


def write(folder: Path, report: dict[str, Any], title: str) -> None:
    """Write ``report.json`` and ``report.md`` into a recorded lesson's folder."""

    (folder / JSON).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / MARKDOWN).write_text(markdown(report, title), encoding="utf-8")
