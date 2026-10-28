"""The persona panels: three panels show different moments for the same match."""
# Spec test: three persona panels show different moments for the same match.

from pydantic import TypeAdapter
from sixth.schema import NarrativeOutput
from sixth.panels import build_panels, display_minute

samples = [
    # analyst, tactical, one moment
    {"output_id": "o1001", "event_id": "e000512", "match_clock_s": 3210.4,
     "user_id": "analyst", "mode": "tactical", "language": "en",
     "text": "Home win probability 42%, up from 38% before the goal. Home momentum label on_top.",
     "evidence": [
        {"claim": "42%", "source": "s_e000512.win_prob_home", "value": 0.42, "unit": "probability", "label_metric": None},
        {"claim": "on_top", "source": "s_e000512.home.momentum_label", "value": "on_top", "unit": "label", "label_metric": "momentum"}],
     "importance": 0.14, "status": "verified", "attempts": 1},
    # home_fan, casual, the spec goal example, one moment
    {"output_id": "o1002", "event_id": "e000412", "match_clock_s": 3794.2,
     "user_id": "home_fan", "mode": "casual", "language": "en",
     "text": "Home score from a big chance and now have a 68% chance to win.",
     "evidence": [
        {"claim": "big chance", "source": "e000412.xg", "value": 0.31, "unit": "label", "label_metric": "xg"},
        {"claim": "68% chance to win", "source": "s_e000412.win_prob_home", "value": 0.68, "unit": "probability", "label_metric": None}],
     "importance": 0.51, "status": "verified", "attempts": 1},
    # player_follower, casual, names the player, fallback path, one moment
    {"output_id": "o1003", "event_id": "e000633", "match_clock_s": 4120.0,
     "user_id": "player_follower", "mode": "casual", "language": "en",
     "text": "h09 on the move. Momentum even.",
     "evidence": [
        {"claim": "Momentum even", "source": "s_e000633.home.momentum_label", "value": "even", "unit": "label", "label_metric": "momentum"}],
     "importance": 0.30, "status": "fallback", "attempts": 2},
]

# Frontend gate: every object must validate through the contract TypeAdapter.
ta = TypeAdapter(NarrativeOutput)
for s in samples:
    ta.validate_python(s)

panels = build_panels(samples)

assert set(panels.keys()) == {"analyst", "home_fan", "player_follower"}, panels.keys()

# Three panels show different moments for the same match.
moments = [panels[k].moments()[0] for k in ["analyst", "home_fan", "player_follower"]]
assert len(set(moments)) == 3, moments

# Display minute is computed frontend-only.
assert display_minute(3210.4) == 54
assert display_minute(3794.2) == 64
assert display_minute(4120.0) == 69

# Each panel holds exactly one card.
for k in panels:
    assert len(panels[k].cards) == 1, k

# Status tags the overlay.
assert panels["analyst"].cards[0].status_tag == "OK"
assert panels["home_fan"].cards[0].status_tag == "OK"
assert panels["player_follower"].cards[0].status_tag == "FALLBACK"

# Emphasis scales off importance (three different tiers).
assert panels["analyst"].cards[0].emphasis_tier == "low"          # 0.14
assert panels["player_follower"].cards[0].emphasis_tier == "medium"  # 0.30
assert panels["home_fan"].cards[0].emphasis_tier == "high"        # 0.51

