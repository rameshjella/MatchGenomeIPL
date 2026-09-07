from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from urllib.request import urlretrieve
from uuid import uuid4
import zipfile

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
        "spouse_name": "Sakshi Dhoni",
        "children_count": 1,
        "source_url": "https://en.wikipedia.org/wiki/MS_Dhoni",
        "verification_status": "provisional",
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
        "verification_status": "provisional",
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
        "season_id": 2016,
        "captain": "Virat Kohli",
        "coach": "Daniel Vettori",
        "owner": "United Spirits",
        "home_venue": "M Chinnaswamy Stadium",
        "source_url": "https://www.iplt20.com/teams/royal-challengers-bengaluru",
        "verification_status": "provisional",
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
                    int(event.get("match_number")) if event.get("match_number") is not None else None,
                    match_date,
                    _normalize_name(info.get("venue")),
                    _normalize_name(info.get("city")),
                    _normalize_name(toss.get("winner")),
                    _normalize_name(toss.get("decision")),
                    _normalize_name(outcome.get("winner")),
                    result_type,
                    result_margin,
                    _normalize_name(info.get("match_type")),
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


