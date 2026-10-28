"""triggers.py: which moments each persona gets.

Rules, per persona:
  1. Surprise S of an event = max(|change in home win chance|, 0.5 x |change in home momentum|).
  2. S is multiplied by the persona's boost when the event involves its favorite team or player.
  3. It fires when the boosted S is at or above the persona's threshold. A goal always fires.
  4. Cooldown: one output per persona per 20 s. A trigger inside the cooldown merges into the
     next output: the strongest pending trigger (a goal first, then the highest S) is sent when
     the cooldown ends, with a count of the triggers merged into it.

This module makes these rules a part the pipeline can call.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .schema import DEFAULT_PERSONAS, PersonaConfig, TriggerPayload, UserPreferences


@dataclass
class Trigger:
    event_id: str
    match_clock_s: float
    surprise: float          # boosted surprise: the output's importance
    persona: PersonaConfig
    is_goal: bool
    merged: int = 0          # triggers merged into this one during the cooldown
    air_s: float = 0.0       # when the comment airs: the moment itself, or the end of the cooldown

    def payload(self, language: str = "en") -> TriggerPayload:
        p = self.persona
        return TriggerPayload(event_id=self.event_id, match_clock_s=self.match_clock_s, surprise=self.surprise,
                              preferences=UserPreferences(user_id=p.persona_id, mode=p.mode,
                                                          favorite_team=p.favorite_team,
                                                          favorite_player=p.favorite_player, language=language))


def involves_favorite(persona: PersonaConfig, event) -> bool:
    if persona.favorite_team is not None and event.team_id == persona.favorite_team:
        return True
    return persona.favorite_player is not None and event.player_id == persona.favorite_player


def is_goal(event) -> bool:
    return event.type == "shot" and getattr(event, "shot_outcome", None) == "goal"


@dataclass
class _State:
    last_out: float = -1e9
    pending: Trigger | None = None
    merged: int = 0


def _stronger(a: Trigger | None, b: Trigger) -> Trigger:
    if a is None:
        return b
    return b if (b.is_goal, b.surprise) > (a.is_goal, a.surprise) else a


def fire_triggers(engine, personas: list[PersonaConfig] | None = None) -> list[Trigger]:
    """All triggers of a match, in time order, after boosts, thresholds and the cooldown."""
    personas = personas or DEFAULT_PERSONAS
    states = {p.persona_id: _State() for p in personas}
    out: list[Trigger] = []

    def flush(p: PersonaConfig, now: float, force: bool = False):
        st = states[p.persona_id]
        if st.pending and (force or now - st.last_out >= p.cooldown_s):
            t = st.pending
            t.merged = st.merged
            t.air_s = max(t.match_clock_s, st.last_out + p.cooldown_s)
            out.append(t)
            st.last_out = t.air_s
            st.pending, st.merged = None, 0

    for ev in engine.events:
        s = engine.surprise_for(ev)
        goal = is_goal(ev)
        for p in personas:
            flush(p, ev.match_clock_s)
            boosted = s * (p.boost if involves_favorite(p, ev) else 1.0)
            if not (goal or boosted >= p.threshold):
                continue
            st = states[p.persona_id]
            trig = Trigger(ev.event_id, ev.match_clock_s, round(boosted, 6), p, goal, air_s=ev.match_clock_s)
            if st.pending is None and ev.match_clock_s - st.last_out >= p.cooldown_s:
                out.append(trig)
                st.last_out = ev.match_clock_s
            else:
                if st.pending is not None:
                    st.merged += 1
                st.pending = _stronger(st.pending, trig)
    for p in personas:
        flush(p, float("inf"), force=True)
    out.sort(key=lambda t: (t.air_s, t.persona.persona_id))
    return out
