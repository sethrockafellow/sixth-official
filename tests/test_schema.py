"""The data contract: valid records pass, invalid ones are refused."""
from pydantic import ValidationError, TypeAdapter
from sixth import schema as S

event_adapter = TypeAdapter(S.Event)

base = dict(
    match_clock_s=600.0, period=1, team_id="home", player_id="h09",
    x_m=50.0, y_m=34.0, possession_id=1, outcome="none",
)

samples = [
    S.PassEvent(event_id="e1", type="pass", receiver_id="h10", pass_type="ground",
                length_m=14.0, end_x_m=62.0, end_y_m=34.0, **base),
    S.ShotEvent(event_id="e2", type="shot", body_part="right_foot", shot_type="open_play",
                shot_outcome="goal", speed_mps=25.5, xg=0.31, **base),
    S.SaveEvent(event_id="e3", type="save", body_part="hands", related_event_id="e2", **base),
    S.RecoveryEvent(event_id="e4", type="recovery", method="tackle", **base),
    S.PressureEvent(event_id="e5", type="pressure", target_player_id="a04", duration_s=2.0, **base),
    S.FoulEvent(event_id="e6", type="foul", fouled_player_id="a05", foul_type="tackle",
                card="yellow", advantage_played=False, **base),
    S.OffsideEvent(event_id="e7", type="offside", **base),
    S.CarryEvent(event_id="e8", type="carry", end_x_m=58.0, end_y_m=35.0, distance_m=8.0, **base),
]

ok = 0
for ev in samples:
    parsed = event_adapter.validate_python(ev.model_dump())
    assert parsed.type == ev.type
    ok += 1

# union rejects an unknown type
try:
    event_adapter.validate_python({**base, "event_id": "e9", "type": "tackle"})
    raise AssertionError("union accepted unknown type")
except ValidationError:
    pass

# output rejects a bad status and empty evidence
try:
    S.NarrativeOutput(output_id="o1", event_id="e2", match_clock_s=600.0, user_id="u1",
                      mode="casual", text="t", evidence=[], importance=0.1,
                      status="maybe", attempts=1)
    raise AssertionError("NarrativeOutput accepted empty evidence and bad status")
except ValidationError:
    pass

assert S.TOLERANCE["probability"] == 0.01
assert S.MetricConstants().sprint_threshold_mps == 5.4




