"""sim.py: the event simulator (generator v2, 2026-10-25).

It plays a synthetic match that copies one real Premier League box score (sixth/history.py):
the same goals in each half, shots, shots on target, fouls, corners and cards for each side.
Clubs and players stay fictional. Between those fixed totals, play is simulated:

  in play     passes (ground, long, crosses, through balls), carries, take-ons and tackles,
              50-50s on the ground and in the air, interceptions, clearances, shots and saves
  pressure    an opponent closes the player down before about a quarter of passes; a pass
              under pressure is completed less often
  dead ball   the ball goes out or the referee stops play: throw-in, goal kick, corner, free
              kick, penalty or kick-off. Each restart waits as long as Premier League restarts
              do on average (Opta), so the ball is in play for about 55 to 58 minutes
  totals      "quota control": the chance of a shot, a corner, a foul or a card is scaled by
              how many the real match still has to come in the time left. A team that still owes
              a goal in a half becomes urgent near the end of it, and scores.

Every rate has a source or is marked as an estimate in docs/REALISM.md.
"""
from __future__ import annotations

import math

from . import formations as F
from .metrics import xg_for_shot

L, W = 105.0, 68.0
HALF_S, MATCH_S = 2700.0, 5400.0
BOX_DEPTH, BOX_Y = 16.5, (13.84, 54.16)

# Time. Seconds between on-the-ball actions while the ball is in play (tuned: about 890 passes).
STEP_S = (0.42, 2.0)
# Average restart times, Premier League (Opta, theanalyst.com): throw-in 17.8 s, goal kick 30.4 s,
# corner 36.1 s (2025/26); free kick 33.3 s and direct free kick 74.5 s (2026/27, first five
# matchweeks). Kick-off after a goal and penalty: estimates (celebration, checks).
DEAD_S = {"throw_in": 17.8, "goal_kick": 30.4, "corner": 36.1, "free_kick": 33.3,
          "free_kick_direct": 74.5, "kick_off": 60.0, "penalty": 90.0}
CARD_EXTRA_S = 20.0          # estimate: the booking itself
# League rates per team per match, from the 6,080 real matches (data/history): the quota base.
LEAGUE = {"shots": 12.7, "corners": 5.33, "fouls": 10.83}
# Passing, calibrated to Premier League 2024/25 (893.5 passes, 83.7% completed; docs/REALISM.md).
LONG_PASS_M = 32.0
P_LONG = 0.15
P_BACK = {"own": 0.10, "middle": 0.18, "final": 0.32}
ZONE_COMPLETE = {"own": 1.03, "middle": 1.0, "final": 0.90}
PASS_SPREAD = 0.95
P_CROSS = 0.40
COMPLETE = {"short": 0.945, "medium": 0.89, "long": 0.53, "cross": 0.217}
# Pressure (estimates): share of passes made under pressure, and how much it costs.
P_PRESSURE = 0.22
PRESSURE_MULT = 0.84                  # completion under pressure, relative to the base rate
FREE_MULT = 1.0 / (1 - P_PRESSURE * (1 - PRESSURE_MULT))   # keeps the overall rate at the base
# Through balls and offsides (tuned 2026-10-25: about 10 through balls and 3 offsides a match).
THROUGH_FROM_M, THROUGH_TO_M, P_THROUGH = 55.0, 78.0, 0.045
# Shots: base chance per action in the box and in the rest of the final 35 m (before quotas).
P_SHOT_BOX, P_SHOT_EDGE = 0.15, 0.035
P_FOUL = 0.028
P_PENALTY_FOUL = 0.35        # a foul on an attacker inside the box is a penalty this often
# What happens to a failed pass (estimates, tuned to about 36 throw-ins and 16 goal kicks).
P_OUT = 0.17                 # a failed pass goes out of play this often (0.65 near a touchline)
P_INTERCEPT = 0.20           # otherwise: intercepted cleanly; else picked up loose, or a 50-50
P_CONTEST_LONG = 0.30        # a long ball is challenged in the air this often
P_TACKLE_OUT = 0.15          # a tackle knocks the ball out for a throw-in this often
P_TAKE_ON = 0.22             # a carry beats a man this often (a take-on duel)
TAKE_ON_WIN = 0.55
URGENT_S = 300.0             # a team that owes a goal in a half becomes urgent this long before its end


def other(team):
    return "away" if team == "home" else "home"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Sim:
    def __init__(self, rng, rosters, seed, real, schedule, shape_at, formation_spot):
        self.rng, self.R, self.seed, self.real = rng, rosters, seed, real
        self.schedule, self._shape_at, self._spot = schedule, shape_at, formation_spot
        self.events = []
        self.t, self.period = 0.0, 1
        self.team, self.carrier = "home", rosters["home"][9]
        self.bx, self.by = 52.5, 34.0
        self.score = {"home": 0, "away": 0}
        self.T = real["targets"]
        self.D = {tm: {"goals_1": 0, "goals_2": 0, "shots": 0, "on_target": 0, "fouls": 0, "corners": 0,
                       "yellows": 0, "reds": 0} for tm in ("home", "away")}
        self.off = set()                 # sent off
        self.booked = set()
        self.recent = []
        tot = self.T["home"]["shots"] + self.T["away"]["shots"]
        self.dom = {"home": 0.0 if tot == 0 else self.T["home"]["shots"] / tot - 0.5}
        self.dom["away"] = -self.dom["home"]
        self.chase_at = 3600.0 + (seed * 37) % 300
        self.protect_at = 4500.0 + (seed * 53) % 300
        self.changed = {"chase": set(), "protect": set()}

    # ------------------------------------------------------------------ small helpers
    def u(self, a=0.0, b=1.0):
        return float(self.rng.uniform(a, b))

    def r(self):
        return float(self.rng.random())

    def half_end(self):
        return HALF_S if self.period == 1 else MATCH_S

    def mat(self, team):
        return 1.0 if team == "home" else -1.0

    def att(self, team, x):
        """Distance from team's own goal line."""
        return x if team == "home" else L - x

    def to_x(self, team, depth):
        return depth if team == "home" else L - depth

    def shape(self, team):
        return self._shape_at(self.schedule, team, self.t)

    def nearest(self, team, x, y, exclude=(), keeper=False):
        best, bd = None, 1e9
        for k, pid in enumerate(self.R[team]):
            if pid in exclude or pid in self.off or (k == 0 and not keeper):
                continue
            sx, sy = self._spot(team, k, self.bx, self.by, team == self.team, self.shape(team))
            d = math.hypot(sx - x, sy - y)
            if d < bd:
                best, bd = pid, d
        return best

    def keeper(self, team):
        return self.R[team][0]

    def ev(self, type_, team, pid, x, y, outcome="none", t=None, **kw):
        t = self.t if t is None else t
        if self.events:
            t = max(t, self.events[-1]["match_clock_s"])
        if self.period == 1:
            t = min(t, HALF_S - 0.1)
        d = {"event_id": "", "type": type_, "match_clock_s": round(min(t, MATCH_S - 0.05), 1),
             "period": self.period, "team_id": team, "player_id": pid,
             "x_m": round(clamp(x, 0.0, L), 2), "y_m": round(clamp(y, 0.0, W), 2),
             "possession_id": 0, "related_event_id": None, "outcome": outcome}
        d.update(kw)
        self.events.append(d)
        return d

    def need(self, kind, team):
        """Quota control: remaining count over the count a league-average side would still get."""
        rem = self.T[team][kind] - self.D[team][kind]
        if rem <= 0:
            return 0.0
        exp_rem = LEAGUE[kind] / MATCH_S * max(1.0, MATCH_S - self.t)
        return clamp((rem + 0.4) / (exp_rem + 0.4), 0.0, 10.0)

    def goals_owed(self, team, half=None):
        h = half or self.period
        return self.T[team][f"goals_{h}"] - self.D[team][f"goals_{h}"]

    def urgent(self):
        """The team that owes a goal in this half with little time left, if any."""
        left = self.half_end() - self.t
        best = None
        for tm in ("home", "away"):
            g = self.goals_owed(tm)
            if g > 0 and left < URGENT_S * g:
                if best is None or g > self.goals_owed(best):
                    best = tm
        return best

    def dead(self, kind):
        """Wait for a restart: about the Premier League average for this kind, varying."""
        mean = DEAD_S[kind]
        s = mean * math.exp(float(self.rng.normal(0.0, 0.35)) - 0.35 ** 2 / 2)
        self.t += s
        return s

    def flight(self, length, kind="ground"):
        speed = {"ground": 13.0, "low": 16.0, "high": 19.0}[kind]
        return max(0.4, length / speed)

    # ------------------------------------------------------------------ the match
    def run(self):
        self.restart("kick_off", "home", 52.5, 34.0, dead_s=0.0)
        while True:
            if self.t >= self.half_end() - 1.0:
                if self.period == 1:
                    self.finish_half()
                    self.period, self.t = 2, HALF_S
                    self.bx, self.by = 52.5, 34.0
                    self.restart("kick_off", "away", 52.5, 34.0, dead_s=0.0)
                    continue
                self.finish_half()
                break
            self.formation_changes()
            self.t += self.u(*STEP_S)
            if self.t >= self.half_end() - 1.0:
                continue
            self.recent = ([self.events[-1]["player_id"]] if self.events else []) + self.recent[:1]
            self.action()
        return self.events, self.score

    def finish_half(self):
        """A goal still owed at the whistle: a ball over the top, and it goes in (rare)."""
        for tm in ("home", "away"):
            while self.goals_owed(tm) > 0:
                self.t = min(self.t, self.half_end() - 6.0)
                if self.team != tm:
                    self.win_ball(tm, "interception")
                gx = L - 9.0 if tm == "home" else 9.0
                rec = self.R[tm][1 + F.front_runners(self.shape(tm))[0]]
                if rec == self.carrier or rec in self.off:
                    rec = self.nearest(tm, gx, 34.0, exclude=(self.carrier,))
                length = math.hypot(gx - self.bx, 34.0 - self.by)
                self.ev("pass", tm, self.carrier, self.bx, self.by, "success", receiver_id=rec, pass_type="long",
                        length_m=round(length, 2), end_x_m=round(gx, 2), end_y_m=34.0, height="high")
                self.t += self.flight(length, "high")
                self.bx, self.by, self.carrier = gx, 34.0, rec
                self.shoot(force_goal=True)
                self.t += 1.0

    def formation_changes(self):
        for tm in ("home", "away"):
            diff = self.score[tm] - self.score[other(tm)]
            now = self.shape(tm)
            if self.t >= self.chase_at and diff < 0 and tm not in self.changed["chase"]:
                self.changed["chase"].add(tm)
                new = F.ATTACKING_SWITCH[now]
                if new != now:
                    self.schedule[tm].append({"from_s": round(self.t, 1), "formation": new, "why": "chasing the game"})
            if self.t >= self.protect_at and diff > 0 and tm not in self.changed["protect"]:
                self.changed["protect"].add(tm)
                if not now.startswith("5"):
                    self.schedule[tm].append({"from_s": round(self.t, 1), "formation": F.PROTECT_LEAD,
                                              "why": "protecting a lead"})

    def action(self):
        T, D = self.team, other(self.team)
        a = self.att(T, self.bx)
        in_box = a > L - BOX_DEPTH and BOX_Y[0] <= self.by <= BOX_Y[1]
        hurry = self.urgent()
        if hurry == D and self.r() < 0.35:            # the team that must score wins the ball back
            self.win_ball(D, "interception" if self.r() < 0.6 else "tackle")
            return
        owed_c = self.T[T]["corners"] - self.D[T]["corners"]
        if owed_c > 0 and a >= 75.0 and MATCH_S - self.t < 400.0 * owed_c and self.r() < 0.15:
            self.team, self.carrier = D, self.nearest(D, self.bx, self.by)   # blocked behind: a corner
            self.clearance(D, corner_mech=10.0)
            return
        p_shot = P_SHOT_BOX if in_box else (P_SHOT_EDGE if a >= 70.0 else 0.0)
        p_shot *= self.need("shots", T)
        if hurry == T and a >= 70.0:
            p_shot = max(p_shot, 0.45)
        foul_need = self.need("fouls", D)
        cards_owed = (self.T[D]["yellows"] - self.D[D]["yellows"]) + (self.T[D]["reds"] - self.D[D]["reds"])
        if cards_owed > 0 and foul_need == 0.0:
            foul_need = 1.0
        p_foul = P_FOUL * foul_need * (0.3 if in_box else 1.0)
        x = self.r()
        if x < p_shot:
            self.shoot()
        elif x < p_shot + p_foul:
            self.foul()
        elif x < p_shot + p_foul + 0.17:
            self.carry()
        elif THROUGH_FROM_M <= a <= THROUGH_TO_M and not self.carrier.endswith("01") and self.r() < P_THROUGH * (3 if hurry == T else 1):
            self.through_ball()
        else:
            self.pass_()

    # ------------------------------------------------------------------ possession changes
    def win_ball(self, team, how):
        """team takes the ball from the carrier where it is."""
        loser = self.carrier
        pid = self.nearest(team, self.bx, self.by)
        if how == "tackle":
            self.ev("duel", team, pid, self.bx, self.by, "success", duel_type="ground", context="tackle",
                    opponent_id=loser)
            if self.r() < P_TACKLE_OUT:              # poked out: a throw-in to the side that lost it
                self.out_for_throw(other(team), self.bx, 0.0 if self.by < 34.0 else W)
                return
        else:
            self.ev("recovery", team, pid, self.bx, self.by, "success", method=how)
        self.team, self.carrier = team, pid

    def fifty_fifty(self, x, y, attacker_team, aerial=False):
        """A loose ball: the nearest player of each side contests it. Returns the winning team."""
        T, D = attacker_team, other(attacker_team)
        pa = self.nearest(T, x, y, exclude=(self.carrier,)) or self.nearest(T, x, y)
        pd = self.nearest(D, x, y)
        p_att = 0.5 + 0.15 * self.dom[T] * 2
        win = T if self.r() < p_att else D
        w, l = (pa, pd) if win == T else (pd, pa)
        self.bx, self.by = x, y
        self.ev("duel", win, w, x, y, "success", duel_type="aerial" if aerial else "ground",
                context="aerial" if aerial else "fifty_fifty", opponent_id=l)
        self.team, self.carrier = win, w
        return win

    def pressure_on(self, team_on_ball, pid):
        """Maybe an opponent closes him down. Returns True if under pressure."""
        D = other(team_on_ball)
        a = self.att(team_on_ball, self.bx)
        zone_f = 1.25 if a < 35.0 else (1.0 if a < 70.0 else 1.2)
        p = P_PRESSURE * zone_f * (1.0 + 0.8 * self.dom[D])
        if self.urgent() == D:
            p *= 1.5
        if self.r() >= p:
            return False
        presser = self.nearest(D, self.bx, self.by)
        last = self.events[-1]["match_clock_s"] if self.events else 0.0
        self.ev("pressure", D, presser, self.bx - self.mat(team_on_ball) * 2.5, self.by + self.u(-2, 2),
                t=max(last, self.t - 0.5), target_player_id=pid, duration_s=round(self.u(0.5, 2.5), 1))
        return True

    # ------------------------------------------------------------------ passing
    def pass_(self):
        T, D = self.team, other(self.team)
        mat, a = self.mat(T), self.att(T, self.bx)
        zone = "own" if a < 35.0 else ("middle" if a < 70.0 else "final")
        pressed = self.pressure_on(T, self.carrier)
        if a >= 70.0 and (self.by < 14.0 or self.by > 54.0) and self.r() < P_CROSS:
            return self.cross(pressed)
        hurry = self.urgent() == T
        long_p = P_LONG * (1.7 if a < 35.0 else (1.0 if a < 70.0 else 0.35)) * (1.6 if hurry else 1.0)
        if self.r() < long_p:
            length, spread = self.u(LONG_PASS_M, 58.0), 0.45
        else:
            length, spread = clamp(float(self.rng.lognormal(math.log(12.5), 0.42)), 4.0, LONG_PASS_M - 0.5), PASS_SPREAD
        back = P_BACK[zone] * (0.4 if hurry else 1.0) * (1.0 - 0.6 * self.dom[T])
        if spread == PASS_SPREAD and self.r() < back:
            ang = math.pi + float(self.rng.normal(0.0, 0.6))
        else:
            ang = float(self.rng.normal(0.0, spread))
        ex = clamp(self.bx + mat * length * math.cos(ang), 1.0, 104.0)
        ey = self.by + length * math.sin(ang)
        ey = clamp(-ey if ey < 0 else (2 * W - ey if ey > W else ey), 1.0, 67.0)
        rec = self.nearest(T, ex, ey, exclude=(self.carrier,), keeper=a < 30.0)
        k = self.R[T].index(rec)
        rx, ry = self._spot(T, k, self.bx, self.by, True, self.shape(T))
        if math.hypot(ex - self.bx, ey - self.by) < LONG_PASS_M:
            ex, ey = 0.5 * ex + 0.5 * rx, 0.5 * ey + 0.5 * ry
        else:
            ex, ey = 0.7 * ex + 0.3 * rx, 0.7 * ey + 0.3 * ry
        ex, ey = clamp(ex, 0.5, 104.5), clamp(ey, 0.5, 67.5)
        length = math.hypot(ex - self.bx, ey - self.by)
        kind = "short" if length < 15.0 else ("medium" if length < LONG_PASS_M else "long")
        ptype = "long" if kind == "long" else "ground"
        height = "ground" if kind != "long" else ("high" if self.r() < 0.8 else "low")
        p_ok = COMPLETE[kind] * ZONE_COMPLETE[zone] * (PRESSURE_MULT if pressed else FREE_MULT)
        p_ok *= 1.0 + 0.10 * self.dom[T] + (0.06 if hurry else 0.0)
        ok = self.r() < min(0.985, p_ok)
        contested = height == "high" and self.r() < P_CONTEST_LONG
        self.ev("pass", T, self.carrier, self.bx, self.by, "success" if ok else "failure", receiver_id=rec,
                pass_type=ptype, length_m=round(length, 2), end_x_m=round(ex, 2), end_y_m=round(ey, 2),
                height=height, under_pressure=pressed)
        passer = self.carrier
        self.t += self.flight(length, height)
        if contested:                                  # the receiver goes up with a defender
            pd = self.nearest(D, ex, ey)
            w, l, wt = (rec, pd, T) if ok else (pd, rec, D)
            self.ev("duel", wt, w, ex, ey, "success", duel_type="aerial", context="aerial", opponent_id=l)
            self.bx, self.by, self.team, self.carrier = ex, ey, wt, w
            return
        self.bx, self.by = ex, ey
        if ok:
            self.carrier = rec
            return
        self.lost_pass(T, passer, rec, ex, ey, length)

    def lost_pass(self, T, passer, rec, ex, ey, length):
        """A failed pass: out of play, intercepted, or a loose ball."""
        D = other(T)
        a_end = self.att(T, ex)
        if a_end > 97.0 and self.r() < 0.6:
            if self.r() < 0.3 * self.need("corners", T):  # off a defender: a corner
                self.corner(T, ey)
            else:
                self.restart("goal_kick", D, *self.goal_kick_spot(D))
            return
        if self.r() < (0.45 if (ey < 12.0 or ey > 56.0) else P_OUT):
            self.out_for_throw(D, ex, 0.0 if ey < 34.0 else W)
            return
        x = self.r()
        if x < P_INTERCEPT:
            pid = self.nearest(D, ex, ey)
            self.ev("recovery", D, pid, ex, ey, "success", method="interception")
            self.team, self.carrier = D, pid
        elif x < 0.75:
            pid = self.nearest(D, ex, ey)
            self.ev("recovery", D, pid, ex, ey, "success", method="loose_ball")
            self.team, self.carrier = D, pid
        else:
            self.fifty_fifty(ex, ey, T)

    def out_for_throw(self, team, x, y):
        self.bx, self.by = clamp(x, 1.0, 104.0), y
        self.restart("throw_in", team, self.bx, self.by)

    def goal_kick_spot(self, team):
        return (5.5 if team == "home" else L - 5.5), 34.0 + self.u(-9.0, 9.0)

    def cross(self, pressed):
        T, D = self.team, other(self.team)
        depth = self.u(90.0, 101.0)
        ex, ey = self.to_x(T, depth), self.u(24.0, 44.0)
        rec = self.nearest(T, ex, ey, exclude=(self.carrier,))
        ok = self.r() < COMPLETE["cross"] * (PRESSURE_MULT if pressed else FREE_MULT) * (1 + 0.15 * self.dom[T])
        length = math.hypot(ex - self.bx, ey - self.by)
        self.ev("pass", T, self.carrier, self.bx, self.by, "success" if ok else "failure", receiver_id=rec,
                pass_type="cross", length_m=round(length, 2), end_x_m=round(ex, 2), end_y_m=round(ey, 2),
                height="high", under_pressure=pressed)
        self.t += self.flight(length, "high")
        self.box_ball(T, rec, ex, ey, ok)

    def box_ball(self, T, rec, ex, ey, attacker_wins):
        """A high ball into the box (a cross or a corner) and what follows."""
        D = other(T)
        pd = self.nearest(D, ex, ey)
        self.bx, self.by = ex, ey
        if attacker_wins:
            if self.r() < 0.75:
                self.ev("duel", T, rec, ex, ey, "success", duel_type="aerial", context="aerial", opponent_id=pd)
            self.team, self.carrier = T, rec
            if self.r() < min(0.9, 0.55 * self.need("shots", T)) or self.urgent() == T:
                self.t += 0.3
                self.shoot(header=True)
            return
        x = self.r()
        if x < 0.2:                                   # the keeper claims it
            gk = self.keeper(D)
            self.ev("recovery", D, gk, ex, ey, "success", method="loose_ball")
            self.team, self.carrier = D, gk
            return
        if x < 0.40:                                  # it runs through, over the line
            self.restart("goal_kick", D, *self.goal_kick_spot(D))
            return
        if self.r() < 0.7:
            self.ev("duel", D, pd, ex, ey, "success", duel_type="aerial", context="aerial", opponent_id=rec)
        self.team, self.carrier = D, pd
        self.clearance(D, head=True, corner_mech=0.35)

    def clearance(self, D, head=False, corner_mech=0.0):
        """D kicks or heads it away. It may go behind (a corner), out (a throw-in), or upfield."""
        T = other(D)
        pid = self.carrier if self.team == D else self.nearest(D, self.bx, self.by)
        if self.r() < corner_mech * self.need("corners", T):
            ex = self.to_x(D, 0.0)
            ey = 0.0 if self.by < 34.0 else W
            self.ev("clearance", D, pid, self.bx, self.by, "none", body_part="head" if head else "foot",
                    end_x_m=round(ex, 2), end_y_m=round(clamp(ey + (6 if ey == 0 else -6), 0, W), 2))
            self.t += 1.2
            self.corner(T, ey)
            return
        dist = self.u(20.0, 45.0)
        ex = clamp(self.bx + self.mat(D) * dist, 2.0, 103.0)
        ey = clamp(self.by + self.u(-18.0, 18.0), 0.0, W)
        self.ev("clearance", D, pid, self.bx, self.by, "none", body_part="head" if head else "foot",
                end_x_m=round(ex, 2), end_y_m=round(ey, 2))
        self.t += self.flight(dist, "high")
        if ey <= 0.5 or ey >= W - 0.5 or (self.r() < 0.30):
            self.out_for_throw(T, ex, 0.0 if ey < 34.0 else W)
            return
        self.bx, self.by = ex, ey
        if self.r() < 0.3:
            self.fifty_fifty(ex, ey, T, aerial=True)
        else:
            win = T if self.r() < 0.5 + 0.2 * self.dom[T] else D
            pid = self.nearest(win, ex, ey)
            self.ev("recovery", win, pid, ex, ey, "success", method="loose_ball")
            self.team, self.carrier = win, pid

    def through_ball(self):
        T, D = self.team, other(self.team)
        mat = self.mat(T)
        runners = [self.R[T][1 + i] for i in F.front_runners(self.shape(T))]
        fwd = [p for p in runners if p != self.carrier and p not in self.recent and p not in self.off]
        fwd = fwd or [p for p in runners if p != self.carrier and p not in self.off] or \
            [self.nearest(T, self.to_x(T, 85.0), self.by, exclude=(self.carrier,))]
        rec = fwd[int(self.rng.integers(0, len(fwd)))]
        depth = self.u(80.0, 93.0)
        ex, ey = self.to_x(T, depth), clamp(self.by + self.u(-14.0, 14.0), 6.0, 62.0)
        x = self.r()
        result = "offside" if x < 0.30 else ("complete" if x < 0.75 else "intercepted")
        length = math.hypot(ex - self.bx, ey - self.by)
        height = "ground" if self.r() < 0.75 else "low"
        self.ev("pass", T, self.carrier, self.bx, self.by, "success" if result == "complete" else "failure",
                receiver_id=rec, pass_type="through", length_m=round(length, 2), end_x_m=round(ex, 2),
                end_y_m=round(ey, 2), height=height)
        self.bx, self.by = ex, ey
        if result == "offside":
            t_off = self.t + max(0.8, length / 15.0)
            self.ev("offside", T, rec, ex, ey, "none", t=t_off, related_event_id="__pass__")
            self.t = t_off
            self.restart("free_kick", D, ex, ey)
            return
        self.t += self.flight(length, height)
        if result == "complete":
            self.carrier = rec
        else:
            pid = self.nearest(D, ex, ey, keeper=True)
            self.ev("recovery", D, pid, ex, ey, "success", method="interception")
            self.team, self.carrier = D, pid

    # ------------------------------------------------------------------ carrying
    def carry(self):
        T, D = self.team, other(self.team)
        dist = self.u(3.0, 15.0)
        ex = clamp(self.bx + self.mat(T) * dist, 0.5, 104.5)
        ey = clamp(self.by + self.u(-4.0, 4.0), 0.5, 67.5)
        pressed = self.pressure_on(T, self.carrier)
        if self.r() < P_TAKE_ON * (1.4 if pressed else 1.0):
            opp = self.nearest(D, self.bx, self.by)
            if self.r() < TAKE_ON_WIN + 0.1 * self.dom[T]:
                self.ev("duel", T, self.carrier, self.bx, self.by, "success", duel_type="ground",
                        context="take_on", opponent_id=opp, under_pressure=pressed)
            else:
                self.ev("duel", D, opp, self.bx, self.by, "success", duel_type="ground", context="tackle",
                        opponent_id=self.carrier, under_pressure=pressed)
                self.team, self.carrier = D, opp
                if self.r() < P_TACKLE_OUT:
                    self.out_for_throw(T, self.bx, 0.0 if self.by < 34.0 else W)
                return
        fail = self.r() >= (0.84 if pressed else 0.9)
        self.ev("carry", T, self.carrier, self.bx, self.by, "failure" if fail else "success",
                end_x_m=round(ex, 2), end_y_m=round(ey, 2), distance_m=round(math.hypot(ex - self.bx, ey - self.by), 2),
                under_pressure=pressed)
        self.t += dist / 5.0
        self.bx, self.by = ex, ey
        if fail:
            self.win_ball(D, "tackle")

    # ------------------------------------------------------------------ fouls and cards
    def foul(self):
        T, D = self.team, other(self.team)
        a = self.att(T, self.bx)
        offender = self.nearest(D, self.bx, self.by)
        victim = self.carrier
        card = None
        fouls_left = max(1, self.T[D]["fouls"] - self.D[D]["fouls"])
        if self.T[D]["reds"] - self.D[D]["reds"] > 0 and self.r() < 1.0 / fouls_left:
            card = "red"
        elif self.T[D]["yellows"] - self.D[D]["yellows"] > 0 and \
                (self.r() < (self.T[D]["yellows"] - self.D[D]["yellows"]) / fouls_left or MATCH_S - self.t < 600):
            card = "yellow"
            if offender in self.booked:              # a second yellow is not modelled: book someone else
                others = [p for p in self.R[D][1:] if p not in self.booked and p not in self.off]
                offender = others[int(self.rng.integers(0, len(others)))] if others else offender
        in_box = a > L - BOX_DEPTH and BOX_Y[0] <= self.by <= BOX_Y[1]
        adv = (not in_box) and card is None and self.r() < 0.2
        self.D[D]["fouls"] += 1
        fx, fy = self.bx, self.by
        self.ev("foul", D, offender, fx, fy, "none", fouled_player_id=victim,
                foul_type=["tackle", "holding", "handball"][int(self.rng.integers(0, 3))] if self.r() < 0.9 else "tackle",
                card=card, advantage_played=adv)
        if card == "yellow":
            self.D[D]["yellows"] += 1
            self.booked.add(offender)
        elif card == "red":
            self.D[D]["reds"] += 1
            self.off.add(offender)
        if adv:
            return
        extra = CARD_EXTRA_S if card else 0.0
        self.t += extra
        if in_box and self.r() < P_PENALTY_FOUL:
            self.restart("penalty", T, self.to_x(T, L - 11.0), 34.0)
            return
        direct = a >= 75.0 and 15.0 <= fy <= 53.0
        self.restart("free_kick", T, fx, fy, direct=direct)

    # ------------------------------------------------------------------ restarts
    def restart(self, kind, team, x, y, dead_s=None, direct=False):
        """The ball is dead until the restart. Returns False if the half ends first."""
        if dead_s is None:
            dead_s = self.dead("free_kick_direct" if (kind == "free_kick" and direct) else kind)
        else:
            self.t += dead_s
        if self.t >= self.half_end() - 1.0:
            return False
        self.bx, self.by = x, y
        D = other(team)
        if kind == "kick_off":
            taker = self.R[team][1 + F.front_runners(self.shape(team))[0]]
            if taker in self.off:
                taker = self.nearest(team, x, y)
            rec = self.nearest(team, self.to_x(team, 40.0), 34.0 + self.u(-8, 8), exclude=(taker,))
            k = self.R[team].index(rec)
            rx, ry = self._spot(team, k, x, y, True, self.shape(team))
            rx = self.to_x(team, min(self.att(team, rx), 48.0))
            self.ev("restart", team, taker, x, y, "success", restart_type=kind, dead_s=round(dead_s, 1),
                    receiver_id=rec, end_x_m=round(rx, 2), end_y_m=round(ry, 2), height="ground")
            self.t += 1.0
            self.team, self.carrier, self.bx, self.by = team, rec, rx, ry
            return True
        if kind == "penalty":
            taker = self.R[team][1 + F.front_runners(self.shape(team))[0]]
            if taker in self.off:
                taker = self.nearest(team, x, y)
            self.ev("restart", team, taker, x, y, "success", restart_type=kind, dead_s=round(dead_s, 1))
            self.team, self.carrier = team, taker
            self.t += 1.0
            self.shoot(penalty=True)
            return True
        if kind == "corner":
            taker = self.nearest(team, x, y)
            if self.r() < 0.15:                       # short corner
                rec = self.nearest(team, x, y, exclude=(taker,))
                ex, ey = clamp(x - self.mat(team) * self.u(6, 14), 1, 104), clamp(y + (8 if y < 34 else -8), 1, 67)
                self.ev("restart", team, taker, x, y, "success", restart_type=kind, dead_s=round(dead_s, 1),
                        receiver_id=rec, end_x_m=round(ex, 2), end_y_m=round(ey, 2), height="ground")
                self.t += 1.2
                self.team, self.carrier, self.bx, self.by = team, rec, ex, ey
                return True
            ex, ey = self.to_x(team, self.u(94.0, 100.0)), self.u(27.0, 41.0)
            rec = self.nearest(team, ex, ey, exclude=(taker,))
            win = self.r() < 0.33 + 0.1 * self.dom[team]
            self.ev("restart", team, taker, x, y, "success" if win else "failure", restart_type=kind,
                    dead_s=round(dead_s, 1), receiver_id=rec, end_x_m=round(ex, 2), end_y_m=round(ey, 2),
                    height="high")
            self.t += self.flight(math.hypot(ex - x, ey - y), "high")
            self.team, self.carrier = team, taker
            self.box_ball(team, rec, ex, ey, win)
            return True
        if kind == "free_kick" and direct:
            taker = self.nearest(team, x, y)
            self.team, self.carrier = team, taker
            if self.r() < 0.45 and self.need("shots", team) > 0:    # at goal
                self.ev("restart", team, taker, x, y, "success", restart_type=kind, dead_s=round(dead_s, 1),
                        direct=True)
                self.t += 0.8
                self.shoot(set_piece=True)
                return True
            ex, ey = self.to_x(team, self.u(92.0, 99.0)), self.u(25.0, 43.0)
            rec = self.nearest(team, ex, ey, exclude=(taker,))
            win = self.r() < 0.30
            self.ev("restart", team, taker, x, y, "success" if win else "failure", restart_type=kind,
                    dead_s=round(dead_s, 1), receiver_id=rec, end_x_m=round(ex, 2), end_y_m=round(ey, 2),
                    height="high")
            self.t += self.flight(math.hypot(ex - x, ey - y), "high")
            self.box_ball(team, rec, ex, ey, win)
            return True
        # throw-in, goal kick, other free kicks: a pass to a teammate
        if kind == "goal_kick":
            taker = self.keeper(team)
            long_ = self.r() < 0.45
            dist = self.u(40.0, 60.0) if long_ else self.u(8.0, 18.0)
            height = "high" if long_ else "ground"
        elif kind == "throw_in":
            taker = self.nearest(team, x, y)
            dist, height = self.u(8.0, 20.0), "low"
        else:
            taker = self.nearest(team, x, y)
            long_ = self.att(team, x) < 50.0 and self.r() < 0.4
            dist = self.u(30.0, 50.0) if long_ else self.u(8.0, 20.0)
            height = "high" if long_ else "ground"
        ang = float(self.rng.normal(0.0, 0.7))
        ex = clamp(x + self.mat(team) * dist * math.cos(ang), 1.0, 104.0)
        ey = y + dist * math.sin(ang) * (1 if kind != "throw_in" else 0.4)
        if kind == "throw_in":
            ey = clamp(abs(ey - y) + 4.0, 4.0, 22.0)
            ey = ey if y < 34 else W - ey
            ex = clamp(x + self.mat(team) * self.u(-6, 14), 1.0, 104.0)
        ey = clamp(ey, 1.0, 67.0)
        rec = self.nearest(team, ex, ey, exclude=(taker,))
        contested = height == "high" and self.r() < 0.55
        ok = self.r() < (0.80 if kind == "throw_in" else (0.5 if contested else 0.93))
        self.ev("restart", team, taker, x, y, "success" if ok else "failure", restart_type=kind,
                dead_s=round(dead_s, 1), receiver_id=rec, end_x_m=round(ex, 2), end_y_m=round(ey, 2), height=height)
        self.t += self.flight(math.hypot(ex - x, ey - y), height)
        self.team, self.carrier = team, taker
        if contested:
            pd = self.nearest(D, ex, ey)
            w, l, wt = (rec, pd, team) if ok else (pd, rec, D)
            self.ev("duel", wt, w, ex, ey, "success", duel_type="aerial", context="aerial", opponent_id=l)
            self.bx, self.by, self.team, self.carrier = ex, ey, wt, w
            return True
        self.bx, self.by = ex, ey
        if ok:
            self.carrier = rec
        elif self.r() < 0.5:
            pid = self.nearest(D, ex, ey)
            self.ev("recovery", D, pid, ex, ey, "success", method="interception")
            self.team, self.carrier = D, pid
        else:
            self.fifty_fifty(ex, ey, team)
        return True

    def corner(self, team, y_side):
        """A corner for team, from the flag on the side the ball went out."""
        self.D[team]["corners"] += 1
        x = self.to_x(team, L - 0.3)
        y = 0.3 if y_side < 34 else W - 0.3
        self.restart("corner", team, x, y)

    # ------------------------------------------------------------------ shots
    def shoot(self, header=False, penalty=False, set_piece=False, force_goal=False):
        T, D = self.team, other(self.team)
        h = self.period
        rem_shots = max(1, self.T[T]["shots"] - self.D[T]["shots"])
        left_half = max(1.0, self.half_end() - self.t)
        frac = left_half / max(1.0, MATCH_S - self.t)
        exp_in_half = max(1.0, rem_shots * frac)
        owed = self.goals_owed(T)
        p_goal = 0.0 if owed <= 0 else clamp(owed / exp_in_half, 0.0, 0.95)
        if self.urgent() == T:
            p_goal = max(p_goal, 0.6)
        goal = force_goal or (owed > 0 and self.r() < p_goal)
        owed_total = self.goals_owed(T, 1) * (h == 1) + self.goals_owed(T, 2)
        sot_rem = (self.T[T]["on_target"] - self.D[T]["on_target"]) - owed_total
        nongoal_rem = max(1, rem_shots - owed_total)
        mat = self.mat(T)
        goal_x = L if T == "home" else 0.0
        if penalty:
            sx, sy, st = goal_x - mat * 11.0, 34.0, "penalty"
        else:
            sx, sy = self.bx, self.by
            st = "set_piece" if set_piece else "open_play"
            if goal and not set_piece and xg_for_shot(sx, sy, T, "right_foot", "open_play") < 0.12:
                sx = goal_x - mat * self.u(5.5, 13.0)
                sy = 34.0 + self.u(-8.0, 8.0)
        body = "head" if header else ("left_foot" if self.r() < 0.5 else "right_foot")
        if goal:
            fo = "goal"
        elif self.r() < clamp(sot_rem / nongoal_rem, 0.0, 1.0):
            fo = "saved"
        else:
            x = self.r()
            fo = "blocked" if (x < 0.42 and not penalty) else ("woodwork" if x < 0.50 else "off_target")
        xg = xg_for_shot(sx, sy, T, body, st)
        self.D[T]["shots"] += 1
        if fo in ("goal", "saved"):
            self.D[T]["on_target"] += 1
        self.ev("shot", T, self.carrier, sx, sy, "success" if fo == "goal" else "none", body_part=body,
                shot_type=st, shot_outcome=fo,
                speed_mps=round(self.u(18.0, 40.0) if fo == "goal" else self.u(14.0, 36.0), 1), xg=round(xg, 4))
        self.bx, self.by = sx, sy
        if fo == "goal":
            self.score[T] += 1
            self.D[T][f"goals_{h}"] += 1
            self.restart("kick_off", D, 52.5, 34.0)
            return
        if fo == "saved":
            gk = self.keeper(D)
            self.t += 0.1
            self.ev("save", D, gk, self.bx - mat * 2.0, self.by, "success",
                    body_part="hands" if self.r() < 0.85 else "body", related_event_id="__shot__")
            if self.r() < 0.6:                        # held
                self.team, self.carrier = D, gk
                self.t += self.u(4.0, 9.0)
                return
            if self.r() < 0.7 * self.need("corners", T):
                self.t += 1.0
                self.corner(T, self.by)
                return
            self.t += 0.8
            self.fifty_fifty(clamp(self.bx - mat * 6.0, 1, 104), clamp(self.by + self.u(-6, 6), 1, 67), T)
            return
        if fo in ("off_target",):
            self.t += 1.5
            self.restart("goal_kick", D, *self.goal_kick_spot(D))
            return
        if fo == "woodwork":
            self.t += 0.8
            if self.r() < 0.5:
                self.fifty_fifty(clamp(self.bx - mat * 5.0, 1, 104), clamp(self.by + self.u(-5, 5), 1, 67), T)
            else:
                self.restart("goal_kick", D, *self.goal_kick_spot(D))
            return
        # blocked
        self.t += 0.5
        if self.r() < 0.65 * self.need("corners", T):
            self.corner(T, self.by)
            return
        if self.r() < 0.5:
            self.team, self.carrier = D, self.nearest(D, self.bx, self.by)
            self.clearance(D)
        else:
            self.fifty_fifty(clamp(self.bx - mat * 3.0, 1, 104), self.by, T)
