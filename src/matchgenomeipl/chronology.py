from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

CHRONOLOGY_METHOD = "season_match_innings_over_ball_source_row"


@dataclass(frozen=True)
class KnowledgeCutoff:
    season_id_inclusive: int

    def allows_season(self, season_id: int) -> bool:
        return season_id <= self.season_id_inclusive


@dataclass(frozen=True)
class EvaluationWindow:
    season_id: int


def chronology_diagnostics(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT season_id, MIN(match_id) AS min_match_id, MAX(match_id) AS max_match_id,
               COUNT(DISTINCT match_id) AS match_count
        FROM deliveries
        GROUP BY season_id
        ORDER BY season_id
        """
    ).fetchall()

    seasons = [int(r["season_id"]) for r in rows]
    adjacent_overlaps: list[dict[str, Any]] = []
    match_id_monotonic_across_seasons = True
    prev_max = None

    for idx in range(len(rows) - 1):
        left = rows[idx]
        right = rows[idx + 1]
        overlap = not (
            int(left["max_match_id"]) < int(right["min_match_id"])
            or int(right["max_match_id"]) < int(left["min_match_id"])
        )
        adjacent_overlaps.append(
            {
                "left_season": int(left["season_id"]),
                "right_season": int(right["season_id"]),
                "match_id_range_overlap": overlap,
            }
        )

    for row in rows:
        min_mid = int(row["min_match_id"])
        max_mid = int(row["max_match_id"])
        if prev_max is not None and min_mid < prev_max:
            match_id_monotonic_across_seasons = False
        prev_max = max(prev_max or max_mid, max_mid)

    return {
        "chronology_method": CHRONOLOGY_METHOD,
        "season_values": seasons,
        "adjacent_season_match_id_range_overlap": adjacent_overlaps,
        "match_id_monotonic_across_seasons": match_id_monotonic_across_seasons,
        "chronology_limitation": (
            "No explicit match date is available in the local dataset. "
            "Chronology currently uses season_id then match_id then innings/ball order. "
            "This is deterministic but replaceable when true match dates are added."
        ),
    }


def ordered_deliveries(conn: sqlite3.Connection, max_rows: int | None = None) -> list[sqlite3.Row]:
    limit_clause = ""
    params: tuple[Any, ...] = ()
    if max_rows is not None:
        limit_clause = " LIMIT ?"
        params = (max_rows,)

    query = (
        """
        SELECT
            season_id,
            match_id,
            innings,
            over_number,
            ball_number,
            source_row_number,
            batter,
            bowler,
            batsman_type,
            bowler_type,
            total_runs,
            is_wicket,
            legal_ball,
            timeline_key,
            COALESCE(
                SUM(legal_ball) OVER (
                    PARTITION BY season_id, match_id, innings
                    ORDER BY over_number, ball_number, source_row_number
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ),
                0
            ) AS legal_balls_before
        FROM deliveries
        ORDER BY season_id, match_id, innings, over_number, ball_number, source_row_number
        """
        + limit_clause
    )
    return conn.execute(query, params).fetchall()

