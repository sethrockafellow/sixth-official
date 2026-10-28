import json
import bisect
import math

import numpy as np

from .schema import EventAdapter
from .metrics import xg_for_shot
from . import formations as F

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
MATCH_S = 5400
DEFAULT_SEED = 42
BOX_DEPTH_M = 16.5
BOX_Y = (13.84, 54.16)
TOP_SPEED_MPS = 9.5      # a fast sprint, the same for every player and official; Premier League peaks: 9.4 to 9.8 m/s
THROUGH_FROM_M = 55.0    # a through ball is tried only from this far up the pitch (from the passer's own goal)
THROUGH_TO_M = 78.0      # and no further, so there is space behind the defence to play into
P_THROUGH = 0.045        # tuned 2026-10-25: about 10 through balls and 3 offsides a match
HALFWAY_M = 52.5
# Pass model (2026-10-25), calibrated to Premier League 2024/25 per-match averages, both teams:
#   893.5 passes, 83.7% completed; long passes (32 m or more, crosses not counted) 10.5% of
#   passes; 22.4 open-play crosses, 21.7% completed. Sources: Opta, via premierleague.com and
#   theanalyst.com (docs/REALISM.md). Long-pass completion has no published league figure: 52%
#   here is an estimate that, with the published figures, gives the 83.7% overall.
LONG_PASS_M = 32.0
STEP_S = (1.3, 6.2)        # seconds between events: sets the number of passes (about 893)
P_LONG = 0.135             # share of passes (not crosses) played long, before the zone weighting
P_BACK = {"own": 0.10, "middle": 0.18, "final": 0.32}   # chance a ground pass is played back, by zone
ZONE_COMPLETE = {"own": 1.03, "middle": 1.0, "final": 0.88}   # passes near goal fail more often
PASS_SPREAD = 0.95         # radians: how far ground passes turn from straight at goal
P_CROSS = 0.57             # chance that a pass from a wide position in the final third is a cross
COMPLETE = {"short": 0.935, "medium": 0.89, "long": 0.53, "cross": 0.217}
P_FOUL = 0.015             # tuned with STEP_S: about 21 fouls a match (was 128)
P_SHOT_BOX = 0.125        # chance of a shot per event with the ball in the box
P_SHOT_EDGE = 0.03        # and from the rest of the final 35 m
P_PENALTY = 0.03           # share of shots in the box that are penalties: about 0.3 a match
SWAY_AMP, SWAY_FREQ = 0.8, 2.2   # each player's own movement around his place in the shape
SHAPE_BLEND = 0.15               # share of the way to the new shape each second (about 6 s in all)
DRIFT_M = 3.0                    # each player's slow drift from his slot (minutes, not seconds)
CHASE_PUSH_M = 4.0               # how far a team pushes up when chasing, or drops when protecting a lead
JOG_M, JOG_SPEEDUP = 3.5, 3.0     # and a quicker one on top, so players cover realistic distances
LINE_JOG = (1.15, 1.3, 0.8)        # that movement for defenders, midfielders, forwards
RECOVERY_GAP_S = 45.0             # one recovery sprint per player at most every 45 s
RUN_SETUP_S = 6          # seconds a through-ball runner has to get onto the defender's shoulder

def other_team(team):
    return "away" if team == "home" else "home"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def make_rosters():
    out = {}
    for team, prefix in (("home", "h"), ("away", "a")):
        out[team] = [f"{prefix}{i:02d}" for i in range(1, 12)]
    return out


def base_pos(team, k, shape, has_ball):
    """Player k's place with the ball at halfway: the keeper, or a slot of the formation as the
    team plays it with or without the ball (sixth/formations.py)."""
    if k == 0:
        return (5.0, 34.0) if team == "home" else (PITCH_LENGTH_M - 5.0, 34.0)
    return F.slot_xy(team, *F.played_shape(shape, has_ball)[k - 1])


def shape_at(schedule, team, t):
    """The formation `team` is set up in at time t."""
    name = schedule[team][0]["formation"]
    for change in schedule[team]:
        if change["from_s"] <= t:
            name = change["formation"]
    return name


def formation_spot(team, k, ball_x, ball_y, has_ball, shape):
    """Where player k of `team` stands for this ball position: the shape the tracking uses."""
    ox, oy = base_pos(team, k, shape, has_ball)
    home = team == "home"
    if k == 0:
        return ox + (ball_x - 52.5) * 0.1, 34.0 + (ball_y - 34.0) * 0.25
    base_depth = ox if home else PITCH_LENGTH_M - ox
    ball_depth = ball_x if home else PITCH_LENGTH_M - ball_x
    depth = clamp(base_depth + (ball_depth - 52.5) * 0.42 + (5.0 if has_ball else -3.0), 6.0 + 0.25 * base_depth, 101.0)
    x = depth if home else PITCH_LENGTH_M - depth
    return x, 34.0 + (oy - 34.0) * (1.0 if has_ball else 0.85) + (ball_y - 34.0) * 0.3


def nearest_player(rosters, team, x, y, ball_x, ball_y, has_ball, exclude=(), keeper=False, shape="4-4-2"):
    """The player of `team` whose spot in the shape is nearest (x, y)."""
    best, best_d = None, 1e9
    for k, pid in enumerate(rosters[team]):
        if pid in exclude or (k == 0 and not keeper):
            continue
        sx, sy = formation_spot(team, k, ball_x, ball_y, has_ball, shape)
        d = math.hypot(sx - x, sy - y)
        if d < best_d:
            best, best_d = pid, d
    return best


def pass_kind(length):
    return "short" if length < 15.0 else ("medium" if length < LONG_PASS_M else "long")


def shot_outcome_for(xg, rng):
    r = rng.random()
    if r < xg:
        return "goal"
    r2 = rng.random()
    if r2 < 0.45:
        return "saved"
    if r2 < 0.75:
        return "off_target"
    if r2 < 0.90:
        return "blocked"
    return "woodwork"


def build_events(rng, rosters, seed=0, real=None):
    """The event log: a synthetic match that copies one real box score (sixth/sim.py)."""
    from .history import match_for_seed
    from .sim import Sim
    real = real or match_for_seed(seed)
    schedule = {tm: [{"from_s": 0.0, "formation": F.setup_for(seed, tm), "why": "set-up"}] for tm in ("home", "away")}
    sim = Sim(rng, rosters, seed, real, schedule, shape_at, formation_spot)
    events, score = sim.run()
    return events, score, schedule, sorted(sim.off), real


def next_team(ev, team):
    """The team on the ball after event ev, when `team` had it before."""
    t = ev["type"]
    tid = ev["team_id"]
    if t == "pass" and ev["outcome"] == "failure":
        return other_team(team)
    if t == "carry" and ev["outcome"] == "failure":
        return other_team(team)
    if t == "recovery" and tid != team:
        return tid
    if t == "shot":
        return other_team(tid)
    if t == "save":
        return tid
    if t == "foul" and not ev["advantage_played"]:
        return other_team(tid)
    if t == "offside":
        return other_team(tid)
    if t in ("duel", "restart", "clearance"):     # v2: the duel winner, the restarting side, the clearer
        return tid
    return team


def assign_possession(events):
    poss = 1
    team = "home"
    for ev in events:
        new = next_team(ev, team)
        if new != team:
            poss += 1
            team = new
        ev["possession_id"] = poss


OFFICIALS = (("ref", "referee"), ("ar1", "assistant_referee"), ("ar2", "assistant_referee"),
             ("fourth", "fourth_official"))
REF_DIAGONAL = ((16.0, 58.0), (89.0, 10.0))   # the referee's corner-to-corner diagonal
AR1_Y, AR2_Y, FOURTH_Y = -1.2, 69.2, 71.2      # outside the touchlines


def depth_from_goal(x, team):
    """Distance from `team`'s own goal line (home defends x = 0)."""
    return x if team == "home" else PITCH_LENGTH_M - x


def offside_line(defending, xs, ball_x):
    """The offside line against `defending`, as a depth from the defenders' own goal line.

    Law 11: an attacker is in an offside position when he is in the opponents' half and nearer
    to their goal line than both the ball and the second-last opponent (the keeper is usually the
    last). Level is onside. So the line is the nearer of the second-last defender and the ball,
    and never past halfway. An attacker whose depth is smaller than the line is offside.
    xs: the x of every player of the defending team, keeper included.
    """
    depths = sorted(depth_from_goal(x, defending) for x in xs)
    return min(depths[1], depth_from_goal(ball_x, defending), HALFWAY_M)


def referee_target(bx, by):
    """The referee works along his diagonal, near the play but at least 9 m from the ball."""
    (x0, y0), (x1, y1) = REF_DIAGONAL
    vx, vy = x1 - x0, y1 - y0
    u = clamp(((bx - x0) * vx + (by - y0) * vy) / (vx * vx + vy * vy), 0.03, 0.97)
    qx, qy = x0 + u * vx, y0 + u * vy
    tx, ty = qx + (bx - qx) * 0.25, qy + (by - qy) * 0.25
    d = math.hypot(tx - bx, ty - by)
    if d < 9.0:
        if d < 1e-6:
            tx, ty = bx - 9.0, by
        else:
            tx, ty = bx + (tx - bx) * 9.0 / d, by + (ty - by) * 9.0 / d
    return [clamp(tx, 1.0, 104.0), clamp(ty, 1.0, 67.0)]


# Speed limits (2026-10-25, v2): Premier League players run above 5.5 m/s (19.8 km/h) for only
# about 700 to 1,000 m a match and sprint (above 7 m/s, 25.2 km/h) for about 150 to 200 m. So only players doing something
# go fast: the man on the ball, the man closing him down and the receiver up to CAP_BUSY, a runner
# timing a through ball up to the top speed; everyone else moves at most CAP_SHAPE.
# In km/h: CAP_SHAPE 18.7, CAP_BACK 21.6, CAP_BUSY 24.8, CAP_REF 19.6, CAP_BUSY_FORWARD 20.5.
CAP_SHAPE, CAP_BACK, CAP_BUSY, CAP_REF = 5.2, 6.0, 6.9, 5.45
CAP_BUSY_FORWARD = 5.7


def _step(prev_xy, target, k, cap=TOP_SPEED_MPS):
    """Run toward the target: close part k of the gap, never faster than the cap."""
    if prev_xy is None:
        return [target[0], target[1]]
    px, py = prev_xy
    dx, dy = (target[0] - px) * k, (target[1] - py) * k
    s = math.hypot(dx, dy)
    cap = min(cap, TOP_SPEED_MPS)
    if s > cap:
        dx, dy = dx * cap / s, dy * cap / s
    return [px + dx, py + dy]


def _on_pitch(xy):
    return [clamp(xy[0], 0.5, 104.5), clamp(xy[1], 0.5, 67.5)]


def _lean(event_id, offside):
    """A margin in metres: 0.4 to 2.5 offside, 0.3 to 2.0 onside, fixed for each event."""
    u = ((int(event_id[1:]) * 2654435761) % 4294967296) / 4294967296.0
    return 0.4 + 2.1 * u if offside else 0.3 + 1.7 * u


def _settle_decision(tb, new, prev, rosters, defending, ball_x):
    """Make the receiver onside or offside at the pass, as the events say, within the speed limit.

    The runner has had RUN_SETUP_S seconds to set up, so this is usually already true. If not,
    move the runner, then the second-last defender, as far as the top speed allows this second.
    """
    r = tb["receiver"]
    want_offside = tb["offside"]

    def status():
        line = offside_line(defending, [new[p][0] for p in rosters[defending]], ball_x)
        return depth_from_goal(new[r][0], defending) - line, line

    def nudge(pid, toward_depth):
        px, py = prev.get(pid, new[pid])
        goal_x = toward_depth if defending == "home" else PITCH_LENGTH_M - toward_depth
        x = clamp(goal_x, 0.5, 104.5)
        room = math.sqrt(max(0.0, TOP_SPEED_MPS ** 2 - (new[pid][1] - py) ** 2))
        new[pid][0] = clamp(x, px - room, px + room)

    def settled(margin):            # at least 20 cm clear, so rounding to centimetres cannot flip it
        return margin <= -0.2 if want_offside else margin >= 0.2

    margin, line = status()
    if settled(margin):
        return
    nudge(r, line - 0.6 if want_offside else line + 0.3)
    margin, line = status()
    if settled(margin):
        return
    runner = depth_from_goal(new[r][0], defending)
    if want_offside:
        # Step the line up past the runner: every outfield defender behind him moves up.
        for p in rosters[defending][1:]:
            if depth_from_goal(new[p][0], defending) < runner + 0.6:
                nudge(p, runner + 0.6)
    else:
        # Play him on: the nearest defender drops just behind him.
        nearest = min(rosters[defending][1:], key=lambda p: abs(depth_from_goal(new[p][0], defending) - runner))
        nudge(nearest, runner - 0.3)


FLIGHT_SPEED = {"ground": 13.0, "low": 16.0, "high": 19.0}   # m/s along the ground (as sixth/sim.py)


def flight_time(length, height):
    return max(0.4, length / FLIGHT_SPEED.get(height or "ground", 13.0))


def ball_path(evs):
    """Where the ball is, as (time, x, y) anchors, and its flights in the air.

    A pass or clearance reaches its end point after its flight time. A goal goes into the net.
    During a dead ball the ball is carried to the restart spot. A flight is
    (start, end, peak height m, height at the end m): a lofted ball rises and falls in a
    parabola; a cross or corner met by a header ends at head height (2.2 m).
    """
    anchors, flights = [], []
    times = [e["match_clock_s"] for e in evs]
    for i, e in enumerate(evs):
        t = e["match_clock_s"]
        nxt = times[i + 1] if i + 1 < len(evs) else t + 2.0
        anchors.append((t, e["x_m"], e["y_m"]))
        ex, ey = e.get("end_x_m"), e.get("end_y_m")
        if ex is not None and ey is not None:
            length = math.hypot(ex - e["x_m"], ey - e["y_m"])
            h = e.get("height") or ("high" if e["type"] == "clearance" else "ground")
            t_end = t + min(flight_time(length, h), 0.85 * max(0.2, nxt - t))
            anchors.append((t_end, ex, ey))
            if h != "ground":
                u = ((int(e["event_id"][1:]) * 2654435761) % 4294967296) / 4294967296.0
                if h == "low":
                    peak = 1.0 + 1.5 * u
                elif e.get("pass_type") == "cross" or e.get("restart_type") in ("corner", "free_kick"):
                    peak = 4.0 + 3.5 * u
                elif e.get("restart_type") == "goal_kick" or e["type"] == "clearance":
                    peak = 9.0 + 9.0 * u
                else:
                    peak = clamp(length * 0.2, 4.0, 14.0) + 2.0 * u
                follow = evs[i + 1] if i + 1 < len(evs) else None
                header = follow is not None and ((follow["type"] == "duel" and follow.get("duel_type") == "aerial")
                                                 or follow.get("body_part") == "head")
                flights.append((t, t_end, peak, 2.2 if header else 0.0))
        if e["type"] == "shot":
            gx = 105.0 if e["team_id"] == "home" else 0.0
            u = ((int(e["event_id"][1:]) * 40503) % 65536) / 65536.0
            if e.get("shot_outcome") == "goal" and nxt - t > 1.0:
                anchors.append((t + 0.7, gx, 31.5 + 5.0 * u))
                flights.append((t, t + 0.7, 0.6 + 1.6 * u, 0.4 + 1.6 * u))
            elif e.get("shot_outcome") in ("off_target", "woodwork") and nxt - t > 1.0:
                anchors.append((t + 0.8, gx, 29.0 + 10.0 * u))
                flights.append((t, t + 0.8, 1.0 + 2.5 * u, 2.4 if e.get("shot_outcome") == "woodwork" else 1.5 + 2.0 * u))
        follow = evs[i + 1] if i + 1 < len(evs) else None
        if follow is not None and follow["type"] == "restart" and follow["dead_s"] > 5.0:
            anchors.append((times[i + 1] - 3.0, follow["x_m"], follow["y_m"]))   # placed on the spot
    anchors.sort(key=lambda a: a[0])
    return anchors, sorted(flights)


def ball_touches(evs, order):
    """The ball between the 1 Hz frames, for the viewer (2026-10-27): every touch at its exact time.

    Returns [t, x, y, slot]: the ball is at (x, y) at time t, played or met by player `slot` (his
    index in `order`), or -1 when nobody is on it (a loose ball, into the net, placed for a
    restart). The times follow ball_path (the same flight times, so the ball's height matches):
    a pass or clearance arrives after its flight time; a run with the ball moves at dribbling
    speed (5.5 m/s); a goal goes into the net in 0.7 s. The page moves the ball from touch to
    touch and brings each player to the ball when he plays it or receives it.
    """
    slot = {pid: k for k, pid in enumerate(order)}
    evs = sorted(evs, key=lambda e: e["match_clock_s"])
    times = [e["match_clock_s"] for e in evs]
    keys = []
    for i, e in enumerate(evs):
        t, kind = e["match_clock_s"], e["type"]
        nxt = times[i + 1] if i + 1 < len(evs) else t + 2.0
        if kind in ("pressure", "offside"):           # not a touch: a man closing down, a flag
            continue
        who = -1 if kind == "foul" else slot.get(e.get("player_id"), -1)
        keys.append([t, e["x_m"], e["y_m"], who])
        ex, ey = e.get("end_x_m"), e.get("end_y_m")
        if ex is not None and ey is not None:
            length = math.hypot(ex - e["x_m"], ey - e["y_m"])
            if kind == "carry":
                keys.append([t + min(length / 5.5, 0.95 * max(0.2, nxt - t)), ex, ey, who])
            else:
                h = e.get("height") or ("high" if kind == "clearance" else "ground")
                t_end = t + min(flight_time(length, h), 0.85 * max(0.2, nxt - t))
                rec = slot.get(e.get("receiver_id"), -1) if e.get("outcome") == "success" else -1
                keys.append([t_end, ex, ey, rec])
        if kind == "shot" and nxt - t > 1.0:
            gx = 105.0 if e["team_id"] == "home" else 0.0
            if e.get("shot_outcome") == "goal":
                u = ((int(e["event_id"][1:]) * 40503) % 65536) / 65536.0
                keys.append([t + 0.7, gx, 31.5 + 5.0 * u, -1])
            elif e.get("shot_outcome") in ("off_target", "woodwork"):
                u = ((int(e["event_id"][1:]) * 40503) % 65536) / 65536.0
                keys.append([t + 0.8, gx, 29.0 + 10.0 * u, -1])
        follow = evs[i + 1] if i + 1 < len(evs) else None
        if follow is not None and follow["type"] == "restart" and follow["dead_s"] > 5.0:
            keys.append([times[i + 1] - 3.0, follow["x_m"], follow["y_m"], -1])     # placed on the spot
    keys.sort(key=lambda k: k[0])
    return [[round(t, 2), round(x, 2), round(y, 2), w] for t, x, y, w in keys]


def ball_height(flights, starts, ts):
    """The ball's height in metres at second ts (0 on the ground)."""
    k = bisect.bisect_right(starts, ts) - 1
    while k >= 0 and flights[k][0] >= ts - 25.0:
        t0, t1, peak, z_end = flights[k]
        if t0 <= ts <= t1 and t1 > t0:
            u = (ts - t0) / (t1 - t0)
            return max(0.0, 4.0 * peak * u * (1.0 - u) + z_end * u)
        k -= 1
    return 0.0


def set_piece_positions(tgt, rosters, restart, cur):
    """Where players go while the ball is dead, for the restart about to be taken.

    corner      the attackers send about five players into the box, two to its edge, and keep
                the rest back; every defender comes back into the box
    penalty     everyone but the taker and the keeper stands outside the box
    kick-off    each team in its own half
    other       the normal shape around the ball (the ball is already on the restart spot)
    """
    kind, team = restart["restart_type"], restart["team_id"]
    opp = other_team(team)

    def X(side, depth):                     # depth from side's own goal line
        return depth if side == "home" else PITCH_LENGTH_M - depth
    if kind == "corner":
        for k, pid in enumerate(rosters[team][1:], start=1):
            if pid == restart["player_id"]:
                tgt[pid] = [restart["x_m"], restart["y_m"]]
            elif k >= 5:                    # midfielders and forwards attack the ball
                tgt[pid] = [X(team, 92.0 + (k * 37 % 9)), 25.0 + (k * 53 % 18)]
            elif k in (3, 4):
                tgt[pid] = [X(team, 80.0), 20.0 + 14.0 * (k - 3) + 7.0]
            else:
                tgt[pid] = [X(team, 55.0), 22.0 + 24.0 * (k - 1)]
        for k, pid in enumerate(rosters[opp][1:], start=1):
            tgt[pid] = [X(opp, 3.0 + (k * 29 % 11)), 24.0 + (k * 41 % 20)]
        tgt[rosters[opp][0]] = [X(opp, 1.0), 34.0]
    elif kind == "penalty":
        for side in ("home", "away"):
            for pid in rosters[side][1:]:
                if pid == restart["player_id"]:
                    tgt[pid] = [restart["x_m"] - (1.5 if team == "home" else -1.5), 34.0]
                    continue
                d_att = tgt[pid][0] if team == "home" else PITCH_LENGTH_M - tgt[pid][0]
                if d_att > 86.0:
                    tgt[pid][0] = X(team, 86.0)
        tgt[rosters[opp][0]] = [X(opp, 0.5), 34.0]
    elif kind == "kick_off":
        for side in ("home", "away"):
            for pid in rosters[side]:
                if (tgt[pid][0] > 51.5) if side == "home" else (tgt[pid][0] < 53.5):
                    tgt[pid][0] = 51.5 if side == "home" else 53.5
        tgt[restart["player_id"]] = [52.5, 34.0]


def recover_xy(team, k, shape, ball_x):
    """Where outfield player k of team should be without the ball, for this ball position."""
    ox, oy = base_pos(team, k, shape, False)
    d = 1.0 if team == "home" else -1.0
    base_depth = ox if d > 0 else PITCH_LENGTH_M - ox
    ball_depth = ball_x if d > 0 else PITCH_LENGTH_M - ball_x
    depth = clamp(base_depth + (ball_depth - 52.5) * 0.42 - 3.0, 6.0 + 0.25 * base_depth, 101.0)
    return (depth if d > 0 else PITCH_LENGTH_M - depth), oy


def build_physical(rng, rosters, events, schedule=None):
    """Tracking at 1 Hz for the ball, the 22 players and the 4 officials, consistent with the events.

    Rebuilt 2026-10-24, off-the-ball movement and officials added 2026-10-25. Every second:
      ball       moves between the event locations (start, then the pass or carry end point)
      shape      each team keeps its formation, shifts along the pitch with the ball, pushes up
                 with the ball and drops back without it, and narrows when defending
      back line  the defending back four hold one flat line, so the offside line is real
      forwards   attackers stay level with or behind the offside line (onside) until they run
      runs       before a through ball the receiver waits on the line (just onside, or a little
                 offside when the ball is mistimed), then sprints onto the ball; a second forward
                 makes a decoy run the other way
      actor      the player in the latest event is on the ball (a passer stays where he struck it);
                 the nearest opponent closes down
      look-ahead the player who touches the ball next heads for that spot in the 3 s before
      officials  the referee works his diagonal; each assistant referee runs his touchline level
                 with the offside line in his half; the fourth official stays at halfway
      running    everyone closes part of the gap to the target each second, never faster than one
                 top speed (TOP_SPEED_MPS, 9.5 m/s or 34.2 km/h), and
                 lower caps by role (CAP_SHAPE, CAP_BUSY and the others above)
    Positions are modelled, not tracked. At the second before each through ball, the receiver is
    onside or offside exactly as the events say (tests/test_tracking.py checks it).
    """
    sway = {}
    for team, pids in rosters.items():
        for pid in pids:
            # (2026-10-25) Larger and quicker personal movement: with realistic passing the ball
            # travels less, and players covered only about 7 km. Real outfield players: 10 to 12 km.
            sway[pid] = (float(rng.uniform(0.005, 0.03)) * SWAY_FREQ, float(rng.uniform(0.005, 0.03)) * SWAY_FREQ,
                         float(rng.uniform(0.0, 6.283)), float(rng.uniform(0.0, 6.283)),
                         float(rng.uniform(2.0, 8.0)) * SWAY_AMP, float(rng.uniform(2.0, 6.0)) * SWAY_AMP)
    evs = sorted(events, key=lambda e: e["match_clock_s"])
    times = [e["match_clock_s"] for e in evs]
    anchors, flights = ball_path(evs)
    a_times = [a[0] for a in anchors]
    on_ball, team = [], "home"
    for e in evs:
        team = next_team(e, team)
        on_ball.append(team)
    throughs = []
    for i, e in enumerate(evs):
        if e["type"] == "pass" and e.get("pass_type") == "through":
            off = any(o["type"] == "offside" and o.get("related_event_id") == e["event_id"] for o in evs[i + 1:i + 4])
            nxt = times[i + 1] if i + 1 < len(evs) else e["match_clock_s"] + 2.0
            throughs.append({"t": e["match_clock_s"], "frame": int(math.floor(e["match_clock_s"])),
                             "team": e["team_id"], "passer": e["player_id"], "receiver": e["receiver_id"],
                             "end": (e["end_x_m"], e["end_y_m"]), "offside": off,
                             # How far on or off the runner sets himself, varied per pass (from the
                             # event number, so the random draws for everything else stay the same).
                             "lean": _lean(e["event_id"], off),
                             "arrive": e["match_clock_s"] + max(1.0, 0.8 * (nxt - e["match_clock_s"]))})
    score_at = {"home": [0] * (MATCH_S + 1), "away": [0] * (MATCH_S + 1)}
    for e in evs:
        if e["type"] == "shot" and e.get("shot_outcome") == "goal":
            for k in range(int(math.ceil(e["match_clock_s"])), MATCH_S + 1):
                score_at[e["team_id"]][k] += 1
    # Personal movement by line: midfielders cover the most ground, forwards less (EPL means).
    line_factor = {}
    for team, pids in rosters.items():
        setup = (schedule or {}).get(team, [{"formation": "4-4-2"}])[0]["formation"]
        for k, pid in enumerate(pids[1:], start=1):
            line = F.TEMPLATES[setup][k - 1][0]
            line_factor[pid] = LINE_JOG[0] if line < 0.5 else (LINE_JOG[1] if line < 1.45 else LINE_JOG[2])
    dead_windows = []                                # (from, to, restart event): the ball is dead
    for e in evs:
        if e["type"] == "restart" and e["dead_s"] > 3.0:
            dead_windows.append((e["match_clock_s"] - e["dead_s"] + 2.0, e["match_clock_s"], e))
    dw_starts = [d[0] for d in dead_windows]
    red_at = {e["player_id"]: e["match_clock_s"] for e in evs if e["type"] == "foul" and e.get("card") == "red"}
    f_starts = [f[0] for f in flights]
    last_recovery = {}
    prev, prev_ball, rows = {}, None, []
    phase = {"home": 0.5, "away": 0.5}               # 0 = shaped without the ball, 1 = with it
    for ts in range(MATCH_S + 1):
        j = bisect.bisect_right(a_times, ts) - 1
        if j < 0:
            bx_, by_ = 52.5, 34.0
        elif j + 1 < len(anchors):
            (t0, x0, y0), (t1, x1, y1) = anchors[j], anchors[j + 1]
            f = 0.0 if t1 <= t0 else min(1.0, (ts - t0) / (t1 - t0))
            bx_, by_ = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        else:
            bx_, by_ = anchors[j][1], anchors[j][2]
        bx_, by_ = clamp(bx_, 0.0, 105.0), clamp(by_, 0.0, 68.0)
        i = bisect.bisect_right(times, ts) - 1
        ev = evs[i] if i >= 0 else None
        poss = on_ball[i] if i >= 0 else "home"
        # The through ball in play now: the next one being set up, else the one just played.
        live = [b for b in throughs if b["frame"] - RUN_SETUP_S <= ts <= b["arrive"] + 1]
        ahead = [b for b in live if ts <= b["frame"]]
        tb = min(ahead, key=lambda b: b["frame"]) if ahead else (max(live, key=lambda b: b["frame"]) if live else None)
        attacking = tb["team"] if tb else poss          # around a through ball, the passing side attacks
        defending = other_team(attacking)
        cur = {tm: shape_at(schedule, tm, ts) for tm in ("home", "away")}
        tgt = {}
        for team, pids in rosters.items():
            d = 1.0 if team == "home" else -1.0           # home attacks toward x = 105
            has_ball = team == attacking
            # The shape changes over a few seconds when possession changes, not in one jump.
            phase[team] += ((1.0 if has_ball else 0.0) - phase[team]) * SHAPE_BLEND
            ph = phase[team]
            for k, pid in enumerate(pids):
                fx, fy, phx, phy, ax, ay = sway[pid]
                o_out, o_in = base_pos(team, k, cur[team], False), base_pos(team, k, cur[team], True)
                ox, oy = o_out[0] + (o_in[0] - o_out[0]) * ph, o_out[1] + (o_in[1] - o_out[1]) * ph
                if k == 0:                                 # goalkeeper
                    x = ox + (bx_ - 52.5) * 0.1
                    y = 34.0 + (by_ - 34.0) * 0.25
                else:
                    base_depth = ox if d > 0 else PITCH_LENGTH_M - ox
                    ball_depth = bx_ if d > 0 else PITCH_LENGTH_M - bx_
                    depth = base_depth + (ball_depth - 52.5) * 0.42 + (-3.0 + 8.0 * ph)
                    depth += ax * math.sin(6.283185 * fx * ts + phx)
                    # Drift (2026-10-25): a player's own habits wander over 20 to 50 minutes, and the
                    # game state moves the whole team: behind after the hour it pushes up, ahead
                    # late it sits deeper. So the shape is never exactly the template.
                    depth += DRIFT_M * math.sin(6.283185 * ts / (1200.0 + 27000.0 * fx) + 1.7 * phx)
                    lead = score_at[team][ts] - score_at[other_team(team)][ts]
                    if lead < 0 and ts >= 3600:
                        depth += CHASE_PUSH_M
                    elif lead > 0 and ts >= 4500:
                        depth -= CHASE_PUSH_M
                    depth = clamp(depth, 6.0 + 0.25 * base_depth, 101.0)
                    x = depth if d > 0 else PITCH_LENGTH_M - depth
                    y = 34.0 + (oy - 34.0) * (0.85 + 0.15 * ph) + (by_ - 34.0) * 0.3
                    y += ay * math.sin(6.283185 * fy * ts + phy)
                    y += DRIFT_M * math.cos(6.283185 * ts / (1500.0 + 27000.0 * fy) + 1.3 * phy)
                tgt[pid] = [x, y]
        # The defending back line (four, or five with wing-backs dropped in): one flat line.
        dp = rosters[defending]
        back = [1 + i for i in F.back_line(cur[defending])]
        line_depth = sum(depth_from_goal(tgt[dp[k]][0], defending) for k in back) / len(back)
        for k in back:
            y0 = base_pos(defending, k, cur[defending], False)[1]
            tgt[dp[k]] = [line_depth if defending == "home" else PITCH_LENGTH_M - line_depth,
                          34.0 + (y0 - 34.0) * 0.85 + (by_ - 34.0) * 0.3]
        # Everyone keeps moving: a quicker personal movement on top of the shape (2026-10-25).
        # The back four move mostly sideways, so their line stays flat; keepers move less.
        for team, pids in rosters.items():
            for k, pid in enumerate(pids):
                fx, fy, phx, phy, _, _ = sway[pid]
                amp = JOG_M * (0.6 if k == 0 else line_factor[pid])
                along = 0.25 if (team == defending and k in back) else 1.0
                tgt[pid][0] += amp * along * math.sin(6.283185 * fx * JOG_SPEEDUP * ts + phy)
                tgt[pid][1] += amp * math.cos(6.283185 * fy * JOG_SPEEDUP * ts + phx)
        actor = None
        if ev is not None and ts - ev["match_clock_s"] < 3.0:
            actor = ev.get("player_id")
            if actor in tgt:
                # A player who kicks the ball away (a pass, a clearance, a shot) stays where he struck
                # it for a moment and does not run after it (2026-10-27: before, every passer chased
                # his own pass for up to 3 s). A player who keeps the ball (a run with it, a tackle
                # won, a recovery, a restart) stays on it.
                if ev["type"] in ("pass", "clearance", "shot") and ts > ev["match_clock_s"]:
                    tgt[actor] = [ev["x_m"], ev["y_m"]] if ts - ev["match_clock_s"] < 1.5 else tgt[actor]
                else:
                    tgt[actor] = [bx_, by_]
            rec = ev.get("receiver_id")
            if rec in tgt and ev.get("end_x_m") is not None and ev["outcome"] == "success" \
                    and not (tb and rec == tb["receiver"]):
                nxt = times[i + 1] if i + 1 < len(evs) else ev["match_clock_s"] + 2.0
                f = min(1.0, 0.5 + 0.5 * (ts - ev["match_clock_s"]) / max(0.2, nxt - ev["match_clock_s"]))
                tgt[rec] = [tgt[rec][0] + (ev["end_x_m"] - tgt[rec][0]) * f, tgt[rec][1] + (ev["end_y_m"] - tgt[rec][1]) * f]
        if tb and tb["frame"] - 2 <= ts <= tb["frame"]:
            tgt[tb["passer"]] = [bx_, by_]               # the passer is on the ball as he plays it
        near = min((p for p in rosters[defending][1:] if not (p in red_at and ts >= red_at[p])),
                   key=lambda p: math.hypot(tgt[p][0] - bx_, tgt[p][1] - by_))
        if math.hypot(tgt[near][0] - bx_, tgt[near][1] - by_) < 20.0:
            tgt[near] = [tgt[near][0] + (bx_ - tgt[near][0]) * 0.55, tgt[near][1] + (by_ - tgt[near][1]) * 0.55]
        k_dw = bisect.bisect_right(dw_starts, ts) - 1
        if k_dw >= 0 and ts <= dead_windows[k_dw][1]:
            set_piece_positions(tgt, rosters, dead_windows[k_dw][2], cur)
            actor = None
        chaser = set()
        # Recovery runs: just after the ball is lost, the two players furthest from their place
        # without the ball sprint back (the source of most sprints by defenders and midfielders).
        if i >= 1 and on_ball[i] != on_ball[i - 1] and ts - ev["match_clock_s"] < 3.0:
            lost = on_ball[i - 1]
            far = sorted(((math.hypot(prev[p_][0] - recover_xy(lost, k_, cur[lost], bx_)[0],
                                      prev[p_][1] - recover_xy(lost, k_, cur[lost], bx_)[1]), p_, k_)
                          for k_, p_ in enumerate(rosters[lost])
                          if k_ > 0 and p_ in prev and line_factor[p_] != LINE_JOG[2]), reverse=True)[:1]
            for gap, p_, k_ in far:
                if gap > 20.0 and ts - last_recovery.get(p_, -1e9) >= RECOVERY_GAP_S:
                    last_recovery[p_] = ts
                    chaser.add(p_)
                    tgt[p_] = list(recover_xy(lost, k_, cur[lost], bx_))
        for pid, tr in red_at.items():                  # sent off: he walks to the nearest touchline
            if ts >= tr and pid in prev:
                tgt[pid] = [prev[pid][0], 0.0 if prev[pid][1] < 34.0 else 68.0]
        # Look ahead (2026-10-27): the player who will touch the ball next (wins a 50-50, picks up a
        # loose ball, intercepts, saves) heads for that spot in the 3 s before, so the tracking
        # meets the events and nobody plays a ball from 20 m away.
        ahead = set()
        if not (k_dw >= 0 and ts <= dead_windows[k_dw][1]):
            j_ = i + 1
            while j_ < len(evs) and times[j_] <= ts + 3.0:
                e2 = evs[j_]
                p2 = e2.get("player_id")
                if e2["type"] in ("recovery", "duel", "save", "pass", "carry", "clearance", "shot") and p2 in tgt \
                        and not (p2 in red_at and ts >= red_at[p2]) and not (tb and p2 == tb["receiver"]) and p2 != actor:
                    f2 = max(0.35, 1.0 - (times[j_] - ts) / 3.0)
                    tgt[p2] = [tgt[p2][0] + (e2["x_m"] - tgt[p2][0]) * f2, tgt[p2][1] + (e2["y_m"] - tgt[p2][1]) * f2]
                    # He runs at a busy player's pace; only a long way off (over 15 m) does he sprint.
                    ahead.add(p2)
                    break                                   # only the next touch
                j_ += 1
        busy = {p for p in (actor, near, tb["passer"] if tb else None) if p} | ahead
        # A long ball or a clearance: whoever goes for it may sprint flat out.
        if ev is not None and ts - ev["match_clock_s"] < 2.0 and (ev.get("height") == "high" or ev["type"] == "clearance"):
            chaser.add(ev.get("receiver_id"))
        nxt_ev = evs[i + 1] if ev is not None and i + 1 < len(evs) else None
        if nxt_ev is not None and nxt_ev["type"] == "duel" and nxt_ev["match_clock_s"] - ts <= 2.0:
            for p_ in (nxt_ev["player_id"], nxt_ev["opponent_id"]):         # both race for a 50-50
                chaser.add(p_)
                if p_ in tgt:
                    tgt[p_] = [nxt_ev["x_m"], nxt_ev["y_m"]]
        if tb and tb["frame"] < ts <= tb["arrive"] + 1:                     # a defender chases the runner
            rx_, ry_ = prev.get(tb["receiver"], (bx_, by_))
            cd = min((p for p in rosters[defending][1:] if p in prev),
                     key=lambda p: math.hypot(prev[p][0] - rx_, prev[p][1] - ry_), default=None)
            if cd:
                chaser.add(cd)
                tgt[cd] = [rx_, ry_]
        if ev is not None and ev.get("receiver_id"):
            busy.add(ev["receiver_id"])
        # Defending side moves first; the back four move together.
        new = {}
        for k, pid in enumerate(rosters[defending]):
            kk = 0.6 if pid in busy else (0.5 if k in back else 0.35)
            cap = CAP_BUSY if pid in busy else (CAP_BACK if k in back else CAP_SHAPE)
            if k == 0:
                cap = CAP_SHAPE
            elif pid in chaser:
                cap = TOP_SPEED_MPS
                kk = max(kk, 0.6)
            new[pid] = _step(prev.get(pid), _on_pitch(tgt[pid]), kk, cap)
        on = {p for side in rosters.values() for p in side if not (p in red_at and ts >= red_at[p])}
        line = offside_line(defending, [new[p][0] for p in rosters[defending] if p in on], bx_)

        def to_x(depth):
            return depth if defending == "home" else PITCH_LENGTH_M - depth
        ap = rosters[attacking]
        runners = [1 + i for i in F.front_runners(cur[attacking])]
        pinned, decoy_id = {}, None
        if tb:
            r = tb["receiver"]
            if ts <= tb["frame"]:
                want = line - tb["lean"] if tb["offside"] else line + tb["lean"]
                pinned[r] = [to_x(want), tgt[r][1] + (tb["end"][1] - tgt[r][1]) * 0.4]
            else:
                pinned[r] = [tb["end"][0], tb["end"][1]]
            decoy = next((ap[k] for k in runners if ap[k] not in (r, actor, tb["passer"])), None)
            decoy_id = decoy
            if decoy:
                if ts <= tb["frame"]:
                    pinned[decoy] = [to_x(line + 1.5), tgt[decoy][1]]
                else:
                    pinned[decoy] = [to_x(max(line - 10.0, 8.0)), clamp(68.0 - tb["end"][1], 6.0, 62.0)]
        for k in runners:                                # the rest stay onside, on the defender's shoulder
            pid = ap[k]
            if pid in pinned or pid == actor:
                continue
            if depth_from_goal(tgt[pid][0], defending) < line + 0.8:
                tgt[pid][0] = to_x(line + 0.8)
        for pid in ap:
            kk = 1.0 if pid in pinned else (0.6 if pid in busy else 0.35)
            busy_cap = CAP_BUSY_FORWARD if line_factor.get(pid) == LINE_JOG[2] else CAP_BUSY
            cap = (TOP_SPEED_MPS if ts >= tb["frame"] - 2 else CAP_SHAPE) if pid in pinned else (busy_cap if pid in busy else CAP_SHAPE)
            if pid == ap[0]:
                cap = CAP_SHAPE
            elif pid in chaser:
                cap = TOP_SPEED_MPS
                kk = max(kk, 0.6)
            elif pid == decoy_id and ts <= tb["frame"]:
                cap = CAP_SHAPE
            new[pid] = _step(prev.get(pid), _on_pitch(pinned.get(pid, tgt[pid])), kk, cap)
        if tb and ts == tb["frame"]:                     # the decision the events record, at the pass
            _settle_decision(tb, new, prev, rosters, defending, bx_)
        # Officials. Each assistant referee is level with the offside line in his half.
        l_home = offside_line("home", [new[p][0] for p in rosters["home"] if p in on], bx_)
        l_away = offside_line("away", [new[p][0] for p in rosters["away"] if p in on], bx_)
        rt = referee_target(bx_, by_)
        rt = [clamp(rt[0] + 5.0 * math.sin(ts / 7.0), 1.0, 104.0), clamp(rt[1] + 4.0 * math.cos(ts / 9.0), 1.0, 67.0)]
        o_tgt = {"ref": rt, "ar1": [l_home, AR1_Y],
                 "ar2": [PITCH_LENGTH_M - l_away, AR2_Y],
                 "fourth": [HALFWAY_M + 2.5 * math.sin(0.004 * ts), FOURTH_Y]}
        o_k = {"ref": 0.3, "ar1": 0.7, "ar2": 0.7, "fourth": 0.2}
        ball_fast = prev_ball is not None and math.hypot(bx_ - prev_ball[0], by_ - prev_ball[1]) > 15.0
        o_cap = {"ref": 7.0 if ball_fast else CAP_REF, "ar1": CAP_BUSY, "ar2": CAP_BUSY, "fourth": 2.0}
        for oid, _ in OFFICIALS:
            new[oid] = _step(prev.get(oid), o_tgt[oid], o_k[oid], o_cap[oid])
        speed = 0.0 if prev_ball is None else math.hypot(bx_ - prev_ball[0], by_ - prev_ball[1])
        prev_ball = (bx_, by_)
        ball = {"x_m": round(bx_, 2), "y_m": round(by_, 2), "speed_mps": round(min(speed, 35.0), 2),
                "z_m": round(ball_height(flights, f_starts, ts), 2)}
        plist, olist = [], []
        for team, pids in rosters.items():
            for pid in pids:
                x, y = new[pid]
                sp = 0.0 if pid not in prev else math.hypot(x - prev[pid][0], y - prev[pid][1])
                prev[pid] = (x, y)
                plist.append({"player_id": pid, "team_id": team, "x_m": round(x, 2), "y_m": round(y, 2),
                              "speed_mps": round(min(sp, TOP_SPEED_MPS), 2),
                              "on_pitch": not (pid in red_at and ts >= red_at[pid])})
        for oid, role in OFFICIALS:
            x, y = new[oid]
            sp = 0.0 if oid not in prev else math.hypot(x - prev[oid][0], y - prev[oid][1])
            prev[oid] = (x, y)
            olist.append({"official_id": oid, "role": role, "x_m": round(x, 2), "y_m": round(y, 2),
                          "speed_mps": round(sp, 2)})
        rows.append({"physical_id": "p_%d" % ts, "match_clock_s": ts, "ball": ball, "players": plist,
                     "officials": olist})
    return rows


def generate_match(seed=DEFAULT_SEED):
    rng = np.random.default_rng(seed)
    team_rosters = make_rosters()
    events, score, schedule, sent_off, real = build_events(rng, team_rosters, seed)
    events.sort(key=lambda e: e["match_clock_s"])      # stable: same-second events keep their order
    for i, ev in enumerate(events):
        ev["event_id"] = f"e{i + 1:06d}"
    last_shot = last_through = None
    for ev in events:
        if ev["type"] == "shot":
            last_shot = ev["event_id"]
        elif ev["type"] == "save" and ev["related_event_id"] == "__shot__":
            ev["related_event_id"] = last_shot
        if ev["type"] == "pass" and ev.get("pass_type") == "through":
            last_through = ev["event_id"]
        elif ev["type"] == "offside" and ev["related_event_id"] == "__pass__":
            ev["related_event_id"] = last_through      # the through ball the runner was offside for
    assign_possession(events)
    validated = [EventAdapter.validate_python(ev).model_dump() for ev in events]
    physical = build_physical(rng, team_rosters, validated, schedule)
    return {"match_id": f"demo-{seed}", "seed": seed,
            "final_score": score, "event_log": validated, "physical_log": physical,
            "formations": schedule, "history": real}


def match_bytes(seed=DEFAULT_SEED):
    return json.dumps(generate_match(seed), sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def save_match(path, seed=DEFAULT_SEED):
    with open(path, "wb") as f:
        f.write(match_bytes(seed))


if __name__ == "__main__":
    save_match(f"match_seed_{DEFAULT_SEED}.json", DEFAULT_SEED)
