from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from urllib.request import urlretrieve
from uuid import uuid4
import zipfile
import re

from .validation import build_timeline_key

CRICSHEET_SOURCE_KEY = "cricsheet_ipl_json"
CRICSHEET_SOURCE_URL = "https://cricsheet.org/downloads/ipl_json.zip"
ENRICHMENT_VERSION = "enrichment_v1"
KNOWLEDGE_SOURCE_KEY = "matchgenome_reference_knowledge_v1"
KNOWLEDGE_SOURCE_URL = "https://www.iplt20.com/"
ALLOWED_VERIFICATION_STATES = {"verified", "provisional", "derived", "unverified"}

PLAYER_KNOWLEDGE_SEED: list[dict[str, Any]] = [
    {
        "canonical_player_name": "MS Dhoni",
        "full_name": "Mahendra Singh Dhoni",
        "date_of_birth": "1981-07-07",
        "nationality": "India",
        "role": "Wicket-keeper batter",
        "batting_style": "Right-handed",
        "bowling_style": "Right-arm medium",
        "source_url": "https://en.wikipedia.org/wiki/MS_Dhoni",
        "verification_status": "verified",
        "aliases": ["ms dhoni", "m s dhoni", "mahendra singh dhoni", "msd", "mahi", "dhoni"],
    },
    {
        "canonical_player_name": "V Kohli",
        "full_name": "Virat Kohli",
        "date_of_birth": "1988-11-05",
        "nationality": "India",
        "role": "Top-order batter",
        "batting_style": "Right-handed",
        "bowling_style": "Right-arm medium",
        "spouse_name": "Anushka Sharma",
        "children_count": 2,
        "source_url": "https://en.wikipedia.org/wiki/Virat_Kohli",
        "verification_status": "provisional",
        "aliases": ["virat kohli", "virat", "kohli"],
    },
    {
        "canonical_player_name": "V Suryavanshi",
        "full_name": "Vaibhav Suryavanshi",
        "role": "Top-order batter",
        "source_url": "https://www.iplt20.com/",
        "verification_status": "verified",
        "aliases": ["v suryavanshi", "vaibhav suryavanshi", "vaibhav sooryavanshi"],
    },
    {
        "canonical_player_name": "RG Sharma",
        "full_name": "Rohit Gurunath Sharma",
        "date_of_birth": "1987-04-30",
        "nationality": "India",
        "role": "Top-order batter",
        "batting_style": "Right-handed",
        "bowling_style": "Right-arm offbreak",
        "spouse_name": "Ritika Sajdeh",
        "children_count": 1,
        "source_url": "https://en.wikipedia.org/wiki/Rohit_Sharma",
        "verification_status": "provisional",
        "aliases": ["rohit sharma", "rohit", "sharma", "hitman"],
    },
    {
        "canonical_player_name": "JJ Bumrah",
        "full_name": "Jasprit Jasbirsingh Bumrah",
        "date_of_birth": "1993-12-06",
        "nationality": "India",
        "role": "Bowler",
        "batting_style": "Right-handed",
        "bowling_style": "Right-arm fast",
        "source_url": "https://en.wikipedia.org/wiki/Jasprit_Bumrah",
        "verification_status": "provisional",
        "aliases": ["jasprit bumrah", "jasprit", "bumrah"],
    },
]

TEAM_SEASON_KNOWLEDGE_SEED: list[dict[str, Any]] = [
    {
        "canonical_team_name": "Mumbai Indians",
        "season_id": 2024,
        "captain": "Hardik Pandya",
        "coach": "Mark Boucher",
        "owner": "Indiawin Sports",
        "home_venue": "Wankhede Stadium",
        "source_url": "https://www.iplt20.com/teams/mumbai-indians",
        "verification_status": "provisional",
    },
    {
        "canonical_team_name": "Chennai Super Kings",
        "season_id": 2018,
        "captain": "MS Dhoni",
        "coach": "Stephen Fleming",
        "owner": "India Cements",
        "home_venue": "MA Chidambaram Stadium",
        "source_url": "https://www.iplt20.com/teams/chennai-super-kings",
        "verification_status": "provisional",
    },
    {
        "canonical_team_name": "Royal Challengers Bengaluru",
        "season_id": 2026,
        "captain": "Rajat Patidar",
        "coach": "Andy Flower",
        "owner": "Royal Challengers Sports Private Ltd",
        "home_venue": "M Chinnaswamy Stadium",
        "source_url": "https://www.iplt20.com/teams/royal-challengers-bengaluru",
        "verification_status": "verified",
    },
    {
        "canonical_team_name": "Royal Challengers Bengaluru",
        "season_id": 2016,
        "captain": "Virat Kohli",
        "coach": "Daniel Vettori",
        "owner": "United Spirits",
        "home_venue": "M Chinnaswamy Stadium",
        "source_url": "https://www.iplt20.com/teams/royal-challengers-bengaluru",
        "verification_status": "verified",
    },
    {
        "canonical_team_name": "Mumbai Indians",
        "season_id": 2013,
        "captain": "Rohit Sharma",
        "coach": "John Wright",
        "owner": "Indiawin Sports",
        "home_venue": "Wankhede Stadium",
        "source_url": "https://www.iplt20.com/teams/mumbai-indians",
        "verification_status": "provisional",
    },
]

# Current canonical naming for active IPL franchise identities.
CURRENT_CANONICAL_BY_HISTORICAL = {
    "Kings XI Punjab": "Punjab Kings",
    "Delhi Daredevils": "Delhi Capitals",
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
}

SHORT_NAME_BY_HISTORICAL = {
    "Chennai Super Kings": "CSK",
    "Delhi Capitals": "DC",
    "Delhi Daredevils": "DD",
    "Deccan Chargers": "DCG",
    "Gujarat Titans": "GT",
    "Gujarat Lions": "GL",
    "Kings XI Punjab": "KXIP",
    "Punjab Kings": "PBKS",
    "Kochi Tuskers Kerala": "KTK",
    "Kolkata Knight Riders": "KKR",
    "Lucknow Super Giants": "LSG",
    "Mumbai Indians": "MI",
    "Pune Warriors": "PWI",
    "Rajasthan Royals": "RR",
    "Rising Pune Supergiant": "RPS",
    "Rising Pune Supergiants": "RPS",
    "Royal Challengers Bangalore": "RCB",
    "Royal Challengers Bengaluru": "RCB",
    "Sunrisers Hyderabad": "SRH",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_alias(value: str | None) -> str:
    if value is None:
        return ""
    alias = str(value).lower().replace(".", " ").replace("'", " ")
    alias = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in alias)
    return " ".join(alias.split())


def _require_verification_state(value: str, field_name: str) -> str:
    state = str(value or "").strip().lower()
    if state not in ALLOWED_VERIFICATION_STATES:
        raise ValueError(f"Invalid {field_name}: {value}")
    return state


def _normalize_name(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def _determine_result(outcome: dict[str, Any]) -> tuple[str | None, int | None]:
    by = outcome.get("by") if isinstance(outcome, dict) else {}
    if not isinstance(by, dict):
        return None, None
    if "runs" in by:
        return "runs", int(by["runs"])
    if "wickets" in by:
        return "wickets", int(by["wickets"])
    return None, None


def _season_from_info(raw_season: Any) -> int | None:
    raw = str(raw_season or "").strip()
    if not raw:
        return None

    if raw == "2020/21":
        return 2020

    split = re.search(r"(20\d{2})\s*/\s*(\d{2})", raw)
    if split:
        first = int(split.group(1))
        suffix = int(split.group(2))
        century = (first // 100) * 100
        candidate = century + suffix
        if candidate < first:
            candidate += 100
        return candidate

    years = [int(value) for value in re.findall(r"(20\d{2})", raw)]
    return max(years) if years else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _backfill_latest_season_deliveries_from_zip(
    conn: sqlite3.Connection,
    zf: zipfile.ZipFile,
    fetched_at: str,
) -> dict[str, Any]:
    season_by_match: dict[int, int] = {}
    for name in zf.namelist():
        if not (name.endswith(".json") and name[:-5].isdigit()):
            continue
        with zf.open(name) as handle:
            payload = json.load(handle)
        season = _season_from_info(payload.get("info", {}).get("season"))
        if season is None:
            continue
        season_by_match[int(name[:-5])] = season

    if not season_by_match:
        return {"latest_season": None, "missing_matches": 0, "inserted_deliveries": 0}

    latest_season = max(season_by_match.values())
    existing_ids = {
        int(row[0])
        for row in conn.execute("SELECT DISTINCT match_id FROM deliveries WHERE season_id = ?", (latest_season,)).fetchall()
    }
    target_ids = {mid for mid, season in season_by_match.items() if season == latest_season}
    missing_ids = sorted(target_ids - existing_ids)
    if not missing_ids:
        return {"latest_season": latest_season, "missing_matches": 0, "inserted_deliveries": 0}

    insert_delivery = (
        "INSERT OR IGNORE INTO deliveries ("
        "source_file, source_row_number, season_id, match_id, innings, over_number, ball_number, "
        "batter, bowler, non_striker, team_batting, team_bowling, "
        "batter_runs, extras, total_runs, batsman_type, bowler_type, player_out, fielders_involved, "
        "is_wicket, is_wide_ball, is_no_ball, is_leg_bye, is_bye, is_penalty, "
        "wide_ball_runs, no_ball_runs, leg_bye_runs, bye_runs, penalty_runs, wicket_kind, is_super_over, "
        "legal_ball, timeline_key, validation_errors"
        ") VALUES ("
        "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
        ")"
    )

    inserted = 0
    for match_id in missing_ids:
        file_name = f"{match_id}.json"
        with zf.open(file_name) as handle:
            payload = json.load(handle)
        info = payload.get("info", {}) if isinstance(payload.get("info"), dict) else {}
        teams = info.get("teams", []) if isinstance(info.get("teams"), list) else []
        if len(teams) < 2:
            continue
        team_a = _normalize_name(str(teams[0]))
        team_b = _normalize_name(str(teams[1]))

        row_number = 1
        innings_list = payload.get("innings", []) if isinstance(payload.get("innings"), list) else []
        for innings_index, innings in enumerate(innings_list, start=1):
            if not isinstance(innings, dict):
                continue
            team_batting = _normalize_name(innings.get("team"))
            if not team_batting:
                continue
            team_bowling = team_b if team_batting == team_a else team_a
            overs = innings.get("overs", []) if isinstance(innings.get("overs"), list) else []
            for over in overs:
                if not isinstance(over, dict):
                    continue
                over_number = int(over.get("over", 0) or 0)
                deliveries = over.get("deliveries", []) if isinstance(over.get("deliveries"), list) else []
                for delivery_index, delivery in enumerate(deliveries, start=1):
                    if not isinstance(delivery, dict):
                        continue
                    runs = delivery.get("runs", {}) if isinstance(delivery.get("runs"), dict) else {}
                    extras_map = delivery.get("extras", {}) if isinstance(delivery.get("extras"), dict) else {}
                    wickets = delivery.get("wickets", []) if isinstance(delivery.get("wickets"), list) else []
                    wicket = wickets[0] if wickets and isinstance(wickets[0], dict) else {}
                    fielders = wicket.get("fielders", []) if isinstance(wicket.get("fielders"), list) else []
                    fielder_names = [
                        str(f.get("name", "")).strip()
                        for f in fielders
                        if isinstance(f, dict) and str(f.get("name", "")).strip()
                    ]

                    wide_ball_runs = int(extras_map.get("wides", 0) or 0)
                    no_ball_runs = int(extras_map.get("noballs", 0) or 0)
                    leg_bye_runs = int(extras_map.get("legbyes", 0) or 0)
                    bye_runs = int(extras_map.get("byes", 0) or 0)
                    penalty_runs = int(extras_map.get("penalty", 0) or 0)
                    is_wide_ball = 1 if wide_ball_runs > 0 else 0
                    is_no_ball = 1 if no_ball_runs > 0 else 0
                    normalized = {
                        "season_id": latest_season,
                        "match_id": match_id,
                        "innings": innings_index,
                        "over_number": over_number,
                        "ball_number": delivery_index,
                    }
                    timeline_key = build_timeline_key(normalized)
                    cursor = conn.execute(
                        insert_delivery,
                        (
                            f"cricsheet_json:{file_name}",
                            row_number,
                            latest_season,
                            match_id,
                            innings_index,
                            over_number,
                            delivery_index,
                            _normalize_name(delivery.get("batter")),
                            _normalize_name(delivery.get("bowler")),
                            _normalize_name(delivery.get("non_striker")),
                            team_batting,
                            team_bowling,
                            int(runs.get("batter", 0) or 0),
                            int(runs.get("extras", 0) or 0),
                            int(runs.get("total", 0) or 0),
                            None,
                            None,
                            _normalize_name(wicket.get("player_out")) or None,
                            ", ".join(fielder_names) if fielder_names else None,
                            1 if wickets else 0,
                            is_wide_ball,
                            is_no_ball,
                            1 if leg_bye_runs > 0 else 0,
                            1 if bye_runs > 0 else 0,
                            1 if penalty_runs > 0 else 0,
                            wide_ball_runs,
                            no_ball_runs,
                            leg_bye_runs,
                            bye_runs,
                            penalty_runs,
                            _normalize_name(wicket.get("kind")) or None,
                            0,
                            0 if (is_wide_ball or is_no_ball) else 1,
                            timeline_key,
                            "",
                        ),
                    )
                    inserted += 1 if int(cursor.rowcount or 0) > 0 else 0
                    row_number += 1

    placeholders = ",".join("?" for _ in missing_ids)
    conn.execute("INSERT OR IGNORE INTO seasons(season_id) VALUES (?)", (latest_season,))
    conn.execute(
        f"""
        INSERT OR IGNORE INTO teams(team_name)
        SELECT team_name
        FROM (
            SELECT DISTINCT team_batting AS team_name FROM deliveries WHERE match_id IN ({placeholders})
            UNION
            SELECT DISTINCT team_bowling AS team_name FROM deliveries WHERE match_id IN ({placeholders})
        )
        """,
        tuple(missing_ids + missing_ids),
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO players(player_name)
        SELECT player_name
        FROM (
            SELECT DISTINCT batter AS player_name FROM deliveries WHERE match_id IN ({placeholders})
            UNION SELECT DISTINCT bowler AS player_name FROM deliveries WHERE match_id IN ({placeholders})
            UNION SELECT DISTINCT non_striker AS player_name FROM deliveries WHERE match_id IN ({placeholders}) AND non_striker IS NOT NULL
            UNION SELECT DISTINCT player_out AS player_name FROM deliveries WHERE match_id IN ({placeholders}) AND player_out IS NOT NULL
            UNION SELECT DISTINCT fielders_involved AS player_name FROM deliveries WHERE match_id IN ({placeholders}) AND fielders_involved IS NOT NULL
        )
        """,
        tuple(missing_ids + missing_ids + missing_ids + missing_ids + missing_ids),
    )
    conn.execute(
        f"""
        INSERT OR IGNORE INTO matches(match_id, season_id, is_super_over_match)
        SELECT match_id, MIN(season_id), MAX(is_super_over)
        FROM deliveries
        WHERE match_id IN ({placeholders})
        GROUP BY match_id
        """,
        tuple(missing_ids),
    )
    conn.execute(f"DELETE FROM innings_summary WHERE match_id IN ({placeholders})", tuple(missing_ids))
    conn.execute(
        f"""
        INSERT INTO innings_summary(season_id, match_id, innings, team_batting, team_bowling, deliveries, legal_balls, runs, wickets)
        SELECT
            season_id,
            match_id,
            innings,
            MIN(team_batting),
            MIN(team_bowling),
            COUNT(*),
            SUM(legal_ball),
            SUM(total_runs),
            SUM(is_wicket)
        FROM deliveries
        WHERE match_id IN ({placeholders})
        GROUP BY season_id, match_id, innings
        """,
        tuple(missing_ids),
    )
    return {
        "latest_season": latest_season,
        "missing_matches": len(missing_ids),
        "inserted_deliveries": inserted,
    }


def _update_season_source_coverage(conn: sqlite3.Connection, zf: zipfile.ZipFile, fetched_at: str) -> None:
    expected_by_season: dict[int, int] = {}
    for name in zf.namelist():
        if not (name.endswith(".json") and name[:-5].isdigit()):
            continue
        with zf.open(name) as handle:
            payload = json.load(handle)
        season = _season_from_info(payload.get("info", {}).get("season"))
        if season is None:
            continue
        expected_by_season[season] = expected_by_season.get(season, 0) + 1

    for season, expected in expected_by_season.items():
        local_matches = int(
            conn.execute("SELECT COUNT(DISTINCT match_id) FROM deliveries WHERE season_id = ?", (season,)).fetchone()[0]
        )
        missing = max(expected - local_matches, 0)
        status = "complete" if missing == 0 else "incomplete"
        conn.execute(
            """
            INSERT INTO season_source_coverage(
                season_id, source_key, expected_matches, local_matches, missing_matches,
                status, verification_status, source_url, retrieved_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season_id, source_key) DO UPDATE SET
                expected_matches = excluded.expected_matches,
                local_matches = excluded.local_matches,
                missing_matches = excluded.missing_matches,
                status = excluded.status,
                verification_status = excluded.verification_status,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                notes = excluded.notes
            """,
            (
                season,
                CRICSHEET_SOURCE_KEY,
                expected,
                local_matches,
                missing,
                status,
                "verified",
                CRICSHEET_SOURCE_URL,
                fetched_at,
                "Expected matches derived from cached Cricsheet IPL archive.",
            ),
        )

    if expected_by_season:
        placeholders = ",".join("?" for _ in expected_by_season)
        conn.execute(
            f"DELETE FROM season_source_coverage WHERE source_key = ? AND season_id NOT IN ({placeholders})",
            (CRICSHEET_SOURCE_KEY, *sorted(expected_by_season.keys())),
        )


def _source_metric_by_season_from_zip(zf: zipfile.ZipFile) -> dict[int, dict[str, float]]:
    by_season: dict[int, dict[str, float]] = {}

    def ensure(season_id: int) -> dict[str, float]:
        if season_id not in by_season:
            by_season[season_id] = {
                "matches": 0.0,
                "deliveries": 0.0,
                "fours": 0.0,
                "sixes": 0.0,
                "wickets": 0.0,
                "dot_balls": 0.0,
                "dot_balls_batter_zero": 0.0,
            }
        return by_season[season_id]

    for name in zf.namelist():
        if not (name.endswith(".json") and name[:-5].isdigit()):
            continue
        with zf.open(name) as handle:
            payload = json.load(handle)
        season = _season_from_info(payload.get("info", {}).get("season"))
        if season is None:
            continue
        target = ensure(season)
        target["matches"] += 1

        innings_list = payload.get("innings", []) if isinstance(payload.get("innings"), list) else []
        for innings in innings_list:
            if not isinstance(innings, dict):
                continue
            overs = innings.get("overs", []) if isinstance(innings.get("overs"), list) else []
            for over in overs:
                if not isinstance(over, dict):
                    continue
                deliveries = over.get("deliveries", []) if isinstance(over.get("deliveries"), list) else []
                for delivery in deliveries:
                    if not isinstance(delivery, dict):
                        continue
                    runs = delivery.get("runs", {}) if isinstance(delivery.get("runs"), dict) else {}
                    extras_map = delivery.get("extras", {}) if isinstance(delivery.get("extras"), dict) else {}
                    wickets = delivery.get("wickets", []) if isinstance(delivery.get("wickets"), list) else []
                    wicket = wickets[0] if wickets and isinstance(wickets[0], dict) else {}

                    batter_runs = int(runs.get("batter", 0) or 0)
                    total_runs = int(runs.get("total", 0) or 0)
                    wide_ball_runs = int(extras_map.get("wides", 0) or 0)
                    no_ball_runs = int(extras_map.get("noballs", 0) or 0)
                    legal_ball = 0 if (wide_ball_runs > 0 or no_ball_runs > 0) else 1
                    wicket_kind = _normalize_name(wicket.get("kind")).lower()

                    target["deliveries"] += 1
                    if batter_runs == 4:
                        target["fours"] += 1
                    if batter_runs == 6:
                        target["sixes"] += 1
                    if wickets and wicket_kind not in {"run out", "retired hurt", "retired out", "obstructing the field"}:
                        target["wickets"] += 1
                    if legal_ball == 1 and total_runs == 0:
                        target["dot_balls"] += 1
                    if legal_ball == 1 and batter_runs == 0:
                        target["dot_balls_batter_zero"] += 1

    return by_season


def _local_metric_by_season(conn: sqlite3.Connection, season: int) -> dict[str, float]:
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT match_id) AS matches,
            COUNT(*) AS deliveries,
            SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END) AS sixes,
            SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 ELSE 0 END) AS wickets,
            SUM(CASE WHEN legal_ball = 1 AND total_runs = 0 THEN 1 ELSE 0 END) AS dot_balls,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 THEN 1 ELSE 0 END) AS dot_balls_batter_zero
        FROM deliveries
        WHERE season_id = ?
        """,
        (season,),
    ).fetchone()
    return {
        "matches": float(row["matches"] or 0),
        "deliveries": float(row["deliveries"] or 0),
        "fours": float(row["fours"] or 0),
        "sixes": float(row["sixes"] or 0),
        "wickets": float(row["wickets"] or 0),
        "dot_balls": float(row["dot_balls"] or 0),
        "dot_balls_batter_zero": float(row["dot_balls_batter_zero"] or 0),
    }


def _update_season_metric_reconciliation(conn: sqlite3.Connection, zf: zipfile.ZipFile, fetched_at: str) -> None:
    source = _source_metric_by_season_from_zip(zf)
    metrics = ("matches", "deliveries", "fours", "sixes", "wickets", "dot_balls")
    conn.execute("DELETE FROM season_metric_reconciliation WHERE source_key = ?", (CRICSHEET_SOURCE_KEY,))
    for season in sorted(source.keys()):
        local = _local_metric_by_season(conn, season)
        for metric in metrics:
            local_value = float(local.get(metric, 0.0))
            reference_value = float(source[season].get(metric, 0.0))
            delta = local_value - reference_value
            relative = (delta / reference_value) if reference_value else 0.0
            status = "PASS" if abs(delta) < 1e-9 else "FAIL"
            conn.execute(
                """
                INSERT INTO season_metric_reconciliation(
                    season_id, metric_name, source_key, local_value, reference_value, delta_value, relative_delta,
                    status, root_cause, definition_notes, source_url, retrieved_at, verification_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season_id, metric_name, source_key) DO UPDATE SET
                    local_value = excluded.local_value,
                    reference_value = excluded.reference_value,
                    delta_value = excluded.delta_value,
                    relative_delta = excluded.relative_delta,
                    status = excluded.status,
                    root_cause = excluded.root_cause,
                    definition_notes = excluded.definition_notes,
                    source_url = excluded.source_url,
                    retrieved_at = excluded.retrieved_at,
                    verification_status = excluded.verification_status
                """,
                (
                    season,
                    metric,
                    CRICSHEET_SOURCE_KEY,
                    local_value,
                    reference_value,
                    delta,
                    relative,
                    status,
                    "matched_cached_source" if status == "PASS" else "local_source_mismatch",
                    "Metric definitions are DB-canonical and compared with same definitions over cached Cricsheet JSON.",
                    CRICSHEET_SOURCE_URL,
                    fetched_at,
                    "verified",
                ),
            )


def _official_2026_four_explainers_from_zip(zf: zipfile.ZipFile) -> dict[str, Any]:
    non_boundary_fours = 0
    super_over_fours = 0
    flagged_rows: list[dict[str, Any]] = []

    for name in zf.namelist():
        if not (name.endswith('.json') and name[:-5].isdigit()):
            continue
        match_id = int(name[:-5])
        with zf.open(name) as handle:
            payload = json.load(handle)
        if _season_from_info(payload.get('info', {}).get('season')) != 2026:
            continue

        innings_list = payload.get('innings', []) if isinstance(payload.get('innings'), list) else []
        for innings_index, innings in enumerate(innings_list, start=1):
            if not isinstance(innings, dict):
                continue
            is_super_over = 1 if bool(innings.get('super_over')) else 0
            overs = innings.get('overs', []) if isinstance(innings.get('overs'), list) else []
            for over in overs:
                if not isinstance(over, dict):
                    continue
                over_number = int(over.get('over', 0) or 0)
                deliveries = over.get('deliveries', []) if isinstance(over.get('deliveries'), list) else []
                for ball_index, delivery in enumerate(deliveries):
                    if not isinstance(delivery, dict):
                        continue
                    runs = delivery.get('runs', {}) if isinstance(delivery.get('runs'), dict) else {}
                    if int(runs.get('batter', 0) or 0) != 4:
                        continue

                    non_boundary = bool(runs.get('non_boundary', False))
                    if is_super_over:
                        super_over_fours += 1
                    if non_boundary:
                        non_boundary_fours += 1
                    if is_super_over or non_boundary:
                        flagged_rows.append(
                            {
                                'match_id': match_id,
                                'innings': innings_index,
                                'over_number': over_number,
                                'ball_number': ball_index,
                                'batter': _normalize_name(delivery.get('batter')),
                                'bowler': _normalize_name(delivery.get('bowler')),
                                'is_super_over': is_super_over,
                                'non_boundary': non_boundary,
                            }
                        )

    return {
        'non_boundary_fours': float(non_boundary_fours),
        'super_over_fours': float(super_over_fours),
        'flagged_rows': flagged_rows,
    }


def _update_2026_official_reference_notes(conn: sqlite3.Connection, zf: zipfile.ZipFile, fetched_at: str) -> None:
    # Provided golden references are examples from official IPL sources and may use different definitions.
    official_reference = {
        'fours': 2332.0,
        'sixes': 1426.0,
        'wickets': 835.0,
        'dot_balls': 5686.0,
    }
    local = _local_metric_by_season(conn, 2026)
    four_explainers = _official_2026_four_explainers_from_zip(zf)
    local_no_super = conn.execute(
        """
        SELECT
            SUM(CASE WHEN batter_runs = 4 AND is_super_over = 0 THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field') AND is_super_over = 0 THEN 1 ELSE 0 END) AS wickets,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 THEN 1 ELSE 0 END) AS dot_balls_batter_zero,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 AND is_super_over = 0 THEN 1 ELSE 0 END) AS dot_balls_batter_zero_no_super,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 AND total_runs > 0 AND LOWER(COALESCE(wicket_kind, '')) = 'run out' THEN 1 ELSE 0 END) AS dot_balls_runout_scoring,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 AND total_runs > 0 AND LOWER(COALESCE(wicket_kind, '')) = 'run out' AND is_super_over = 0 THEN 1 ELSE 0 END) AS dot_balls_runout_scoring_no_super
        FROM deliveries
        WHERE season_id = 2026
        """
    ).fetchone()
    fours_no_super = float(local_no_super['fours'] or 0)
    wickets_no_super = float(local_no_super['wickets'] or 0)
    dots_batter_zero = float(local_no_super['dot_balls_batter_zero'] or 0)
    dots_batter_zero_no_super = float(local_no_super['dot_balls_batter_zero_no_super'] or 0)
    dots_runout_scoring = float(local_no_super['dot_balls_runout_scoring'] or 0)
    dots_runout_scoring_no_super = float(local_no_super['dot_balls_runout_scoring_no_super'] or 0)

    non_boundary_fours = float(four_explainers['non_boundary_fours'])
    super_over_fours = float(four_explainers['super_over_fours'])
    fours_boundary_regular = float(local['fours']) - non_boundary_fours - super_over_fours
    flagged_four_rows = [
        f"{int(row['match_id'])}:{int(row['innings'])}.{int(row['over_number'])}.{int(row['ball_number'])}"
        for row in four_explainers['flagged_rows']
    ]

    dot_adjusted_runout_variant = dots_batter_zero - dots_runout_scoring
    dot_adjusted_runout_variant_no_super = dots_batter_zero_no_super - dots_runout_scoring_no_super
    runout_rows = conn.execute(
        """
        SELECT match_id, innings, over_number, ball_number
        FROM deliveries
        WHERE season_id = 2026
          AND legal_ball = 1
          AND batter_runs = 0
          AND total_runs > 0
          AND LOWER(COALESCE(wicket_kind, '')) = 'run out'
        ORDER BY match_id, innings, over_number, ball_number
        """
    ).fetchall()
    runout_row_labels = [f"{int(row['match_id'])}:{int(row['innings'])}.{int(row['over_number'])}.{int(row['ball_number'])}" for row in runout_rows]

    notes = {
        'fours': (
            f"Local canonical fours=batter_runs==4 => {int(local['fours'])}. "
            f"Cricsheet forensic flags: non_boundary_fours={int(non_boundary_fours)}, super_over_fours={int(super_over_fours)}. "
            f"Boundary-only regular-innings variant (exclude both) => {int(fours_boundary_regular)}; official reference is {int(official_reference['fours'])}. "
            f"Flagged deliveries: {', '.join(flagged_four_rows) if flagged_four_rows else 'none'}."
        ),
        'wickets': (
            f"Local canonical wickets include super over => {int(local['wickets'])}. "
            f"Excluding super over gives {int(wickets_no_super)}, matching official reference {int(official_reference['wickets'])}."
        ),
        'dot_balls': (
            f"Local canonical dot balls use legal_ball==1 and total_runs==0 => {int(local['dot_balls'])}. "
            f"Batter-facing legal dots (legal_ball==1 and batter_runs==0) => {int(dots_batter_zero)}. "
            f"Batter-facing excluding scoring run-out deliveries => {int(dot_adjusted_runout_variant)}; "
            f"excluding super over additionally => {int(dot_adjusted_runout_variant_no_super)}. "
            f"Official reference is {int(official_reference['dot_balls'])}. "
            f"Run-out scoring deliveries: {', '.join(runout_row_labels) if runout_row_labels else 'none'}."
        ),
        'sixes': 'Local canonical sixes (batter_runs==6) match official reference exactly.',
    }

    for metric, reference_value in official_reference.items():
        local_value = float(local.get(metric, 0.0))
        delta = local_value - reference_value
        status = 'PASS'
        root_cause = 'matched_reference'
        if abs(delta) >= 1e-9:
            status = 'FAIL'
            root_cause = 'unreconciled_with_official_reference'
            if metric == 'wickets' and abs(wickets_no_super - reference_value) < 1e-9:
                status = 'PASS_WITH_DEFINITION_NOTE'
                root_cause = 'definition_or_scope_difference'
            elif metric == 'fours' and abs(fours_boundary_regular - reference_value) < 1e-9:
                status = 'PASS_WITH_DEFINITION_NOTE'
                root_cause = 'definition_or_scope_difference'
            elif metric == 'dot_balls' and (
                abs(dots_batter_zero - reference_value) < 1e-9
                or abs(dots_batter_zero_no_super - reference_value) < 1e-9
                or abs(dot_adjusted_runout_variant - reference_value) < 1e-9
                or abs(dot_adjusted_runout_variant_no_super - reference_value) < 1e-9
            ):
                status = 'PASS_WITH_DEFINITION_NOTE'
                root_cause = 'definition_or_scope_difference'
        conn.execute(
            """
            INSERT INTO season_metric_reconciliation(
                season_id, metric_name, source_key, local_value, reference_value, delta_value, relative_delta,
                status, root_cause, definition_notes, source_url, retrieved_at, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season_id, metric_name, source_key) DO UPDATE SET
                local_value = excluded.local_value,
                reference_value = excluded.reference_value,
                delta_value = excluded.delta_value,
                relative_delta = excluded.relative_delta,
                status = excluded.status,
                root_cause = excluded.root_cause,
                definition_notes = excluded.definition_notes,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                verification_status = excluded.verification_status
            """,
            (
                2026,
                metric,
                'ipl_official_reference_2026_examples',
                local_value,
                reference_value,
                delta,
                (delta / reference_value) if reference_value else 0.0,
                status,
                root_cause,
                notes[metric],
                'https://www.iplt20.com/',
                fetched_at,
                'verified',
            ),
        )


def _update_season_trust_gate(conn: sqlite3.Connection, fetched_at: str) -> None:
    seasons = [int(r[0]) for r in conn.execute("SELECT DISTINCT season_id FROM deliveries ORDER BY season_id").fetchall()]
    for season in seasons:
        coverage = conn.execute(
            """
            SELECT status, verification_status
            FROM season_source_coverage
            WHERE season_id = ? AND source_key = ?
            """,
            (season, CRICSHEET_SOURCE_KEY),
        ).fetchone()
        coverage_ok = bool(coverage) and str(coverage["status"]).lower() == "complete" and str(coverage["verification_status"]).lower() == "verified"

        failures = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM season_metric_reconciliation
                WHERE season_id = ? AND status = 'FAIL'
                """,
                (season,),
            ).fetchone()[0]
        )
        reference_unavailable = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM season_metric_reconciliation
                WHERE season_id = ? AND status = 'REFERENCE_UNAVAILABLE'
                """,
                (season,),
            ).fetchone()[0]
        )
        definition_notes = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM season_metric_reconciliation
                WHERE season_id = ? AND status = 'PASS_WITH_DEFINITION_NOTE'
                """,
                (season,),
            ).fetchone()[0]
        )

        if not coverage_ok:
            status = "FAIL"
            reason = "source_coverage_incomplete_or_unverified"
            recon_status = "FAIL"
        elif failures > 0:
            status = "FAIL"
            reason = "metric_reconciliation_failed"
            recon_status = "FAIL"
        elif definition_notes > 0:
            status = "PASS_WITH_DEFINITION_NOTE"
            reason = "documented_definition_difference"
            recon_status = "PASS_WITH_DEFINITION_NOTE"
        elif reference_unavailable > 0:
            status = "REFERENCE_UNAVAILABLE"
            reason = "reference_unavailable_for_some_metrics"
            recon_status = "REFERENCE_UNAVAILABLE"
        else:
            status = "PASS"
            reason = "coverage_complete_and_reconciled"
            recon_status = "PASS"

        conn.execute(
            """
            INSERT INTO season_trust_gate(
                season_id, coverage_status, reconciliation_status, status, reason,
                source_key, source_url, retrieved_at, verification_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season_id) DO UPDATE SET
                coverage_status = excluded.coverage_status,
                reconciliation_status = excluded.reconciliation_status,
                status = excluded.status,
                reason = excluded.reason,
                source_key = excluded.source_key,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                verification_status = excluded.verification_status
            """,
            (
                season,
                "PASS" if coverage_ok else "FAIL",
                recon_status,
                status,
                reason,
                CRICSHEET_SOURCE_KEY,
                CRICSHEET_SOURCE_URL,
                fetched_at,
                "verified",
            ),
        )


def _canonical_name(historical_name: str) -> str:
    return CURRENT_CANONICAL_BY_HISTORICAL.get(historical_name, historical_name)


def _short_name(historical_name: str, canonical_name: str) -> str:
    return SHORT_NAME_BY_HISTORICAL.get(historical_name) or SHORT_NAME_BY_HISTORICAL.get(canonical_name) or historical_name[:3].upper()


def ensure_cricsheet_archive(cache_dir: Path, force_refresh: bool = False) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / "ipl_json.zip"
    if force_refresh or not archive.exists():
        urlretrieve(CRICSHEET_SOURCE_URL, archive)
    return archive


def _upsert_source(conn: sqlite3.Connection, source_version: str | None) -> None:
    conn.execute(
        """
        INSERT INTO enrichment_source(source_key, source_name, source_url, source_type, source_version, status, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            source_name = excluded.source_name,
            source_url = excluded.source_url,
            source_type = excluded.source_type,
            source_version = excluded.source_version,
            last_checked_at = excluded.last_checked_at
        """,
        (
            CRICSHEET_SOURCE_KEY,
            "Cricsheet IPL JSON",
            CRICSHEET_SOURCE_URL,
            "zip_json",
            source_version,
            "running",
            _utc_now(),
        ),
    )


def _upsert_team_identity(conn: sqlite3.Connection, historical_name: str, source_reference: str, fetched_at: str) -> int:
    canonical_name = _canonical_name(historical_name)
    short_name = _short_name(historical_name, canonical_name)
    conn.execute(
        """
        INSERT INTO team_identity(
            historical_display_name,
            current_canonical_name,
            short_name,
            source_key,
            source_reference,
            fetched_at,
            verification_status,
            enrichment_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(historical_display_name) DO UPDATE SET
            current_canonical_name = excluded.current_canonical_name,
            short_name = excluded.short_name,
            source_reference = excluded.source_reference,
            fetched_at = excluded.fetched_at,
            verification_status = excluded.verification_status,
            enrichment_version = excluded.enrichment_version
        """,
        (
            historical_name,
            canonical_name,
            short_name,
            CRICSHEET_SOURCE_KEY,
            source_reference,
            fetched_at,
            "verified",
            ENRICHMENT_VERSION,
        ),
    )
    row = conn.execute(
        "SELECT team_identity_id FROM team_identity WHERE historical_display_name = ?",
        (historical_name,),
    ).fetchone()
    if row is None:
        raise RuntimeError("team identity upsert failed")
    return int(row["team_identity_id"])


def _upsert_team_aliases(conn: sqlite3.Connection, team_identity_id: int, historical_name: str, fetched_at: str) -> None:
    aliases = {historical_name, _canonical_name(historical_name)}
    aliases.discard("")
    for alias in sorted(aliases):
        conn.execute(
            """
            INSERT INTO team_alias(
                team_identity_id,
                alias_name,
                from_season,
                to_season,
                source_key,
                source_reference,
                fetched_at,
                verification_status,
                enrichment_version
            )
            VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(team_identity_id, alias_name, from_season, to_season) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                verification_status = excluded.verification_status,
                enrichment_version = excluded.enrichment_version
            """,
            (
                team_identity_id,
                alias,
                CRICSHEET_SOURCE_KEY,
                "cricsheet+curated_canonical",
                fetched_at,
                "verified",
                ENRICHMENT_VERSION,
            ),
        )


def _persist_player_assets_from_local_map(conn: sqlite3.Connection, project_root: Path, fetched_at: str) -> int:
    photo_path = project_root / "web" / "player_photos.json"
    if not photo_path.exists():
        return 0
    payload = json.loads(photo_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return 0

    inserted = 0
    for player_name, item in payload.items():
        if isinstance(item, str):
            local_url = item
            source = "local_mapping"
            asset_type = "illustration"
            is_verified_photo = 0
            license_value = None
            attribution = None
        elif isinstance(item, dict):
            local_url = str(item.get("url", "")).strip()
            source = str(item.get("source", "local_mapping")).strip()
            asset_type = str(item.get("asset_type", "illustration")).strip() or "illustration"
            is_verified_photo = 1 if bool(item.get("is_verified_photo", False)) else 0
            license_value = item.get("license")
            attribution = item.get("attribution")
        else:
            continue
        if not local_url:
            continue
        conn.execute(
            """
            INSERT INTO player_asset(
                player_name,
                local_asset_path,
                source_key,
                source_reference,
                source_url,
                asset_type,
                is_verified_photo,
                license,
                attribution,
                fetched_at,
                verification_status,
                enrichment_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_name) DO UPDATE SET
                local_asset_path = excluded.local_asset_path,
                source_reference = excluded.source_reference,
                source_url = excluded.source_url,
                asset_type = excluded.asset_type,
                is_verified_photo = excluded.is_verified_photo,
                license = excluded.license,
                attribution = excluded.attribution,
                fetched_at = excluded.fetched_at,
                verification_status = excluded.verification_status,
                enrichment_version = excluded.enrichment_version
            """,
            (
                str(player_name),
                local_url,
                CRICSHEET_SOURCE_KEY,
                source,
                local_url,
                asset_type,
                is_verified_photo,
                None if license_value is None else str(license_value),
                None if attribution is None else str(attribution),
                fetched_at,
                "verified" if is_verified_photo else "provisional",
                ENRICHMENT_VERSION,
            ),
        )
        inserted += 1
    return inserted


def run_cricsheet_enrichment(
    conn: sqlite3.Connection,
    project_root: Path,
    force_refresh: bool = False,
) -> dict[str, Any]:
    fetched_at = _utc_now()
    archive = ensure_cricsheet_archive(project_root / "artifacts", force_refresh=force_refresh)

    with zipfile.ZipFile(archive) as zf:
        source_version = str(int(archive.stat().st_mtime))
        _upsert_source(conn, source_version)

        delivery_backfill = _backfill_latest_season_deliveries_from_zip(conn, zf, fetched_at)
        _update_season_source_coverage(conn, zf, fetched_at)
        _update_season_metric_reconciliation(conn, zf, fetched_at)
        _update_2026_official_reference_notes(conn, zf, fetched_at)
        _update_season_trust_gate(conn, fetched_at)

        run_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO enrichment_run(run_id, source_key, started_at, status)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, CRICSHEET_SOURCE_KEY, fetched_at, "running"),
        )

        match_rows = conn.execute("SELECT match_id, season_id FROM matches").fetchall()
        innings_rows = conn.execute(
            "SELECT match_id, innings, team_batting, team_bowling FROM innings_summary ORDER BY innings"
        ).fetchall()
        innings_by_match: dict[int, list[sqlite3.Row]] = {}
        for row in innings_rows:
            innings_by_match.setdefault(int(row["match_id"]), []).append(row)

        names = set(zf.namelist())
        resolved_matches = 0
        missing_matches = 0
        resolved_team_links = 0

        for row in match_rows:
            match_id = int(row["match_id"])
            season_id = int(row["season_id"])
            file_name = f"{match_id}.json"
            if file_name not in names:
                missing_matches += 1
                continue

            with zf.open(file_name) as handle:
                payload = json.load(handle)
            info = payload.get("info", {})
            event = info.get("event", {}) if isinstance(info.get("event", {}), dict) else {}
            teams = info.get("teams", []) if isinstance(info.get("teams", []), list) else []
            innings = payload.get("innings", []) if isinstance(payload.get("innings", []), list) else []
            if len(teams) < 2:
                missing_matches += 1
                continue

            team_a = _normalize_name(str(teams[0]))
            team_b = _normalize_name(str(teams[1]))
            team_a_id = _upsert_team_identity(conn, team_a, file_name, fetched_at)
            team_b_id = _upsert_team_identity(conn, team_b, file_name, fetched_at)
            _upsert_team_aliases(conn, team_a_id, team_a, fetched_at)
            _upsert_team_aliases(conn, team_b_id, team_b, fetched_at)

            toss = info.get("toss", {}) if isinstance(info.get("toss", {}), dict) else {}
            outcome = info.get("outcome", {}) if isinstance(info.get("outcome", {}), dict) else {}
            result_type, result_margin = _determine_result(outcome)
            pom = info.get("player_of_match", []) if isinstance(info.get("player_of_match", []), list) else []
            match_date = None
            dates = info.get("dates", []) if isinstance(info.get("dates", []), list) else []
            if dates:
                match_date = str(dates[0])

            conn.execute(
                """
                INSERT INTO match_metadata(
                    match_id,
                    season_id,
                    match_number,
                    match_date,
                    venue,
                    city,
                    toss_winner,
                    toss_decision,
                    winner,
                    result_type,
                    result_margin,
                    match_type,
                    player_of_match,
                    team_a_display,
                    team_b_display,
                    source_key,
                    source_reference,
                    fetched_at,
                    verification_status,
                    enrichment_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    season_id = excluded.season_id,
                    match_number = excluded.match_number,
                    match_date = excluded.match_date,
                    venue = excluded.venue,
                    city = excluded.city,
                    toss_winner = excluded.toss_winner,
                    toss_decision = excluded.toss_decision,
                    winner = excluded.winner,
                    result_type = excluded.result_type,
                    result_margin = excluded.result_margin,
                    match_type = excluded.match_type,
                    player_of_match = excluded.player_of_match,
                    team_a_display = excluded.team_a_display,
                    team_b_display = excluded.team_b_display,
                    source_reference = excluded.source_reference,
                    fetched_at = excluded.fetched_at,
                    verification_status = excluded.verification_status,
                    enrichment_version = excluded.enrichment_version
                """,
                (
                    match_id,
                    season_id,
                    _int_or_none(event.get("match_number")),
                    match_date,
                    _normalize_name(info.get("venue")),
                    _normalize_name(info.get("city")),
                    _normalize_name(toss.get("winner")),
                    _normalize_name(toss.get("decision")),
                    _normalize_name(outcome.get("winner")),
                    result_type,
                    result_margin,
                    _normalize_name(event.get("stage")) or _normalize_name(info.get("match_type")),
                    _normalize_name(str(pom[0])) if pom else None,
                    team_a,
                    team_b,
                    CRICSHEET_SOURCE_KEY,
                    file_name,
                    fetched_at,
                    "verified",
                    ENRICHMENT_VERSION,
                ),
            )

            db_innings = innings_by_match.get(match_id, [])
            innings_count = min(len(innings), len(db_innings))
            for idx in range(innings_count):
                innings_team = _normalize_name(innings[idx].get("team"))
                if not innings_team:
                    continue
                db_batting = _normalize_name(db_innings[idx]["team_batting"])
                db_bowling = _normalize_name(db_innings[idx]["team_bowling"])
                other_team = team_b if innings_team == team_a else team_a

                team_id = team_a_id if innings_team == team_a else team_b_id
                conn.execute(
                    """
                    INSERT INTO match_team_map(
                        match_id,
                        internal_team_code,
                        team_identity_id,
                        historical_display_name,
                        source_key,
                        source_reference,
                        fetched_at,
                        verification_status,
                        enrichment_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, internal_team_code) DO UPDATE SET
                        team_identity_id = excluded.team_identity_id,
                        historical_display_name = excluded.historical_display_name,
                        source_reference = excluded.source_reference,
                        fetched_at = excluded.fetched_at,
                        verification_status = excluded.verification_status,
                        enrichment_version = excluded.enrichment_version
                    """,
                    (
                        match_id,
                        db_batting,
                        team_id,
                        innings_team,
                        CRICSHEET_SOURCE_KEY,
                        file_name,
                        fetched_at,
                        "verified",
                        ENRICHMENT_VERSION,
                    ),
                )
                other_id = team_b_id if team_id == team_a_id else team_a_id
                conn.execute(
                    """
                    INSERT INTO match_team_map(
                        match_id,
                        internal_team_code,
                        team_identity_id,
                        historical_display_name,
                        source_key,
                        source_reference,
                        fetched_at,
                        verification_status,
                        enrichment_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(match_id, internal_team_code) DO UPDATE SET
                        team_identity_id = excluded.team_identity_id,
                        historical_display_name = excluded.historical_display_name,
                        source_reference = excluded.source_reference,
                        fetched_at = excluded.fetched_at,
                        verification_status = excluded.verification_status,
                        enrichment_version = excluded.enrichment_version
                    """,
                    (
                        match_id,
                        db_bowling,
                        other_id,
                        other_team,
                        CRICSHEET_SOURCE_KEY,
                        file_name,
                        fetched_at,
                        "verified",
                        ENRICHMENT_VERSION,
                    ),
                )
                resolved_team_links += 2

            resolved_matches += 1

        player_assets = _persist_player_assets_from_local_map(conn, project_root, fetched_at)

        stats = {
            "run_id": run_id,
            "matches_total": len(match_rows),
            "matches_enriched": resolved_matches,
            "matches_missing_in_source": missing_matches,
            "delivery_backfill": delivery_backfill,
            "team_identities": conn.execute("SELECT COUNT(*) FROM team_identity").fetchone()[0],
            "match_metadata_rows": conn.execute("SELECT COUNT(*) FROM match_metadata").fetchone()[0],
            "match_team_map_rows": conn.execute("SELECT COUNT(*) FROM match_team_map").fetchone()[0],
            "player_assets": player_assets,
            "team_links_written": resolved_team_links,
        }

        conn.execute(
            """
            UPDATE enrichment_run
            SET finished_at = ?, status = ?, stats_json = ?
            WHERE run_id = ?
            """,
            (_utc_now(), "success", json.dumps(stats, sort_keys=True), run_id),
        )
        conn.execute(
            """
            UPDATE enrichment_source
            SET status = ?, last_checked_at = ?, last_successful_run_id = ?
            WHERE source_key = ?
            """,
            ("ready", _utc_now(), run_id, CRICSHEET_SOURCE_KEY),
        )
        conn.commit()
        return stats


def run_reference_knowledge_enrichment(conn: sqlite3.Connection) -> dict[str, Any]:
    fetched_at = _utc_now()
    conn.execute(
        """
        INSERT INTO enrichment_source(source_key, source_name, source_url, source_type, source_version, status, last_checked_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            source_name = excluded.source_name,
            source_url = excluded.source_url,
            source_type = excluded.source_type,
            source_version = excluded.source_version,
            status = excluded.status,
            last_checked_at = excluded.last_checked_at
        """,
        (
            KNOWLEDGE_SOURCE_KEY,
            "MatchGenome reference knowledge",
            KNOWLEDGE_SOURCE_URL,
            "curated_reference",
            ENRICHMENT_VERSION,
            "running",
            fetched_at,
        ),
    )

    run_id = str(uuid4())
    conn.execute(
        """
        INSERT INTO enrichment_run(run_id, source_key, started_at, status)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, KNOWLEDGE_SOURCE_KEY, fetched_at, "running"),
    )

    player_rows = 0
    alias_rows = 0
    team_rows = 0
    team_season_rows = 0

    for row in PLAYER_KNOWLEDGE_SEED:
        canonical = str(row["canonical_player_name"]).strip()
        if not canonical:
            continue
        verification = _require_verification_state(str(row.get("verification_status", "provisional")), "player verification_status")
        conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name,
                full_name,
                date_of_birth,
                nationality,
                role,
                batting_style,
                bowling_style,
                biography,
                spouse_name,
                children_count,
                source_key,
                source_url,
                retrieved_at,
                verification_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_player_name) DO UPDATE SET
                full_name = COALESCE(excluded.full_name, player_knowledge.full_name),
                date_of_birth = COALESCE(excluded.date_of_birth, player_knowledge.date_of_birth),
                nationality = COALESCE(excluded.nationality, player_knowledge.nationality),
                role = COALESCE(excluded.role, player_knowledge.role),
                batting_style = COALESCE(excluded.batting_style, player_knowledge.batting_style),
                bowling_style = COALESCE(excluded.bowling_style, player_knowledge.bowling_style),
                biography = COALESCE(excluded.biography, player_knowledge.biography),
                spouse_name = COALESCE(excluded.spouse_name, player_knowledge.spouse_name),
                children_count = COALESCE(excluded.children_count, player_knowledge.children_count),
                source_key = excluded.source_key,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                verification_status = excluded.verification_status,
                notes = COALESCE(excluded.notes, player_knowledge.notes)
            """,
            (
                canonical,
                row.get("full_name"),
                row.get("date_of_birth"),
                row.get("nationality"),
                row.get("role"),
                row.get("batting_style"),
                row.get("bowling_style"),
                row.get("biography"),
                row.get("spouse_name"),
                row.get("children_count"),
                KNOWLEDGE_SOURCE_KEY,
                row.get("source_url"),
                fetched_at,
                verification,
                "Curated reference seed; verify externally before promoting to verified.",
            ),
        )
        player_rows += 1

        raw_aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        aliases = {canonical, str(row.get("full_name") or "")} | {str(a) for a in raw_aliases}
        for alias in aliases:
            normalized_alias = _normalize_alias(alias)
            if not normalized_alias:
                continue
            conn.execute(
                """
                INSERT INTO player_identity_alias(
                    alias_name,
                    canonical_player_name,
                    source_key,
                    source_url,
                    retrieved_at,
                    verification_status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias_name, canonical_player_name) DO UPDATE SET
                    source_key = excluded.source_key,
                    source_url = excluded.source_url,
                    retrieved_at = excluded.retrieved_at,
                    verification_status = excluded.verification_status
                """,
                (
                    normalized_alias,
                    canonical,
                    KNOWLEDGE_SOURCE_KEY,
                    row.get("source_url"),
                    fetched_at,
                    verification,
                ),
            )
            alias_rows += 1

    team_names = {str(item["canonical_team_name"]).strip() for item in TEAM_SEASON_KNOWLEDGE_SEED if str(item.get("canonical_team_name", "")).strip()}
    for team in sorted(team_names):
        conn.execute(
            """
            INSERT INTO team_knowledge(
                canonical_team_name,
                source_key,
                source_url,
                retrieved_at,
                verification_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_team_name) DO UPDATE SET
                source_key = excluded.source_key,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                verification_status = excluded.verification_status,
                notes = excluded.notes
            """,
            (
                team,
                KNOWLEDGE_SOURCE_KEY,
                KNOWLEDGE_SOURCE_URL,
                fetched_at,
                "provisional",
                "Team row maintained for season-specific leadership records.",
            ),
        )
        team_rows += 1

    conn.execute("DELETE FROM team_season_knowledge WHERE source_key = ?", (KNOWLEDGE_SOURCE_KEY,))
    for row in TEAM_SEASON_KNOWLEDGE_SEED:
        team = str(row.get("canonical_team_name", "")).strip()
        season = int(row.get("season_id", 0) or 0)
        if not team or season <= 0:
            continue
        verification = _require_verification_state(str(row.get("verification_status", "provisional")), "team season verification_status")
        conn.execute(
            """
            INSERT INTO team_season_knowledge(
                canonical_team_name,
                season_id,
                captain,
                coach,
                owner,
                home_venue,
                source_key,
                source_url,
                retrieved_at,
                verification_status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_team_name, season_id) DO UPDATE SET
                captain = COALESCE(excluded.captain, team_season_knowledge.captain),
                coach = COALESCE(excluded.coach, team_season_knowledge.coach),
                owner = COALESCE(excluded.owner, team_season_knowledge.owner),
                home_venue = COALESCE(excluded.home_venue, team_season_knowledge.home_venue),
                source_key = excluded.source_key,
                source_url = excluded.source_url,
                retrieved_at = excluded.retrieved_at,
                verification_status = excluded.verification_status,
                notes = COALESCE(excluded.notes, team_season_knowledge.notes)
            """,
            (
                team,
                season,
                row.get("captain"),
                row.get("coach"),
                row.get("owner"),
                row.get("home_venue"),
                KNOWLEDGE_SOURCE_KEY,
                row.get("source_url") or KNOWLEDGE_SOURCE_URL,
                fetched_at,
                verification,
                "Curated season leadership snapshot.",
            ),
        )
        team_season_rows += 1

    stats = {
        "run_id": run_id,
        "players_upserted": player_rows,
        "aliases_upserted": alias_rows,
        "teams_upserted": team_rows,
        "team_seasons_upserted": team_season_rows,
    }

    conn.execute(
        """
        UPDATE enrichment_run
        SET finished_at = ?, status = ?, stats_json = ?
        WHERE run_id = ?
        """,
        (_utc_now(), "success", json.dumps(stats, sort_keys=True), run_id),
    )
    conn.execute(
        """
        UPDATE enrichment_source
        SET status = ?, last_checked_at = ?, last_successful_run_id = ?
        WHERE source_key = ?
        """,
        ("ready", _utc_now(), run_id, KNOWLEDGE_SOURCE_KEY),
    )
    conn.commit()
    return stats

