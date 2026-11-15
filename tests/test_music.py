"""The music bed (``pageant.music``): what it plays, section by section, and that it is the same each time.

The bed was one progression of 24 seconds, played the same way from its intro to its outro, so a
lesson of five minutes heard it come round a dozen times. It goes in sections now: the bed's own
progression opens it and comes back between three others, and the arpeggio changes its figure
each section and rests for one now and then. These hold the plan to that, and the sound to the
same length always giving the same track.

The bed takes numpy, which only the record extra installs: without it these are skipped, unless
``PAGEANT_STUDIO_TESTS=required``, as CI's studio job sets it.
"""

from __future__ import annotations

import os

import pytest

try:
    from pageant import music
except ModuleNotFoundError as missing:
    if os.environ.get("PAGEANT_STUDIO_TESTS") == "required":
        raise
    pytest.skip(f"the music takes the record extra; {missing.name} is not installed", allow_module_level=True)


def figure(section: music.Section) -> tuple[tuple[int, ...] | None, tuple[int, ...]]:
    return section.pattern, section.shape


def test_the_bed_opens_on_its_own_progression_played_as_it_always_was() -> None:
    first = music.plan(40)[0]

    assert first == music.Section(("Dmaj9", "Bm7", "Gmaj7", "A(add9)"), (1, 0, 1, 1, 0, 1, 0, 1), (0, 1, 2, 3, 2, 1))


def test_the_plan_has_a_section_for_every_24_seconds_and_is_the_same_for_the_same_length() -> None:
    assert len(music.plan(10)) == 1
    assert len(music.plan(24)) == 1
    assert len(music.plan(25)) == 2
    assert len(music.plan(300)) == 13
    assert music.plan(300) == music.plan(300)
    # A longer bed begins as the shorter one does.
    assert music.plan(600)[:13] == music.plan(300)


def test_its_own_progression_comes_back_between_each_of_the_others() -> None:
    order = [music.PROGRESSIONS.index(s.chords) for s in music.plan(1200)]

    assert order[0::2] == [0] * len(order[0::2])
    others = order[1::2]
    assert set(others) == {1, 2, 3}
    for i in range(0, len(others) - 2, 3):
        assert sorted(others[i : i + 3]) == [1, 2, 3], "each goes round once before any comes again"
    assert all(a != b for a, b in zip(others, others[1:], strict=False)), "never the same one twice running"


def test_no_eight_bars_come_back_played_the_same_way_for_minutes() -> None:
    sections = music.plan(1200)
    heard: dict[tuple[tuple[str, ...], tuple[tuple[int, ...] | None, tuple[int, ...]]], int] = {}
    for index, section in enumerate(sections):
        key = (section.chords, figure(section))
        if key in heard and section.pattern is not None:
            assert index - heard[key] >= 6, (
                f"section {index} plays section {heard[key]} again, {index - heard[key]} sections on"
            )
        heard[key] = index
    for before, after in zip(sections, sections[1:], strict=False):
        assert figure(before) != figure(after) or before.pattern is None


def test_the_arpeggio_rests_now_and_then_but_never_at_first_and_never_two_sections_close() -> None:
    rests = [index for index, section in enumerate(music.plan(1800)) if section.pattern is None]

    assert rests, "it rests at all"
    assert min(rests) >= 2
    assert all(b - a >= 3 for a, b in zip(rests, rests[1:], strict=False))
    assert len(rests) <= len(music.plan(1800)) // 3


def test_every_chord_a_section_plays_is_voiced_rooted_and_arpeggiated_in_its_register() -> None:
    names = {name for progression in music.PROGRESSIONS for name in progression}

    assert names == set(music.CHORDS) == set(music.ROOTS) == set(music.ARPEGGIOS)
    for name in names:
        assert all(47 <= note <= 69 for note in music.CHORDS[name]), name
        assert 35 <= music.ROOTS[name] <= 45, name
        assert all(64 <= note <= 85 for note in music.ARPEGGIOS[name]), name
        assert sorted(music.ARPEGGIOS[name]) == music.ARPEGGIOS[name], name
    for progression in music.PROGRESSIONS:
        assert progression[-1] in {"A(add9)", "Bm7"}, "each leads back to the bed's own Dmaj9"


def test_the_same_length_always_gives_the_same_track_at_minus_one_dbfs() -> None:
    first, again = music.compose(30), music.compose(30)

    assert first.shape == (30 * music.RATE, 2)
    assert (first == again).all()
    assert abs(float(abs(first).max()) - 10 ** (-1 / 20)) < 1e-9
