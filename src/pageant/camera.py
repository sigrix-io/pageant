"""Where a frame looks, and how the pointer gets somewhere: the camera and the pointer's paths.

A lesson films a ``Screen``: a computer's, ``LANDSCAPE``, ``WIDTH`` x ``HEIGHT`` CSS pixels, unless it
says otherwise, or a phone's held upright, ``PHONE``, for a vertical video. On the landscape screen
the camera shows a rectangle of it, a ``View``, scaled up to fill the frame, so the text a step is
about is large enough to read on a phone; the whole screen is the view at scale 1. A phone's screen
is filmed whole: its page is laid out for a phone already. A view frames what a lesson points at
(``framing``): the element, as large as it fits above the captions at the foot of the screen, up to
the lesson's largest zoom, and never past the screen's edges. Between two views the camera eases
(``between``), and the pointer moves along a gently curved path that speeds up and slows down as a
hand does (``path``), one point to a frame.

Standard library only: it is all arithmetic, and tested without a browser.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Screen:
    """The screen a lesson films: its size in CSS pixels, the device scale Chromium paints it at, and
    the foot of it its captions cover.

    The frame is the screen at its scale, in device pixels. The page sees a window of the screen's
    size, so it lays itself out for it as it would for a person's: a phone's screen gets the page a
    phone gets.
    """

    width: int
    height: int
    scale: float
    #: The foot of the screen, in CSS pixels, that a caption of two or three lines covers: an element
    #: a step points at is above it, or the page is scrolled to put it there.
    band: int

    @property
    def frame(self) -> tuple[int, int]:
        """A frame's size in device pixels: the screen at its scale."""

        return round(self.width * self.scale), round(self.height * self.scale)

    @property
    def upright(self) -> bool:
        """Whether the screen is taller than it is wide, as a phone is held: a vertical video's."""

        return self.height > self.width


#: A computer's screen, 1280x720 CSS pixels painted at 1.5, so frames are 1920x1080: what a learning
#: site and YouTube play. Its captions are at its foot (``overlay.js``).
LANDSCAPE = Screen(1280, 720, 1.5, 125)
#: A phone's, held upright: 360x640 CSS pixels painted at 3, so frames are 1080x1920, the vertical
#: video YouTube Shorts and the like play. Its captions sit above the foot of the screen that those
#: players cover with their own titles (``overlay.js``).
PHONE = Screen(360, 640, 3.0, 250)
#: The landscape screen, in CSS pixels: the screen the camera moves on.
WIDTH, HEIGHT = LANDSCAPE.width, LANDSCAPE.height
#: How much of the room above the captions a framed element fills, at most.
FILL = 0.72
#: A zoom smaller than this is not worth the camera's move: the view stays where it is.
LEAST_ZOOM = 1.18
#: How long the camera takes to move between two views, in seconds.
MOVE_SECONDS = 0.7
#: A pointer's move takes this long at the least, and at the most, in seconds, longer the further it goes.
QUICKEST, SLOWEST = 0.32, 0.95
#: How far a pointer's path bows out of a straight line, as a share of its length, and at most in pixels.
BOW, MOST_BOW = 0.08, 48.0


@dataclass(frozen=True)
class View:
    """A rectangle of the screen, at ``x``, ``y`` and ``width`` CSS pixels wide, shown in the whole frame.

    Its height follows from the screen's shape, so a view is never stretched.
    """

    x: float
    y: float
    width: float

    @property
    def scale(self) -> float:
        """How much larger than on the screen the view shows what is in it."""

        return WIDTH / self.width

    @property
    def height(self) -> float:
        return self.width * HEIGHT / WIDTH

    @property
    def whole(self) -> bool:
        """Whether the view is the whole screen, to within a pixel's rounding."""

        return abs(self.width - WIDTH) < 0.5 and abs(self.x) < 0.5 and abs(self.y) < 0.5

    def holds(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Whether the point (``x``, ``y``) on the screen is in the view, ``margin`` pixels inside its edges."""

        return (
            self.x + margin <= x <= self.x + self.width - margin
            and self.y + margin <= y <= self.y + self.height - margin
        )


#: The whole screen.
WHOLE = View(0.0, 0.0, float(WIDTH))


def framing(
    box: tuple[float, float, float, float],
    most: float,
    *,
    band: float = 0.0,
) -> View:
    """The view that frames ``box`` (x, y, width and height on the screen, in CSS pixels).

    The box is shown as large as fits in ``FILL`` of the room above ``band``, the pixels at the foot
    of the frame that captions cover, and no larger than ``most`` times; its middle sits in the
    middle of that room, unless that would take the view past the screen's edges. A zoom under
    ``LEAST_ZOOM`` is not made, nor is any when ``most`` is 1 or less: the view is the whole screen.
    """

    x, y, width, height = box
    if most <= 1 or width <= 0 or height <= 0:
        return WHOLE
    room = HEIGHT - band
    scale = min(most, FILL * WIDTH / width, FILL * room / height)
    if scale < LEAST_ZOOM:
        return WHOLE
    seen_width, seen_height = WIDTH / scale, HEIGHT / scale
    # The box's middle at the middle of the room above the band, which is the frame's own middle
    # moved up by half the band, in the view's own (smaller) pixels.
    left = x + width / 2 - seen_width / 2
    top = y + height / 2 - (room / 2) / scale
    left = min(max(left, 0.0), WIDTH - seen_width)
    top = min(max(top, 0.0), HEIGHT - seen_height)
    return View(left, top, seen_width)


def ease(t: float) -> float:
    """Ease in and out (cubic): slow at the start and the end, quickest halfway."""

    t = min(max(t, 0.0), 1.0)
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def hand(t: float) -> float:
    """How far along a reach a hand is at ``t`` of its time: the minimum-jerk profile, 10t³ − 15t⁴ + 6t⁵."""

    t = min(max(t, 0.0), 1.0)
    return t**3 * (10 - 15 * t + 6 * t * t)


def between(start: View, end: View, t: float) -> View:
    """The view ``t`` of the way from ``start`` to ``end``, eased; at 0 it is ``start``, at 1 ``end``."""

    k = ease(t)
    # The scale moves evenly in its logarithm, so zooming in and out by the same factor take as long
    # and neither seems to rush its end.
    scale = math.exp(math.log(start.scale) + (math.log(end.scale) - math.log(start.scale)) * k)
    width = WIDTH / scale
    # The point that stays put relative to both views' edges: their corners move in step.
    if abs(start.width - end.width) < 1e-9:
        u = k
    else:
        u = (start.width - width) / (start.width - end.width)
    return View(start.x + (end.x - start.x) * u, start.y + (end.y - start.y) * u, width)


def frames_for(seconds: float, fps: int) -> int:
    """How many frames ``seconds`` take at ``fps``, one at the least."""

    return max(1, round(seconds * fps))


def reach_seconds(distance: float) -> float:
    """How long the pointer takes to move ``distance`` CSS pixels: a short move quickly, a long one longer."""

    return min(SLOWEST, max(QUICKEST, 0.22 + distance / 1500))


def path(start: tuple[float, float], end: tuple[float, float], fps: int) -> list[tuple[float, float]]:
    """The pointer's points from ``start`` to ``end``, one to a frame, the last of them ``end`` itself.

    The path bows gently to one side of the straight line, as a wrist's arc does, by ``BOW`` of its
    length and at most ``MOST_BOW`` pixels, and it speeds up and slows down as a hand does (``hand``).
    A move of under a pixel is made in one frame.
    """

    (x0, y0), (x1, y1) = start, end
    distance = math.hypot(x1 - x0, y1 - y0)
    if distance < 1:
        return [end]
    count = frames_for(reach_seconds(distance), fps)
    # The control point: the middle of the line, moved off it at right angles. Which side follows
    # the direction of travel, so a move and its way back bow the same way, as an arm's would.
    bow = min(MOST_BOW, BOW * distance)
    normal_x, normal_y = -(y1 - y0) / distance, (x1 - x0) / distance
    cx, cy = (x0 + x1) / 2 + normal_x * bow, (y0 + y1) / 2 + normal_y * bow
    points = []
    for index in range(1, count + 1):
        t = hand(index / count)
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        points.append((a * x0 + b * cx + c * x1, a * y0 + b * cy + c * y1))
    points[-1] = end
    return points


__all__ = [
    "BOW",
    "FILL",
    "HEIGHT",
    "LANDSCAPE",
    "LEAST_ZOOM",
    "MOST_BOW",
    "MOVE_SECONDS",
    "PHONE",
    "QUICKEST",
    "SLOWEST",
    "WHOLE",
    "WIDTH",
    "Screen",
    "View",
    "between",
    "ease",
    "frames_for",
    "framing",
    "hand",
    "path",
    "reach_seconds",
]
