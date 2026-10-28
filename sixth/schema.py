# schema.py - the data contract (Pydantic v2).
# 2026-10-25 (v2): restarts with dead-ball time, duels, clearances, pressure on each action,
# pass height, ball height, players sent off, and team metrics (field tilt, PPDA, duels won).

from __future__ import annotations
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, TypeAdapter

# ---------- shared literals ----------
TeamId = Literal["home", "away"]
EventOutcome = Literal["success", "failure", "none"]
EventType = Literal["pass","shot","save","recovery","pressure","foul","offside","carry",
                    "duel","clearance","restart"]
MomentumLabel = Literal["on_top","even","under_pressure"]
Block = Literal["high","mid","low"]
Mode = Literal["tactical","casual"]
Unit = Literal["probability","xg","index","m","mps","s","count","label"]

# ---------- fixed match config (v1) ----------
class MatchConfig(BaseModel):
    seed: int
    pitch_length_m: float = 105.0
    pitch_width_m: float = 68.0
    goal_width_m: float = 7.32
    total_seconds: float = 5400.0
    period_1_end_s: float = 2700.0
    tracking_hz: int = 1
    # display minute is frontend only: floor(match_clock_s / 60) + 1

# ---------- tunable metric constants (v1 defaults) ----------
class MetricConstants(BaseModel):
    momentum_tau_s: float = 300.0
    momentum_window_s: float = 900.0
    momentum_offset: float = 0.05
    # xG = 1/(1+e^-(a + b*theta - c*d)), theta = goal-mouth angle (rad), d = distance (m).
    # Refit 2026-10-25 to typical public open-play xG values (about 0.17 from 11 m central,
    # 0.09 from 16 m, 0.03 from 25 m); the old curve (-1.0, 1.6, 0.09) gave about 0.21 a shot.
    xg_a: float = -1.212
    xg_b: float = 1.222
    xg_c: float = 0.1048
    xg_header_mult: float = 0.5
    xg_penalty: float = 0.76
    win_base_goals: float = 1.4
    press_window_s: float = 300.0
    possession_window_s: float = 300.0
    sprint_threshold_mps: float = 5.4   # DECISION: chosen, tunable, not in spec
    action_box_value: float = 0.03      # momentum value: box pass, box carry, attacking-third recovery
    win_prob_max_goals: int = 10        # Poisson sum 0..10 goals each
    win_prob_momentum_base: float = 0.8
    win_prob_momentum_scale: float = 0.4
    line_high_m: float = 40.0           # block high if line_height_m >= 40
    line_mid_m: float = 25.0            # block mid if 25 <= line_height_m < 40

# ---------- event base ----------
class EventBase(BaseModel):
    event_id: str
    type: EventType
    match_clock_s: float
    period: Literal[1, 2]
    team_id: TeamId
    player_id: str
    x_m: float = Field(ge=0, le=105)
    y_m: float = Field(ge=0, le=68)
    possession_id: int
    related_event_id: Optional[str] = None
    outcome: EventOutcome
    under_pressure: bool = False     # v2: an opponent was closing the player down

class PassEvent(EventBase):
    type: Literal["pass"]
    receiver_id: str
    pass_type: Literal["ground","cross","through","long","clearance"]
    length_m: float
    end_x_m: float = Field(ge=0, le=105)
    end_y_m: float = Field(ge=0, le=68)
    height: Optional[Literal["ground","low","high"]] = None   # v2: ground, below head height, above it

class ShotEvent(EventBase):
    type: Literal["shot"]
    body_part: Literal["left_foot","right_foot","head","other"]
    shot_type: Literal["open_play","set_piece","penalty"]
    shot_outcome: Literal["goal","saved","off_target","blocked","woodwork"]
    speed_mps: float = Field(ge=0)   # written by generator, not 1 Hz
    xg: Optional[float] = Field(default=None, ge=0, le=1)  # written by engine; None until the engine writes it

class SaveEvent(EventBase):
    type: Literal["save"]
    body_part: Literal["hands","feet","body","head"]
    # related_event_id (base) = the shot

class RecoveryEvent(EventBase):
    type: Literal["recovery"]
    method: Literal["tackle","interception","loose_ball"]

class PressureEvent(EventBase):
    type: Literal["pressure"]
    target_player_id: str
    duration_s: float = Field(ge=0)

class FoulEvent(EventBase):
    type: Literal["foul"]
    fouled_player_id: str
    foul_type: Literal["tackle","holding","handball"]
    card: Optional[Literal["yellow","red"]] = None
    advantage_played: bool = False

class OffsideEvent(EventBase):
    type: Literal["offside"]

class CarryEvent(EventBase):
    type: Literal["carry"]
    end_x_m: float = Field(ge=0, le=105)
    end_y_m: float = Field(ge=0, le=68)
    distance_m: float = Field(ge=0)

class DuelEvent(EventBase):
    """v2. A contest for the ball between two players. team_id and player_id: the winner."""
    type: Literal["duel"]
    duel_type: Literal["ground","aerial"]
    context: Literal["fifty_fifty","tackle","take_on","aerial"]
    opponent_id: str                 # the player who lost it

class ClearanceEvent(EventBase):
    """v2. A defender kicks or heads the ball away from danger."""
    type: Literal["clearance"]
    body_part: Literal["foot","head"]
    end_x_m: float = Field(ge=0, le=105)
    end_y_m: float = Field(ge=0, le=68)

RestartType = Literal["kick_off","throw_in","goal_kick","corner","free_kick","penalty"]

class RestartEvent(EventBase):
    """v2. Play starts again after the ball was dead. dead_s: how long it was dead."""
    type: Literal["restart"]
    restart_type: RestartType
    dead_s: float = Field(ge=0)
    direct: bool = False             # a free kick in shooting range, taken at goal
    receiver_id: Optional[str] = None
    end_x_m: Optional[float] = Field(default=None, ge=0, le=105)
    end_y_m: Optional[float] = Field(default=None, ge=0, le=68)
    height: Optional[Literal["ground","low","high"]] = None

Event = Annotated[
    Union[PassEvent, ShotEvent, SaveEvent, RecoveryEvent,
          PressureEvent, FoulEvent, OffsideEvent, CarryEvent,
          DuelEvent, ClearanceEvent, RestartEvent],
    Field(discriminator="type"),
]

EventAdapter = TypeAdapter(Event)   # validates one dict into the right Event subclass

# ---------- state objects ----------
class MatchState(BaseModel):
    snapshot_id: str
    match_clock_s: float
    score_home: int = Field(ge=0)
    score_away: int = Field(ge=0)
    possession_team: TeamId
    win_prob_home: float = Field(ge=0, le=1)
    draw_prob: float = Field(ge=0, le=1)
    win_prob_away: float = Field(ge=0, le=1)
    # engine asserts win_prob_home + draw_prob + win_prob_away == 1

class TacticalState(BaseModel):
    team_id: TeamId
    momentum: float = Field(ge=0, le=1)
    momentum_label: MomentumLabel
    pressing_intensity: float = Field(ge=0, le=1)
    line_height_m: float = Field(ge=0)
    defensive_block: Block
    possession_share_5min: float = Field(ge=0, le=1)
    xg_total: float = Field(ge=0)
    # v2 (2026-10-25), standard analyst metrics over the last 10 minutes (docs/METRICS.md):
    field_tilt: float = Field(default=0.5, ge=0, le=1)        # share of both teams' final-third passes
    ppda: float = Field(default=0.0, ge=0)                    # opponent passes per defensive action
    duels_won_share: float = Field(default=0.5, ge=0, le=1)   # share of duels won

# one state_log entry = MatchState + one TacticalState per team
class Snapshot(BaseModel):
    match_state: MatchState
    home: TacticalState
    away: TacticalState

class BallState(BaseModel):
    x_m: float = Field(ge=0, le=105)
    y_m: float = Field(ge=0, le=68)
    speed_mps: float = Field(ge=0)
    z_m: float = Field(default=0.0, ge=0)   # v2: height above the grass

class PlayerState(BaseModel):
    player_id: str
    team_id: TeamId
    x_m: float = Field(ge=0, le=105)
    y_m: float = Field(ge=0, le=68)
    speed_mps: float = Field(ge=0)
    on_pitch: bool = True            # v2: False after a red card

class OfficialState(BaseModel):
    """A match official. Assistants and the fourth official stand outside the touchlines."""
    official_id: Literal["ref", "ar1", "ar2", "fourth"]
    role: Literal["referee", "assistant_referee", "fourth_official"]
    x_m: float = Field(ge=-3, le=108)
    y_m: float = Field(ge=-3, le=72)
    speed_mps: float = Field(ge=0)

class PhysicalRow(BaseModel):
    physical_id: str          # "p_" + whole second  (DECISION: added for cite)
    match_clock_s: int
    ball: BallState
    players: list[PlayerState]
    officials: list[OfficialState] = Field(default_factory=list)   # added 2026-10-25

PhysicalState = PhysicalRow   # older name, kept so generate_data and reference_state import

# ---------- three append-only stores ----------
EventLog = dict[str, Event]        # keyed by event_id
StateLog = dict[str, Snapshot]     # keyed by snapshot_id
PhysicalLog = dict[str, PhysicalRow]  # keyed by physical_id

# ---------- tool responses (each carries a cite id) ----------
class EventPage(BaseModel):
    as_of_snapshot_id: str
    events: list[Event] = Field(max_length=50)

class TacticalResponse(BaseModel):
    snapshot_id: str
    team_id: TeamId
    tactical: TacticalState

class PlayerSnapshot(BaseModel):
    physical_id: str
    player_id: str
    x_m: float
    y_m: float
    speed_mps: float
    distance_m: float = Field(ge=0)   # computed over physical_log up to at_s
    sprint_count: int = Field(ge=0)   # computed, threshold = sprint_threshold_mps

class EventContext(BaseModel):
    event: Event
    state_before: Snapshot
    state_after: Snapshot
    deltas: dict[str, float]   # every numeric field, state_after - state_before

class BallPos(BaseModel):
    x_m: float
    y_m: float

class BallSummary(BaseModel):
    from_physical_id: str
    to_physical_id: str
    start: BallPos
    end: BallPos
    peak_speed_mps: float = Field(ge=0)
    peak_speed_at_s: float = Field(ge=0)
    total_distance_m: float = Field(ge=0)

# ---------- trigger and personas ----------
class UserPreferences(BaseModel):
    user_id: str
    mode: Mode
    favorite_team: Optional[TeamId] = None
    favorite_player: Optional[str] = None
    language: str = "en"

class TriggerPayload(BaseModel):
    event_id: str
    match_clock_s: float
    surprise: float = Field(ge=0)
    preferences: UserPreferences

class PersonaConfig(BaseModel):
    persona_id: str
    mode: Mode
    favorite_team: Optional[TeamId] = None
    favorite_player: Optional[str] = None
    threshold: float = Field(ge=0)
    boost: float = Field(default=1.0, ge=1.0)  # applied when event touches favorite
    cooldown_s: float = 20.0
    language: str = "en"

DEFAULT_PERSONAS: list[PersonaConfig] = [
    # Thresholds tuned 2026-10-24 (the spec marks them tunable): the spec's 0.06 / 0.10 / 0.12 gave
    # about 17 moments a match once the generator made realistic matches; these give about 40.
    PersonaConfig(persona_id="analyst", mode="tactical", threshold=0.02, boost=1.0),
    PersonaConfig(persona_id="home_fan", mode="casual", favorite_team="home", threshold=0.035, boost=1.5),
    PersonaConfig(persona_id="player_follower", mode="casual", favorite_player="h09", threshold=0.04, boost=2.0),
]

# ---------- output (frontend reads only this) ----------
class EvidenceItem(BaseModel):
    claim: str                       # exact words from text
    source: str                      # <snapshot_id|event_id|physical_id>.<field path>
    value: Union[float, str]
    unit: Unit
    label_metric: Optional[str] = None

class NarrativeOutput(BaseModel):
    output_id: str
    event_id: str
    match_clock_s: float
    user_id: str
    mode: Mode
    language: str = "en"
    text: str
    evidence: list[EvidenceItem] = Field(min_length=1)
    importance: float = Field(ge=0)  # boosted surprise from engine
    status: Literal["verified","verified_on_retry","fallback"]
    attempts: int = Field(ge=1, le=2)

# ---------- verifier ----------
CheckName = Literal[
    "sentence_rule","claim_present","source_resolves",
    "value_matches","label_matches","no_loose_numbers","causal_words",
    "claim_number_matches",   # added 2026-10-24: the number written in the claim must be the cited value
]

class CheckFailure(BaseModel):
    check: CheckName
    detail: str
    claim: Optional[str] = None
    source: Optional[str] = None

class VerificationResult(BaseModel):
    output_id: str
    passed: bool
    failures: list[CheckFailure] = []

TOLERANCE: dict = {
    "probability": 0.01,
    "xg": 0.01,
    "index": 0.02,
    "m": 1.0,
    "mps": 0.5,
    "s": 1.0,
    "count": 0.0,
    "label": None,      # exact
    "categorical": None,
}

LABEL_BANDS: dict = {
    "momentum": [("on_top", 0.65, 1.0), ("even", 0.35, 0.65), ("under_pressure", 0.0, 0.35)],
    "pressing_intensity": [("intense press", 0.6, 1.0), ("normal press", 0.3, 0.6), ("sitting off", 0.0, 0.3)],
    "xg": [("big chance", 0.3, 1.0), ("half chance", 0.1, 0.3), ("long shot", 0.0, 0.1)],
}

CAUSAL_WORDS = {"because", "forced", "led to", "broke",
                # Spanish, added 2026-10-24
                "porque", "provocó", "obligó", "llevó a", "rompió"}

FALLBACK_TEMPLATES: dict = {
    "goal": "{team} score. Win chance {home_before:.0%} to {home_after:.0%}.",
    "default": "{team} on the move. Momentum {momentum_label}.",
}
