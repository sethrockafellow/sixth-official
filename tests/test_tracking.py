"""Movement must be physically believable, and offside decisions must match the positions.

Players and officials: no jumps, realistic distances, a shape that moves. Every through ball:
at the second before the pass, the receiver is offside exactly when the events record an offside.
"""
import math
from collections import defaultdict

import pytest

from sixth.engine import ReferenceStateEngine
from sixth.generate import (AR1_Y, AR2_Y, TOP_SPEED_MPS, depth_from_goal, generate_match, offside_line,
                            other_team)

SEEDS = (4, 7, 11, 42, 99)


@pytest.fixture(scope="module")
def match():
    return generate_match(4)


@pytest.fixture(scope="module")
def matches():
    return {s: generate_match(s) for s in SEEDS}


def per_second_moves(rows, key="players", id_key="player_id"):
    prev, moves, dist = {}, [], defaultdict(float)
    for r in rows:
        for p in r[key]:
            q = prev.get(p[id_key])
            if q:
                v = math.hypot(p["x_m"] - q[0], p["y_m"] - q[1])
                moves.append(v)
                dist[p[id_key]] += v
            prev[p[id_key]] = (p["x_m"], p["y_m"])
    return moves, dist


def test_nobody_moves_faster_than_a_sprint(matches):
    for m in matches.values():
        for key, id_key in (("players", "player_id"), ("officials", "official_id")):
            moves, _ = per_second_moves(m["physical_log"], key, id_key)
            assert max(moves) <= TOP_SPEED_MPS + 0.05      # rounding to centimetres


def test_distance_covered_is_realistic(match):
    _, dist = per_second_moves(match["physical_log"])
    outfield = [d / 1000 for pid, d in dist.items() if not pid.endswith("01")]
    keepers = [d / 1000 for pid, d in dist.items() if pid.endswith("01")]
    assert 8.5 <= sum(outfield) / len(outfield) <= 12.5      # real outfield players: about 10 to 12 km
    assert all(2.0 <= k <= 7.0 for k in keepers)              # real keepers: about 5 to 6 km


def test_officials_cover_realistic_distances(match):
    _, dist = per_second_moves(match["physical_log"], "officials", "official_id")
    assert 9.0 <= dist["ref"] / 1000 <= 13.0                  # real referees: about 10 to 12 km
    assert all(3.5 <= dist[a] / 1000 <= 8.0 for a in ("ar1", "ar2"))   # real assistants: about 5 to 7 km
    assert dist["fourth"] / 1000 < 1.0                        # stays at the technical area


def test_assistants_stay_on_their_touchline_and_half(match):
    for r in match["physical_log"]:
        o = {x["official_id"]: x for x in r["officials"]}
        assert o["ar1"]["y_m"] == pytest.approx(AR1_Y, abs=0.05) and o["ar1"]["x_m"] <= 52.5 + 0.05
        assert o["ar2"]["y_m"] == pytest.approx(AR2_Y, abs=0.05) and o["ar2"]["x_m"] >= 52.5 - 0.05


def test_line_height_moves_with_the_play(match):
    E = ReferenceStateEngine(match)
    blocks = {s.home.defensive_block for s in E.snapshots}
    assert blocks == {"low", "mid", "high"}


def test_realistic_numbers_of_through_balls_and_offsides(matches):
    th = [sum(1 for e in m["event_log"] if e.get("pass_type") == "through") for m in matches.values()]
    off = [sum(1 for e in m["event_log"] if e["type"] == "offside") for m in matches.values()]
    assert 3 <= sum(th) / len(th) <= 20            # through balls per match
    assert 1 <= sum(off) / len(off) <= 6           # real matches: about 3 to 4 offsides


def test_offside_decisions_match_the_positions(matches):
    """At the second before each through ball, the receiver is offside if and only if flagged."""
    for seed, m in matches.items():
        ev, rows = m["event_log"], m["physical_log"]
        flagged = {e["related_event_id"] for e in ev if e["type"] == "offside"}
        for e in ev:
            if e.get("pass_type") != "through":
                continue
            r = rows[int(math.floor(e["match_clock_s"]))]
            de = other_team(e["team_id"])
            line = offside_line(de, [p["x_m"] for p in r["players"] if p["team_id"] == de and p.get("on_pitch", True)],
                                r["ball"]["x_m"])
            rx = next(p["x_m"] for p in r["players"] if p["player_id"] == e["receiver_id"])
            offside = depth_from_goal(rx, de) < line
            assert offside == (e["event_id"] in flagged), (seed, e["event_id"])


def test_offside_flags_the_receiver_not_the_passer(matches):
    for m in matches.values():
        by_id = {e["event_id"]: e for e in m["event_log"]}
        for e in m["event_log"]:
            if e["type"] == "offside":
                assert e["player_id"] == by_id[e["related_event_id"]]["receiver_id"]
