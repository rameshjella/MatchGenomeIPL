from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import sqlite3
from typing import Any

from .constants import NON_BOWLER_WICKETS


@lru_cache(maxsize=1)
def _player_photo_map() -> dict[str, dict[str, Any]]:
    mapping_path = Path(__file__).resolve().parents[2] / "web" / "player_photos.json"
    if not mapping_path.exists():
        return {}
    try:
        import json

        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            mapped: dict[str, dict[str, Any]] = {}
            for key, value in payload.items():
                name = str(key)
                if isinstance(value, str):
                    mapped[name] = {
                        "kind": "local",
                        "url": value,
                        "source": "local_mapping",
                        "asset_type": "illustration",
                        "is_verified_photo": False,
                    }
                elif isinstance(value, dict):
                    url = str(value.get("url", "")).strip()
                    if url:
                        asset_type = str(value.get("asset_type", "")).strip() or "illustration"
                        is_verified_photo = bool(value.get("is_verified_photo", False))
                        mapped[name] = {
                            "kind": "local",
                            "url": url,
                            "source": str(value.get("source", "local_mapping")),
                            "license": value.get("license"),
                            "asset_type": asset_type,
                            "is_verified_photo": is_verified_photo,
                            "attribution": value.get("attribution"),
                        }
            return mapped
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


def _phase_order(phase: str) -> int:
    return {"powerplay": 0, "middle": 1, "death": 2}.get(phase, 99)


def _avatar_seed(name: str) -> int:
    return sum(ord(ch) for ch in name) % 360


def _photo_payload(conn: sqlite3.Connection, player_name: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            local_asset_path,
            source_reference,
            source_url,
            asset_type,
            is_verified_photo,
            license,
            attribution,
            verification_status
        FROM player_asset
        WHERE player_name = ?
        """,
        (player_name,),
    ).fetchone()
    if row is not None:
        local_asset = str(row["local_asset_path"] or "").strip()
        if local_asset:
            return {
                "kind": "local",
                "url": local_asset,
                "source": str(row["source_reference"] or "player_asset"),
                "source_url": row["source_url"],
                "license": row["license"],
                "asset_type": str(row["asset_type"] or "illustration"),
                "is_verified_photo": bool(row["is_verified_photo"]),
                "attribution": row["attribution"],
                "verification_status": row["verification_status"],
            }

    photo_map = _player_photo_map()
    if player_name in photo_map:
        return photo_map[player_name]
    return {
        "kind": "placeholder",
        "initials": _initials(player_name),
        "seed": _avatar_seed(player_name),
        "asset_type": "avatar_fallback",
        "is_verified_photo": False,
    }


def _evidence_tier(sample_size: int) -> str:
    if sample_size >= 120:
        return "high"
    if sample_size >= 40:
        return "medium"
    if sample_size >= 12:
        return "low"
    return "small"


def list_players(conn: sqlite3.Connection, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    raw = query.strip().lower()
    normalized = raw.replace(" ", "")
    q = f"%{raw}%"
    normalized_q = f"%{normalized}%"
    rows = conn.execute(
        """
        SELECT player_name
        FROM players
        WHERE ? = ''
           OR LOWER(player_name) LIKE ?
           OR REPLACE(LOWER(player_name), ' ', '') LIKE ?
        ORDER BY player_name
        LIMIT ?
        """,
        (raw, q, normalized_q, max(1, min(limit, 200))),
    ).fetchall()

    payload: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["player_name"])
        payload.append({"player_name": name, "photo": _photo_payload(conn, name)})
    return payload


def get_player_intelligence(conn: sqlite3.Connection, player_name: str) -> dict[str, Any]:
    row = conn.execute("SELECT 1 FROM players WHERE player_name = ?", (player_name,)).fetchone()
    if row is None:
        raise ValueError("player not found")

    placeholders = ",".join("?" for _ in NON_BOWLER_WICKETS)

    batting_agg = conn.execute(
        """
        SELECT runs, balls_faced, fours, sixes, dots
        FROM batter_stats_agg
        WHERE batter = ?
        """,
        (player_name,),
    ).fetchone()
    if batting_agg is None:
        batting_agg = {"runs": 0, "balls_faced": 0, "fours": 0, "sixes": 0, "dots": 0}

    batting_meta = conn.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN is_wicket = 1 AND player_out = ? THEN 1 ELSE 0 END), 0) AS outs,
            COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) AS innings
        FROM deliveries
        WHERE batter = ?
        """,
        (player_name, player_name),
    ).fetchone()

    bowling_agg = conn.execute(
        """
        SELECT runs_conceded, legal_balls, wickets, dots
        FROM bowler_stats_agg
        WHERE bowler = ?
        """,
        (player_name,),
    ).fetchone()
    if bowling_agg is None:
        bowling_agg = {"runs_conceded": 0, "legal_balls": 0, "wickets": 0, "dots": 0}

    batting_balls = int(batting_agg["balls_faced"])
    bowling_balls = int(bowling_agg["legal_balls"])

    bowling_meta = conn.execute(
        """
        SELECT COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) AS innings
        FROM deliveries
        WHERE bowler = ?
        """,
        (player_name,),
    ).fetchone()

    total_matches = conn.execute(
        """
        SELECT COUNT(DISTINCT season_id || '-' || match_id) AS matches
        FROM deliveries
        WHERE batter = ? OR bowler = ? OR non_striker = ? OR player_out = ? OR fielders_involved = ?
        """,
        (player_name, player_name, player_name, player_name, player_name),
    ).fetchone()

    batting_by_season: list[sqlite3.Row] = []
    batting_by_phase: list[sqlite3.Row] = []
    if batting_balls > 0:
        batting_by_season = conn.execute(
            """
            SELECT season_id,
                   SUM(batter_runs) AS runs,
                   SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END) AS balls,
                   SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END) AS fours,
                   SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END) AS sixes,
                   SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END) AS dots
            FROM deliveries
            WHERE batter = ?
            GROUP BY season_id
            ORDER BY season_id
            """,
            (player_name,),
        ).fetchall()

        batting_by_phase = conn.execute(
            f"""
            WITH player_innings AS (
                SELECT DISTINCT season_id, match_id, innings
                FROM deliveries
                WHERE batter = ?
            ),
            timeline AS (
                SELECT
                    d.*,
                    COALESCE(
                        SUM(d.legal_ball) OVER (
                            PARTITION BY d.season_id, d.match_id, d.innings
                            ORDER BY d.over_number, d.ball_number, d.source_row_number
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                        ),
                        0
                    ) AS legal_balls_before
                FROM deliveries d
                INNER JOIN player_innings pi
                    ON pi.season_id = d.season_id
                   AND pi.match_id = d.match_id
                   AND pi.innings = d.innings
            )
            SELECT phase,
                   SUM(batter_runs) AS runs,
                   SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END) AS balls,
                   SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END) AS dots
            FROM (
                SELECT *, {_phase_case()} AS phase
                FROM timeline
                WHERE batter = ?
            )
            GROUP BY phase
            """,
            (player_name, player_name),
        ).fetchall()

    bowling_by_season: list[sqlite3.Row] = []
    bowling_by_phase: list[sqlite3.Row] = []
    if bowling_balls > 0:
        bowling_by_season = conn.execute(
            f"""
            SELECT season_id,
                   SUM(total_runs - bye_runs - leg_bye_runs) AS runs_conceded,
                   SUM(legal_ball) AS legal_balls,
                   SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets,
                   SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END) AS dots
            FROM deliveries
            WHERE bowler = ?
            GROUP BY season_id
            ORDER BY season_id
            """,
            tuple(NON_BOWLER_WICKETS) + (player_name,),
        ).fetchall()

        bowling_by_phase = conn.execute(
            f"""
            WITH player_innings AS (
                SELECT DISTINCT season_id, match_id, innings
                FROM deliveries
                WHERE bowler = ?
            ),
            timeline AS (
                SELECT
                    d.*,
                    COALESCE(
                        SUM(d.legal_ball) OVER (
                            PARTITION BY d.season_id, d.match_id, d.innings
                            ORDER BY d.over_number, d.ball_number, d.source_row_number
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                        ),
                        0
                    ) AS legal_balls_before
                FROM deliveries d
                INNER JOIN player_innings pi
                    ON pi.season_id = d.season_id
                   AND pi.match_id = d.match_id
                   AND pi.innings = d.innings
            )
            SELECT
                phase,
                SUM(total_runs - bye_runs - leg_bye_runs) AS runs_conceded,
                SUM(legal_ball) AS legal_balls,
                SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets,
                SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END) AS dots
            FROM (
                SELECT *, {_phase_case()} AS phase
                FROM timeline
                WHERE bowler = ?
            )
            GROUP BY phase
            """,
            (player_name,) + tuple(NON_BOWLER_WICKETS) + (player_name,),
        ).fetchall()

    batting_outcomes_rows: list[sqlite3.Row] = []
    bowling_outcomes_rows: list[sqlite3.Row] = []
    if batting_balls > 0:
        batting_outcomes_rows = conn.execute(
            f"""
            SELECT {_delivery_outcome_case()} AS outcome_label, COUNT(*) AS deliveries
            FROM deliveries
            WHERE batter = ?
            GROUP BY outcome_label
            """,
            (player_name,),
        ).fetchall()
    if bowling_balls > 0:
        bowling_outcomes_rows = conn.execute(
            f"""
            SELECT {_delivery_outcome_case()} AS outcome_label, COUNT(*) AS deliveries
            FROM deliveries
            WHERE bowler = ?
            GROUP BY outcome_label
            """,
            (player_name,),
        ).fetchall()

    batter_vs_bowler: list[sqlite3.Row] = []
    bowler_vs_batter: list[sqlite3.Row] = []
    batter_vs_bowler_type: list[sqlite3.Row] = []
    bowler_vs_batter_type: list[sqlite3.Row] = []
    if batting_balls > 0:
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
    if bowling_balls > 0:
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

    batting_runs = int(batting_agg["runs"])
    dismissals = int(batting_meta["outs"])
    bowling_runs = int(bowling_agg["runs_conceded"])
    bowling_wickets = int(bowling_agg["wickets"])

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

    photo = _photo_payload(conn, player_name)

    return {
        "player": {
            "name": player_name,
            "photo": photo,
            "role": role,
            "role_label": role.replace("_", " ").title(),
        },
        "sections": {
            "has_batting": batting_balls > 0,
            "has_bowling": bowling_balls > 0,
        },
        "overview": {
            "matches": int(total_matches["matches"]),
            "batting_innings": int(batting_meta["innings"]),
            "bowling_innings": int(bowling_meta["innings"]),
            "batting": {
                "runs": batting_runs,
                "balls": batting_balls,
                "strike_rate": _safe_div(batting_runs * 100.0, batting_balls),
                "average": _safe_div(float(batting_runs), float(dismissals)),
                "fours": int(batting_agg["fours"]),
                "sixes": int(batting_agg["sixes"]),
                "boundaries": int(batting_agg["fours"]) + int(batting_agg["sixes"]),
                "dot_ball_rate": _safe_div(int(batting_agg["dots"]) * 100.0, batting_balls),
                "dismissals": dismissals,
            },
            "bowling": {
                "runs_conceded": bowling_runs,
                "legal_balls": bowling_balls,
                "wickets": bowling_wickets,
                "economy": _safe_div(bowling_runs * 6.0, bowling_balls),
                "strike_rate": _safe_div(float(bowling_balls), float(bowling_wickets)),
                "dot_ball_rate": _safe_div(int(bowling_agg["dots"]) * 100.0, bowling_balls),
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
                    "fours": int(r["fours"]),
                    "sixes": int(r["sixes"]),
                    "boundaries": int(r["fours"]) + int(r["sixes"]),
                    "dot_ball_rate": _safe_div(int(r["dots"]) * 100.0, int(r["balls"])),
                }
                for r in batting_by_season
            ],
            "by_phase": sorted(
                [
                {
                    "phase": str(r["phase"]),
                    "runs": int(r["runs"]),
                    "balls": int(r["balls"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["balls"])),
                    "dot_ball_rate": _safe_div(int(r["dots"]) * 100.0, int(r["balls"])),
                }
                for r in batting_by_phase
                ],
                key=lambda item: _phase_order(str(item["phase"])),
            ),
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
                    "dot_ball_rate": _safe_div(int(r["dots"]) * 100.0, int(r["legal_balls"])),
                    "strike_rate": _safe_div(float(int(r["legal_balls"])), float(int(r["wickets"]))),
                }
                for r in bowling_by_season
            ],
            "by_phase": sorted(
                [
                {
                    "phase": str(r["phase"]),
                    "runs_conceded": int(r["runs_conceded"]),
                    "legal_balls": int(r["legal_balls"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs_conceded"]) * 6.0, int(r["legal_balls"])),
                    "dot_ball_rate": _safe_div(int(r["dots"]) * 100.0, int(r["legal_balls"])),
                    "strike_rate": _safe_div(float(int(r["legal_balls"])), float(int(r["wickets"]))),
                }
                for r in bowling_by_phase
                ],
                key=lambda item: _phase_order(str(item["phase"])),
            ),
        },
        "matchups": {
            "batter_vs_bowler": [
                {
                    "opponent": str(r["opponent"]),
                    "sample_size": int(r["deliveries"]),
                    "runs": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["deliveries"])),
                    "evidence_tier": _evidence_tier(int(r["deliveries"])),
                }
                for r in batter_vs_bowler
                if int(r["deliveries"]) >= 4
            ],
            "bowler_vs_batter": [
                {
                    "opponent": str(r["opponent"]),
                    "sample_size": int(r["deliveries"]),
                    "runs_conceded": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs"]) * 6.0, int(r["deliveries"])),
                    "evidence_tier": _evidence_tier(int(r["deliveries"])),
                }
                for r in bowler_vs_batter
                if int(r["deliveries"]) >= 4
            ],
            "batter_vs_bowler_type": [
                {
                    "opponent_type": str(r["opponent_type"]),
                    "sample_size": int(r["deliveries"]),
                    "runs": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "strike_rate": _safe_div(int(r["runs"]) * 100.0, int(r["deliveries"])),
                    "evidence_tier": _evidence_tier(int(r["deliveries"])),
                }
                for r in batter_vs_bowler_type
                if int(r["deliveries"]) >= 4
            ],
            "bowler_vs_batter_type": [
                {
                    "opponent_type": str(r["opponent_type"]),
                    "sample_size": int(r["deliveries"]),
                    "runs_conceded": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                    "economy": _safe_div(int(r["runs"]) * 6.0, int(r["deliveries"])),
                    "evidence_tier": _evidence_tier(int(r["deliveries"])),
                }
                for r in bowler_vs_batter_type
                if int(r["deliveries"]) >= 4
            ],
        },
    }

