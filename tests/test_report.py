"""A recording's report (``pageant.report``): the hand checks before publishing, read off the recording's log.

One recording that gives nothing to look at, then each check on its own: the loudness and its true
peak, a caption held past its voice, a stretch with no voice, a picture that does not change, motion
with too few distinct frames, the seconds after the last line, and the chapters YouTube makes. The
still picture and the silences are read between the first line and the end of the last, so a title
card or an end card held on screen is not one. A vertical video is held to a Short's rules instead:
no end screen, no chapters, and three minutes at most. Standard library only, as the module is.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from pageant import report

#: ffmpeg's ``ebur128=peak=true`` summary, as it ends its report.
SUMMARY = """[Parsed_ebur128_0 @ 0x5586] Summary:

  Integrated loudness:
    I:         -14.4 LUFS
    Threshold: -24.6 LUFS

  Loudness range:
    LRA:         4.2 LU
    Threshold:  -34.6 LUFS
    LRA low:    -16.9 LUFS
    LRA high:   -12.7 LUFS

  True peak:
    Peak:       -1.7 dBFS
"""


@dataclasses.dataclass
class Recording:
    """A minute of a lesson that gives nothing to look at, to change one thing of at a time."""

    seconds: float = 60.0
    lines: list[report.Line] = dataclasses.field(
        default_factory=lambda: [
            report.Line(2.0, 8.0, "The first line.", 5.5),
            report.Line(8.0, 20.0, "The second line, over a step.", 9.0),
            report.Line(20.0, 49.0, "The third.", 27.0),
        ]
    )
    voiced: list[tuple[float, float]] = dataclasses.field(
        default_factory=lambda: [(2.25, 7.3), (8.25, 17.0), (20.25, 26.0), (30.0, 37.0), (40.5, 48.5)]
    )
    #: A frame that changes every frame for the first 50 seconds, then the end card held 10 s.
    runs: list[int] = dataclasses.field(default_factory=lambda: [1] * 3000 + [600])
    chapters: list[tuple[float, str]] = dataclasses.field(
        default_factory=lambda: [(0.0, "One"), (20.0, "Two"), (40.0, "Three")]
    )
    loudness: report.Loudness | None = dataclasses.field(default_factory=lambda: report.Loudness(-14.2, -1.8))
    size: tuple[int, int] = (1920, 1080)

    def built(self) -> dict[str, Any]:
        return report.build(
            seconds=self.seconds,
            fps=60,
            size=self.size,
            lines=self.lines,
            voiced=self.voiced,
            runs=self.runs,
            chapters=self.chapters,
            loudness=self.loudness,
            target=-14.0,
        )


def test_ffmpegs_loudness_summary_is_read() -> None:
    assert report.loudness_of("Input #0, mov...\n" + SUMMARY) == report.Loudness(-14.4, -1.7)
    with pytest.raises(ValueError, match="no loudness summary"):
        report.loudness_of("ffmpeg ran nothing")


def test_a_recording_with_nothing_to_look_at_has_no_findings() -> None:
    built = Recording().built()

    assert built["findings"] == []
    assert built["voice"] == {"first": 2.2, "last_ends": 48.5, "longest_silence": {"seconds": 4.0, "at": 26.0}}
    assert built["picture"]["busiest_second"] == 60
    assert built["end"] == {"after_last_line": 11.5}
    assert built["captions"]["longest_past_voice"][0]["past"] == 3.0


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"loudness": report.Loudness(-16.6, -1.8)}, "-16.6 LUFS, not within 1 LU of -14"),
        ({"loudness": report.Loudness(-14.0, -0.4)}, "true peak is -0.4 dBTP, over -1"),
        (
            {"lines": [report.Line(2.0, 15.8, "Enter a card.", 3.5)]},
            "A caption stays up 10.3 s after its voice at 0:02.0: “Enter a card.”",
        ),
        ({"voiced": [(2.25, 7.3), (14.0, 48.5)]}, "Nothing is said for 6.7 s from 0:07.3."),
        ({"runs": [1] * 600 + [540] + [1] * 1860 + [600]}, "The picture does not change for 9.0 s from 0:10.0."),
        ({"runs": [2] * 1500 + [600]}, "The busiest second of motion has 30 distinct frames of 60"),
        (
            {"seconds": 51.0, "runs": [1] * 3000 + [60]},
            "runs 2.5 s after its last line; YouTube's end screen takes 5 to 20",
        ),
        ({"seconds": 75.0, "runs": [1] * 3000 + [1500]}, "runs 26.5 s after its last line"),
        ({"chapters": [(4.0, "One"), (20.0, "Two"), (40.0, "Three")]}, "The first chapter starts at 0:04.0"),
        ({"chapters": [(0.0, "One"), (30.0, "Two")]}, "YouTube makes chapters of 3 or more; this has 2."),
        ({"chapters": [(0.0, "One"), (20.0, "Two"), (25.0, "Three"), (40.0, "Four")]}, "The chapter “Two” is 5.0 s"),
    ],
    ids=[
        "quiet",
        "true peak",
        "past its voice",
        "silence",
        "still",
        "choppy",
        "end too short",
        "end too long",
        "first chapter late",
        "two chapters",
        "short chapter",
    ],
)
def test_each_check_finds_what_it_is_for(change: dict[str, Any], says: str) -> None:
    findings = dataclasses.replace(Recording(), **change).built()["findings"]

    assert any(says in finding for finding in findings), findings
    assert len(findings) == 1, findings


def test_a_title_card_and_an_end_card_held_still_are_not_a_still_picture() -> None:
    # Ten seconds of title card before the first line, and the end card after the last: both still.
    recording = Recording(
        seconds=70.0,
        lines=[report.Line(12.0, 49.0, "One long line over the steps.", 37.0)],
        voiced=[(12.25, 48.5)],
        runs=[720] + [1] * 2880 + [600],
    )

    built = recording.built()

    assert built["picture"]["longest_still"]["seconds"] < 1
    assert not any("does not change" in finding for finding in built["findings"])


#: A Short of that minute: the same lines on a phone's screen, ending a breath after its last one.
SHORT = {"size": (1080, 1920), "seconds": 50.0, "runs": [1] * 3000}


def test_a_vertical_video_is_held_to_a_shorts_rules_not_to_an_end_screens_or_chapters() -> None:
    # Two chapters, and a second and a half after the last line: wrong for YouTube's landscape video,
    # and right for a Short, which has no chapters and plays again from the start.
    built = dataclasses.replace(Recording(), chapters=[(0.0, "One"), (30.0, "Two")], **SHORT).built()

    assert built["vertical"] is True
    assert built["end"] == {"after_last_line": 1.5}
    assert built["findings"] == []
    assert "| Length | 0:50.0 (50 s), 1080×1920 at 60 fps, vertical |" in report.markdown(built, "Short")


@pytest.mark.parametrize(
    ("change", "says"),
    [
        (
            {"seconds": 54.0, "runs": [1] * 3000 + [240]},
            "runs 5.5 s after its last line; a Short has no end screen and plays again from the start, so 3 at most",
        ),
        ({"seconds": 190.0, "runs": [1] * 3000 + [8400]}, "YouTube shows a vertical video as a Short up to 180"),
    ],
    ids=["long tail", "too long"],
)
def test_each_of_a_shorts_checks_finds_what_it_is_for(change: dict[str, Any], says: str) -> None:
    findings = dataclasses.replace(Recording(), **{**SHORT, **change}).built()["findings"]

    assert any(says in finding for finding in findings), findings


def test_a_line_nothing_spoke_is_not_held_against_its_voice() -> None:
    built = Recording(lines=[report.Line(2.0, 30.0, "A note to read.", 0.0)]).built()

    assert built["captions"]["longest_past_voice"] == []
    assert built["findings"] == []


def test_the_report_is_written_as_json_and_as_a_table_with_what_to_look_at(tmp_path: Path) -> None:
    clean = Recording().built()
    report.write(tmp_path, clean, "Notebook basics: lesson 1")

    assert json.loads((tmp_path / report.JSON).read_text(encoding="utf-8")) == clean
    text = (tmp_path / report.MARKDOWN).read_text(encoding="utf-8")
    assert text.startswith("# Notebook basics: lesson 1\n")
    assert "| Loudness | -14.2 LUFS (target -14), true peak -1.8 dBTP |" in text
    assert "| Chapters | 0:00.0 One, 0:20.0 Two, 0:40.0 Three |" in text
    assert text.endswith("## To look at\n\nNothing.\n")

    loud = Recording(loudness=report.Loudness(-12.0, -0.5)).built()
    text = report.markdown(loud, "Loud")
    assert "- The mix is -12 LUFS, not within 1 LU of -14." in text
    assert "- The mix's true peak is -0.5 dBTP, over -1." in text
