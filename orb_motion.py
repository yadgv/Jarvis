"""How the corner orb moves around the screen (no Tk here, so it can be tested anywhere)."""
import math


class Roamer:
    """Makes the orb wander while Jarvis is listening, thinking or talking, then
    glide back home when he's done. Pure maths (no Tk), so it can be tested.

    It stays near the edges of the screen on the home corner's side (a band
    along the top or bottom edge and down the near side), so it doesn't sit
    over what he's working on and the text panel keeps opening the same way.
    It holds still while the mouse is near it (so it can be clicked) and moves
    on a soft spring, with a gentle bob, never faster than MAX_SPEED."""

    BAND = 0.2          # how far into the screen it may go, as a share of the screen
    STIFF = 5.0         # spring: higher = snappier
    DAMP = 4.2          # a touch under critical (2*sqrt(STIFF)=4.47): a little overshoot, lively
    MAX_SPEED = 520.0   # pixels a second
    HOLD = (2.5, 5.0)   # seconds at each spot before choosing the next
    NEAR_MOUSE = 150    # pixels: the mouse this close and it waits for him

    def __init__(self, seed=None):
        import random
        self.rand = random.Random(seed)
        self.x = self.y = None          # orb's top-left, floats
        self.vx = self.vy = 0.0
        self.target = None
        self.next_pick = 0.0
        self.home_x = self.home_y = 0.0
        self.t = 0.0
        self.resting = True             # at home and still: no need to move the window

    def place(self, x, y):
        self.x, self.y, self.vx, self.vy = float(x), float(y), 0.0, 0.0

    def zone(self, home, size, screen):
        """(x0, y0, x1, y1): where the orb's top-left may go."""
        sw, sh = screen
        hx, hy = home
        left_side = hx + size / 2 < sw / 2
        top_side = hy + size / 2 < sh / 2
        m = 16
        x0, x1 = (m, sw / 2 - size) if left_side else (sw / 2, sw - size - m)
        y0, y1 = (m, sh / 2 - size) if top_side else (sh / 2, sh - size - 64)
        return x0, y0, max(x0, x1), max(y0, y1)

    def pick(self, home, size, screen):
        """A new spot: along the top/bottom edge band or down the near side band."""
        x0, y0, x1, y1 = self.zone(home, size, screen)
        sw, sh = screen
        bx, by = self.BAND * sw, self.BAND * sh
        hx, hy = home
        if self.rand.random() < 0.6:     # along the near horizontal edge
            x = self.rand.uniform(x0, x1)
            y = hy + self.rand.uniform(-1, 1) * by * 0.5
        else:                            # down the near side
            x = hx + self.rand.uniform(-1, 1) * bx * 0.4
            y = self.rand.uniform(y0, y1)
        return min(max(x, x0), x1), min(max(y, y0), y1)

    def step(self, dt, active, home, size, screen, pointer=None, calm=False):
        """Advance by dt seconds. Returns the orb's new top-left, or None when it's
        resting at home (nothing to move)."""
        if self.x is None:
            self.place(*home)
        self.t += dt
        hx, hy = home
        if active and not calm:
            if self.target is None or self.t >= self.next_pick:
                self.target = self.pick(home, size, screen)
                self.next_pick = self.t + self.rand.uniform(*self.HOLD)
            tx, ty = self.target
            # a slow bob so it never looks parked
            tx += 7 * math.sin(self.t * 1.7)
            ty += 5 * math.sin(self.t * 2.3 + 1.0)
        else:
            self.target = None
            tx, ty = hx, hy
            if calm or (abs(self.x - hx) < 0.6 and abs(self.y - hy) < 0.6
                        and abs(self.vx) + abs(self.vy) < 2):
                if not self.resting or (self.x, self.y) != (hx, hy):
                    self.place(hx, hy)
                    self.resting = True
                    return hx, hy
                return None
        if pointer is not None and active:
            px, py = pointer
            cx, cy = self.x + size / 2, self.y + size / 2
            if math.hypot(px - cx, py - cy) < self.NEAR_MOUSE:
                tx, ty = self.x, self.y            # he's reaching for it: hold still
                self.next_pick = self.t + 1.0
        self.resting = False
        ax = self.STIFF * (tx - self.x) - self.DAMP * self.vx
        ay = self.STIFF * (ty - self.y) - self.DAMP * self.vy
        self.vx += ax * dt
        self.vy += ay * dt
        speed = math.hypot(self.vx, self.vy)
        if speed > self.MAX_SPEED:
            self.vx, self.vy = self.vx * self.MAX_SPEED / speed, self.vy * self.MAX_SPEED / speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        return self.x, self.y
