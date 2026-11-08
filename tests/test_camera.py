"""The camera's framing and the pointer's paths (``pageant.camera``): arithmetic, held to what a viewer sees.

A view frames what a step points at as large as fits above the captions, no larger than the lesson
allows, and never past the screen's edges; the camera eases between views, zooming in and out at
an even pace; the pointer bows gently on its way and speeds up and slows down as a hand does.
"""

from __future__ import annotations

import math

import pytest

from pageant import camera
from pageant.camera import HEIGHT, WHOLE, WIDTH, View

BAND = 125


def test_a_small_element_is_framed_as_large_as_the_lesson_allows_above_the_captions() -> None:
    # "You keep $7.20", 393x74 in the middle of the screen.
    view = camera.framing((700, 260, 393, 74), 2.0, band=BAND)

    assert view.scale == pytest.approx(2.0)
    assert view.height == pytest.approx(360.0)
    middle_x = (700 + 393 / 2 - view.x) * view.scale
    middle_y = (260 + 74 / 2 - view.y) * view.scale
    assert middle_x == pytest.approx(WIDTH / 2), "in the middle across"
    assert middle_y == pytest.approx((HEIGHT - BAND) / 2), "in the middle of the room above the captions"


def test_a_larger_element_is_framed_to_fill_the_room_above_the_captions_and_no_more() -> None:
    view = camera.framing((300, 200, 500, 300), 3.0, band=BAND)

    shown_height = 300 * view.scale
    assert shown_height == pytest.approx(camera.FILL * (HEIGHT - BAND)), "its height fills its share of the room"
    assert 500 * view.scale <= WIDTH


def test_a_view_never_goes_past_the_screens_edges() -> None:
    corner = camera.framing((1200, 10, 60, 30), 2.0, band=BAND)
    origin = camera.framing((0, 690, 50, 20), 2.0, band=BAND)

    for view in (corner, origin):
        assert 0 <= view.x <= WIDTH - view.width
        assert 0 <= view.y <= HEIGHT - view.height
    assert corner.x + corner.width == pytest.approx(WIDTH) and corner.y == 0
    assert origin.x == 0 and origin.y + origin.height == pytest.approx(HEIGHT)


@pytest.mark.parametrize(
    ("box", "most"),
    [
        ((0, 0, 1200, 600), 2.0),  # nearly the whole screen: a zoom under LEAST_ZOOM is not worth a move
        ((100, 100, 300, 80), 1.0),  # a lesson that does not zoom
        ((100, 100, 300, 80), 0.5),
        ((100, 100, 0, 80), 2.0),  # an element with nothing to show
    ],
)
def test_no_zoom_is_made_where_none_is_worth_it_or_allowed(box: tuple[float, float, float, float], most: float) -> None:
    assert camera.framing(box, most, band=BAND) == WHOLE


def test_the_camera_eases_between_views_and_zooms_at_an_even_pace() -> None:
    near = View(400, 200, 640)

    assert camera.between(WHOLE, near, 0) == WHOLE
    assert camera.between(WHOLE, near, 1) == near
    halfway = camera.between(WHOLE, near, 0.5)
    assert halfway.scale == pytest.approx(math.sqrt(near.scale)), "halfway in scale is halfway in its logarithm"
    scales = [camera.between(WHOLE, near, step / 30).scale for step in range(31)]
    assert scales == sorted(scales), "it zooms one way, never back"
    moves = [b - a for a, b in zip(scales, scales[1:], strict=False)]
    assert moves[0] < moves[15] > moves[-1], "slow at its start and its end"


def test_the_corners_move_in_step_so_the_view_closes_in_on_what_it_frames() -> None:
    near = View(400, 200, 640)

    for step in range(1, 30):
        view = camera.between(WHOLE, near, step / 30)
        # Every view on the way holds the one it is going to: nothing framed leaves the frame.
        assert view.x <= near.x + 1e-6 and view.y <= near.y + 1e-6
        assert view.x + view.width >= near.x + near.width - 1e-6
        assert view.y + view.height >= near.y + near.height - 1e-6


def test_a_pan_at_one_scale_eases_too() -> None:
    left, right = View(0, 0, 640), View(640, 360, 640)

    halfway = camera.between(left, right, 0.5)
    assert halfway == View(320, 180, 640)
    assert camera.between(left, right, 0.1).x < 0.1 * 640, "slow to start"


def test_a_view_says_what_is_in_it() -> None:
    view = View(100, 100, 640)

    assert view.holds(420, 280)
    assert not view.holds(90, 280)
    assert not view.holds(735, 280, margin=10)
    assert WHOLE.whole and not view.whole


def test_the_easings_start_and_end_where_they_should_and_never_turn_back() -> None:
    for curve in (camera.ease, camera.hand):
        values = [curve(step / 100) for step in range(101)]
        assert values[0] == 0 and values[-1] == pytest.approx(1)
        assert values == sorted(values)
        assert curve(0.5) == pytest.approx(0.5)
        assert curve(-1) == 0 and curve(2) == pytest.approx(1)


def test_the_pointers_path_ends_where_it_aims_one_point_a_frame() -> None:
    points = camera.path((640, 360), (1180, 40), 60)

    distance = math.dist((640, 360), (1180, 40))
    assert len(points) == camera.frames_for(camera.reach_seconds(distance), 60)
    assert points[-1] == (1180, 40)
    assert math.dist(points[0], (640, 360)) < 5, "it starts gently"


def test_the_pointers_path_bows_to_one_side_and_speeds_up_then_slows_down() -> None:
    start, end = (100.0, 600.0), (1100.0, 600.0)
    points = camera.path(start, end, 60)

    # A level move: how far it bows is how far off the line it goes, all to one side.
    offsets = [y - 600 for _, y in points[:-1]]
    assert all(offset > 0 for offset in offsets[1:]) or all(offset < 0 for offset in offsets[1:])
    most = max(abs(offset) for offset in offsets)
    assert most == pytest.approx(min(camera.MOST_BOW, camera.BOW * 1000) / 2, rel=0.05)
    steps = [math.dist(a, b) for a, b in zip([start, *points], points, strict=False)]
    middle = len(steps) // 2
    assert steps[0] < steps[middle] > steps[-1]


def test_a_longer_move_takes_longer_within_its_bounds() -> None:
    assert camera.reach_seconds(0) == camera.QUICKEST
    assert camera.reach_seconds(10_000) == camera.SLOWEST
    assert camera.reach_seconds(200) < camera.reach_seconds(800)


def test_a_move_of_under_a_pixel_is_made_at_once() -> None:
    assert camera.path((10.0, 10.0), (10.4, 10.2), 60) == [(10.4, 10.2)]
