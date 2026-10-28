"""tools.py: the narrator's tools, bound to one moment of the match.

The engine computes, the narrator writes. Each tool returns numbers and labels only, never
sentences, and each answer carries the id that a claim cites (a snapshot_id or an event_id),
so the verifier can check every claim against the same stores.

History is fixed: a tool refuses any time after the moment being narrated ("the replay
clock"), so the narrator can never use the future.

Four of the spec's six tools are here. The player and ball summaries (spec tools 4 and 6)
are left out of version 1: their values are computed sums, which the verifier cannot look up.
"""
from __future__ import annotations

from .roster import CLUBS, name_event
from .schema import Snapshot


class ReplayClockError(ValueError):
    """A tool was asked about a time after the moment being narrated."""


class MatchTools:
    def __init__(self, engine, now_s: float):
        self.engine = engine
        self.now_s = float(now_s)
        self.calls: list[dict] = []      # each call and its answer: the trace shown on screen

    def _clock(self, at_s) -> float:
        at = float(self.now_s if at_s is None else at_s)
        if at > self.now_s + 1e-9:
            raise ReplayClockError(f"at_s {at} is after the replay clock {self.now_s}: history is fixed")
        return at

    def _log(self, name, args, result):
        self.calls.append({"tool": name, "args": args, "result": result})
        return result

    @staticmethod
    def _snapshot(s: Snapshot) -> dict:
        d = s.match_state.model_dump()
        d["home"], d["away"] = s.home.model_dump(), s.away.model_dump()
        return d

    # 1
    def get_match_state(self, at_s: float | None = None) -> dict:
        """The score, possession and win chances at a time. Cite fields as <snapshot_id>.<field>."""
        at = self._clock(at_s)
        s = self.engine.state_at(at)
        ms = {**s.match_state.model_dump(), "teams": CLUBS}
        return self._log("get_match_state", {"at_s": at}, ms)

    # 2
    def get_events(self, type: str | None = None, from_s: float = 0.0, to_s: float | None = None,
                   limit: int = 20) -> dict:
        """Events in a time range (type may be empty for all). Cite fields as <event_id>.<field>."""
        to = self._clock(to_s)
        evs = self.engine.get_events(type or None, float(from_s), to, limit=max(1, min(int(limit), 50)))
        res = {"events": [name_event(e.model_dump()) for e in evs]}
        return self._log("get_events", {"type": type, "from_s": from_s, "to_s": to, "limit": limit}, res)

    # 3
    def get_tactical_state(self, team_id: str, at_s: float | None = None) -> dict:
        """One team's momentum, pressing, line height, block, possession share and xG total.
        Cite fields as <snapshot_id>.<team_id>.<field>."""
        at = self._clock(at_s)
        if team_id not in ("home", "away"):
            raise ValueError("team_id must be home or away")
        s = self.engine.state_at(at)
        res = {"snapshot_id": s.match_state.snapshot_id, "team_id": team_id, "team_name": CLUBS[team_id],
               "tactical": getattr(s, team_id).model_dump()}
        return self._log("get_tactical_state", {"team_id": team_id, "at_s": at}, res)

    # 5
    def get_event_context(self, event_id: str) -> dict:
        """The event, the state before and after it, and the change in every number.
        Cite a change as <event_id>.deltas.<key>, for example e000412.deltas.win_prob_home."""
        e = self.engine.event_by_id.get(event_id)
        if e is None:
            raise ValueError(f"no event {event_id}")
        self._clock(e.match_clock_s)
        before, after = self.engine.state_before(e), self.engine.state_after(e)
        res = {"event": name_event(e.model_dump()), "teams": CLUBS,
               "state_before": self._snapshot(before), "state_after": self._snapshot(after),
               "deltas": self.engine.deltas_for(e)}
        return self._log("get_event_context", {"event_id": event_id}, res)
