from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from .constants import NON_BOWLER_WICKETS


def _player_photo_map() -> dict[str, str]:
    mapping_path = Path(__file__).resolve().parents[2] / "web" / "player_photos.json"
    if not mapping_path.exists():
        return {}
    try:
        import json

        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items()}
    except Exception:
        return {}
    return {}


def _initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _phase_case(alias: str = "legal_balls_before") -> str:
    return f"CASE WHEN {alias} < 36 THEN 'powerplay' WHEN {alias} < 90 THEN 'middle' ELSE 'death' END"


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 2)


def _delivery_outcome_case() -> str:
    return (
        "CASE "
        "WHEN is_wicket = 1 THEN 'wicket' "
        "WHEN total_runs = 0 THEN '0' "
        "WHEN total_runs = 1 THEN '1' "
        "WHEN total_runs = 2 THEN '2' "
        "WHEN total_runs = 4 THEN '4' "
        "WHEN total_runs = 6 THEN '6' "
        "ELSE '3+' END"
    )


def list_players(conn: sqlite3.Connection, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    q = f"%{query.strip().lower()}%"
    rows = conn.execute(
        """
        SELECT player_name
        FROM players
        WHERE ? = '%%' OR LOWER(player_name) LIKE ?
        ORDER BY player_name
        LIMIT ?
        """,
        (q, q, max(1, min(limit, 200))),
    ).fetchall()

    photo_map = _player_photo_map()
    payload: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["player_name"])
        if name in photo_map:
            photo = {"kind": "local", "url": photo_map[name], "source": "local_mapping"}
        else:
            photo = {"kind": "placeholder", "initials": _initials(name)}
        payload.append({"player_name": name, "photo": photo})
    return payload


def get_player_intelligence(conn: sqlite3.Connection, player_name: str) -> dict[str, Any]:
    row = conn.execute("SELECT 1 FROM players WHERE player_name = ?", (player_name,)).fetchone()
    if row is None:
        raise ValueError("player not found")

    placeholders = ",".join("?" for _ in NON_BOWLER_WICKETS)

    batting = conn.execute(
        """
        SELECT
            COALESCE(SUM(batter_runs), 0) AS runs,
            COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls,
            COALESCE(SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END), 0) AS fours,
            COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes,
            COALESCE(SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS dots,
            COALESCE(SUM(CASE WHEN is_wicket = 1 AND player_out = ? THEN 1 ELSE 0 END), 0) AS outs,
            COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) AS innings
        FROM deliveries
        WHERE batter = ?
        """,
        (player_name, player_name),
    ).fetchone()

    bowling = conn.execute(
        f"""
        SELECT
            COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs_conceded,
            COALESCE(SUM(legal_ball), 0) AS legal_balls,
            COALESCE(SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END), 0) AS wickets,
            COALESCE(SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END), 0) AS dots,
            COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) AS innings
        FROM deliveries
        WHERE bowler = ?
        """,
        tuple(NON_BOWLER_WICKETS) + (player_name,),
    ).fetchone()

    total_matches = conn.execute(
        """
        SELECT COUNT(DISTINCT season_id || '-' || match_id) AS matches
        FROM deliveries
        WHERE batter = ? OR bowler = ? OR non_striker = ? OR player_out = ? OR fielders_involved = ?
        """,
        (player_name, player_name, player_name, player_name, player_name),
    ).fetchone()

    batting_by_season = conn.execute(
        """
        SELECT season_id,
               SUM(batter_runs) AS runs,
               SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END) AS balls,
               SUM(CASE WHEN batter_runs IN (4, 6) THEN 1 ELSE 0 END) AS boundaries
        FROM deliveries
        WHERE batter = ?
        GROUP BY season_id
        ORDER BY season_id
        """,
        (player_name,),
    ).fetchall()

    batting_by_phase = conn.execute(
        f"""
        SELECT phase,
               SUM(batter_runs) AS runs,
               SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END) AS balls,
               SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END) AS dots
        FROM (
            SELECT base.*, {_phase_case()} AS phase
            FROM (
                SELECT d.*,
                       COALESCE(
                           SUM(legal_ball) OVER (
                               PARTITION BY season_id, match_id, innings
                               ORDER BY over_number, ball_number, source_row_number
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                           ),
                           0
                       ) AS legal_balls_before
                FROM deliveries d
                WHERE batter = ?
            ) base
        )
        GROUP BY phase
        ORDER BY phase
        """,
        (player_name,),
    ).fetchall()

    bowling_by_season = conn.execute(
        f"""
        SELECT season_id,
               SUM(total_runs - bye_runs - leg_bye_runs) AS runs_conceded,
               SUM(legal_ball) AS legal_balls,
               SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets
        FROM deliveries
        WHERE bowler = ?
        GROUP BY season_id
        ORDER BY season_id
        """,
        tuple(NON_BOWLER_WICKETS) + (player_name,),
    ).fetchall()

    bowling_by_phase = conn.execute(
        f"""
        SELECT phase,
               SUM(total_runs - bye_runs - leg_bye_runs) AS runs_conceded,
               SUM(legal_ball) AS legal_balls,
               SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets
        FROM (
            SELECT base.*, {_phase_case()} AS phase
            FROM (
                SELECT d.*,
                       COALESCE(
                           SUM(legal_ball) OVER (
                               PARTITION BY season_id, match_id, innings
                               ORDER BY over_number, ball_number, source_row_number
                               ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                           ),
                           0
                       ) AS legal_balls_before
                FROM deliveries d
                WHERE bowler = ?
            ) base
        )
        GROUP BY phase
        ORDER BY phase
        """,
        tuple(NON_BOWLER_WICKETS) + (player_name,),
    ).fetchall()

    batting_outcomes_rows = conn.execute(
        f"""
        SELECT {_delivery_outcome_case()} AS outcome_label, COUNT(*) AS deliveries
        FROM deliveries
        WHERE batter = ?
        GROUP BY outcome_label
        """,
        (player_name,),
    ).fetchall()

    bowling_outcomes_rows = conn.execute(
        f"""
        SELECT {_delivery_outcome_case()} AS outcome_label, COUNT(*) AS deliveries
        FROM deliveries
        WHERE bowler = ?
        GROUP BY outcome_label
        """,
        (player_name,),
    ).fetchall()

    batter_vs_bowler = conn.execute(
        """
        SELECT bowler AS opponent, deliveries, runs, wickets
        FROM batter_bowler_stats_agg
        WHERE batter = ?
        ORDER BY deliveries DESC, opponent
        LIMIT 12
        """,
        (player_name,),
    ).fetchall()

    bowler_vs_batter = conn.execute(
        """
        SELECT batter AS opponent, deliveries, runs, wickets
        FROM batter_bowler_stats_agg
        WHERE bowler = ?
        ORDER BY deliveries DESC, opponent
        LIMIT 12
        """,
        (player_name,),
    ).fetchall()

    batter_vs_bowler_type = conn.execute(
        """
        SELECT COALESCE(bowler_type, 'unknown') AS opponent_type, deliveries, runs, wickets
        FROM batter_bowler_type_stats_agg
        WHERE batter = ?
        ORDER BY deliveries DESC, opponent_type
        LIMIT 8
        """,
        (player_name,),
    ).fetchall()

    bowler_vs_batter_type = conn.execute(
        """
        SELECT COALESCE(batsman_type, 'unknown') AS opponent_type, deliveries, runs, wickets
        FROM bowler_batter_type_stats_agg
        WHERE bowler = ?
        ORDER BY deliveries DESC, opponent_type
        LIMIT 8
        """,
        (player_name,),
    ).fetchall()

    batting_runs = int(batting["runs"])
    batting_balls = int(batting["balls"])
    dismissals = int(batting["outs"])
    bowling_runs = int(bowling["runs_conceded"])
    bowling_balls = int(bowling["legal_balls"])
    bowling_wickets = int(bowling["wickets"])

    role = "all_rounder"
    if batting_balls > 0 and bowling_balls == 0:
        role = "batter"
    elif bowling_balls > 0 and batting_balls == 0:
        role = "bowler"
    elif batting_balls == 0 and bowling_balls == 0:
        role = "unknown"

    outcomes_template = {k: 0 for k in ["0", "1", "2", "3+", "4", "6", "wicket"]}
    batting_outcomes = dict(outcomes_template)
    for item in batting_outcomes_rows:
        batting_outcomes[str(item["outcome_label"])] = int(item["deliveries"])

    bowling_outcomes = dict(outcomes_template)
    for item in bowling_outcomes_rows:
        bowling_outcomes[str(item["outcome_label"])] = int(item["deliveries"])

    photo_map = _player_photo_map()
    if player_name in photo_map:
        photo = {"kind": "local", "url": photo_map[player_name], "source": "local_mapping"}
    else:
        photo = {"kind": "placeholder", "initials": _initials(player_name)}

    return {
        "player": {"name": player_name, "photo": photo, "role": role},
        "overview": {
            "matches": int(total_matches["matches"]),
            "batting_innings": int(batting["innings"]),
            "bowling_innings": int(bowling["innings"]),
            "batting": {
                "runs": batting_runs,
                "balls": batting_balls,
                "strike_rate": _safe_div(batting_runs * 100.0, batting_balls),
                "average": _safe_div(float(batting_runs), float(dismissals)),
                "fours": int(batting["fours"]),
                "sixes": int(batting["sixes"]),
                "boundaries": int(batting["fours"]) + int(batting["sixes"]),
                "dot_ball_rate": _safe_div(int(batting["dots"]) * 100.0, batting_balls),
                "dismissals": dismissals,
            },
            "bowling": {
                "runs_conceded": bowling_runs,
                "legal_balls": bowling_balls,
                "wickets": bowling_wickets,
                "economy": _safe_div(bowling_runs * 6.0, bowling_balls),
                "strike_rate": _safe_div(float(bowling_balls), float(bowling_wickets)),
                "dot_ball_rate": _safe_div(int(bowling["dots"]) * 100.0, bowling_balls),
            },
        },
        "batting_intelligence": {
            "outcome_distribution": batting_outcomes,
            "by_season": [
                {
                    "season_id": int(r["season_id"]),
                    "runs": int(r["runs"]),
                    "balls": int(r["balls"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["balls"])),
                    "boundaries": int(r["boundaries"]),
                }
                for r in batting_by_season
            ],
            "by_phase": [
                {
                    "phase": str(r["phase"]),
                    "runs": int(r["runs"]),
                    "balls": int(r["balls"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["balls"])),
                    "dot_ball_rate": _safe_div(int(r["dots"]) * 100.0, int(r["balls"])),
                }
                for r in batting_by_phase
            ],
        },
        "bowling_intelligence": {
            "outcome_distribution": bowling_outcomes,
            "by_season": [
                {
                    "season_id": int(r["season_id"]),
                    "runs_conceded": int(r["runs_conceded"]),
                    "legal_balls": int(r["legal_balls"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs_conceded"]) * 6.0, int(r["legal_balls"])),
                }
                for r in bowling_by_season
            ],
            "by_phase": [
                {
                    "phase": str(r["phase"]),
                    "runs_conceded": int(r["runs_conceded"]),
                    "legal_balls": int(r["legal_balls"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs_conceded"]) * 6.0, int(r["legal_balls"])),
                }
                for r in bowling_by_phase
            ],
        },
        "matchups": {
            "batter_vs_bowler": [
                {
                    "opponent": str(r["opponent"]),
                    "sample_size": int(r["deliveries"]),
                    "runs": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["deliveries"])),
                }
                for r in batter_vs_bowler
                if int(r["deliveries"]) >= 8
            ],
            "bowler_vs_batter": [
                {
                    "opponent": str(r["opponent"]),
                    "sample_size": int(r["deliveries"]),
                    "runs_conceded": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs"]) * 6.0, int(r["deliveries"])),
                }
                for r in bowler_vs_batter
                if int(r["deliveries"]) >= 8
            ],
            "batter_vs_bowler_type": [
                {
                    "opponent_type": str(r["opponent_type"]),
                    "sample_size": int(r["deliveries"]),
                    "runs": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["deliveries"])),
                }
                for r in batter_vs_bowler_type
                if int(r["deliveries"]) >= 12
            ],
            "bowler_vs_batter_type": [
                {
                    "opponent_type": str(r["opponent_type"]),
                    "sample_size": int(r["deliveries"]),
                    "runs_conceded": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs"]) * 6.0, int(r["deliveries"])),
                }
                for r in bowler_vs_batter_type
                if int(r["deliveries"]) >= 12
            ],
        },
    }

