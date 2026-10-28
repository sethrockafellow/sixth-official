"""Generator v2 and the new metrics (2026-10-25): history-driven box scores, restarts and dead-ball
time, duels and pressure, ball height, the fitted win model, and dead-ball findings."""
import json
import math

import pytest

from sixth import engine, generate, insights, winmodel
from sixth.history import match_for_seed

SEEDS = range(1, 13)


@pytest.fixture(scope="module")
def matches():
    return {s: generate.generate_match(s) for s in SEEDS}


def count(ev, team, kind):
    if kind in ("goals_1", "goals_2"):
        half = int(kind[-1])
        return sum(1 for e in ev if e["type"] == "shot" and e["team_id"] == team and e["shot_outcome"] == "goal"
                   and e["period"] == half)
    if kind == "yellows":
        return sum(1 for e in ev if e["type"] == "foul" and e["team_id"] == team and e["card"] == "yellow")
    if kind == "reds":
        return sum(1 for e in ev if e["type"] == "foul" and e["team_id"] == team and e["card"] == "red")
    raise KeyError(kind)


def test_goals_by_half_and_cards_copy_the_real_match(matches):
    for seed, m in matches.items():
        real = match_for_seed(seed)["targets"]
        for team in ("home", "away"):
            for kind in ("goals_1", "goals_2", "reds"):
                assert count(m["event_log"], team, kind) == real[team][kind], (seed, team, kind)
            assert abs(count(m["event_log"], team, "yellows") - real[team]["yellows"]) <= 1


def test_restarts_and_ball_in_play(matches):
    rows = []
    for m in matches.values():
        rs = [e for e in m["event_log"] if e["type"] == "restart"]
        rows.append({k: sum(e["restart_type"] == k for e in rs) for k in ("throw_in", "goal_kick", "corner", "free_kick")}
                    | {"in_play_min": (5400 - sum(e["dead_s"] for e in rs)) / 60})
    avg = {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}
    assert 28 <= avg["throw_in"] <= 46, avg        # Premier League 2025/26: 35.8 a match
    assert 10 <= avg["goal_kick"] <= 21, avg       # 15.5
    assert 7 <= avg["corner"] <= 13.5, avg         # 10.3 (2024/25)
    assert 43 <= avg["in_play_min"] <= 58, avg     # real: 55 to 58 of about 99; this clock has no added time


def test_duels_and_pressure(matches):
    for m in matches.values():
        ev = m["event_log"]
        duels = [e for e in ev if e["type"] == "duel"]
        assert {e["duel_type"] for e in duels} == {"ground", "aerial"}
        assert all(e["player_id"][0] != e["opponent_id"][0] for e in duels)      # opponents
        ps = [e for e in ev if e["type"] == "pass"]
        up = [e for e in ps if e["under_pressure"]]
        free = [e for e in ps if not e["under_pressure"]]
        assert 0.15 <= len(up) / len(ps) <= 0.35
        rate = lambda xs: sum(e["outcome"] == "success" for e in xs) / len(xs)
        assert rate(up) < rate(free) - 0.08          # pressure costs completed passes


def test_ball_goes_up_and_comes_down(matches):
    m = matches[4]
    zs = [r["ball"]["z_m"] for r in m["physical_log"]]
    assert max(zs) > 6.0 and sum(z > 0.5 for z in zs) > 100
    _, flights = generate.ball_path(m["event_log"])
    for t0, t1, peak, z_end in flights:
        assert t1 > t0 and peak >= 0 and 0 <= z_end <= 3.6      # a shot over the bar ends up to 3.5 m high


def test_sent_off_players_leave_the_pitch():
    for seed in range(1, 400):
        real = match_for_seed(seed)["targets"]
        if real["home"]["reds"] + real["away"]["reds"]:
            break
    m = generate.generate_match(seed)
    red = next(e for e in m["event_log"] if e["type"] == "foul" and e["card"] == "red")
    late = m["physical_log"][min(5400, int(red["match_clock_s"]) + 60)]
    p = next(x for x in late["players"] if x["player_id"] == red["player_id"])
    assert p["on_pitch"] is False


def test_win_model_beats_simpler_forecasts():
    v = json.loads((winmodel.Path(winmodel.__file__).parent / "win_model.json").read_text())["validation"]
    assert v["pre_match"]["model"] < v["pre_match"]["base_rates"]
    assert v["half_time"]["model"] < v["half_time"]["half_time_score_table"] < v["half_time"]["previous_model"] + 0.01
    M = winmodel.default()
    h, d, a = M.chances(2700, 1, 0, 1500, 1500)
    assert abs(h + d + a - 1) < 1e-9 and h > 0.6
    assert M.chances(5400, 2, 1, 1500, 1500) == (1.0, 0.0, 0.0)
    # A stronger home side is favoured before kick-off; a red card hurts the side that gets it.
    assert M.chances(0, 0, 0, 1700, 1400)[0] > M.chances(0, 0, 0, 1400, 1700)[0]
    assert M.chances(3000, 0, 0, 1500, 1500, reds_home=1)[0] < M.chances(3000, 0, 0, 1500, 1500)[0]


def test_exact_tests():
    assert insights.binom_two_sided(5, 10, 0.5) == pytest.approx(1.0)
    assert insights.binom_two_sided(10, 10, 0.5) == pytest.approx(2 / 1024)
    assert insights.poisson_two_sided(0, 0.0) == 1.0
    assert insights.poisson_two_sided(8, 1.0) < 0.001


def test_deadball_cards_use_only_the_past():
    E = engine.ReferenceStateEngine(generate.generate_match(4))
    cards, findings = insights.deadball_cards(E)
    assert len(cards) > 40
    for c in cards:
        assert c["t0"] < c["t1"] and c["dead_s"] >= insights.DEAD_CARD_S
        f = c.get("finding")
        if f:
            assert f["t"] == c["t0"] and f["p_adj"] >= f["p"]
            assert f["significant"] == (f["p_adj"] < 0.05)
        if c["restart"] == "corner":
            assert "what_if" in c

