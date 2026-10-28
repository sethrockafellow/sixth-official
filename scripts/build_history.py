"""scripts/build_history.py: make data/history/pl_matches.csv from the public season files.

  python scripts/build_history.py <folder with season-0910.csv ... season-2425.csv>

Source: football-data.co.uk match results, as mirrored by github.com/datasets/football-datasets
(datasets/premier-league/season-YYYY.csv). One row per Premier League match, 2009/10 to 2024/25:
6,080 matches.

What it writes, one row per match, in date order:
  season, date              when the match was played
  home, away                club codes (C01, C02 ...). The real club names are not kept: this
                            project shows fictional clubs only. The codes are given in order of
                            first appearance, so the same source files always give the same codes.
  elo_home, elo_away        each club's Elo rating before the match, from earlier results only
  hg, ag, hthg, htag        goals, full time and half-time
  hs, as, hst, ast          shots and shots on target
  hf, af, hc, ac            fouls committed and corners
  hy, ay, hr, ar            yellow and red cards

Elo (the usual football version): every club starts at 1500, a promoted club starts at 1420
(promoted clubs are usually weaker). After each match:
  expected home score  E = 1 / (1 + 10 ** (-(elo_home + HOME_ADV - elo_away) / 400))
  result               S = 1 win, 0.5 draw, 0 loss
  change               K * G * (S - E), where G grows with the goal margin
The rating before the match is what a pre-match forecast can use: nothing from the future.
"""
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history" / "pl_matches.csv"
SEASONS = ["0910", "1011", "1112", "1213", "1314", "1415", "1516", "1617",
           "1718", "1819", "1920", "2021", "2122", "2223", "2324", "2425"]
K, HOME_ADV, START, PROMOTED = 20.0, 65.0, 1500.0, 1420.0
COLS = ["season", "date", "home", "away", "elo_home", "elo_away", "hg", "ag", "hthg", "htag",
        "hs", "as", "hst", "ast", "hf", "af", "hc", "ac", "hy", "ay", "hr", "ar"]


def margin_factor(diff: int) -> float:
    """The goal-margin weight G of the World Football Elo ratings."""
    d = abs(diff)
    return 1.0 if d <= 1 else (1.5 if d == 2 else (11 + d) / 8)


def main(folder: Path):
    codes, elo, rows = {}, {}, []
    for s in SEASONS:
        with open(folder / f"season-{s}.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                for club in (r["HomeTeam"], r["AwayTeam"]):
                    if club not in codes:
                        codes[club] = f"C{len(codes) + 1:02d}"
                        elo[club] = START if s == SEASONS[0] else PROMOTED
                h, a = r["HomeTeam"], r["AwayTeam"]
                hg, ag = int(r["FTHG"]), int(r["FTAG"])
                rows.append({"season": f"20{s[:2]}/{s[2:]}", "date": r["Date"], "home": codes[h], "away": codes[a],
                             "elo_home": round(elo[h], 1), "elo_away": round(elo[a], 1),
                             "hg": hg, "ag": ag, "hthg": int(r["HTHG"]), "htag": int(r["HTAG"]),
                             "hs": int(r["HS"]), "as": int(r["AS"]), "hst": int(r["HST"]), "ast": int(r["AST"]),
                             "hf": int(r["HF"]), "af": int(r["AF"]), "hc": int(r["HC"]), "ac": int(r["AC"]),
                             "hy": int(r["HY"]), "ay": int(r["AY"]), "hr": int(r["HR"]), "ar": int(r["AR"])})
                e = 1.0 / (1.0 + 10 ** (-(elo[h] + HOME_ADV - elo[a]) / 400.0))
                res = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
                change = K * margin_factor(hg - ag) * (res - e)
                elo[h] += change
                elo[a] -= change
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} matches, {len(codes)} clubs -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
