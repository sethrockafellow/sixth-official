"""formations.py: team shapes. The templates the generator plays, and the detector that measures them.

A template is 10 outfield slots, each (line, width) in the team's own frame:
  line   0 = the back line, 1 = midfield, 2 = the front line (in between for holding or
         attacking midfielders)
  width  -1 = the team's left touchline side, +1 = its right, as the team faces the goal it attacks
The roster is in slot order: defenders first, then midfielders, then forwards, each left to right.

The detector (`detect`) takes 10 average positions, centres them, scales each template to the same
spread, assigns players to slots in the cheapest way (the Hungarian method), and reports the mean
distance in metres between each player and his slot. "Players on average 2.6 m from a true 4-4-2."
"""
from __future__ import annotations

import math

LINE_M = 24.0          # metres between lines (back line to midfield) when the ball is at halfway
BACK_LINE_M = 16.0     # depth of the back line from the team's own goal, ball at halfway
HALF_WIDTH_M = 27.0    # width -1..+1 maps to 7 m .. 61 m across the pitch


def _row(line, widths):
    return [(line, w) for w in widths]


TEMPLATES = {
    "4-4-2":   _row(0, [-.75, -.25, .25, .75]) + _row(1, [-.75, -.25, .25, .75]) + _row(2, [-.2, .2]),
    "4-3-3":   _row(0, [-.75, -.25, .25, .75]) + _row(1, [-.4, 0, .4]) + _row(2, [-.7, 0, .7]),
    "4-2-3-1": _row(0, [-.75, -.25, .25, .75]) + _row(.8, [-.25, .25]) + _row(1.5, [-.7, 0, .7]) + _row(2.2, [0]),
    "4-1-4-1": _row(0, [-.75, -.25, .25, .75]) + _row(.7, [0]) + _row(1.4, [-.75, -.25, .25, .75]) + _row(2.2, [0]),
    "4-5-1":   _row(0, [-.75, -.25, .25, .75]) + _row(1, [-.8, -.4, 0, .4, .8]) + _row(2, [0]),
    "4-4-1-1": _row(0, [-.75, -.25, .25, .75]) + _row(1, [-.75, -.25, .25, .75]) + _row(1.6, [0]) + _row(2.2, [0]),
    "3-5-2":   _row(0, [-.5, 0, .5]) + _row(1, [-.9, -.45, 0, .45, .9]) + _row(2, [-.2, .2]),
    "3-4-3":   _row(0, [-.5, 0, .5]) + _row(1, [-.75, -.25, .25, .75]) + _row(2, [-.7, 0, .7]),
    "5-3-2":   _row(0, [-.9, -.45, 0, .45, .9]) + _row(1, [-.4, 0, .4]) + _row(2, [-.2, .2]),
    "5-4-1":   _row(0, [-.9, -.45, 0, .45, .9]) + _row(1, [-.75, -.25, .25, .75]) + _row(2, [0]),
}

# What a team switches to when it chases a game, and the shape it uses to protect a lead.
ATTACKING_SWITCH = {"4-4-2": "4-3-3", "4-3-3": "3-4-3", "4-2-3-1": "4-4-2", "4-1-4-1": "4-3-3",
                    "4-5-1": "4-4-2", "4-4-1-1": "4-4-2", "3-5-2": "3-4-3", "3-4-3": "3-4-3",
                    "5-3-2": "3-5-2", "5-4-1": "4-4-2"}
PROTECT_LEAD = "5-4-1"
# Set-ups the generator picks from (a hash of the seed picks one per team).
SETUPS = ["4-2-3-1", "4-3-3", "4-4-2", "4-3-3", "4-2-3-1", "3-4-3", "4-4-2", "5-3-2", "3-5-2", "4-1-4-1"]


def setup_for(seed: int, team: str) -> str:
    return SETUPS[(seed * 7 + (0 if team == "home" else 3)) % len(SETUPS)]


def played_shape(name: str, has_ball: bool) -> list[tuple[float, float]]:
    """The shape a set-up actually takes, with or without the ball (same slot order).

    With the ball:    full-backs of a back four push up into midfield; wide midfielders of a
                      back three push on.
    Without the ball: wide forwards drop into midfield (a 4-3-3 defends as a 4-5-1); a back
                      three's wide midfielders drop into the back line (a back five).
    """
    slots = TEMPLATES[name]
    n_back = sum(1 for line, _ in slots if line == 0)
    out = []
    for line, w in slots:
        if has_ball:
            if line == 0 and n_back == 4 and abs(w) >= 0.7:
                line = 0.6
            elif n_back == 3 and 0.8 <= line <= 1.2 and abs(w) >= 0.7:
                line += 0.35
        else:
            if 1.4 <= line and abs(w) >= 0.6:       # wide forwards and wide attacking midfielders
                line = 1.0
            elif n_back == 3 and 0.8 <= line <= 1.2 and abs(w) >= 0.7:
                line = 0.05
                w = 0.9 if w > 0 else -0.9
        out.append((line, w))
    return out


def back_line(name: str) -> list[int]:
    """Outfield slot indices (0..9) that hold the back line without the ball."""
    return [i for i, (line, _) in enumerate(played_shape(name, False)) if line < 0.3]


def front_runners(name: str) -> list[int]:
    """Outfield slot indices that run in behind with the ball: the front line, then attacking midfielders."""
    shape = played_shape(name, True)
    order = sorted(range(10), key=lambda i: -shape[i][0])
    top = [i for i in order if shape[i][0] >= 1.4][:3]
    return top if len(top) >= 2 else order[:2]      # always two, so one can run while the other passes


def labels(name: str) -> list[str]:
    """Team-sheet position for each outfield slot of a template (LB, LCB, CDM, LW, ST...)."""
    slots = TEMPLATES[name]
    n_back = sum(1 for line, _ in slots if line == 0)
    rows = {}
    for i, (line, w) in enumerate(slots):
        rows.setdefault(line, []).append((w, i))
    out = [""] * len(slots)
    for line, members in rows.items():
        members.sort()
        n = len(members)
        if line == 0:
            names = {3: ["LCB", "CB", "RCB"], 4: ["LB", "LCB", "RCB", "RB"], 5: ["LWB", "LCB", "CB", "RCB", "RWB"]}[n]
        elif line < 0.95:
            names = {1: ["CDM"], 2: ["LDM", "RDM"]}[n]
        elif line <= 1.2:
            names = {3: ["LCM", "CM", "RCM"], 4: ["LM", "LCM", "RCM", "RM"],
                     5: (["LWB", "LCM", "CM", "RCM", "RWB"] if n_back == 3 else ["LM", "LCM", "CM", "RCM", "RM"])}[n]
        elif line < 1.9:
            names = {1: ["SS" if line >= 1.6 else "CAM"], 3: ["LW", "CAM", "RW"], 4: ["LM", "LCM", "RCM", "RM"]}[n]
        else:
            names = {1: ["ST"], 2: ["LS", "RS"], 3: ["LW", "ST", "RW"]}[n]
        for (w, i), label in zip(members, names):
            out[i] = label
    return out


def team_sheet(match: dict) -> dict:
    """Each player's shirt number and listed position, from his team's set-up formation."""
    from .roster import PLAYERS, SHIRT
    out = {}
    for team, prefix in (("home", "h"), ("away", "a")):
        setup = match["formations"][team][0]["formation"]
        pos = ["GK"] + labels(setup)
        for k in range(11):
            pid = f"{prefix}{k + 1:02d}"
            out[pid] = {"name": PLAYERS.get(pid, pid), "number": SHIRT.get(pid, k + 1), "position": pos[k], "team": team}
    return out


def slot_xy(team: str, line: float, width: float) -> tuple[float, float]:
    """A slot in pitch metres with the ball at halfway (home attacks toward x = 105)."""
    depth = BACK_LINE_M + line * LINE_M
    x = depth if team == "home" else 105.0 - depth
    y = 34.0 + width * HALF_WIDTH_M if team == "home" else 34.0 - width * HALF_WIDTH_M
    return x, y


def to_team_frame(team: str, x: float, y: float) -> tuple[float, float]:
    """(depth from own goal, width to the team's right) in metres."""
    return (x, y - 34.0) if team == "home" else (105.0 - x, 34.0 - y)


def from_team_frame(team: str, depth: float, width: float) -> tuple[float, float]:
    return (depth, 34.0 + width) if team == "home" else (105.0 - depth, 34.0 - width)


# ---------------------------------------------------------------------------- detection
def hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost assignment for a square matrix: result[row] = column. O(n^3)."""
    n = len(cost)
    INF = float("inf")
    u, v = [0.0] * (n + 1), [0.0] * (n + 1)
    p, way = [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [0] * n
    for j in range(1, n + 1):
        result[p[j] - 1] = j - 1
    return result


def _centre(pts):
    md = sum(p[0] for p in pts) / len(pts)
    mw = sum(p[1] for p in pts) / len(pts)
    return [(p[0] - md, p[1] - mw) for p in pts], (md, mw)


def _spread(vals):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) or 1.0


def fit(points: list[tuple[float, float]], name: str):
    """How well 10 points (depth, width in metres, team frame) match a template.

    Returns (mean distance in metres, slots in the team frame aligned to the points, assignment
    with assignment[player] = slot)."""
    P, (md, mw) = _centre(points)
    T = [(line * LINE_M, w * HALF_WIDTH_M) for line, w in TEMPLATES[name]]
    T, _ = _centre(T)
    sd = _spread([p[0] for p in P]) / _spread([t[0] for t in T])
    sw = _spread([p[1] for p in P]) / _spread([t[1] for t in T])
    T = [(t[0] * sd, t[1] * sw) for t in T]
    cost = [[(p[0] - t[0]) ** 2 + (p[1] - t[1]) ** 2 for t in T] for p in P]
    a = hungarian(cost)
    mean = sum(math.sqrt(cost[i][a[i]]) for i in range(len(P))) / len(P)
    slots = [(t[0] + md, t[1] + mw) for t in T]
    return mean, slots, a


def detect(points):
    """Every template, closest first: [(name, mean distance m, slots, assignment), ...]."""
    out = []
    for name in TEMPLATES:
        d, slots, a = fit(points, name)
        out.append((name, d, slots, a))
    return sorted(out, key=lambda r: r[1])


def expected_label(name: str, has_ball: bool) -> str:
    """What the detector should report for a set-up played perfectly, with or without the ball."""
    shape = played_shape(name, has_ball)
    pts = [(line * LINE_M, w * HALF_WIDTH_M) for line, w in shape]
    return detect(pts)[0][0]


# ---------------------------------------------------------------------------- a whole match
ROLL_S = 300          # the live shape is refreshed every 5 minutes


def analyse(match: dict, block_s: int = 900) -> dict:
    """Shape per team, per 15-minute block, without and with the ball.

    For each second in the block where the team does (or does not) have the ball, each outfield
    player's position is taken relative to his team's centre that second; those are averaged and
    put back around the team's average centre. That removes the shift of the whole team with the
    ball, so what is left is the shape."""
    from .generate import next_team
    rows, events = match["physical_log"], match["event_log"]
    times, after, team_on = [], [], "home"
    for e in events:
        team_on = next_team(e, team_on)
        times.append(e["match_clock_s"])
        after.append(team_on)
    import bisect
    poss = [(after[i] if (i := bisect.bisect_right(times, ts) - 1) >= 0 else "home") for ts in range(len(rows))]
    out = {}
    for team in ("home", "away"):
        order = [p["player_id"] for p in rows[0]["players"] if p["team_id"] == team][1:]   # outfield
        def window(b0, b1):
            block = {"from_s": b0, "to_s": b1}
            for state, has in (("out", False), ("in", True)):
                sums = {pid: [0.0, 0.0] for pid in order}
                cen, n = [0.0, 0.0], 0
                for ts in range(b0, block["to_s"]):
                    if (poss[ts] == team) != has:
                        continue
                    by_id = {p["player_id"]: to_team_frame(team, p["x_m"], p["y_m"]) for p in rows[ts]["players"] if p["team_id"] == team}
                    c = [sum(by_id[q][0] for q in order) / 10, sum(by_id[q][1] for q in order) / 10]
                    for pid in order:
                        sums[pid][0] += by_id[pid][0] - c[0]
                        sums[pid][1] += by_id[pid][1] - c[1]
                    cen[0] += c[0]
                    cen[1] += c[1]
                    n += 1
                if n < 60:                                   # under a minute of play: not enough to judge
                    block[state] = None
                    continue
                pts = [(sums[p][0] / n + cen[0] / n, sums[p][1] / n + cen[1] / n) for p in order]
                ranked = detect(pts)
                best, second = ranked[0], ranked[1]
                block[state] = {
                    "seconds": n, "best": best[0], "best_m": round(best[1], 2),
                    "next": second[0], "next_m": round(second[1], 2),
                    "players": [list(map(lambda v: round(v, 1), from_team_frame(team, *p))) for p in pts],
                    "slots": [list(map(lambda v: round(v, 1), from_team_frame(team, *s))) for s in best[2]],
                    "assign": best[3],
                    "all_m": {name: round(d, 2) for name, d, _, _ in ranked},
                }
            return block
        blocks = [window(b0, min(b0 + block_s, len(rows) - 1)) for b0 in range(0, len(rows) - 1, block_s)]
        # Live (2026-10-27): every 5 minutes, the shape over the last 15 minutes (or since kick-off),
        # so the page shows a shape from 5' on instead of waiting for the first full block.
        rolling = [window(max(0, end - block_s), end) for end in range(ROLL_S, len(rows), ROLL_S)]
        out[team] = {"setup": match.get("formations", {}).get(team, []), "players": order, "blocks": blocks,
                     "rolling": rolling}
    return out
