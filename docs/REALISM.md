# How realistic is the synthetic match?

The generator makes every match from a seed. Since 2026-10-25 (version 2) each seed copies the box
score of one real Premier League match, and play is simulated around it. This page lists what the
generator is calibrated to, what it measures, and what is still simplified. `tests/test_match.py`,
`tests/test_tracking.py`, `tests/test_formations.py` and `tests/test_v2.py` fail if these numbers
drift. The metrics and the win chance are in `docs/METRICS.md`.

## 1. Real matches drive each synthetic match

`data/history/pl_matches.csv` holds 6,080 real Premier League matches, 2009/10 to 2024/25. Source:
football-data.co.uk results, as mirrored at github.com/datasets/football-datasets.
`scripts/build_history.py` makes the file. For each match it keeps:

- the season and the date
- goals at half-time and full time
- shots, shots on target, fouls, corners, yellow cards and red cards, for each side
- each club's Elo rating before the match, calculated only from earlier results

The real club names are removed: each club is a code (C01, C02 ...). The page shows fictional clubs
and players only.

Each seed picks one match (`sixth/history.py`). The simulator (`sixth/sim.py`) then plays a match
that ends with the same box score. It uses quota control: the chance of a shot, a corner, a foul
or a card goes up or down with how many the real match still has to come in the time left. A team
that still owes a goal in a half becomes urgent near the end of that half, and scores.

**Box score copied, 50 matches (seeds 1000 to 1049), per team:**

| Total | Exact | Within 1 |
|---|---|---|
| Goals, first half | 100% | 100% |
| Goals, second half | 100% | 100% |
| Yellow cards | 100% | 100% |
| Red cards | 100% | 100% |
| Shots on target | 97% | 100% |
| Fouls | 96% | 99% |
| Shots | 93% | 100% |
| Corners | 93% | 100% |

Goal minutes are not in the source data. The simulator chooses them, so the score at half-time
and at full time is real, and the minutes are synthetic.

## 2. Measured against the Premier League (50 matches, seeds 1000 to 1049)

Per match, both teams together.

| Measure | Generator | Premier League | Source |
|---|---|---|---|
| Passes | 878 | 893.5 (2024/25) | Opta, via premierleague.com |
| Pass completion | 81.7% | 83.7% (2024/25) | Opta, via premierleague.com |
| Long passes (32 m or more), share | 10.1% | 10.5% (2024/25) | Opta, via theanalyst.com |
| Open-play crosses | 25.1 | 22.4 (2024/25) | Opta, via premierleague.com |
| Shots | 26.0 | 25.9 (2024/25) | the real box scores |
| Goals | 2.9 | 2.9 (2024/25) | the real box scores |
| Fouls | 21.8 | 22.1 (2024/25) | the real box scores |
| Corners | 10.4 | 10.3 (2024/25) | the real box scores |
| Throw-ins | 37.4 | 35.8 (2025/26) | Opta, via theanalyst.com |
| Goal kicks | 14.6 | 15.5 (2025/26) | Opta, via theanalyst.com |
| Offsides | 3.5 | about 3 to 4 | approximate |
| Ball in play, minutes | 48.5 of 90 | about 57 of about 99 | Opta, via theanalyst.com |

**Ball in play is lower than real, on purpose.** Each restart waits as long as the Premier League
average for its kind (section 4). Real matches add about 9 minutes of stoppage time; this clock
stops at 90 minutes. So the same dead time fits into a shorter match: 54% of the clock is in play
here, against about 58% in real matches.

## 3. How play is simulated

Every few seconds the team with the ball does one thing. In order of how the chance is set:

1. **Shot,** only in the final 35 m, at a base rate scaled by quota control.
2. **Foul** by the defending side (lower inside the box), scaled by quota control.
3. **Carry,** sometimes a take-on: the carrier beats his man (55%) or loses a tackle.
4. **Through ball,** from 55 to 78 m up the pitch: about 3 in 10 are offside, timed in the
   tracking so the runner is really offside at the pass.
5. **Pass:** a cross from a wide area in the final third, a long ball, or a ground pass, with the
   calibrated lengths and directions of version 1. The receiver is the teammate whose place in the
   formation is nearest the target.

**What happens to a failed pass:** it goes out (a throw-in, a goal kick, or off a defender for a
corner), it is intercepted, it is picked up loose, or it becomes a 50-50 (a ground duel).

**Duels.** A ground duel is a 50-50, a tackle or a take-on. An aerial duel is a long ball, a cross,
a corner, a goal kick or a clearance that two players go up for. The winner keeps the ball. The
side that takes more shots in the real match wins slightly more duels and completes slightly more
passes, so territory follows the box score. Per match: about 99 ground duels and 48 aerial duels
(no published league figure for this exact definition).

**Pressure.** Before about a quarter of passes (24%) an opponent closes the player down: a
pressure event, and the pass is marked `under_pressure`. Pressure is more likely near either goal
and from the side that dominates the real match. Passes under pressure are completed 69% of the
time, other passes 86%. The share and the cost are estimates, chosen so the overall completion
stays near the league figure.

**Clearances.** A defender who wins a high ball in his box clears it: upfield, out for a throw-in,
or behind for a corner.

## 4. Dead balls and restarts

When the ball goes out or the referee stops play, the simulator waits before the restart. The
wait is drawn around the Premier League average for that restart (Opta, via theanalyst.com):

| Restart | Average wait | Season of the figure |
|---|---|---|
| Throw-in | 17.8 s | 2025/26 |
| Goal kick | 30.4 s | 2025/26 |
| Corner | 36.1 s | 2025/26 |
| Free kick | 33.3 s | 2026/27, first five matchweeks |
| Direct free kick (shot at goal) | 74.5 s | 2026/27, first five matchweeks |
| Kick-off after a goal | 60 s | estimate |
| Penalty | 90 s | estimate |
| Extra time for a card | 20 s | estimate |

During the wait the players set up: for a corner, about five attackers go into the box and every
defender comes back; for a penalty, everyone else stands outside the box; for a kick-off, each
team is in its own half. The ball is carried to the spot. Every restart after a wait of 10 s or
more gets a card on the page (`docs/METRICS.md`, section 5).

## 5. Ball height

Each pass, cross, corner, goal kick, clearance and shot has a height: ground, low (under head
height) or high. A lofted ball flies in a parabola between its start and its end:

| Ball | Peak height |
|---|---|
| Low pass or chip | 1 to 2.5 m |
| Cross, corner, free kick into the box | 4 to 7.5 m |
| Other long pass | about 0.2 x its length, 4 to 16 m |
| Goal kick, clearance | 9 to 18 m |
| Shot | 0.6 to 3.5 m |

A cross or corner met by a header ends at head height (2.2 m), not on the grass. The tracking
has the height every second (`z_m`), and the page draws it from the flights, so it moves smoothly.

## 6. Running, against Premier League means

The page shows speeds in km/h. The 1 Hz tracking gives each player's distance in five speed zones,
the zones FIFA uses in its World Cup physical reports: walking 0 to 7 km/h, jogging 7 to 15,
running 15 to 20, high-speed running 20 to 25, sprinting over 25. It also gives the number of
sprints and the top speed. Per match, 3 matches (seeds 1000 to 1002):

| Position | Total | Walk | Jog | Run | High-speed | Sprint | Sprints | Top speed |
|---|---|---|---|---|---|---|---|---|
| Defenders | 10.1 km | 3,554 m | 4,728 m | 1,152 m | 630 m | 85 m | 9 | 31 km/h |
| Midfielders | 11.0 km | 2,769 m | 5,441 m | 1,892 m | 768 m | 80 m | 7 | 34 km/h |
| Forwards | 11.4 km | 3,192 m | 4,204 m | 2,120 m | 1,555 m | 322 m | 24 | 34 km/h |
| Keepers | 4.6 km | 4,123 m | 332 m | 181 m | 0 | 0 | 0 | 19 km/h |

Reference: Premier League means by position, 2019/20 and 2020/21 (Biology of Sport; 38 matches,
16 outfield players). Its thresholds are 19.8 and 25.2 km/h, close to FIFA's 20 and 25.

| Position | Distance | Over 19.8 km/h | Over 25.2 km/h | Top speed |
|---|---|---|---|---|
| Defenders, real | 10.0 km | 697 m | 151 m | 34.7 km/h |
| Midfielders, real | 11.6 km | 992 m | 158 m | 33.7 km/h |
| Forwards, real | 10.7 km | 941 m | 202 m | 35.4 km/h |

How the generator gets there: one top speed for everyone (34.2 km/h), and only players who are
doing something may run fast. The man on the ball, the man closing him down and the receiver go up
to 24.8 km/h (forwards 20.5 km/h). A runner timing a through ball, a player chasing a long ball or
racing for a 50-50, and the player furthest out of position when the ball is lost may sprint (one
recovery sprint per player every 45 s at most). Everyone else moves at most 18.7 km/h. The
referee covers about 9.9 km and the assistants about 5.3 km. The page compares only the total
distance with the benchmark; the zone distances have no published benchmark checked here.

**Known gap:** forwards run fast (over 20 km/h) about twice as far as real forwards.

**Touches (2026-10-27).** A player who passes, clears or shoots stays where he struck the ball;
before, he ran after his own pass for up to 3 s. The player who will touch the ball next (wins a
50-50, picks up a loose ball, intercepts, saves) heads for that spot in the 3 s before, at a busy
player's pace. In seed 4, in the 1 Hz tracking, the distance between a player and the ball he plays fell at the
90th percentile from 9.2 m to 7.8 m (the median stays about 2.9 m). The page then closes the
rest (section 11). The running table above is measured after this change.

## 7. Formations

Unchanged from version 1. Each team has a set-up formation (`sixth/formations.py`), played
differently with and without the ball (a 4-3-3 defends as a 4-5-1, a 3-5-2 as a 5-3-2). Shape
changes take a few seconds. Each player drifts about 3 m over 20 to 50 minutes. A team behind
after about the hour switches to a more attacking shape; a team ahead from about 75' drops into a
5-4-1. The detector fits every template to each 15-minute block (the Hungarian method) and names
the shape played in 91% of blocks without the ball and 100% with it.

**Red cards (version 2):** a player sent off walks to the touchline and leaves the play. His team
plays on with ten, with his place in the shape left empty.

## 8. Shirt numbers and positions

Each player has a fixed squad number (`SHIRT` in `sixth/roster.py`) in every match. Larkspur FC
uses the traditional 1 to 11 pattern with one 14; Copper Vale has a modern spread (31 in goal).
The position is the slot in the starting formation. The narrator never writes numbers.

## 9. Shots and expected goals (xG)

Shots happen only in the final 35 m. The xG curve (`MetricConstants` in `sixth/schema.py`) gives
about 0.17 from 11 m straight on, 0.09 from 16 m and 0.03 from 25 m (typical public open-play
values, approximate). A shot that must be a goal (to copy the box score) is taken from a good
position if the current one is poor (xG under 0.12). A header has half the xG of a shot with the
foot. A penalty is 0.76.

## 10. Still simplified

- **Positions are modelled,** not tracked. There is no man-marking.
- **Goal minutes, shot locations and who scores are synthetic.** Only the totals are real.
- **No substitutions.** Formation changes happen without one.
- **No second yellow cards.** A red card is always a straight red.
- **Penalties are rare:** about 0.1 a match, against about 0.3 in real matches.
- **No stoppage time.** The match is exactly 90 minutes, so the ball is in play less of the time.
- **Forwards' high-speed running** is about twice the real figure (section 6).
- **Duel and pressure rates have no exact league figure** for these definitions: they are
  estimates.
- **The xG reference values** are typical public values, not a fitted model of real shots.

## 11. Between the seconds: how the page draws movement (2026-10-27)

The tracking has one position a second. The page (`app/web/motion.js`) samples the match at the
screen's rate instead of drawing straight lines between seconds:

- **The ball** moves from touch to touch at the exact event times (`touches` in
  `/api/tracking`, from `sixth/generate.py` `ball_touches`). About 4 touches in 10 happen less
  than a second apart, so straight lines between seconds skipped them. A struck ball slows as it
  arrives; a run with the ball moves at 5.5 m/s.
- **Players** follow a smooth curve through their 1 Hz positions (a Catmull-Rom spline) and are
  drawn to the ball when they play it or receive it: just behind it when they strike it, and with
  it at their feet between their own touches. Measured on seed 4: a player is 0.45 m from every
  ball he plays (the set distance), against a median of 2.9 m and a 90th percentile of 7.8 m
  with straight lines between seconds. The sprint limit below can hold a player back a moment.
- **Nobody is drawn faster than a sprint** (10.5 m/s) from one drawn frame to the next: where
  the data asks for more, the player arrives a moment late.
- **In the player camera,** each figure faces where it runs (or the ball, standing), leans into
  a run and bobs once a stride; the camera bobs with the player's stride.
- **Offside decisions** still use the 1 Hz positions, so they stay exactly as the events say.

Still simplified: nobody kicks, jumps or dives, and passes are chosen by a model of the shape,
not by players reading the game. A close look at 1x still shows a simulation.

## Sources

- Real box scores: football-data.co.uk Premier League results, 2009/10 to 2024/25, via
  github.com/datasets/football-datasets (datasets/premier-league)
- Passing and long balls per match: premierleague.com/en/news/4426039
- Long passes as a share of all passes, 2024/25: theanalyst.com/articles/premier-league-long-balls-pressing-errors-stats
- Open-play crosses and cross accuracy, 2024/25: premierleague.com/en/news/4148090
- Ball in play and restart times: theanalyst.com/articles/premier-league-rules-throw-ins-goal-kicks-ball-in-play
  and theanalyst.com/articles/premier-league-delays-set-piece-throw-in-stats
- Running by position: Biology of Sport, "The relationships between distances covered above
  generic and relative speed thresholds by male soccer players in English Premier League matches
  across two competitive seasons" (termedia.pl)
