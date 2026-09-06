from __future__ import annotations

import sqlite3
from typing import Any

from .constants import NON_BOWLER_WICKETS, OUTCOME_LABELS


def classify_delivery_outcome(row: sqlite3.Row | dict[str, Any]) -> str:
    is_wicket = int(row["is_wicket"])
    if is_wicket == 1:
        return "wicket"

    total_runs = int(row["total_runs"])
    if total_runs == 0:
        return "0"
    if total_runs == 1:
        return "1"
    if total_runs == 2:
        return "2"
    if total_runs == 4:
        return "4"
    if total_runs == 6:
        return "6"
    return "3+"


def dataset_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    seasons = conn.execute("SELECT COUNT(DISTINCT season_id) FROM deliveries").fetchone()[0]
    matches = conn.execute("SELECT COUNT(DISTINCT match_id) FROM deliveries").fetchone()[0]
    deliveries = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
    innings = conn.execute("SELECT COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) FROM deliveries").fetchone()[0]
    wickets = conn.execute("SELECT COALESCE(SUM(is_wicket), 0) FROM deliveries").fetchone()[0]

    per_season = {
        row["season_id"]: row["match_count"]
        for row in conn.execute(
            "SELECT season_id, COUNT(DISTINCT match_id) AS match_count "
            "FROM deliveries GROUP BY season_id ORDER BY season_id"
        )
    }

    return {
        "seasons": seasons,
        "matches": matches,
        "deliveries": deliveries,
        "innings": innings,
        "wickets": wickets,
        "matches_per_season": per_season,
    }


def batter_stats(conn: sqlite3.Connection, batter: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(batter_runs), 0) AS runs,
            COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls_faced,
            COALESCE(SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END), 0) AS fours,
            COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes,
            COALESCE(SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS dots
        FROM deliveries
        WHERE batter = ?
        """,
        (batter,),
    ).fetchone()

    balls_faced = int(row["balls_faced"])
    runs = int(row["runs"])
    strike_rate = round((runs * 100.0 / balls_faced), 2) if balls_faced else 0.0
    dot_rate = round((int(row["dots"]) * 100.0 / balls_faced), 2) if balls_faced else 0.0

    return {
        "batter": batter,
        "runs": runs,
        "balls_faced": balls_faced,
        "strike_rate": strike_rate,
        "fours": int(row["fours"]),
        "sixes": int(row["sixes"]),
        "dot_ball_rate": dot_rate,
    }


def bowler_stats(conn: sqlite3.Connection, bowler: str) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in NON_BOWLER_WICKETS)
    row = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs_conceded,
            COALESCE(SUM(legal_ball), 0) AS legal_balls,
            COALESCE(SUM(CASE
                WHEN is_wicket = 1
                     AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders})
                THEN 1 ELSE 0 END), 0) AS wickets,
            COALESCE(SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END), 0) AS dots
        FROM deliveries
        WHERE bowler = ?
        """,
        tuple(NON_BOWLER_WICKETS) + (bowler,),
    ).fetchone()

    legal_balls = int(row["legal_balls"])
    overs = legal_balls / 6.0
    runs_conceded = int(row["runs_conceded"])
    economy = round(runs_conceded / overs, 2) if overs > 0 else 0.0
    dot_rate = round((int(row["dots"]) * 100.0 / legal_balls), 2) if legal_balls else 0.0

    return {
        "bowler": bowler,
        "runs_conceded": runs_conceded,
        "legal_balls": legal_balls,
        "economy": economy,
        "wickets": int(row["wickets"]),
        "dot_ball_rate": dot_rate,
    }


def innings_progression(conn: sqlite3.Connection, season_id: int, match_id: int, innings: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT over_number, ball_number,
               SUM(total_runs) OVER (
                   ORDER BY over_number, ball_number, source_row_number
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS score,
               SUM(is_wicket) OVER (
                   ORDER BY over_number, ball_number, source_row_number
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS wickets
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
        ORDER BY over_number, ball_number, source_row_number
        """,
        (season_id, match_id, innings),
    ).fetchall()

    return [
        {
            "over_number": int(r["over_number"]),
            "ball_number": int(r["ball_number"]),
            "score": int(r["score"]),
            "wickets": int(r["wickets"]),
        }
        for r in rows
    ]


def runs_wickets_by_over(conn: sqlite3.Connection, season_id: int, match_id: int, innings: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT over_number,
               SUM(total_runs) AS runs,
               SUM(is_wicket) AS wickets
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
        GROUP BY over_number
        ORDER BY over_number
        """,
        (season_id, match_id, innings),
    ).fetchall()
    return [{"over_number": int(r["over_number"]), "runs": int(r["runs"]), "wickets": int(r["wickets"])} for r in rows]


def current_score_at_delivery(conn: sqlite3.Connection, season_id: int, match_id: int, innings: int, over_number: int, ball_number: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(total_runs), 0) AS score,
            COALESCE(SUM(is_wicket), 0) AS wickets,
            COALESCE(SUM(legal_ball), 0) AS legal_balls
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND (over_number < ? OR (over_number = ? AND ball_number <= ?))
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number),
    ).fetchone()

    legal_balls = int(row["legal_balls"])
    overs = legal_balls / 6.0
    run_rate = round((int(row["score"]) / overs), 2) if overs > 0 else 0.0

    return {
        "score": int(row["score"]),
        "wickets": int(row["wickets"]),
        "legal_balls": legal_balls,
        "run_rate": run_rate,
    }


def outcome_distribution(rows: list[sqlite3.Row]) -> dict[str, int]:
    counts = {label: 0 for label in OUTCOME_LABELS}
    for row in rows:
        counts[classify_delivery_outcome(row)] += 1
    return counts

