"""insights.py: what to show while the ball is dead.

When the ball goes out, play stops for 15 to 75 seconds (Premier League averages by restart).
That pause gets a card with two things, both computed from data up to the moment the ball
went out (never later):

  what if    for a corner, a penalty or a free kick in shooting range: how often such a set
             piece becomes a goal, and the win chance now and if this one goes in
             (sixth/winmodel.py)
  finding    the biggest change in the last 5 minutes compared with the match before them,
             with an exact test of how often a change that size happens by chance

The finding tests 4 things for each team (8 tests at each pause):
  duels       share of duels won                       exact binomial test
  passing     share of passes completed                exact binomial test
  territory   share of final-third passes (field tilt) exact binomial test
  shots       shots in the 5 minutes                   exact Poisson test, at the earlier rate
The p-value is multiplied by the number of tests (Bonferroni), so 8 looks do not make luck
look like a pattern. "Unusual" means that adjusted p-value is below 0.05.

"""
from __future__ import annotations

import math

WINDOW_S = 300.0
MIN_BEFORE_S = 600.0
DEAD_CARD_S = 10.0
METRICS = ("duels", "passing", "territory", "shots")
# How often a set piece becomes a goal (approximate public figures; marked as estimates in
# docs/METRICS.md): about 3 in 100 corners, 6 in 100 direct free kicks, 78 in 100 penalties.
SET_PIECE_GOAL = {"corner": 0.03, "free_kick": 0.06, "penalty": 0.78}


def binom_two_sided(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial test: the chance of a result at least this unlikely."""
    if n == 0:
        return 1.0
    p = min(max(p, 1e-9), 1 - 1e-9)
    pmf = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    cut = pmf[k] * (1 + 1e-7)
    return min(1.0, sum(x for x in pmf if x <= cut))


def poisson_two_sided(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    hi = max(k, int(lam * 4 + 20))
    pmf = [math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(hi + 1)]
    cut = pmf[k] * (1 + 1e-7)
    return min(1.0, sum(x for x in pmf if x <= cut))


def _final_third(e) -> bool:
    return e.x_m >= 70.0 if e.team_id == "home" else e.x_m <= 35.0


def _counts(events, team, lo, hi):
    """Raw counts for one team over lo < t <= hi."""
    c = {"duels_won": 0, "duels": 0, "passes_ok": 0, "passes": 0, "ft_own": 0, "ft_all": 0, "shots": 0}
    for e in events:
        if not (lo < e.match_clock_s <= hi):
            continue
        if e.type == "duel":
            c["duels"] += 1
            c["duels_won"] += e.team_id == team
        elif e.type == "pass":
            if e.team_id == team:
                c["passes"] += 1
                c["passes_ok"] += e.outcome == "success"
            if _final_third(e):
                c["ft_all"] += 1
                c["ft_own"] += e.team_id == team
        elif e.type == "shot" and e.team_id == team:
            c["shots"] += 1
    return c


def findings_at(E, t: float, anchor: str) -> list[dict]:
    """Every tested change at time t, most surprising first. anchor names them (an event id)."""
    if t < MIN_BEFORE_S:
        return []
    out = []
    for team in ("home", "away"):
        now = _counts(E.events, team, t - WINDOW_S, t)
        before = _counts(E.events, team, -1.0, t - WINDOW_S)
        span_before = max(1.0, t - WINDOW_S)
        tests = {
            "duels": ("duels_won", "duels"),
            "passing": ("passes_ok", "passes"),
            "territory": ("ft_own", "ft_all"),
        }
        for metric, (kk, nn) in tests.items():
            k, n, k0, n0 = now[kk], now[nn], before[kk], before[nn]
            if n < 6 or n0 < 20:
                continue
            p0 = k0 / n0
            out.append({"metric": metric, "team": team, "now_k": k, "now_n": n, "now_rate": round(k / n, 4),
                        "before_k": k0, "before_n": n0, "before_rate": round(p0, 4),
                        "p": binom_two_sided(k, n, p0)})
        k, k0 = now["shots"], before["shots"]
        lam = k0 / span_before * WINDOW_S
        if t >= 900.0 and k0 >= 3:
            out.append({"metric": "shots", "team": team, "now_k": k, "now_n": None, "now_rate": None,
                        "before_k": k0, "before_n": None, "before_rate": None,
                        "expected": round(lam, 2), "p": poisson_two_sided(k, lam)})
    m = 2 * len(METRICS)
    for f in out:
        f["id"] = f"f_{anchor}_{f['team']}_{f['metric']}"
        f["t"] = round(t, 1)
        f["window_min"] = int(WINDOW_S // 60)
        f["p"] = round(f["p"], 6)
        f["p_adj"] = round(min(1.0, f["p"] * m), 6)
        f["significant"] = f["p_adj"] < 0.05
        up = (f["now_rate"] > f["before_rate"]) if f["now_rate"] is not None else (f["now_k"] > f["expected"])
        f["direction"] = "up" if up else "down"
    out.sort(key=lambda f: f["p"])
    return out


def _score_and_xg(E, t):
    s = E.state_at(t)
    ms = s.match_state
    reds = {"home": 0, "away": 0}
    for e in E.events:
        if e.match_clock_s > t:
            break
        if e.type == "foul" and e.card == "red":
            reds[e.team_id] += 1
    return ms, s.home.xg_total, s.away.xg_total, reds


def deadball_cards(E) -> tuple[list[dict], dict]:
    """A card for every restart after a pause of DEAD_CARD_S or more, and every finding they use."""
    from .winmodel import default as win_model
    M = win_model()
    cards, store = [], {}
    for e in E.events:
        if e.type != "restart" or e.dead_s < DEAD_CARD_S or e.restart_type == "kick_off" and e.dead_s < 30:
            continue
        t0 = round(e.match_clock_s - e.dead_s, 1)
        ms, xh, xa, reds = _score_and_xg(E, t0)
        card = {"event_id": e.event_id, "t0": t0, "t1": e.match_clock_s, "dead_s": e.dead_s,
                "restart": e.restart_type, "direct": bool(e.direct), "team": e.team_id,
                "win_now": [round(ms.win_prob_home, 4), round(ms.draw_prob, 4), round(ms.win_prob_away, 4)]}
        kind = "free_kick" if e.restart_type == "free_kick" and e.direct else e.restart_type
        if kind in SET_PIECE_GOAL and (kind != "free_kick" or e.direct):
            sh, sa = ms.score_home + (e.team_id == "home"), ms.score_away + (e.team_id == "away")
            w = M.chances(t0, sh, sa, E.elo[0], E.elo[1], xh, xa, reds["home"], reds["away"])
            card["what_if"] = {"goal_rate": SET_PIECE_GOAL[kind], "win_if_goal": [round(x, 4) for x in w]}
        fs = findings_at(E, t0, e.event_id)
        if fs:
            card["finding"] = fs[0]
            store[fs[0]["id"]] = fs[0]
        cards.append(card)
    return cards, store

