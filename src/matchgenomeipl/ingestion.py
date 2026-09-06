from __future__ import annotations

import csv
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from .constants import REQUIRED_COLUMNS
from .database import initialize_schema, reset_ingested_data, upsert_ingestion_state
from .validation import build_timeline_key, validate_and_normalize_row, validate_columns


@dataclass
class IngestionStats:
    run_id: str | None
    source_file: str
    started_at: str
    finished_at: str
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    duplicate_delivery_identities: int
    schema_errors: list[str]
    skipped: bool
    source_changed: bool
    status: str
    source_size_bytes: int
    source_mtime_ns: int
    schema_fingerprint: str | None = None
    content_sha256: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_source_path(csv_path: Path | str) -> str:
    return str(Path(csv_path).resolve())


def _quick_source_state(csv_path: Path | str) -> dict[str, Any]:
    source = Path(csv_path)
    stat = source.stat()
    return {
        "source_path": _normalized_source_path(source),
        "source_size_bytes": int(stat.st_size),
        "source_mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
    }


def _file_sha256(csv_path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(csv_path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _schema_fingerprint(columns: list[str]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()


def _existing_source_record(conn: sqlite3.Connection, source_path: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM data_sources WHERE source_path = ?", (source_path,)).fetchone()


def _is_source_unchanged(existing: sqlite3.Row | None, quick_state: dict[str, Any]) -> bool:
    if existing is None:
        return False
    return (
        int(existing["source_size_bytes"]) == int(quick_state["source_size_bytes"])
        and int(existing["source_mtime_ns"]) == int(quick_state["source_mtime_ns"])
        and str(existing["status"]) == "ready"
    )


def _materialize_runtime_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM seasons")
    conn.execute("DELETE FROM teams")
    conn.execute("DELETE FROM players")
    conn.execute("DELETE FROM matches")
    conn.execute("DELETE FROM innings_summary")
    conn.execute("DELETE FROM batter_stats_agg")
    conn.execute("DELETE FROM bowler_stats_agg")
    conn.execute("DELETE FROM batter_bowler_stats_agg")
    conn.execute("DELETE FROM batter_bowler_type_stats_agg")
    conn.execute("DELETE FROM bowler_batter_type_stats_agg")
    conn.execute("DELETE FROM phase_outcome_stats_agg")
    conn.execute("DELETE FROM outcome_stats_agg")

    conn.execute("INSERT INTO seasons(season_id) SELECT DISTINCT season_id FROM deliveries ORDER BY season_id")
    conn.execute(
        """
        INSERT INTO teams(team_name)
        SELECT team_name
        FROM (
            SELECT DISTINCT team_batting AS team_name FROM deliveries
            UNION
            SELECT DISTINCT team_bowling AS team_name FROM deliveries
        )
        ORDER BY team_name
        """
    )
    conn.execute(
        """
        INSERT INTO players(player_name)
        SELECT player_name
        FROM (
            SELECT DISTINCT batter AS player_name FROM deliveries
            UNION SELECT DISTINCT bowler AS player_name FROM deliveries
            UNION SELECT DISTINCT non_striker AS player_name FROM deliveries WHERE non_striker IS NOT NULL
            UNION SELECT DISTINCT player_out AS player_name FROM deliveries WHERE player_out IS NOT NULL
            UNION SELECT DISTINCT fielders_involved AS player_name FROM deliveries WHERE fielders_involved IS NOT NULL
        )
        ORDER BY player_name
        """
    )
    conn.execute(
        """
        INSERT INTO matches(match_id, season_id, is_super_over_match)
        SELECT match_id, MIN(season_id), MAX(is_super_over)
        FROM deliveries
        GROUP BY match_id
        """
    )
    conn.execute(
        """
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
        GROUP BY season_id, match_id, innings
        """
    )

    conn.execute(
        """
        INSERT INTO batter_stats_agg(batter, runs, balls_faced, fours, sixes, dots)
        SELECT
            batter,
            SUM(batter_runs),
            SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END),
            SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END),
            SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END)
        FROM deliveries
        GROUP BY batter
        """
    )
    conn.execute(
        """
        INSERT INTO bowler_stats_agg(bowler, runs_conceded, legal_balls, wickets, dots)
        SELECT
            bowler,
            SUM(total_runs - bye_runs - leg_bye_runs),
            SUM(legal_ball),
            SUM(CASE WHEN is_wicket = 1
                         AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field')
                     THEN 1 ELSE 0 END),
            SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END)
        FROM deliveries
        GROUP BY bowler
        """
    )
    conn.execute(
        """
        INSERT INTO batter_bowler_stats_agg(batter, bowler, deliveries, runs, wickets)
        SELECT batter, bowler, COUNT(*), SUM(batter_runs), SUM(is_wicket)
        FROM deliveries
        GROUP BY batter, bowler
        """
    )
    conn.execute(
        """
        INSERT INTO batter_bowler_type_stats_agg(batter, bowler_type, deliveries, runs, wickets)
        SELECT batter, bowler_type, COUNT(*), SUM(batter_runs), SUM(is_wicket)
        FROM deliveries
        GROUP BY batter, bowler_type
        """
    )
    conn.execute(
        """
        INSERT INTO bowler_batter_type_stats_agg(bowler, batsman_type, deliveries, runs, wickets)
        SELECT bowler, batsman_type, COUNT(*), SUM(batter_runs), SUM(is_wicket)
        FROM deliveries
        GROUP BY bowler, batsman_type
        """
    )

    conn.execute(
        """
        INSERT INTO phase_outcome_stats_agg(phase, outcome_label, deliveries)
        SELECT
            CASE
                WHEN legal_balls_before < 36 THEN 'powerplay'
                WHEN legal_balls_before < 90 THEN 'middle'
                ELSE 'death'
            END AS phase,
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
        FROM (
            SELECT
                d.*, COALESCE(
                    SUM(legal_ball) OVER (
                        PARTITION BY season_id, match_id, innings
                        ORDER BY over_number, ball_number, source_row_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS legal_balls_before
            FROM deliveries d
        )
        GROUP BY phase, outcome_label
        """
    )
    conn.execute(
        """
        INSERT INTO outcome_stats_agg(outcome_label, deliveries)
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
        GROUP BY outcome_label
        """
    )


def _upsert_source_record(conn: sqlite3.Connection, source: dict[str, Any], stats: IngestionStats) -> None:
    conn.execute(
        """
        INSERT INTO data_sources(
            source_path,
            source_size_bytes,
            source_mtime_ns,
            content_sha256,
            schema_fingerprint,
            row_count,
            last_ingested_at,
            last_successful_run_id,
            status,
            data_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_path) DO UPDATE SET
            source_size_bytes = excluded.source_size_bytes,
            source_mtime_ns = excluded.source_mtime_ns,
            content_sha256 = excluded.content_sha256,
            schema_fingerprint = excluded.schema_fingerprint,
            row_count = excluded.row_count,
            last_ingested_at = excluded.last_ingested_at,
            last_successful_run_id = excluded.last_successful_run_id,
            status = excluded.status,
            data_version = excluded.data_version
        """,
        (
            source["source_path"],
            source["source_size_bytes"],
            source["source_mtime_ns"],
            stats.content_sha256,
            stats.schema_fingerprint,
            stats.total_rows,
            stats.finished_at,
            stats.run_id,
            stats.status,
            "v1",
        ),
    )


def ingest_csv_to_sqlite(conn: sqlite3.Connection, csv_path: Path | str, force_refresh: bool = False) -> IngestionStats:
    initialize_schema(conn)
    source = _quick_source_state(csv_path)
    existing = _existing_source_record(conn, source["source_path"])

    if not force_refresh and _is_source_unchanged(existing, source):
        finished_at = _utc_now()
        return IngestionStats(
            run_id=None,
            source_file=source["source_path"],
            started_at=finished_at,
            finished_at=finished_at,
            total_rows=int(existing["row_count"] or 0),
            loaded_rows=0,
            rejected_rows=0,
            duplicate_delivery_identities=0,
            schema_errors=[],
            skipped=True,
            source_changed=False,
            status="skipped_unchanged",
            source_size_bytes=source["source_size_bytes"],
            source_mtime_ns=source["source_mtime_ns"],
            schema_fingerprint=str(existing["schema_fingerprint"] or ""),
            content_sha256=str(existing["content_sha256"] or ""),
        )

    path = Path(csv_path)
    run_id = str(uuid.uuid4())
    started_at = _utc_now()

    conn.execute(
        """
        INSERT INTO ingestion_runs(run_id, source_file, started_at, status, source_size_bytes, source_mtime_ns)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, source["source_path"], started_at, "running", source["source_size_bytes"], source["source_mtime_ns"]),
    )
    upsert_ingestion_state(conn, "dataset_status", "ingesting")
    upsert_ingestion_state(conn, "active_run_id", run_id)
    conn.commit()

    total_rows = 0
    loaded_rows = 0
    rejected_rows = 0
    duplicate_delivery_identities = 0
    schema_errors: list[str] = []

    seen_identities: set[tuple[int, int, int, int, int]] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        schema_ok, schema_messages = validate_columns(columns)
        schema_errors.extend(schema_messages)
        schema_fp = _schema_fingerprint(columns)

        if not schema_ok:
            finished_at = _utc_now()
            stats = IngestionStats(
                run_id=run_id,
                source_file=source["source_path"],
                started_at=started_at,
                finished_at=finished_at,
                total_rows=0,
                loaded_rows=0,
                rejected_rows=0,
                duplicate_delivery_identities=0,
                schema_errors=schema_errors,
                skipped=False,
                source_changed=True,
                status="failed",
                source_size_bytes=source["source_size_bytes"],
                source_mtime_ns=source["source_mtime_ns"],
                schema_fingerprint=schema_fp,
            )
            conn.execute(
                "UPDATE ingestion_runs SET finished_at = ?, status = ?, stats_json = ?, error_message = ?, schema_fingerprint = ? WHERE run_id = ?",
                (finished_at, "failed", json.dumps(asdict(stats), sort_keys=True), ";".join(schema_errors), schema_fp, run_id),
            )
            upsert_ingestion_state(conn, "dataset_status", "refresh_failed")
            upsert_ingestion_state(conn, "active_run_id", "")
            upsert_ingestion_state(conn, "last_error", ";".join(schema_errors))
            conn.commit()
            raise ValueError(f"Fatal schema validation failure: {schema_errors}")

        insert_raw = (
            "INSERT INTO raw_deliveries (source_file, source_row_number, raw_record_json, ingestion_run_id) "
            "VALUES (?, ?, ?, ?)"
        )
        insert_reject = (
            "INSERT INTO rejected_deliveries (source_file, source_row_number, reason, details, ingestion_run_id) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        insert_delivery = (
            "INSERT INTO deliveries ("
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

        try:
            conn.execute("BEGIN IMMEDIATE")
            reset_ingested_data(conn, commit=False)

            for row_number, row in enumerate(reader, start=2):
                total_rows += 1
                conn.execute(insert_raw, (source["source_path"], row_number, json.dumps(row, sort_keys=True), run_id))

                validation = validate_and_normalize_row(row)
                normalized = validation.normalized

                identity = (
                    normalized.get("season_id"),
                    normalized.get("match_id"),
                    normalized.get("innings"),
                    normalized.get("over_number"),
                    normalized.get("ball_number"),
                )

                if None not in identity and identity in seen_identities:
                    validation.errors.append("duplicate_delivery_identity")
                    duplicate_delivery_identities += 1
                elif None not in identity:
                    seen_identities.add(identity)

                if validation.errors:
                    rejected_rows += 1
                    conn.execute(
                        insert_reject,
                        (
                            source["source_path"],
                            row_number,
                            validation.errors[0],
                            "|".join(validation.errors),
                            run_id,
                        ),
                    )
                    continue

                normalized["timeline_key"] = build_timeline_key(normalized)

                conn.execute(
                    insert_delivery,
                    (
                        source["source_path"],
                        row_number,
                        normalized["season_id"],
                        normalized["match_id"],
                        normalized["innings"],
                        normalized["over_number"],
                        normalized["ball_number"],
                        normalized["batter"],
                        normalized["bowler"],
                        normalized["non_striker"],
                        normalized["team_batting"],
                        normalized["team_bowling"],
                        normalized["batter_runs"],
                        normalized["extras"],
                        normalized["total_runs"],
                        normalized["batsman_type"],
                        normalized["bowler_type"],
                        normalized["player_out"],
                        normalized["fielders_involved"],
                        normalized["is_wicket"],
                        normalized["is_wide_ball"],
                        normalized["is_no_ball"],
                        normalized["is_leg_bye"],
                        normalized["is_bye"],
                        normalized["is_penalty"],
                        normalized["wide_ball_runs"],
                        normalized["no_ball_runs"],
                        normalized["leg_bye_runs"],
                        normalized["bye_runs"],
                        normalized["penalty_runs"],
                        normalized["wicket_kind"],
                        normalized["is_super_over"],
                        normalized["legal_ball"],
                        normalized["timeline_key"],
                        "",
                    ),
                )
                loaded_rows += 1

            _materialize_runtime_tables(conn)

            finished_at = _utc_now()
            stats = IngestionStats(
                run_id=run_id,
                source_file=source["source_path"],
                started_at=started_at,
                finished_at=finished_at,
                total_rows=total_rows,
                loaded_rows=loaded_rows,
                rejected_rows=rejected_rows,
                duplicate_delivery_identities=duplicate_delivery_identities,
                schema_errors=schema_errors,
                skipped=False,
                source_changed=True,
                status="ready",
                source_size_bytes=source["source_size_bytes"],
                source_mtime_ns=source["source_mtime_ns"],
                schema_fingerprint=schema_fp,
                content_sha256=_file_sha256(path),
            )

            _upsert_source_record(conn, source, stats)
            upsert_ingestion_state(conn, "dataset_status", "ready")
            upsert_ingestion_state(conn, "active_run_id", "")
            upsert_ingestion_state(conn, "last_run_id", run_id)
            upsert_ingestion_state(conn, "last_error", "")

            conn.execute(
                """
                UPDATE ingestion_runs
                SET finished_at = ?, status = ?, stats_json = ?, source_content_sha256 = ?, schema_fingerprint = ?, row_count = ?
                WHERE run_id = ?
                """,
                (
                    finished_at,
                    "success",
                    json.dumps(asdict(stats), sort_keys=True),
                    stats.content_sha256,
                    schema_fp,
                    total_rows,
                    run_id,
                ),
            )

            conn.commit()
            return stats
        except Exception as exc:
            conn.rollback()
            finished_at = _utc_now()
            conn.execute(
                "UPDATE ingestion_runs SET finished_at = ?, status = ?, error_message = ? WHERE run_id = ?",
                (finished_at, "failed", str(exc), run_id),
            )
            upsert_ingestion_state(conn, "dataset_status", "refresh_failed")
            upsert_ingestion_state(conn, "active_run_id", "")
            upsert_ingestion_state(conn, "last_error", str(exc))
            conn.commit()
            raise


def ensure_dataset_ready(conn: sqlite3.Connection, csv_path: Path | str) -> IngestionStats:
    return ingest_csv_to_sqlite(conn, csv_path, force_refresh=False)


def required_columns() -> list[str]:
    return list(REQUIRED_COLUMNS)

