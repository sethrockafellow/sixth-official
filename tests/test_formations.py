"""Formations: the assignment method, the templates, the played shapes, and the detector on real
generated matches (it must find the shape the generator was actually playing)."""
import itertools
import random

import pytest

from sixth import formations as F
from sixth import generate as g


def test_hungarian_finds_the_cheapest_assignment():
    rnd = random.Random(1)
    for _ in range(25):
        c = [[rnd.random() for _ in range(6)] for _ in range(6)]
        a = F.hungarian(c)
        best = min(itertools.permutations(range(6)), key=lambda p: sum(c[i][p[i]] for i in range(6)))
        assert sum(c[i][a[i]] for i in range(6)) == pytest.approx(sum(c[i][best[i]] for i in range(6)))


@pytest.mark.parametrize("name", list(F.TEMPLATES))
def test_every_template_recognises_itself_shifted_stretched_and_noisy(name):
    rnd = random.Random(name)
    for _ in range(10):
        pts = [(line * F.LINE_M * 1.2 + 30 + rnd.gauss(0, 1.5), w * F.HALF_WIDTH_M * 0.85 + rnd.gauss(0, 1.5))
               for line, w in F.TEMPLATES[name]]
        rnd.shuffle(pts)
        assert F.detect(pts)[0][0] == name


def test_played_shapes_read_as_analysts_describe_them():
    assert F.expected_label("4-3-3", False) == "4-5-1"     # wingers drop: defends as a 4-5-1
    assert F.expected_label("3-5-2", False) == "5-3-2"     # wing-backs drop: a back five
    assert F.expected_label("3-4-3", False) == "5-4-1"
    for name in F.TEMPLATES:                                 # with the ball, the set-up shows
        assert F.expected_label(name, True) == name


@pytest.fixture(scope="module")
def matches():
    return {s: g.generate_match(s) for s in range(1, 11)}


def test_the_detector_finds_the_shape_being_played(matches):
    """In 15-minute blocks with one shape in force, the detector names the shape played."""
    hits = {"out": 0, "in": 0}
    total = {"out": 0, "in": 0}
    for m in matches.values():
        A = F.analyse(m)
        for team in ("home", "away"):
            for b in A[team]["blocks"]:
                names = {g.shape_at(m["formations"], team, t) for t in range(b["from_s"], b["to_s"], 30)}
                if len(names) != 1:
                    continue
                name = names.pop()
                for state, has in (("out", False), ("in", True)):
                    if b[state]:
                        total[state] += 1
                        hits[state] += b[state]["best"] == F.expected_label(name, has)
    assert hits["out"] / total["out"] >= 0.8, (hits, total)
    assert hits["in"] / total["in"] >= 0.9, (hits, total)


def test_changes_follow_the_game_state(matches):
    for m in matches.values():
        goals = sorted((e["match_clock_s"], e["team_id"]) for e in m["event_log"]
                       if e["type"] == "shot" and e.get("shot_outcome") == "goal")
        for team in ("home", "away"):
            for c in m["formations"][team][1:]:
                # A change can come in the same second as the goal that caused it.
                lead = sum(1 if tm == team else -1 for t, tm in goals if t <= c["from_s"])
                if c["why"] == "chasing the game":
                    assert lead < 0 and c["from_s"] >= 3600
                else:
                    assert c["why"] == "protecting a lead" and lead > 0 and c["from_s"] >= 4500


def test_squad_numbers_are_unique_per_club_and_fixed_across_matches(matches):
    from sixth.roster import SHIRT
    for prefix in ("h", "a"):
        nums = [SHIRT[f"{prefix}{k:02d}"] for k in range(1, 12)]
        assert len(set(nums)) == 11 and all(1 <= n <= 99 for n in nums)
    for m in matches.values():                       # the slot changes; the number does not
        assert {pid: v["number"] for pid, v in F.team_sheet(m).items()} == SHIRT
