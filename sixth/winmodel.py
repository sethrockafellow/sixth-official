"""winmodel.py: home win, draw and away win chances at any moment of a match.

Fitted and tested on 6,080 real Premier League matches (scripts/fit_win_model.py; the numbers
are in sixth/win_model.json and docs/WIN_MODEL.md). How it works:

  scoring rates   each club's goals per match before kick-off, from the two Elo ratings
  timing          a share s1 of goals come in the first half; inside a half the rate is flat
  game state      a team that trails attacks more and scores more; a team that leads scores
                  less. Multipliers fitted on real second halves.
  evidence        expected goals (xG) so far move each rate a little: a team that makes more
                  chances than expected is probably playing better than its rating
                  (assumption: weight kappa = 4 expected goals; not testable with this data)
  red cards       a team with 10 men scores at about 0.70 of its rate, its opponent at about
                  1.30 (approximate values from the research literature; an assumption here)

Then it plays out the rest of the match minute by minute over every possible goal difference,
so a goal changes the rates for the minutes after it. No simulation noise: the same inputs
always give the same chances.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

HALF_S, MATCH_S = 2700.0, 5400.0
SPAN = 12                                   # goal differences -12 to +12 are tracked


class WinModel:
    def __init__(self, params: dict):
        self.p = params
        self.gamma = np.array([params["gamma"][str(max(-2, min(2, g)))] for g in range(-SPAN, SPAN + 1)])

    def rates(self, elo_home: float, elo_away: float) -> tuple[float, float]:
        """Pre-match expected goals for each side."""
        d = (elo_home - elo_away) / 400.0
        return math.exp(self.p["a_home"] + self.p["b"] * d), math.exp(self.p["a_away"] - self.p["b"] * d)

    def share_by(self, t: float) -> float:
        """The share of a match's goals expected by time t."""
        s1 = self.p["s1"]
        return s1 * t / HALF_S if t <= HALF_S else s1 + (1 - s1) * (t - HALF_S) / HALF_S

    def form(self, mu: float, xg: float | None, t: float) -> float:
        """How the xG so far moves a team's rate: a ratio, kept between 0.5 and 2."""
        if xg is None or t <= 0:
            return 1.0
        k = self.p["kappa"]
        return min(2.0, max(0.5, (k + xg) / (k + mu * self.share_by(t))))

    def chances(self, t: float, score_home: int, score_away: int, elo_home: float, elo_away: float,
                xg_home: float | None = None, xg_away: float | None = None,
                reds_home: int = 0, reds_away: int = 0) -> tuple[float, float, float]:
        t = min(max(float(t), 0.0), MATCH_S)
        mu_h, mu_a = self.rates(elo_home, elo_away)
        f_h, f_a = self.form(mu_h, xg_home, t), self.form(mu_a, xg_away, t)
        red_h = self.p["red_self"] ** reds_home * self.p["red_opponent"] ** reds_away
        red_a = self.p["red_self"] ** reds_away * self.p["red_opponent"] ** reds_home
        raw = _play_out(round(t), score_home - score_away, round(mu_h * f_h * red_h, 6),
                        round(mu_a * f_a * red_a, 6), self.p["s1"], self.p["s2_scale"], tuple(self.gamma))
        return calibrate(raw, self.p.get("temperature", 1.0))


def calibrate(p: tuple, temperature: float) -> tuple[float, float, float]:
    """Soften over-confident chances: each chance to the power 1/T, then rescaled to sum to 1.

    A Poisson model is a little too sure of itself: real scorelines vary more than it allows
    (team strength is never known exactly). T is fitted on the training seasons.
    """
    if temperature == 1.0:
        return p
    w = [max(x, 1e-12) ** (1.0 / temperature) for x in p]
    s = sum(w)
    certain = [x >= 1.0 - 1e-12 for x in p]
    if any(certain):                       # a settled result stays settled
        return tuple(1.0 if c else 0.0 for c in certain)
    return tuple(x / s for x in w)


@lru_cache(maxsize=200_000)
def _play_out(t: int, diff: int, mu_h: float, mu_a: float, s1: float, s2_scale: float, gamma: tuple):
    g = np.array(gamma)
    p = np.zeros(2 * SPAN + 1)
    p[max(-SPAN, min(SPAN, diff)) + SPAN] = 1.0
    now = float(t)
    while now < MATCH_S - 1e-9:
        end = min(now + 60.0, HALF_S if now < HALF_S else MATCH_S)
        dt = end - now
        if now < HALF_S:
            per_s_h, per_s_a = mu_h * s1 / HALF_S, mu_a * s1 / HALF_S
        else:
            per_s_h, per_s_a = mu_h * (1 - s1) * s2_scale / HALF_S, mu_a * (1 - s1) * s2_scale / HALF_S
        ph = per_s_h * dt * np.exp(g)             # home's state is the goal difference
        pa = per_s_a * dt * np.exp(g[::-1])       # away's state is minus the goal difference
        stay = p * (1.0 - ph - pa)
        up = np.zeros_like(p)
        down = np.zeros_like(p)
        up[1:] = (p * ph)[:-1]
        up[-1] += (p * ph)[-1]
        down[:-1] = (p * pa)[1:]
        down[0] += (p * pa)[0]
        p = stay + up + down
        now = end
    home = float(p[SPAN + 1:].sum())
    draw = float(p[SPAN])
    away = max(0.0, 1.0 - home - draw)
    return home, draw, away


@lru_cache(maxsize=1)
def default() -> WinModel:
    return WinModel(json.loads((Path(__file__).parent / "win_model.json").read_text(encoding="utf-8")))
