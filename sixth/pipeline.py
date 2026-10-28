"""pipeline.py: one match, end to end.

  ingest     generate a synthetic match (events and 1 Hz tracking), or load one
  interpret  the engine computes a snapshot after every event: score, win chances, momentum ...
  explain    for each moment that a persona's trigger fires on, the narrator writes a comment
             from its tools; the verifier checks every claim; one retry, then a template
  render     the result is one JSON file the screen replays: the timeline and every comment,
             with its evidence, its tool calls and what the verifier stopped
  personalize three personas get different moments; each comment comes in English and Spanish

Run it:  python -m sixth.run --seed 4 --narrator template
         python -m sixth.run --seed 4 --narrator foundry     (needs az login and the two settings)
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time
from pathlib import Path

from . import engine as engine_mod
from . import generate
from .roster import CLUBS, PLAYERS
from .schema import DEFAULT_PERSONAS, EvidenceItem, NarrativeOutput
from .tools import MatchTools
from . import insights
from .triggers import fire_triggers, is_goal
from .verifier import VerifierStore, catch_rate, fallback_output, verify

LANGUAGES = ("en", "es")


def build_store(E) -> VerifierStore:
    return VerifierStore(events=E.event_by_id, states=E.snapshot_by_id,
                         physical={r.physical_id: r for r in E.physical},
                         deltas={e.event_id: E.deltas_for(e) for e in E.events})


def to_output(draft: dict, trig, lang: str, n: int) -> NarrativeOutput:
    ev = []
    for e in draft["evidence"]:
        ev.append(EvidenceItem(claim=str(e.get("claim", "")), source=str(e.get("source", "")),
                               value=e.get("value") if isinstance(e.get("value"), (int, float, str)) else str(e.get("value")),
                               unit=e.get("unit") if e.get("unit") in ("probability", "xg", "index", "m", "mps", "s", "count", "label") else "label",
                               label_metric=e.get("label_metric") or None))
    if not ev:
        raise ValueError("no evidence")
    p = trig.persona
    return NarrativeOutput(output_id=f"o{n:04d}", event_id=trig.event_id, match_clock_s=trig.match_clock_s,
                           user_id=p.persona_id, mode=p.mode, language=lang, text=draft["text"], evidence=ev,
                           importance=trig.surprise, status="fallback", attempts=1)


def failure_list(r) -> list[dict]:
    return [{"check": f.check, "detail": f.detail, "claim": f.claim, "source": f.source} for f in r.failures]


async def narrate_one(narrator, E, store, trig, lang, n):
    """One comment: draft, verify, retry once, then the template. Returns its record."""
    payload = trig.payload(lang).model_dump()
    tools = MatchTools(E, trig.match_clock_s)
    rec = {"tries": [], "tool_calls": tools.calls}
    out, draft = None, None
    for attempt in (1, 2):
        try:
            if attempt == 1:
                draft, info = await narrator.draft(payload, tools)
            else:
                draft, info = await narrator.draft(payload, tools, previous=draft, failures=fails_obj)
            cand = to_output(draft, trig, lang, n)
            r = verify(cand, store, trig.match_clock_s)
            rec["tries"].append({"draft": draft, "passed": r.passed, "failures": failure_list(r), **info})
            if r.passed:
                cand.status, cand.attempts = ("verified", 1) if attempt == 1 else ("verified_on_retry", 2)
                out = cand
                break
            fails_obj = r.failures
        except Exception as e:   # an unreadable answer or a model error counts as a failed try
            rec["tries"].append({"draft": draft, "passed": False,
                                 "failures": [{"check": "unreadable", "detail": f"{type(e).__name__}: {e}"[:300]}]})
            fails_obj = []
            if draft is None:
                draft = {"text": "", "evidence": []}
    if out is None:
        base = NarrativeOutput(output_id=f"o{n:04d}", event_id=trig.event_id, match_clock_s=trig.match_clock_s,
                               user_id=trig.persona.persona_id, mode=trig.persona.mode, language=lang, text="-",
                               evidence=[EvidenceItem(claim="-", source="-", value="-", unit="label")],
                               importance=trig.surprise, status="fallback", attempts=2)
        out = fallback_output(base, store)
    rec["output"] = out.model_dump()
    rec["merged"] = trig.merged
    rec["air_s"] = trig.air_s
    rec["is_goal"] = trig.is_goal
    return rec


def timeline(E) -> dict:
    """What the screen draws: the score and win chances over time, and the notable events."""
    series, notable = [], []
    for s in E.snapshots:
        ms = s.match_state
        series.append([round(ms.match_clock_s, 1), round(ms.win_prob_home, 4), round(ms.draw_prob, 4),
                       round(s.home.momentum, 4), ms.score_home, ms.score_away,
                       # v2: [6..11] field tilt, PPDA and duels won (home, away), [12, 13] xG totals
                       round(s.home.field_tilt, 3), round(s.away.field_tilt, 3), round(s.home.ppda, 1),
                       round(s.away.ppda, 1), round(s.home.duels_won_share, 3), round(s.away.duels_won_share, 3),
                       round(s.home.xg_total, 2), round(s.away.xg_total, 2)])
    for e in E.events:
        kind = e.type
        if kind == "shot" or (kind == "foul" and getattr(e, "card", None)) or kind == "save":
            notable.append({"event_id": e.event_id, "t": e.match_clock_s, "type": kind, "team_id": e.team_id,
                            "player": PLAYERS.get(e.player_id, e.player_id),
                            "outcome": getattr(e, "shot_outcome", None) or getattr(e, "card", None),
                            "xg": getattr(e, "xg", None), "goal": is_goal(e)})
    # every event, compact, for the pitch view:
    # [t, type, team (0 home, 1 away), x, y, end x, end y, outcome, player, pass type]
    # pass type (2026-10-25): ground, long, cross or through for passes, else None.
    # v2: [.., pass type, kind, extra]: kind is the restart type, duel type or card; extra is the
    # dead-ball seconds for a restart, the height of a pass, or the duel context.
    types = ["pass", "carry", "shot", "save", "recovery", "pressure", "foul", "offside", "duel", "clearance", "restart"]
    events = []
    for e in E.events:
        ex, ey = getattr(e, "end_x_m", None), getattr(e, "end_y_m", None)
        out = getattr(e, "shot_outcome", None) or e.outcome
        events.append([round(e.match_clock_s, 1), types.index(e.type), 0 if e.team_id == "home" else 1,
                       round(e.x_m, 1), round(e.y_m, 1), None if ex is None else round(ex, 1),
                       None if ey is None else round(ey, 1), out, PLAYERS.get(e.player_id, e.player_id),
                       getattr(e, "pass_type", None),
                       getattr(e, "restart_type", None) or getattr(e, "duel_type", None) or getattr(e, "card", None),
                       round(e.dead_s, 1) if e.type == "restart" else (getattr(e, "height", None) or getattr(e, "context", None))])
    # keep the series small: one point every 30 s, plus every change of score
    small, last_t, last_score = [], -1e9, None
    for row in series:
        if row[0] - last_t >= 30 or (row[4], row[5]) != last_score:
            small.append(row)
            last_t, last_score = row[0], (row[4], row[5])
    return {"series": small, "notable": notable, "event_types": types, "events": events}


from .formations import team_sheet  # noqa: E402


async def run_match(seed: int, narrator, languages=LANGUAGES, limit: int | None = None,
                    concurrency: int = 4, log=print) -> dict:
    t0 = time.perf_counter()
    match = generate.generate_match(seed)
    E = engine_mod.ReferenceStateEngine(match)
    cards, _ = insights.deadball_cards(E)
    store = build_store(E)
    triggers = fire_triggers(E, DEFAULT_PERSONAS)
    if limit:
        triggers = triggers[:limit]
    log(f"seed {seed}: {len(E.events)} events, final score {match['final_score']}, {len(triggers)} moments "
        f"x {len(languages)} languages")
    jobs = [(trig, lang) for trig in triggers for lang in languages]
    sem = asyncio.Semaphore(concurrency)
    records = [None] * len(jobs)

    async def go(i, trig, lang):
        async with sem:
            records[i] = await narrate_one(narrator, E, store, trig, lang, i + 1)
            o = records[i]["output"]
            log(f"  {i + 1}/{len(jobs)} {o['user_id']:<16} {lang} {o['status']:<17} {o['text'][:70]}")

    await asyncio.gather(*(go(i, t, l) for i, (t, l) in enumerate(jobs)))
    outs = [NarrativeOutput(**r["output"]) for r in records]
    stopped = [{"output_id": r["output"]["output_id"], "user_id": r["output"]["user_id"],
                "language": r["output"]["language"], "event_id": r["output"]["event_id"],
                "t": r["output"]["match_clock_s"], "draft": t["draft"], "failures": t["failures"]}
               for r in records for t in r["tries"] if not t["passed"]]
    return {
        "made": datetime.datetime.now().isoformat(timespec="seconds"),
        "seed": seed, "narrator": narrator.name, "model": getattr(narrator, "model", None),
        "clubs": CLUBS, "players": PLAYERS, "lineup": team_sheet(match), "final_score": match["final_score"],
        "history": {k: match["history"][k] for k in ("season", "date", "row", "elo_home", "elo_away", "targets", "source")},
        "pre_match": list(E.snapshots[0].match_state.model_dump()[k] for k in ("win_prob_home", "draw_prob", "win_prob_away")),
        "deadball": cards,
        "personas": [p.model_dump() for p in DEFAULT_PERSONAS], "languages": list(languages),
        "timeline": timeline(E), "comments": records, "stopped": stopped,
        "catch": catch_rate(outs), "seconds": round(time.perf_counter() - t0, 1),
    }


def save(result: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, default=str), encoding="utf-8")
    return path
