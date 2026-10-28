import math

from .schema import MetricConstants, MatchConfig, LABEL_BANDS as BAND

C = MetricConstants()
CFG = MatchConfig(seed=0)

# Pitch geometry. Length and width are fixed by the spec. Box and third
# sizes come from the standard football pitch; they are geometry, not
# tunable model constants.
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
GOAL_CENTRE_Y_M = PITCH_WIDTH_M / 2.0
BOX_DEPTH_M = 16.5
BOX_HALF_WIDTH_M = 40.32 / 2.0
THIRD_LENGTH_M = PITCH_LENGTH_M / 3.0


def goal_centre_for(attacking_team):
    if attacking_team == "home":
        return PITCH_LENGTH_M, GOAL_CENTRE_Y_M
    return 0.0, GOAL_CENTRE_Y_M


def in_attacking_third(x_m, attacking_team):
    if attacking_team == "home":
        return x_m >= 2.0 * THIRD_LENGTH_M
    return x_m < THIRD_LENGTH_M


def in_box(x_m, y_m, attacking_team):
    if not (GOAL_CENTRE_Y_M - BOX_HALF_WIDTH_M <= y_m <= GOAL_CENTRE_Y_M + BOX_HALF_WIDTH_M):
        return False
    if attacking_team == "home":
        return PITCH_LENGTH_M - BOX_DEPTH_M <= x_m <= PITCH_LENGTH_M
    return 0.0 <= x_m <= BOX_DEPTH_M


def _angle_to_goal_rad(x_m, y_m, goal_x):
    half = CFG.goal_width_m / 2.0
    ax = goal_x - x_m
    ay = GOAL_CENTRE_Y_M - half - y_m
    bx = goal_x - x_m
    by = GOAL_CENTRE_Y_M + half - y_m
    cross = ax * by - ay * bx
    dot = ax * bx + ay * by
    return abs(math.atan2(cross, dot))


def xg_for_shot(x_m, y_m, attacking_team, body_part, shot_type):
    if shot_type == "penalty":
        return C.xg_penalty
    gx, gy = goal_centre_for(attacking_team)
    d = math.hypot(gx - x_m, gy - y_m)
    theta = _angle_to_goal_rad(x_m, y_m, gx)
    z = C.xg_a + C.xg_b * theta - C.xg_c * d
    value = 1.0 / (1.0 + math.exp(-z))
    if body_part == "head":
        value *= C.xg_header_mult
    return value


def _action_value(event, team_id):
    if event.type == "shot":
        return event.xg if event.team_id == team_id else 0.0
    if event.team_id != team_id:
        return 0.0
    if event.type == "pass" and event.outcome == "success" and in_box(event.end_x_m, event.end_y_m, team_id):
        return C.action_box_value
    if event.type == "carry" and event.outcome == "success" and in_box(event.end_x_m, event.end_y_m, team_id):
        return C.action_box_value
    if event.type == "recovery" and in_attacking_third(event.x_m, team_id):
        return C.action_box_value
    if event.type == "restart" and event.restart_type in ("corner", "penalty"):   # v2: set-piece threat
        return C.action_box_value
    if event.type == "restart" and event.restart_type == "free_kick" and event.direct:
        return C.action_box_value
    return 0.0


def momentum_at(t, events):
    totals = {}
    for team_id in ("home", "away"):
        total = 0.0
        for event in events:
            dt = t - event.match_clock_s
            if 0.0 <= dt <= C.momentum_window_s:
                value = _action_value(event, team_id)
                if value > 0.0:
                    total += value * math.exp(-dt / C.momentum_tau_s)
        totals[team_id] = total
    home = (totals["home"] + C.momentum_offset) / (totals["home"] + totals["away"] + 2.0 * C.momentum_offset)
    return home, 1.0 - home


def _poisson_pmf(lam, k):
    if lam <= 0.0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


# The version 1 win model (momentum and a flat Poisson rate). The engine no longer uses it: the
# win chance comes from sixth/winmodel.py. It is kept only so scripts/fit_win_model.py can show
# the new model against it (docs/METRICS.md, section 1).
def win_probabilities(t, score_home, score_away, momentum_home):
    t = max(0.0, min(float(t), CFG.total_seconds))
    remaining = 1.0 - t / CFG.total_seconds
    lam_home = C.win_base_goals * remaining * (C.win_prob_momentum_base + C.win_prob_momentum_scale * momentum_home)
    lam_away = C.win_base_goals * remaining * (C.win_prob_momentum_base + C.win_prob_momentum_scale * (1.0 - momentum_home))
    n = C.win_prob_max_goals
    pmf_h = [_poisson_pmf(lam_home, k) for k in range(n + 1)]
    pmf_a = [_poisson_pmf(lam_away, k) for k in range(n + 1)]
    win = 0.0
    draw = 0.0
    for gh in range(n + 1):
        for ga in range(n + 1):
            p = pmf_h[gh] * pmf_a[ga]
            if score_home + gh > score_away + ga:
                win += p
            elif score_home + gh == score_away + ga:
                draw += p
    total = win + draw
    if total > 1.0:
        win, draw = win / total, draw / total
    win = min(1.0, max(0.0, round(win, 10)))
    draw = min(1.0 - win, max(0.0, round(draw, 10)))
    away = max(0.0, round(1.0 - win - draw, 10))
    return win, draw, away


def pressing_intensity(t, team_id, events):
    opponent = "away" if team_id == "home" else "home"
    lo = t - C.press_window_s
    pressures = 0
    opp_passes = 0
    for event in events:
        if not (lo < event.match_clock_s <= t):
            continue
        if event.type == "pressure" and event.team_id == team_id:
            pressures += 1
        if event.type == "pass" and event.team_id == opponent:
            opp_passes += 1
    if opp_passes == 0:
        return 0.0
    return min(1.0, pressures / opp_passes)


def line_height_m(players, team_id, gk_player_ids):
    depths = []
    for player in players:
        if player.player_id in gk_player_ids:
            continue
        if player.team_id != team_id:
            continue
        if team_id == "home":
            depths.append(player.x_m)
        else:
            depths.append(PITCH_LENGTH_M - player.x_m)
    if not depths:
        return 0.0
    deepest = sorted(depths)[:4]
    return sum(deepest) / len(deepest)


def defensive_block(height_m):
    if height_m >= C.line_high_m:
        return "high"
    if height_m >= C.line_mid_m:
        return "mid"
    return "low"


def possession_share(t, team_id, segments):
    if not segments:
        return 0.5
    lo = max(0.0, t - C.possession_window_s)
    hi = t
    owned = 0.0
    start, team = segments[0]
    for end, next_team in segments[1:]:
        s = max(lo, start)
        e = min(hi, end)
        if e > s and team == team_id:
            owned += e - s
        start, team = end, next_team
    e = min(hi, float("inf"))
    if e > start and team == team_id:
        owned += e - max(lo, start)
    window = hi - lo
    if window <= 0.0:
        return 0.5
    return min(1.0, max(0.0, owned / window))


def surprise(state_before, state_after):
    d_wp = abs(state_after.match_state.win_prob_home - state_before.match_state.win_prob_home)
    d_mom = abs(state_after.home.momentum - state_before.home.momentum)
    return max(d_wp, 0.5 * d_mom)


def momentum_label(momentum):
    if momentum >= BAND["momentum"][0][1]:
        return "on_top"
    if momentum > BAND["momentum"][2][2]:
        return "even"
    return "under_pressure"


def pressing_label(intensity):
    if intensity >= BAND["pressing_intensity"][0][1]:
        return "intense press"
    if intensity >= BAND["pressing_intensity"][1][1]:
        return "normal press"
    return "sitting off"


def xg_label(xg):
    if xg >= BAND["xg"][0][1]:
        return "big chance"
    if xg >= BAND["xg"][1][1]:
        return "half chance"
    return "long shot"


# ---------------------------------------------------------------- v2 team metrics (docs/METRICS.md)
METRIC_WINDOW_S = 600.0


def _recent(events, t, window=METRIC_WINDOW_S):
    lo = t - window
    return [e for e in events if lo < e.match_clock_s <= t]


def field_tilt(t, team_id, events):
    """Share of both teams' passes made in the attacking third, last 10 minutes. 0.5 if none."""
    own = opp = 0
    for e in _recent(events, t):
        if e.type != "pass":
            continue
        if in_attacking_third(e.x_m, e.team_id):
            if e.team_id == team_id:
                own += 1
            else:
                opp += 1
    return 0.5 if own + opp == 0 else own / (own + opp)


def is_defensive_action(e):
    """A tackle won, an interception or a foul: the PPDA denominator."""
    if e.type == "foul":
        return True
    if e.type == "recovery" and e.method == "interception":
        return True
    return e.type == "duel" and e.context == "tackle"


def ppda(t, team_id, events):
    """Passes per defensive action: opponent passes in their own 60% of the pitch divided by this
    team's defensive actions there, last 10 minutes. Lower means a harder press. Capped at 30."""
    opp = "away" if team_id == "home" else "home"
    passes = actions = 0
    for e in _recent(events, t):
        if e.type == "pass" and e.team_id == opp:
            depth = e.x_m if opp == "home" else PITCH_LENGTH_M - e.x_m
            if depth <= 0.6 * PITCH_LENGTH_M:
                passes += 1
        elif e.team_id == team_id and is_defensive_action(e):
            depth_opp = e.x_m if opp == "home" else PITCH_LENGTH_M - e.x_m
            if depth_opp <= 0.6 * PITCH_LENGTH_M:
                actions += 1
    if actions == 0:
        return 30.0   # the documented cap (fixed 2026-10-27: was min(30, passes))
    return min(30.0, passes / actions)


def duels_won_share(t, team_id, events):
    won = total = 0
    for e in _recent(events, t):
        if e.type == "duel":
            total += 1
            won += e.team_id == team_id
    return 0.5 if total == 0 else won / total
