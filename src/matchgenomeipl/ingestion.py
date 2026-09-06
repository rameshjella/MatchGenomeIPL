from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .constants import REQUIRED_COLUMNS
from .database import initialize_schema, reset_ingested_data
from .validation import build_timeline_key, validate_and_normalize_row, validate_columns


@dataclass
class IngestionStats:
    run_id: str
    source_file: str
    started_at: str
    finished_at: str
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    duplicate_delivery_identities: int
    schema_errors: list[str]


def ingest_csv_to_sqlite(conn: sqlite3.Connection, csv_path: Path | str) -> IngestionStats:
    path = Path(csv_path)
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    initialize_schema(conn)
    reset_ingested_data(conn)

    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_file, started_at, status) VALUES (?, ?, ?, ?)",
        (run_id, str(path), started_at, "running"),
    )
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

        if not schema_ok:
            finished_at = datetime.now(timezone.utc).isoformat()
            stats = IngestionStats(
                run_id=run_id,
                source_file=str(path),
                started_at=started_at,
                finished_at=finished_at,
                total_rows=0,
                loaded_rows=0,
                rejected_rows=0,
                duplicate_delivery_identities=0,
                schema_errors=schema_errors,
            )
            conn.execute(
                "UPDATE ingestion_runs SET finished_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
                (finished_at, "failed", json.dumps(asdict(stats), sort_keys=True), run_id),
            )
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

        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            conn.execute(insert_raw, (str(path), row_number, json.dumps(row, sort_keys=True), run_id))

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
                        str(path),
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
                    str(path),
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

    finished_at = datetime.now(timezone.utc).isoformat()
    stats = IngestionStats(
        run_id=run_id,
        source_file=str(path),
        started_at=started_at,
        finished_at=finished_at,
        total_rows=total_rows,
        loaded_rows=loaded_rows,
        rejected_rows=rejected_rows,
        duplicate_delivery_identities=duplicate_delivery_identities,
        schema_errors=schema_errors,
    )

    conn.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, stats_json = ? WHERE run_id = ?",
        (finished_at, "success", json.dumps(asdict(stats), sort_keys=True), run_id),
    )
    conn.commit()
    return stats


def required_columns() -> list[str]:
    return list(REQUIRED_COLUMNS)

