# Sixth Official

**Match commentary that checks its own facts.** Sixth Official turns a synthetic football match into
short, personalized comments for each viewer, written by an AI agent on Microsoft Foundry. Each
number and label the agent cites is checked against the match data before it airs. A comment that
fails goes back to the agent once with the list of failures; if it fails again, a plain template
sentence airs instead. The checks are on cited numbers and labels, not on the meaning of every
word: see [Known limitations](#known-limitations).

**Live site:** https://sixth-official.niceriver-a2594222.eastus2.azurecontainerapps.io/ (Azure Container Apps)

Built for the Microsoft x Premier League *Inside the Game* developer hackathon. Clubs, players and
play are synthetic and fictional. Each match copies the box score of one real Premier League match
(goals in each half, shots, corners, fouls and cards), so its story follows real football.

> Status (2026-10-27, version 2): set pieces and dead-ball time, duels and pressure, ball height,
> real box scores, a win-chance model tested on 1,520 real matches, dead-ball cards with
> significance tests, running in km/h against Premier League means, a key-moments replay, a 3D
> player camera, a broadcast-style page, a glossary and a full-time summary. Details:
> `docs/REALISM.md` and `docs/METRICS.md`.

## The five stages

| Stage | What happens | Where |
|---|---|---|
| Ingest | A seeded simulator plays a full match that copies one real box score: passes, carries, take-ons, duels, pressure, clearances, shots, saves, fouls, cards, offsides, and restarts with Premier League dead-ball times, plus 1 Hz tracking of the ball (with height), all 22 players and the 4 officials | `sixth/history.py`, `sixth/sim.py`, `sixth/generate.py` |
| Interpret | After every event the engine computes a snapshot: score, win, draw and loss chances (a model fitted and tested on real matches), momentum, pressing, line height and block, possession share, xG, field tilt, PPDA, duels won. Each dead ball gets a card with a tested finding | `sixth/engine.py`, `sixth/metrics.py`, `sixth/winmodel.py`, `sixth/insights.py` |
| Explain | Each persona's trigger picks the moments that matter to it. The narrator agent (Microsoft Agent Framework on a Foundry model) calls tools for the facts, writes the comment and cites each fact; the verifier checks every claim | `sixth/triggers.py`, `sixth/tools.py`, `sixth/narrator.py`, `sixth/verifier.py` |
| Render | One JSON file per match: the timeline and every comment with its evidence, its tool calls, and the drafts the verifier stopped | `sixth/pipeline.py` |
| Personalize | Three personas get different moments and different writing: an analyst, a home fan, a player follower. Every comment in English and Spanish | `sixth/schema.py`, `sixth/prompts/narrator.md` |

## What the verifier checks

Every claim in a comment has an evidence item: the exact words, a source path into the match data
(for example `s_e000412.win_prob_home`), the value, and the unit. The verifier stops a comment when:

1. a sentence has no checked claim;
2. a claim's words are not in the text;
3. a source does not exist, or is later than the moment (the future does not exist yet);
4. the reported value differs from the stored value;
5. the number written in the text differs from the stored value (68% for 0.684 is fine; 80% is not);
6. a label (for example "big chance", or the Spanish "ocasión clara") does not fit the stored number;
7. a number in the text is not part of any claim;
8. a causal word ("because", "porque") has no measured change behind it.

`tests/test_verifier.py` plants each of these errors into good comments and checks that it is stopped.

What the verifier does **not** check: the words around a number (who did it, which team, the unit
and the period). It trusts the agent to cite the right source for the subject of the sentence.

## Known limitations

- **One number per claim.** The verifier compares the first number in each claim with its source.
  If a claim holds a second number, that second number is not compared with anything.
- **Subject and unit come from the agent.** "Copper Vale have 0.9 xG" passes if the cited value is
  0.9, even if the source is Larkspur's xG. The tools show the agent the team and player names
  for each source, but the verifier does not compare them with the sentence.
- **The bundled Foundry match was narrated before the 2026-10-27 verifier fix.** Before the fix, a
  source path to a field that did not exist passed without a value check, and a measured change
  (a delta) from later in the match was not stopped. Those comments have not been checked again
  with the fixed verifier; new runs use it.
- **The "unusual" findings are tested again at every pause.** Each test is corrected for the 8
  things checked at one pause (Bonferroni), not for looking again and again through the match. Over
  a whole match, some "unusual" cards are expected by chance. See `docs/METRICS.md`, section on
  dead-ball findings.
- **Synthetic data.** The players and the play are generated from averages; at 1x in the player
  camera the movement can look unnatural.
- **Engineering.** No lockfile (the versions in `requirements.txt` are minimums); the page script
  `app/web/app.js` is one large file; some tests compare against saved numbers from one seed.

## Run it

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q tests                              # 61 tests, no Azure needed
python -m sixth.run --seed 4 --narrator template       # a full match, rule-based comments, no Azure
```

With Microsoft Foundry (a project with a deployed model, for example `gpt-5-mini`):

```bash
cp .env.example .env          # then fill in FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL
az login                      # the code signs in as you: no keys
python -m sixth.check_foundry # one comment, with the tool calls and the verifier's result
python -m sixth.run --seed 4 --narrator foundry --limit 3   # three moments
python -m sixth.run --seed 4 --narrator foundry             # the full match
```
## Video
https://media.rockafellowlabs.com/SixthOfficial.mp4

## The replay page

```bash
python -m app.server          # then open http://localhost:8000
```

It replays a narrated match from `data/`: the scoreboard, the pitch, the win chances over time
(the future stays dimmed), and the match log with the three viewers' comments side by side.
Click any comment to see each cited fact behind it, its source and stored value, the tools the agent
called, and any draft the verifier stopped, with the reason. English and Spanish.

The site calls no model: matches are narrated beforehand with `python -m sixth.run`, so testing it
costs nothing.

The page opens on All players, with a short "How to use this page" guide (English and Spanish).

Views: Latest play, All players (offside line, officials, ball height, speed trails), Heat map,
Shape (formation per 15-minute block) and Running (distance in FIFA's five speed zones, walking
to sprinting, in km/h, against Premier League means). Also on the page:

- **Key moments:** a drop-down of goals, penalties, cards, big chances, saves, corners and
  through balls, filled in as they happen (as in a live match). Picking one replays the 8
  seconds before it and holds on the moment, with the players in it ringed and labelled.
- **Player camera:** a 3D view from a player's (or the referee's) eyes, in step with the
  replay. Open it from a key moment or by clicking a player. Hold the middle mouse button and
  move to turn his head. Players are capsules; the ball flies at its tracked height.
- **Zoom:** the mouse wheel over the pitch zooms around the pointer (and never scrolls the
  page); drag to move; Follow the ball.
- **Hover labels:** point at a player for his number, name, position, club and speed.
- **Glossary:** `glossary.html` explains every term (xG, PPDA, duels, field tilt ...); the stat
  names link to it.
- **Win chance chart:** click any minute (or use the arrow keys) to go there.
- **Kit colors:** pick each club's color; the page keeps every text at WCAG AA contrast.
- **Half-time switch:** the teams change ends for the second half.
- **Dead-ball cards:** while the ball is dead, what the restart could change and the most unusual
  change of the last 5 minutes.
- **Full time:** a large final-score notice and a match report. The pitch and the replay stay.

Refit and retest the win-chance model: `python scripts/fit_win_model.py`.

## Deploy to Azure Container Apps

```bash
az extension add --name containerapp --upgrade
az containerapp up --name sixth-official --resource-group sixth-official-rg --location eastus2 \
    --environment sixth-official-env --source .
```

The command builds the image in Azure from the `Dockerfile` (no local Docker needed), creates a
container registry and a Container Apps environment, and prints the site's URL.

## Microsoft technology

- **Microsoft Foundry**: the model behind every comment (`FoundryChatClient`).
- **Microsoft Agent Framework**: the narrator agent and its function tools; the tool-call loop.
- **Azure Container Apps**: the judges' site.

## Who built it

Seth Rockafellow (RockafellowLabs), with AI coding assistance.

## License

MIT

## Third-party files in the page

- Atkinson Hyperlegible (Braille Institute) and Doto fonts (`app/web/fonts`), SIL Open Font License 1.1
  (`OFL-Atkinson-Hyperlegible.txt`, `OFL-Doto.txt`).
- three.js r149 (`app/web/vendor/three.min.js`), MIT License (`three-LICENSE.txt`), for the player camera.
