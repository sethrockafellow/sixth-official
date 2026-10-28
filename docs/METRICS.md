# Metrics: what each number means, and how it is worked out

Every number on the page and in a comment comes from the engine (`sixth/engine.py`,
`sixth/metrics.py`, `sixth/winmodel.py`, `sixth/insights.py`). The narrator only cites them, and
the verifier checks each citation. This page gives each metric's definition, what makes it valid,
and its limits.

## 1. Win chance

**Definition.** The chance that the home club wins, that the match is drawn, and that the away
club wins, at that moment. The three add up to 1.

**How it is calculated** (`sixth/winmodel.py`):

1. **Scoring rates before kick-off, from Elo.** Each club's Elo rating is calculated from earlier
   real results only (`scripts/build_history.py`). With d = (Elo home - Elo away) / 400:
   home goals per match = exp(0.384 + 0.667 d), away goals per match = exp(0.144 - 0.667 d).
2. **When goals come.** 44.6% of goals come in the first half. Inside a half the rate is flat.
3. **Game state.** A team's rate changes with its goal difference. Fitted on real second halves
   (the goals each team scored after half-time, given the half-time score): trailing by one,
   +8%; leading by one, +4%, against level.
4. **Evidence from the match.** Expected goals (xG) so far move each rate:
   rate x (4 + xG so far) / (4 + expected goals so far), kept between 0.5 and 2 times.
5. **Red cards.** A team with ten men scores at 0.70 of its rate; its opponent at 1.30.
6. **Play out the rest.** The rest of the match is played minute by minute over every possible
   goal difference. A goal changes the rates for the minutes after it. There is no random noise:
   the same inputs always give the same answer.

**Why it is valid.** It was fitted on 4,180 real matches (2010/11 to 2020/21) and tested on 1,520
later matches it never saw (2021/22 to 2024/25). Brier score: the mean squared error of the three
chances against what happened. Lower is better.

| Moment | This model | Simpler forecast | Model it replaced |
|---|---|---|---|
| Before kick-off | 0.571 | 0.644 (league base rates) | not tested |
| Half-time | 0.473 | 0.503 (how often each half-time score ended each way) | 0.505 |

Calibration at half-time, home win (test matches): when the model said 0 to 10%, home teams won 5%
of the time; 40 to 50%, 48%; 90 to 100%, 96%. The full table is in `sixth/win_model.json`
(`validation`). Rerun the fit and the test: `python scripts/fit_win_model.py`.

**Limits.**
- Home leads are a little less safe in recent seasons than the model says (it says 75 to 85%,
  and 70 to 77% happened). Home advantage has fallen since 2020; the fit used older seasons.
- Steps 4 and 5 are assumptions. The real data has no xG and no red-card minutes, so they could
  not be tested here. The red-card values are approximate figures from the research literature.
- In a synthetic match the Elo ratings are real (the clubs of the copied match), and the xG is
  synthetic.

## 2. Expected goals (xG)

**Definition.** The chance that a shot from that position becomes a goal:
1 / (1 + exp(-(-1.212 + 1.222 x angle - 0.1048 x distance))), angle in radians (how much of the
goal the shooter can see), distance in metres. A header counts half. A penalty is 0.76.

**Valid because** it is fitted to typical public open-play values (about 0.17 from 11 m straight on,
0.09 from 16 m, 0.03 from 25 m). **Limits:** those reference values are approximate, not one
dataset; there is no goalkeeper or defender position in the model.

## 3. Team metrics, last 10 minutes

| Metric | Definition | Reading it |
|---|---|---|
| Field tilt | The team's passes made in its attacking third, divided by both teams' passes in their attacking thirds | 50% is even. 70% means the team has the territory. |
| PPDA | Passes per defensive action: the opponent's passes in its own 60% of the pitch, divided by this team's tackles won, interceptions and fouls in that area | Lower means a harder press. Real teams: about 8 to 15. Capped at 30 (no defensive actions). |
| Duels won | Duels won by the team, divided by all duels (ground and aerial) | 50% is even. |
| xG, whole match | The sum of the team's shot xG | |

These are standard analyst definitions (field tilt and PPDA are used by public football
analytics sites). **Limit:** each is a count over 10 minutes, so it is noisy; the page never calls
a 10-minute value unusual unless it passes the test in section 5.

## 4. Momentum and the trigger

Momentum (0 to 1) weighs recent shots (by xG), passes and carries into the box, recoveries in the
attacking third and set pieces (corners, penalties, direct free kicks), with older actions
counting less (half-life about 3.5 minutes). It decides which moments get a comment, together with
the change in win chance. It is a heuristic, not a fitted model.

## 5. The dead-ball card

While the ball is dead (any restart after 10 seconds or more), the page shows a card made only
from data up to the moment the ball went out (`sixth/insights.py`).

**What if** (corners, penalties, free kicks in shooting range): how often such a set piece becomes
a goal, and the restarting team's win chance now and if this one goes in (from section 1).
The set-piece rates are approximate public figures: about 3 in 100 corners, 6 in 100 direct free
kicks, 78 in 100 penalties. They are estimates.

**Finding:** the biggest change in the last 5 minutes compared with the match before them. Eight
tests, four for each team:

| Test | Compared | Test used |
|---|---|---|
| Duels | share of duels won, last 5 minutes against before | exact binomial test |
| Passing | share of passes completed | exact binomial test |
| Territory | share of final-third passes | exact binomial test |
| Shots | shots in the last 5 minutes against the team's earlier rate | exact Poisson test |

Each test needs enough data: at least 6 events in the 5 minutes and 20 before; findings start
after 10 minutes, and the shots test after 15 minutes with at least 3 earlier shots.

**How "unusual" is decided.** Each p-value is the chance of a change at least this large if
nothing had really changed. Because 8 things are checked at every pause, the smallest p-value is
multiplied by 8 (the Bonferroni correction). "Unusual" means that corrected value is below 0.05.
If nothing passes, the card shows the biggest change and says it is within normal variation.
The correction is for one pause only. The page tests again at every pause, so over a whole match
some "unusual" cards are expected by chance alone.

**Limits.** Events in a match are not fully independent (one long spell of pressure makes many
duels), so the exact tests are a little too generous. Bonferroni partly offsets this. In this
demo about 1 in 4 cards shows an unusual change.

## 6. Running

Speeds are in km/h. From the 1 Hz tracking, each player gets his total distance and the metres in
five speed zones, as in FIFA's World Cup physical reports: walking 0 to 7 km/h, jogging 7 to 15,
running 15 to 20, high-speed running 20 to 25, sprinting over 25. A sprint (a run of seconds over
25 km/h) counts once. Top speed is the fastest second. "Pace per 90" scales the total distance to
90 minutes and compares it with the Premier League mean and standard deviation for the player's
position (Biology of Sport, 2019/20 and 2020/21): within 1 standard deviation is typical.
**Limits:** 1 Hz tracking misses short accelerations, so real sprint counts are higher; the
zone distances are not compared with a benchmark.
