"""The generator, the engine, the triggers and the tools on real matches."""
import pytest

from sixth import engine, generate, schema, tools, triggers


@pytest.fixture(scope="module")
def E():
    return engine.ReferenceStateEngine(generate.generate_match(4))


def test_same_seed_same_bytes():
    assert generate.match_bytes(42) == generate.match_bytes(42)


def test_matches_look_like_football():
    """Per-match averages over 20 matches, against the Premier League 2024/25 (docs/REALISM.md)."""
    rows = []
    for seed in range(1, 21):
        m = generate.generate_match(seed)
        ev = m["event_log"]
        ps = [e for e in ev if e["type"] == "pass"]
        nc = [e for e in ps if e["pass_type"] != "cross"]
        cr = [e for e in ps if e["pass_type"] == "cross"]
        rows.append({
            "passes": len(ps),
            "completion": 100 * sum(e["outcome"] == "success" for e in ps) / len(ps),
            "long_share": 100 * sum(e["length_m"] >= generate.LONG_PASS_M for e in nc) / len(nc),
            "crosses": len(cr),
            "shots": sum(1 for e in ev if e["type"] == "shot"),
            "goals": sum(m["final_score"].values()),
            "fouls": sum(1 for e in ev if e["type"] == "foul"),
            "offsides": sum(1 for e in ev if e["type"] == "offside"),
        })
    avg = {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}
    assert 820 <= avg["passes"] <= 960, avg          # PL 2024/25: 893.5 a match
    assert 81.0 <= avg["completion"] <= 86.5, avg    # 83.7%
    assert 9.0 <= avg["long_share"] <= 12.5, avg     # 10.5% of passes are 32 m or more
    assert 16 <= avg["crosses"] <= 28, avg           # 22.4 open-play crosses
    assert 18 <= avg["shots"] <= 32, avg             # about 25 shots
    assert 2.0 <= avg["goals"] <= 3.8, avg           # about 2.9 goals
    assert 14 <= avg["fouls"] <= 28, avg             # about 21 fouls (approximate)
    assert 1 <= avg["offsides"] <= 6, avg


def test_state_before_a_goal_shows_the_old_score(E):
    goal = next(e for e in E.events if triggers.is_goal(e))
    before, after = E.state_before(goal), E.state_after(goal)
    side = goal.team_id
    old = getattr(before.match_state, f"score_{side}")
    assert getattr(after.match_state, f"score_{side}") == old + 1


def test_win_chances_sum_to_one(E):
    for s in E.snapshots[::50]:
        ms = s.match_state
        assert abs(ms.win_prob_home + ms.draw_prob + ms.win_prob_away - 1) < 1e-6


def test_every_goal_fires_for_every_persona(E):
    trs = triggers.fire_triggers(E)
    for g in [e for e in E.events if triggers.is_goal(e)]:
        assert {t.persona.persona_id for t in trs if t.event_id == g.event_id} == {
            p.persona_id for p in schema.DEFAULT_PERSONAS}


def test_cooldown_20_seconds(E):
    trs = triggers.fire_triggers(E)
    for p in schema.DEFAULT_PERSONAS:
        ts = sorted(t.air_s for t in trs if t.persona.persona_id == p.persona_id)
        assert all(b - a >= p.cooldown_s - 1e-6 for a, b in zip(ts, ts[1:]))
        assert all(t.air_s >= t.match_clock_s for t in trs)


def test_personas_get_different_moments(E):
    trs = triggers.fire_triggers(E)
    sets = {p.persona_id: {t.event_id for t in trs if t.persona.persona_id == p.persona_id}
            for p in schema.DEFAULT_PERSONAS}
    assert len({frozenset(s) for s in sets.values()}) == 3


def test_tools_refuse_the_future(E):
    t = tools.MatchTools(E, 1200.0)
    with pytest.raises(tools.ReplayClockError):
        t.get_match_state(1260.0)
    with pytest.raises(tools.ReplayClockError):
        t.get_events(None, 0, 1300.0)
    late = next(e for e in E.events if e.match_clock_s > 1300)
    with pytest.raises(tools.ReplayClockError):
        t.get_event_context(late.event_id)
    assert t.get_match_state(1200.0)["snapshot_id"]


def test_tool_answers_name_players(E):
    t = tools.MatchTools(E, 5400.0)
    ev = t.get_event_context(E.events[10].event_id)["event"]
    assert ev["player_name"] and not any(ch.isdigit() for ch in ev["player_name"])
