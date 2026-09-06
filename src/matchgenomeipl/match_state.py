from __future__ import annotations

import sqlite3
from typing import Any

from .analytics import classify_delivery_outcome, outcome_distribution


def innings_phase(legal_balls_before: int) -> str:
    if legal_balls_before < 36:
        return "powerplay"
    if legal_balls_before < 90:
        return "middle"
    return "death"


def get_target_delivery(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT *
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND over_number = ? AND ball_number = ?
        """,
        (season_id, match_id, innings, over_number, ball_number),
    ).fetchone()
    if row is None:
        raise ValueError("Target delivery not found")
    return row


def _before_innings_clause() -> str:
    return "(over_number < ? OR (over_number = ? AND ball_number < ?))"


def build_pre_delivery_state(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
    recent_n: int = 6,
) -> dict[str, Any]:
    target = get_target_delivery(conn, season_id, match_id, innings, over_number, ball_number)

    before_totals = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(total_runs), 0) AS score_before,
            COALESCE(SUM(is_wicket), 0) AS wickets_before,
            COALESCE(SUM(legal_ball), 0) AS legal_balls_before
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND {_before_innings_clause()}
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number),
    ).fetchone()

    score_before = int(before_totals["score_before"])
    wickets_before = int(before_totals["wickets_before"])
    legal_balls_before = int(before_totals["legal_balls_before"])
    run_rate = round(score_before / (legal_balls_before / 6.0), 2) if legal_balls_before > 0 else 0.0

    recent_rows = conn.execute(
        f"""
        SELECT *
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND {_before_innings_clause()}
        ORDER BY over_number DESC, ball_number DESC, source_row_number DESC
        LIMIT ?
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number, recent_n),
    ).fetchall()
    recent_outcomes = [classify_delivery_outcome(r) for r in reversed(recent_rows)]

    batter_before = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(batter_runs), 0) AS runs,
            COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls,
            COALESCE(SUM(CASE WHEN batter_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ? AND batter = ?
          AND {_before_innings_clause()}
        """,
        (season_id, match_id, innings, target["batter"], over_number, over_number, ball_number),
    ).fetchone()

    bowler_before = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs_conceded,
            COALESCE(SUM(legal_ball), 0) AS legal_balls,
            COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ? AND bowler = ?
          AND {_before_innings_clause()}
        """,
        (season_id, match_id, innings, target["bowler"], over_number, over_number, ball_number),
    ).fetchone()

    historical_base = conn.execute(
        "SELECT * FROM deliveries WHERE timeline_key < ?",
        (target["timeline_key"],),
    ).fetchall()

    match_up_rows = conn.execute(
        "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler = ?",
        (target["timeline_key"], target["batter"], target["bowler"]),
    ).fetchall()

    batter_vs_bowler_type_rows = conn.execute(
        "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler_type = ?",
        (target["timeline_key"], target["batter"], target["bowler_type"]),
    ).fetchall()

    bowler_vs_batter_type_rows = conn.execute(
        "SELECT * FROM deliveries WHERE timeline_key < ? AND bowler = ? AND batsman_type = ?",
        (target["timeline_key"], target["bowler"], target["batsman_type"]),
    ).fetchall()

    return {
        "observed_state": {
            "season_id": int(target["season_id"]),
            "match_id": int(target["match_id"]),
            "innings": int(target["innings"]),
            "team_batting": target["team_batting"],
            "team_bowling": target["team_bowling"],
            "over_number": int(target["over_number"]),
            "ball_number": int(target["ball_number"]),
            "striker": target["batter"],
            "non_striker": target["non_striker"],
            "bowler": target["bowler"],
            "score_before_delivery": score_before,
            "wickets_before_delivery": wickets_before,
            "legal_balls_before_delivery": legal_balls_before,
            "current_run_rate": run_rate,
            "innings_phase": innings_phase(legal_balls_before),
            "recent_delivery_outcomes": recent_outcomes,
            "batter_innings_runs_before": int(batter_before["runs"]),
            "batter_innings_balls_before": int(batter_before["balls"]),
            "batter_innings_boundaries_before": int(batter_before["boundaries"]),
            "bowler_innings_runs_conceded_before": int(bowler_before["runs_conceded"]),
            "bowler_innings_legal_balls_before": int(bowler_before["legal_balls"]),
            "bowler_innings_wickets_before": int(bowler_before["wickets"]),
        },
        "historical_features": {
            "historical_delivery_count": len(historical_base),
            "batter_vs_bowler_sample": len(match_up_rows),
            "batter_vs_bowler_outcomes": outcome_distribution(match_up_rows),
            "batter_vs_bowler_type_sample": len(batter_vs_bowler_type_rows),
            "batter_vs_bowler_type_outcomes": outcome_distribution(batter_vs_bowler_type_rows),
            "bowler_vs_batter_type_sample": len(bowler_vs_batter_type_rows),
            "bowler_vs_batter_type_outcomes": outcome_distribution(bowler_vs_batter_type_rows),
        },
        "target_outcome": classify_delivery_outcome(target),
        "target_identity": {
            "season_id": int(target["season_id"]),
            "match_id": int(target["match_id"]),
            "innings": int(target["innings"]),
            "over_number": int(target["over_number"]),
            "ball_number": int(target["ball_number"]),
        },
    }

