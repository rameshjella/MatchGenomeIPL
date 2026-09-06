REQUIRED_COLUMNS = [
    "season_id",
    "match_id",
    "batter",
    "bowler",
    "non_striker",
    "team_batting",
    "team_bowling",
    "over_number",
    "ball_number",
    "batter_runs",
    "extras",
    "total_runs",
    "batsman_type",
    "bowler_type",
    "player_out",
    "fielders_involved",
    "is_wicket",
    "is_wide_ball",
    "is_no_ball",
    "is_leg_bye",
    "is_bye",
    "is_penalty",
    "wide_ball_runs",
    "no_ball_runs",
    "leg_bye_runs",
    "bye_runs",
    "penalty_runs",
    "wicket_kind",
    "is_super_over",
    "innings",
]

BOOLEAN_COLUMNS = [
    "is_wicket",
    "is_wide_ball",
    "is_no_ball",
    "is_leg_bye",
    "is_bye",
    "is_penalty",
    "is_super_over",
]

INTEGER_COLUMNS = [
    "season_id",
    "match_id",
    "over_number",
    "ball_number",
    "batter_runs",
    "extras",
    "total_runs",
    "wide_ball_runs",
    "no_ball_runs",
    "leg_bye_runs",
    "bye_runs",
    "penalty_runs",
    "innings",
]

TEXT_COLUMNS = [
    "batter",
    "bowler",
    "non_striker",
    "team_batting",
    "team_bowling",
    "batsman_type",
    "bowler_type",
    "player_out",
    "fielders_involved",
    "wicket_kind",
]

OUTCOME_LABELS = ["0", "1", "2", "3+", "4", "6", "wicket"]

# Wickets that are generally not credited to the bowler.
NON_BOWLER_WICKETS = {
    "run out",
    "retired hurt",
    "retired out",
    "obstructing the field",
}
