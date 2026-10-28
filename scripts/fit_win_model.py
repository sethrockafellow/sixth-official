"""scripts/fit_win_model.py: fit the win-chance model on real matches and test it on later ones.

  python scripts/fit_win_model.py        writes sixth/win_model.json and prints the test results

Data: data/history/pl_matches.csv (scripts/build_history.py), 6,080 Premier League matches.
  fit on   2010/11 to 2020/21 (4,180 matches; 2009/10 only warms up the Elo ratings)
  test on  2021/22 to 2024/25 (1,520 matches the fit never saw)

The model (sixth/winmodel.py runs it during a match):
  1. Pre-match scoring rates from Elo. d = (elo_home - elo_away) / 400.
       home goals ~ Poisson(exp(a_home + b * d)),  away goals ~ Poisson(exp(a_away - b * d))
  2. When the goals come. A share s1 of a match's goals come in the first half. Inside a half,
     the rate is flat.
  3. Game state. A team's rate is multiplied by exp(gamma[state]), where state is its goal
     difference (-2 or less, -1, 0, +1, +2 or more). Fitted on second halves: the goals each
     team scored after half-time, given the half-time score.
  4. The rest of the match is played out exactly, minute by minute, over every possible score
     (sixth/winmodel.py). The result: home win, draw and away win chances.
  During a match two more things move the rates (the data here cannot test them, so they are
  marked as assumptions in docs/WIN_MODEL.md): expected goals so far, and red cards.

The test: Brier score (lower is better; the mean squared error of the three chances against
what happened) before kick-off and at half-time, for this model and two simpler ones.
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "history" / "pl_matches.csv"
OUT = ROOT / "sixth" / "win_model.json"
TRAIN = {f"20{y:02d}/{y + 1:02d}" for y in range(10, 21)}
TEST = {f"20{y:02d}/{y + 1:02d}" for y in range(21, 25)}
STATES = (-2, -1, 0, 1, 2)


def load():
    with open(DATA, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in r:
            if k not in ("season", "date", "home", "away"):
                r[k] = float(r[k])
        r["d"] = (r["elo_home"] - r["elo_away"]) / 400.0
    return rows


def fit_poisson(x, y, iters=50):
    """Poisson regression log E[y] = c0 + c1 x by Newton's method."""
    X = np.column_stack([np.ones_like(x), x])
    beta = np.array([math.log(y.mean()), 0.0])
    for _ in range(iters):
        mu = np.exp(X @ beta)
        grad = X.T @ (y - mu)
        hess = X.T @ (X * mu[:, None])
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    return beta


def state(diff):
    return max(-2, min(2, int(diff)))


def fit(rows):
    d = np.array([r["d"] for r in rows])
    hg = np.array([r["hg"] for r in rows])
    ag = np.array([r["ag"] for r in rows])
    # One slope for both sides: fit home on +d and away on -d together.
    x = np.concatenate([d, -d])
    y = np.concatenate([hg, ag])
    side = np.concatenate([np.ones_like(d), np.zeros_like(d)])
    X = np.column_stack([side, 1 - side, x])
    beta = np.array([math.log(hg.mean()), math.log(ag.mean()), 0.0])
    for _ in range(60):
        mu = np.exp(X @ beta)
        step = np.linalg.solve(X.T @ (X * mu[:, None]), X.T @ (y - mu))
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    a_home, a_away, b = (float(v) for v in beta)
    ht = sum(r["hthg"] + r["htag"] for r in rows)
    ft = sum(r["hg"] + r["ag"] for r in rows)
    s1 = ht / ft
    # Game state, from second halves: observed / expected goals in each state.
    obs = {s: 0.0 for s in STATES}
    exp_ = {s: 0.0 for s in STATES}
    for r in rows:
        mh = math.exp(a_home + b * r["d"]) * (1 - s1)
        ma = math.exp(a_away - b * r["d"]) * (1 - s1)
        sh = state(r["hthg"] - r["htag"])
        obs[sh] += r["hg"] - r["hthg"]
        exp_[sh] += mh
        obs[-sh] += r["ag"] - r["htag"]
        exp_[-sh] += ma
    base = obs[0] / exp_[0]
    gamma = {s: math.log((obs[s] / exp_[s]) / base) for s in STATES}
    # The level state is the reference: fold its ratio into the second-half share.
    s2_scale = base
    return {"a_home": a_home, "a_away": a_away, "b": b, "s1": s1, "s2_scale": s2_scale,
            "gamma": {str(s): round(g, 4) for s, g in gamma.items()},
            "gamma_n": {str(s): round(exp_[s], 1) for s in STATES}}


def main():
    import sys
    sys.path.insert(0, str(ROOT))
    from sixth import winmodel
    rows = load()
    train = [r for r in rows if r["season"] in TRAIN]
    test = [r for r in rows if r["season"] in TEST]
    params = fit(train)
    params.update({"kappa": 4.0, "red_self": 0.70, "red_opponent": 1.30, "max_goals": 10})
    M = winmodel.WinModel(params)
    # 5. Calibration: one temperature T for all moments, fitted on the training seasons.
    def outcome0(r):
        return (1, 0, 0) if r["hg"] > r["ag"] else ((0, 1, 0) if r["hg"] == r["ag"] else (0, 0, 1))
    raw_train = [M.chances(0.0, 0, 0, r["elo_home"], r["elo_away"]) for r in train] + \
                [M.chances(2700.0, int(r["hthg"]), int(r["htag"]), r["elo_home"], r["elo_away"]) for r in train]
    outs = [outcome0(r) for r in train] * 2
    best = min((sum(sum((q - o) ** 2 for q, o in zip(winmodel.calibrate(p, T), out)) for p, out in zip(raw_train, outs)), T)
               for T in [1.0 + 0.02 * i for i in range(41)])
    params["temperature"] = round(best[1], 2)
    M = winmodel.WinModel(params)

    def outcome(r):
        return (1, 0, 0) if r["hg"] > r["ag"] else ((0, 1, 0) if r["hg"] == r["ag"] else (0, 0, 1))

    def brier(preds, rs):
        return sum(sum((p - o) ** 2 for p, o in zip(pr, outcome(r))) for pr, r in zip(preds, rs)) / len(rs)

    # Base rates from the training seasons: the forecast that knows nothing about the clubs.
    n = len(train)
    base = (sum(r["hg"] > r["ag"] for r in train) / n, sum(r["hg"] == r["ag"] for r in train) / n,
            sum(r["hg"] < r["ag"] for r in train) / n)
    res = {}
    pre = [M.chances(0.0, 0, 0, r["elo_home"], r["elo_away"]) for r in test]
    res["pre_match"] = {"model": brier(pre, test), "base_rates": brier([base] * len(test), test)}
    half = [M.chances(2700.0, int(r["hthg"]), int(r["htag"]), r["elo_home"], r["elo_away"]) for r in test]
    # A simpler half-time forecast: how often each half-time score ended in each result (training).
    table = {}
    for r in train:
        k = state(r["hthg"] - r["htag"])
        table.setdefault(k, [0, 0, 0])
        o = outcome(r)
        for i in range(3):
            table[k][i] += o[i]
    lookup = [tuple(v / sum(table[state(r["hthg"] - r["htag"])]) for v in table[state(r["hthg"] - r["htag"])])
              for r in test]
    # The model this replaces (sixth/metrics.py before 2026-10-25: 1.4 goals, no home advantage).
    from sixth.metrics import win_probabilities
    old = [win_probabilities(2700.0, int(r["hthg"]), int(r["htag"]), 0.5) for r in test]
    res["half_time"] = {"model": brier(half, test), "half_time_score_table": brier(lookup, test),
                        "previous_model": brier(old, test)}
    # Calibration at half-time: predicted home-win chance in bands against how often it happened.
    bands = []
    for lo in np.arange(0.0, 1.0, 0.1):
        sel = [(p[0], outcome(r)[0]) for p, r in zip(half, test) if lo <= p[0] < lo + 0.1]
        if len(sel) >= 15:
            bands.append({"from": round(float(lo), 1), "to": round(float(lo) + 0.1, 1), "matches": len(sel),
                          "predicted": round(sum(s[0] for s in sel) / len(sel), 3),
                          "happened": round(sum(s[1] for s in sel) / len(sel), 3)})
    res["half_time_calibration_home_win"] = bands
    res["test_matches"] = len(test)
    res["train_matches"] = len(train)
    params["validation"] = {k: ({kk: round(vv, 4) for kk, vv in v.items()} if isinstance(v, dict) else v)
                            for k, v in res.items()}
    OUT.write_text(json.dumps(params, indent=1), encoding="utf-8")
    print(json.dumps(params, indent=1))


if __name__ == "__main__":
    main()
