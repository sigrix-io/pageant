"""A lesson's loudness in two passes (``pageant.loudness``): the measuring filter, the report, the levelling filter.

One pass of ffmpeg's ``loudnorm`` left a lesson mixed for -16 LUFS at -16.6 LUFS, measured; the second
pass is handed what the first measured, so it lands on the target. ffmpeg itself runs in the record
job, where the example lesson is filmed and mixed; what each pass says, and reads, is pinned here.
"""

from __future__ import annotations

import math

import pytest

from pageant import loudness

#: The tail of a first pass's report, as ffmpeg's loudnorm prints it at the info level.
REPORT = """[Parsed_loudnorm_0 @ 0x55d2]
{
	"input_i" : "-18.62",
	"input_tp" : "-3.10",
	"input_lra" : "6.80",
	"input_thresh" : "-29.05",
	"output_i" : "-14.04",
	"output_tp" : "-2.00",
	"output_lra" : "5.90",
	"output_thresh" : "-24.43",
	"normalization_type" : "dynamic",
	"target_offset" : "0.04"
}
"""


def test_the_first_pass_measures_against_the_target_and_prints_what_it_found() -> None:
    assert loudness.first_pass(-14) == "loudnorm=I=-14:TP=-2:LRA=11:print_format=json"
    assert loudness.first_pass(loudness.WEB) == "loudnorm=I=-16:TP=-2:LRA=11:print_format=json"


def test_the_report_is_read_from_the_last_figures_ffmpeg_printed() -> None:
    figures = loudness.measured("frame=  100 fps=0.0\nsize=N/A time=00:01:00.00\n" + REPORT)

    assert figures == {
        "input_i": -18.62,
        "input_tp": -3.10,
        "input_lra": 6.80,
        "input_thresh": -29.05,
        "target_offset": 0.04,
    }


def test_a_brace_earlier_in_the_report_is_not_taken_for_the_figures() -> None:
    report = "Input #0, wav, from 'mix.wav':\n  Metadata:\n    comment : {take 2}\n" + REPORT

    assert loudness.measured(report)["input_i"] == -18.62


def test_a_report_with_no_figures_is_refused_rather_than_read_as_silence() -> None:
    with pytest.raises(ValueError, match="no loudness figures"):
        loudness.measured("ffmpeg ran, and its first pass printed nothing")
    with pytest.raises(ValueError, match="lack target_offset"):
        loudness.measured(REPORT.replace('"target_offset" : "0.04"', '"other" : "0"'))


def test_the_second_pass_is_handed_what_the_first_measured() -> None:
    level = loudness.second_pass(-14, loudness.measured(REPORT))

    assert level == (
        "loudnorm=I=-14:TP=-2:LRA=11:measured_I=-18.62:measured_TP=-3.1:measured_LRA=6.8"
        ":measured_thresh=-29.05:offset=0.04:linear=true:print_format=none"
    )


def test_a_silent_mix_is_levelled_in_one_pass() -> None:
    silent = dict(loudness.measured(REPORT), input_i=-math.inf, input_thresh=-math.inf)

    assert loudness.second_pass(-16, silent) == "loudnorm=I=-16:TP=-2:LRA=11"
