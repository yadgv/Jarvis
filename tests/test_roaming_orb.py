"""The orb wanders near the screen edges while Jarvis is active, then glides home."""
import math

from brain import settings
from orb_motion import Roamer

SCREEN = (1920, 1080)
SIZE = 128
HOME = (1920 - 24 - SIZE, 24)    # top-right corner


def _run(r, seconds, active, pointer=None, calm=False, dt=1 / 60):
    path = []
    for _ in range(int(seconds / dt)):
        path.append(r.step(dt, active, HOME, SIZE, SCREEN, pointer, calm))
    return path


def test_rests_at_home_when_idle():
    r = Roamer(seed=1)
    path = _run(r, 1, active=False)
    assert all(p is None for p in path[1:])          # nothing to move while idle at home


def test_roams_smoothly_within_its_zone_then_returns():
    r = Roamer(seed=2)
    path = [p for p in _run(r, 20, active=True) if p]
    x0, y0, x1, y1 = r.zone(HOME, SIZE, SCREEN)
    assert max(math.hypot(x - HOME[0], y - HOME[1]) for x, y in path) > 150     # it really moves
    for x, y in path:
        assert x0 - 30 <= x <= x1 + 30 and y0 - 30 <= y <= y1 + 30            # stays on its side
    steps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])]
    assert max(steps) <= Roamer.MAX_SPEED / 60 + 0.5                         # no jumps
    back = _run(r, 6, active=False)
    assert back[-1] is None and (r.x, r.y) == HOME                           # home and still


def test_never_crosses_to_the_other_half():
    """The text panel opens towards the middle, so the orb stays on its home side."""
    r = Roamer(seed=3)
    for x, y in [p for p in _run(r, 30, active=True) if p]:
        assert x + SIZE / 2 > SCREEN[0] / 2 - 10 and y + SIZE / 2 < SCREEN[1] / 2 + 10


def test_holds_still_when_the_mouse_is_near():
    r = Roamer(seed=4)
    _run(r, 3, active=True)
    here = (r.x, r.y)
    pointer = (r.x + SIZE / 2 + 20, r.y + SIZE / 2)
    _run(r, 2, active=True, pointer=pointer)
    assert math.hypot(r.x - here[0], r.y - here[1]) < 40


def test_reduce_animations_keeps_it_home():
    r = Roamer(seed=5)
    path = _run(r, 3, active=True, calm=True)
    assert all(p in (None, HOME) for p in path)


def test_setting_defaults_on():
    assert settings.app_defaults()["roam"] is True
