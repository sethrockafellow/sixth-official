# verifier.py - the verifier: checks every claim in a comment against the match data (schema.py).
# Checks evidence by source path, retries once, then falls back to a template sentence.
# All seven spec checks in order; any failure means fail. Catch rate is the demo number.

import re
from typing import Any, Callable, Optional

from .schema import (
    EvidenceItem, NarrativeOutput, VerificationResult, CheckFailure,
    TOLERANCE, LABEL_BANDS, CAUSAL_WORDS,
)

# A sentence ends at . ! or ? followed by a space or the end, so "0.62" stays inside its sentence
# (fixed 2026-10-24: the old pattern split "momentum is 0.62." into two sentences).
_SENT = re.compile(r".+?(?:[.!?]+(?=\s|$)|$)", re.S)
_NUM = re.compile(r"\d+(?:\.\d+)?")

# Added 2026-10-24: the labels as a Spanish viewer reads them, so a Spanish label is checked too.
LABEL_ALIASES = {
    "on_top": ["dominando", "dominan", "domina", "mandan", "manda"],
    "even": ["igualado", "igualada", "parejo", "pareja"],
    "under_pressure": ["bajo presión", "sometido", "sometidos"],
    "intense press": ["presión intensa", "presión alta"],
    "normal press": ["presión normal", "presión media"],
    "sitting off": ["repliegue", "replegado", "replegados", "esperando atrás"],
    "big chance": ["ocasión clara", "gran ocasión"],
    "half chance": ["media ocasión", "ocasión a medias"],
    "long shot": ["disparo lejano", "tiro lejano", "desde lejos"],
}


def _claim_number(claim: str, unit: str, value) -> tuple[bool, str]:
    """Added 2026-10-24. The number written in a claim must be the cited value.
    Before this check, a text could say 80% while citing a stored 0.68, and pass."""
    nums = _NUM.findall(claim.replace(",", "."))
    if not nums or unit == "label":
        return True, ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "value is not numeric"
    shown = float(nums[0])
    if unit == "probability" or "%" in claim:
        target, tol = v * 100.0, 1.0           # whole percents: 0.684 may be written 68%
    else:
        decimals = len(nums[0].split(".")[1]) if "." in nums[0] else 0
        rounding = 0.5 * 10 ** -decimals       # 21.4 m may be written 21 m
        target, tol = v, max(TOLERANCE.get(unit) or 0.0, rounding)
    if abs(shown - target) > tol + 1e-9:
        return False, f"the claim says {nums[0]}{'%' if unit == 'probability' else ''}, the source is {value}"
    return True, ""


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.findall(text) if s.strip()]


def _dig(obj: Any, parts: list[str]):
    """Walk attribute or key paths. None if any step is missing."""
    cur = obj
    for p in parts:
        if cur is None:
            return None
        if isinstance(cur, dict):
            if p not in cur:
                return None
            cur = cur[p]
        elif hasattr(cur, p):
            cur = getattr(cur, p)
        else:
            return None
    return cur


class VerifierStore:
    """Read-only view over the three append-only stores, keyed by id."""

    def __init__(self, events=None, states=None, physical=None, deltas=None):
        self.events = events or {}
        self.states = states or {}
        self.physical = physical or {}
        self.deltas = deltas or {}

    def resolve(self, source: str, at_s: float):
        """Return (found, time_ok, value) for a source path at or before at_s."""
        head, _, path = source.partition(".")
        if not path:
            return False, False, None
        parts = path.split(".")
        if head.startswith("s_"):
            snap = self.states.get(head)
            if snap is None:
                return False, False, None
            if snap.match_state.match_clock_s > at_s:
                return True, False, None
            v = _dig(snap, parts)
            if v is None:
                v = _dig(getattr(snap, "match_state", None), parts)
            return True, True, v
        if head.startswith("p_"):
            row = self.physical.get(head)
            if row is None:
                return False, False, None
            if float(row.match_clock_s) > at_s:
                return True, False, None
            return True, True, _dig(row, parts)
        ev = self.events.get(head)
        if ev is None:
            return False, False, None
        if parts[0] == "deltas":
            d = self.deltas.get(head)
            if not d:
                return False, False, None
            return True, True, _dig(d, parts[1:])
        if ev.match_clock_s > at_s:
            return True, False, None
        return True, True, _dig(ev, parts)


def verify(output: NarrativeOutput, store: VerifierStore, at_s: float) -> VerificationResult:
    """Run the seven spec checks in order. Any failure means fail."""
    f: list[CheckFailure] = []
    text = output.text
    sentences = split_sentences(text)

    # 1. sentence rule
    for s in sentences:
        if not any(ei.claim in s for ei in output.evidence):
            f.append(CheckFailure(check="sentence_rule", detail=f"sentence has no claim: {s!r}"))
    # 2. claim present
    for ei in output.evidence:
        if ei.claim not in text:
            f.append(CheckFailure(check="claim_present", claim=ei.claim,
                                  detail=f"claim not in text: {ei.claim!r}"))
    # 3. source resolves (at or before at_s)
    for ei in output.evidence:
        found, time_ok, _ = store.resolve(ei.source, at_s)
        if not found:
            f.append(CheckFailure(check="source_resolves", source=ei.source,
                                  detail=f"source not found: {ei.source}"))
        elif not time_ok:
            f.append(CheckFailure(check="source_resolves", source=ei.source,
                                  detail=f"source is after trigger time {at_s}"))
    # 4. value matches
    for ei in output.evidence:
        found, time_ok, stored = store.resolve(ei.source, at_s)
        if not found or not time_ok or stored is None:
            continue
        tol = TOLERANCE.get(ei.unit)
        if tol is None:
            if str(stored) != str(ei.value):
                f.append(CheckFailure(check="value_matches", source=ei.source,
                                      detail=f"expected {stored!r}, output says {ei.value!r}"))
        else:
            try:
                if abs(float(stored) - float(ei.value)) > tol:
                    f.append(CheckFailure(check="value_matches", source=ei.source,
                                          detail=f"value off by more than {tol}"))
            except (TypeError, ValueError):
                f.append(CheckFailure(check="value_matches", source=ei.source,
                                      detail="value is not numeric"))
    # 4b. the number written in the claim is the cited value (added 2026-10-24)
    for ei in output.evidence:
        found, time_ok, stored = store.resolve(ei.source, at_s)
        if not found or not time_ok or stored is None:
            continue
        ok, why = _claim_number(ei.claim, ei.unit, stored)
        if not ok:
            f.append(CheckFailure(check="claim_number_matches", source=ei.source, claim=ei.claim, detail=why))
    # 5. label matches
    for ei in output.evidence:
        if not ei.label_metric:
            continue
        if ei.label_metric not in LABEL_BANDS:
            f.append(CheckFailure(check="label_matches", source=ei.source, claim=ei.claim,
                                  detail=f"unknown label metric {ei.label_metric}"))
            continue
        found, time_ok, stored = store.resolve(ei.source, at_s)
        if not found or not time_ok or stored is None:
            f.append(CheckFailure(check="label_matches", source=ei.source, claim=ei.claim,
                                  detail="cannot resolve source for label check"))
            continue
        claim_low = ei.claim.lower()
        matched = False
        for label, lo, hi in LABEL_BANDS[ei.label_metric]:
            names = [label.replace("_", " ").lower()] + LABEL_ALIASES.get(label, [])
            if any(n in claim_low for n in names):
                matched = True
                if isinstance(stored, str):
                    if stored.replace("_", " ") != label.replace("_", " "):   # fixed 2026-10-24: "on top" vs "on_top" always failed
                        f.append(CheckFailure(check="label_matches", source=ei.source,
                                              claim=ei.claim,
                                              detail=f"stored label {stored!r} is not {label!r}"))
                elif not (lo <= float(stored) <= hi):
                    f.append(CheckFailure(check="label_matches", source=ei.source, claim=ei.claim,
                                          detail=f"stored {stored} outside band {lo}-{hi} for {label}"))
                break
        if not matched:   # added 2026-10-24: a label claim with no known label was never checked
            f.append(CheckFailure(check="label_matches", source=ei.source, claim=ei.claim,
                                  detail=f"no {ei.label_metric} label in the claim"))
    # 6. no loose numbers
    for m in _NUM.finditer(text):
        covered = False
        for ei in output.evidence:
            start = 0
            while True:
                i = text.find(ei.claim, start)
                if i < 0:
                    break
                end = i + len(ei.claim)
                if i <= m.start() and m.end() <= end:
                    covered = True
                    break
                start = i + 1
        if not covered:
            f.append(CheckFailure(check="no_loose_numbers",
                                  detail=f"number {m.group(0)} not in any claim"))
    # 7. causal words need deltas
    low = text.lower()
    if any(w in low for w in CAUSAL_WORDS):
        has_delta = any(len(e.source.split(".")) > 1 and e.source.split(".")[1] == "deltas"
                        for e in output.evidence)
        if not has_delta:
            f.append(CheckFailure(check="causal_words",
                                  detail="causal word used without a deltas source"))

    return VerificationResult(output_id=output.output_id, passed=not f, failures=f)


LABEL_WORDS_ES = {"on_top": "dominando", "even": "igualado", "under_pressure": "bajo presión"}


def fallback_output(output: NarrativeOutput, store: VerifierStore) -> NarrativeOutput:
    """One sentence filled only from the stored state after the event. Status fallback.
    Rewritten 2026-10-24: the old text had a sentence with no claim, so it failed the
    verifier's own sentence rule; it now passes every check, in English or Spanish."""
    es = (output.language or "en").startswith("es")
    ev = store.events.get(output.event_id)
    snap = store.states.get("s_" + output.event_id)
    if ev is None or snap is None:
        text = "Momento clave del partido." if es else "Key moment on the match."
        claim = text.rstrip(".")
        evi = [EvidenceItem(claim=claim, source=output.event_id + ".type",
                            value=(ev.type if ev else "event"), unit="label", label_metric=None)]
    else:
        side = "home" if ev.team_id == "home" else "away"
        from .roster import CLUBS                  # 2026-10-26: club names, not "Home" and "Away"
        team = CLUBS[side]
        wph = snap.match_state.win_prob_home
        if ev.type == "shot" and getattr(ev, "shot_outcome", None) == "goal":
            claim = f"{round(wph * 100)}%"
            text = (f"Gol del {team}: probabilidad de victoria local {claim}." if es
                    else f"Goal for {team}: home win chance {claim}.")
            evi = [EvidenceItem(claim=claim, source=f"s_{output.event_id}.win_prob_home",
                                value=wph, unit="probability", label_metric=None)]
        else:
            ts = getattr(snap, side)
            label = ts.momentum_label
            claim = LABEL_WORDS_ES.get(label, label) if es else label.replace("_", " ")
            text = (f"{team}, ritmo del partido: {claim}." if es else f"{team} on the move, momentum {claim}.")
            evi = [EvidenceItem(claim=claim, source=f"s_{output.event_id}.{side}.momentum_label",
                                value=label, unit="label", label_metric="momentum")]
    return NarrativeOutput(
        output_id=output.output_id, event_id=output.event_id,
        match_clock_s=output.match_clock_s, user_id=output.user_id,
        mode=output.mode, language=output.language, text=text,
        evidence=evi, importance=output.importance, status="fallback", attempts=2,
    )


def run_agent_once(agent_fn: Callable[[NarrativeOutput, list], NarrativeOutput],
                   first: NarrativeOutput, store: VerifierStore, at_s: float) -> NarrativeOutput:
    """Verify, retry once with the failure list, then fall back."""
    r1 = verify(first, store, at_s)
    if r1.passed:
        first.status = "verified"
        first.attempts = 1
        return first
    second = agent_fn(first, r1.failures)
    r2 = verify(second, store, at_s)
    if r2.passed:
        second.status = "verified_on_retry"
        second.attempts = 2
        return second
    out = fallback_output(first, store)
    out.importance = first.importance
    return out


def catch_rate(outputs: list) -> dict:
    n = len(outputs)
    retried = sum(1 for o in outputs if o.status == "verified_on_retry")
    fb = sum(1 for o in outputs if o.status == "fallback")
    return {"total": n, "verified_on_retry": retried, "fallback": fb,
            "catch_rate": (retried + fb) / n if n else 0.0}
