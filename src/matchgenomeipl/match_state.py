from __future__ import annotations

import sqlite3
from typing import Any

from .analytics import classify_delivery_outcome
from .constants import OUTCOME_LABELS


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


def get_legal_balls_before_delivery(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
) -> int:
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(legal_ball), 0) AS legal_balls_before
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND {_before_innings_clause()}
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number),
    ).fetchone()
    return int(row["legal_balls_before"])


def _empty_outcome_counts() -> dict[str, int]:
    return {label: 0 for label in OUTCOME_LABELS}


def _outcome_counts_before_timeline(
    conn: sqlite3.Connection,
    timeline: str,
    where_clause: str = "",
    extra_params: tuple[Any, ...] = (),
) -> tuple[int, dict[str, int]]:
    rows = conn.execute(
        """
        SELECT
            CASE
                WHEN is_wicket = 1 THEN 'wicket'
                WHEN total_runs = 0 THEN '0'
                WHEN total_runs = 1 THEN '1'
                WHEN total_runs = 2 THEN '2'
                WHEN total_runs = 4 THEN '4'
                WHEN total_runs = 6 THEN '6'
                ELSE '3+'
            END AS outcome_label,
            COUNT(*) AS deliveries
        FROM deliveries
        WHERE timeline_key < ?
        """
        + where_clause
        + "\nGROUP BY outcome_label",
        (timeline,) + extra_params,
    ).fetchall()
    counts = _empty_outcome_counts()
    sample_size = 0
    for row in rows:
        label = str(row["outcome_label"])
        value = int(row["deliveries"])
        counts[label] = value
        sample_size += value
    return sample_size, counts


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

    timeline = str(target["timeline_key"])
    historical_delivery_count = conn.execute(
        "SELECT COUNT(*) AS n FROM deliveries WHERE timeline_key < ?",
        (timeline,),
    ).fetchone()

    batter_vs_bowler_sample, batter_vs_bowler_outcomes = _outcome_counts_before_timeline(
        conn,
        timeline,
        " AND batter = ? AND bowler = ?",
        (target["batter"], target["bowler"]),
    )
    batter_vs_bowler_type_sample, batter_vs_bowler_type_outcomes = _outcome_counts_before_timeline(
        conn,
        timeline,
        " AND batter = ? AND bowler_type = ?",
        (target["batter"], target["bowler_type"]),
    )
    bowler_vs_batter_type_sample, bowler_vs_batter_type_outcomes = _outcome_counts_before_timeline(
        conn,
        timeline,
        " AND bowler = ? AND batsman_type = ?",
        (target["bowler"], target["batsman_type"]),
    )

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
            "historical_delivery_count": int(historical_delivery_count["n"]),
            "batter_vs_bowler_sample": batter_vs_bowler_sample,
            "batter_vs_bowler_outcomes": batter_vs_bowler_outcomes,
            "batter_vs_bowler_type_sample": batter_vs_bowler_type_sample,
            "batter_vs_bowler_type_outcomes": batter_vs_bowler_type_outcomes,
            "bowler_vs_batter_type_sample": bowler_vs_batter_type_sample,
            "bowler_vs_batter_type_outcomes": bowler_vs_batter_type_outcomes,
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

