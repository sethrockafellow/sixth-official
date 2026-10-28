"""Reference state engine for the Sixth Official.

The state engine: it builds the three stores (events, snapshots, 1 Hz
tracking) from a generated match and answers the lookups the narrator's
tools and the verifier make.

Ground rules honored: one clock (match_clock_s only), the engine
computes and the agent writes (numbers and labels only), history is
fixed (state_at(t) never sees data after t).

Source paths, as the verifier reads them:
s_<event_id>.<field> for snapshots (s_000000 is the base pre-state),
<event_id>.xg and <event_id>.<field> for the event log.
"""

import json
from bisect import bisect_right

from .schema import EventAdapter, MatchConfig, MatchState, PhysicalState, TacticalState, Snapshot
from .metrics import (
    C,
    duels_won_share,
    field_tilt,
    ppda,
    defensive_block,
    line_height_m,
    momentum_at,
    momentum_label,
    possession_share,
    pressing_intensity,
    surprise,
)
from .winmodel import default as win_model

GK_PLAYER_IDS = ("h01", "a01")
BASE_SNAPSHOT_ID = "s_000000"

NUMERIC_TOP = (
    ("score_home", "score_home"),
    ("score_away", "score_away"),
    ("win_prob_home", "win_prob_home"),
    ("draw_prob", "draw_prob"),
    ("win_prob_away", "win_prob_away"),
)
NUMERIC_TEAM = (
    ("field_tilt", "field_tilt"),
    ("ppda", "ppda"),
    ("duels_won_share", "duels_won_share"),
    ("momentum", "momentum"),
    ("pressing_intensity", "pressing_intensity"),
    ("line_height_m", "line_height_m"),
    ("possession_share_5min", "possession_share_5min"),
    ("xg_total", "xg_total"),
)


def team_of_player(player_id):
    return "home" if player_id.startswith("h") else "away"


def other(team):
    return "away" if team == "home" else "home"


def _as_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item


def normalize_events(raw_events):
    events = [EventAdapter.validate_python(_as_dict(e)) for e in raw_events]
    events.sort(key=lambda e: (e.match_clock_s, e.event_id))
    return events


def normalize_physical(raw_rows):
    rows = [PhysicalState.model_validate(_as_dict(r)) for r in raw_rows]
    rows.sort(key=lambda p: p.match_clock_s)
    return rows


class ReferenceStateEngine:
    """Builds the three stores and answers the spec lookup rules."""

    def __init__(self, match):
        self.match_id = match.get("match_id")
        self.events = normalize_events(match["event_log"])
        self.physical = normalize_physical(match["physical_log"])
        self.event_by_id = {e.event_id: e for e in self.events}
        self.event_index = {e.event_id: i for i, e in enumerate(self.events)}
        self.possession_segments = [(0.0, "home")]
        hist = match.get("history") or {}
        self.elo = (float(hist.get("elo_home", 1500.0)), float(hist.get("elo_away", 1500.0)))
        self.history = hist
        self.snapshots = []
        self.snapshot_by_id = {}
        self._build_snapshots()
        self._snap_clocks = [s.match_state.match_clock_s for s in self.snapshots]

    # --- possession -----------------------------------------------------

    @staticmethod
    def possession_after(e, current):
        """Team on the ball immediately after event e (my v1 rule)."""
        t = e.team_id
        if e.type in ("duel", "restart", "clearance"):      # v2
            return t
        if e.type == "pass" and e.outcome == "success":
            return team_of_player(e.receiver_id)
        if e.type == "carry" and e.outcome == "success":
            return t
        if e.type in ("recovery", "save"):
            return t
        if e.outcome == "failure":
            return other(t)
        if e.type in ("shot", "offside"):
            return other(t)
        return current

    # --- snapshots ------------------------------------------------------

    def _make_snapshot(self, sid, t, sh, sa, poss, window_events, xg_totals, reds=None):
        mom_h, mom_a = momentum_at(t, window_events)
        reds = reds or {"home": 0, "away": 0}
        # v2: the fitted model (sixth/winmodel.py): Elo, score, time, xG so far, red cards.
        wp_h, draw, wp_a = win_model().chances(t, sh, sa, self.elo[0], self.elo[1], xg_totals["home"],
                                               xg_totals["away"], reds["home"], reds["away"])
        row = self.physical_at(t)
        players = row.players if row is not None else []
        tactical = {}
        for team in ("home", "away"):
            mom = mom_h if team == "home" else mom_a
            press = pressing_intensity(t, team, window_events)
            lh = line_height_m(players, team, GK_PLAYER_IDS)
            tactical[team] = TacticalState(
                team_id=team,
                momentum=mom,
                momentum_label=momentum_label(mom),
                pressing_intensity=press,
                line_height_m=lh,
                defensive_block=defensive_block(lh),
                possession_share_5min=possession_share(
                    t, team, self.possession_segments
                ),
                xg_total=xg_totals[team],
                field_tilt=field_tilt(t, team, window_events),
                ppda=ppda(t, team, window_events),
                duels_won_share=duels_won_share(t, team, window_events),
            )
        return Snapshot(match_state=MatchState(
            snapshot_id=sid,
            match_clock_s=t,
            score_home=sh,
            score_away=sa,
            possession_team=poss,
            win_prob_home=wp_h,
            draw_prob=draw,
            win_prob_away=wp_a),
            home=tactical["home"],
            away=tactical["away"],
        )

    def _build_snapshots(self):
        sh = sa = 0
        xg_totals = {"home": 0.0, "away": 0.0}
        reds = {"home": 0, "away": 0}
        poss = "home"
        base = self._make_snapshot(
            BASE_SNAPSHOT_ID, 0.0, sh, sa, poss, [], xg_totals
        )
        self.snapshots.append(base)
        self.snapshot_by_id[base.match_state.snapshot_id] = base
        lo = 0
        for i, e in enumerate(self.events):
            if e.type == "shot" and e.shot_outcome == "goal":
                if e.team_id == "home":
                    sh += 1
                else:
                    sa += 1
            if e.type == "shot":
                xg_totals[e.team_id] += e.xg
            if e.type == "foul" and e.card == "red":
                reds[e.team_id] += 1
            poss = self.possession_after(e, poss)
            self.possession_segments.append((e.match_clock_s, poss))
            while lo < i and self.events[lo].match_clock_s < e.match_clock_s - C.momentum_window_s:
                lo += 1
            snap = self._make_snapshot(
                "s_" + e.event_id,
                e.match_clock_s,
                sh,
                sa,
                poss,
                self.events[lo : i + 1],
                xg_totals,
                reds,
            )
            self.snapshots.append(snap)
            self.snapshot_by_id[snap.match_state.snapshot_id] = snap

    # --- lookups (spec rules) -------------------------------------------

    def state_at(self, t):
        i = bisect_right(self._snap_clocks, t) - 1
        if i < 0:
            return None
        return self.snapshots[i]

    def state_before(self, e):
        idx = self.event_index[e.event_id]
        return self.snapshots[idx]

    def state_after(self, e):
        idx = self.event_index[e.event_id]
        return self.snapshots[idx + 1]

    def physical_at(self, t):
        if t is None:
            return None
        i = int(min(max(t, 0.0), MatchConfig(seed=0).total_seconds))
        if i >= len(self.physical):
            i = len(self.physical) - 1
        return self.physical[i]

    def surprise_for(self, e):
        return surprise(self.state_before(e), self.state_after(e))

    def get_events(self, type_, from_s, to_s, limit=50):
        out = []
        for e in self.events:
            if type_ is not None and e.type != type_:
                continue
            if not (from_s <= e.match_clock_s <= to_s):
                continue
            out.append(e)
            if limit is not None and len(out) >= limit:
                break
        return out

    def deltas_for(self, e):
        before = self.state_before(e)
        after = self.state_after(e)
        d = {}
        for key, path in NUMERIC_TOP:
            d[path] = getattr(after.match_state, key) - getattr(before.match_state, key)
        for team in ("home", "away"):
            tb = getattr(before, team)
            ta = getattr(after, team)
            for key, name in NUMERIC_TEAM:
                d["%s.%s" % (team, name)] = getattr(ta, key) - getattr(tb, key)
        return d

    def get_event_context(self, event_id):
        e = self.event_by_id[event_id]
        return {
            "event": e.model_dump(),
            "state_before": self.state_before(e).model_dump(),
            "state_after": self.state_after(e).model_dump(),
            "deltas": self.deltas_for(e),
        }

    # --- reporting --------------------------------------------------------

    def possession_mismatches(self):
        """Events where my derived possession flip disagrees with the
        generator's possession_id change. Informational: my rule is a v1
        approximation of the generator's convention, not a spec field."""
        bad = []
        prev_poss = "home"
        prev_pid = self.events[0].possession_id if self.events else 1
        for e in self.events:
            poss = self.possession_after(e, prev_poss)
            if (poss != prev_poss) != (e.possession_id != prev_pid):
                bad.append(e.event_id)
            prev_poss, prev_pid = poss, e.possession_id
        return bad

    def serialize(self):
        return json.dumps(
            {s.match_state.snapshot_id: s.model_dump() for s in self.snapshots},
            sort_keys=True,
            default=str,
        )
