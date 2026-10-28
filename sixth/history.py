"""history.py: real Premier League box scores that the synthetic matches copy.

data/history/pl_matches.csv holds 6,080 real matches, 2009/10 to 2024/25 (scripts/build_history.py
made it from the public football-data.co.uk results). Each seed picks one of them. The generator
then plays a synthetic match that ends with the same box score: goals in each half, shots, shots
on target, fouls, corners and cards for each side. Clubs and players stay fictional; the season
and date say which real match it copies.

2009/10 is left out: it only warms up the Elo ratings, which start equal.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "history" / "pl_matches.csv"
INT_COLS = ("hg", "ag", "hthg", "htag", "hs", "as", "hst", "ast", "hf", "af", "hc", "ac", "hy", "ay", "hr", "ar")
WARM_UP = 380


@lru_cache(maxsize=1)
def rows() -> list[dict]:
    with open(DATA, newline="", encoding="utf-8") as f:
        out = list(csv.DictReader(f))
    for i, r in enumerate(out):
        r["row"] = i
        for k in INT_COLS:
            r[k] = int(r[k])
        r["elo_home"], r["elo_away"] = float(r["elo_home"]), float(r["elo_away"])
    return out


def match_for_seed(seed: int) -> dict:
    """The real match a seed copies, as targets for each side."""
    R = rows()
    r = R[WARM_UP + (seed * 7919) % (len(R) - WARM_UP)]
    side = {
        "home": {"goals_1": r["hthg"], "goals_2": r["hg"] - r["hthg"], "shots": r["hs"], "on_target": r["hst"],
                 "fouls": r["hf"], "corners": r["hc"], "yellows": r["hy"], "reds": r["hr"]},
        "away": {"goals_1": r["htag"], "goals_2": r["ag"] - r["htag"], "shots": r["as"], "on_target": r["ast"],
                 "fouls": r["af"], "corners": r["ac"], "yellows": r["ay"], "reds": r["ar"]},
    }
    for s in side.values():                    # a goal is a shot on target, and a shot
        s["on_target"] = max(s["on_target"], s["goals_1"] + s["goals_2"])
        s["shots"] = max(s["shots"], s["on_target"])
    return {"season": r["season"], "date": r["date"], "row": r["row"], "elo_home": r["elo_home"],
            "elo_away": r["elo_away"], "targets": side,
            "source": "football-data.co.uk Premier League results, row %d of data/history/pl_matches.csv" % r["row"]}
