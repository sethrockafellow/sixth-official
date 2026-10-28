# panels.py - the persona panels (Sixth Official).
# Reads ONLY NarrativeOutput (the frozen schema contract). Tool results never reach the frontend.
# Three persona panels. Display minute and screen units are frontend-only conversions.
import math
from typing import Optional

from .schema import NarrativeOutput, PersonaConfig, DEFAULT_PERSONAS

# status -> overlay tag
_STATUS_TAG = {
    "verified": "OK",
    "verified_on_retry": "RETRY",
    "fallback": "FALLBACK",
}


def display_minute(match_clock_s: float) -> int:
    # Spec: floor(match_clock_s / 60) + 1. Frontend only, never stored.
    return int(math.floor(match_clock_s / 60)) + 1


def emphasis_tier(importance: float) -> str:
    # importance = boosted surprise (>=0, can exceed 1 after persona boost).
    # Bucket for the overlay emphasis scale.
    if importance < 0.25:
        return "low"
    if importance < 0.5:
        return "medium"
    return "high"


def emphasis_weight(importance: float) -> float:
    # Proportional overlay weight, clamped to [0, 1].
    return max(0.0, min(1.0, importance))


class PanelCard:
    # One overlay card, built from exactly one NarrativeOutput.
    def __init__(self, out: NarrativeOutput):
        self.output_id = out.output_id
        self.event_id = out.event_id
        self.minute = display_minute(out.match_clock_s)
        self.text = out.text
        self.status = out.status
        self.status_tag = _STATUS_TAG[out.status]
        self.attempts = out.attempts
        self.importance = out.importance
        self.emphasis_tier = emphasis_tier(out.importance)
        self.emphasis_weight = emphasis_weight(out.importance)
        self.mode = out.mode

    def render(self) -> str:
        return (f"[{self.status_tag}] m{self.minute:02d} {self.text}"
                f"  <emphasis:{self.emphasis_tier} w={self.emphasis_weight:.2f} attempts={self.attempts}>")


class PersonaPanel:
    # One panel per persona. Holds the cards that fired for that user.
    def __init__(self, persona_id: str, mode: str, cards: list):
        self.persona_id = persona_id
        self.mode = mode
        self.cards = cards

    def moments(self) -> list:
        return [c.event_id for c in self.cards]

    def render(self) -> str:
        if not self.cards:
            return f"# {self.persona_id} ({self.mode}) -- no moments"
        lines = [f"# {self.persona_id} ({self.mode}) -- {len(self.cards)} moment(s)"]
        for c in sorted(self.cards, key=lambda c: c.minute):
            lines.append(c.render())
        return "\n".join(lines)


def build_panels(outputs, personas: Optional[list] = None) -> dict:
    # Frontend gate: every input is validated through the NarrativeOutput contract.
    # Tool results never reach the frontend; only the contract object does.
    from pydantic import TypeAdapter
    if personas is None:
        personas = DEFAULT_PERSONAS
    ta = TypeAdapter(NarrativeOutput)
    panels = {p.persona_id: PersonaPanel(p.persona_id, p.mode, []) for p in personas}
    for raw in outputs:
        out = raw if isinstance(raw, NarrativeOutput) else ta.validate_python(raw)
        pid = out.user_id
        if pid not in panels:
            panels[pid] = PersonaPanel(pid, out.mode, [])
        panels[pid].cards.append(PanelCard(out))
    return panels
