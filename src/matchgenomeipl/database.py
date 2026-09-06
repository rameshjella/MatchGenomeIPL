from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {str(r[1]) for r in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def connect_db(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL UNIQUE,
            source_size_bytes INTEGER NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            content_sha256 TEXT,
            schema_fingerprint TEXT,
            row_count INTEGER,
            last_ingested_at TEXT,
            last_successful_run_id TEXT,
            status TEXT NOT NULL DEFAULT 'unknown',
            data_version TEXT
        );

        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            stats_json TEXT,
            status TEXT NOT NULL,
            source_size_bytes INTEGER,
            source_mtime_ns INTEGER,
            source_content_sha256 TEXT,
            schema_fingerprint TEXT,
            row_count INTEGER,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS ingestion_state (
            state_key TEXT PRIMARY KEY,
            state_value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS raw_deliveries (
            raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            raw_record_json TEXT NOT NULL,
            ingestion_run_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_file, source_row_number)
        );

        CREATE TABLE IF NOT EXISTS rejected_deliveries (
            reject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            reason TEXT NOT NULL,
            details TEXT NOT NULL,
            ingestion_run_id TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            season_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            innings INTEGER NOT NULL,
            over_number INTEGER NOT NULL,
            ball_number INTEGER NOT NULL,
            batter TEXT NOT NULL,
            bowler TEXT NOT NULL,
            non_striker TEXT,
            team_batting TEXT NOT NULL,
            team_bowling TEXT NOT NULL,
            batter_runs INTEGER NOT NULL,
            extras INTEGER NOT NULL,
            total_runs INTEGER NOT NULL,
            batsman_type TEXT,
            bowler_type TEXT,
            player_out TEXT,
            fielders_involved TEXT,
            is_wicket INTEGER NOT NULL,
            is_wide_ball INTEGER NOT NULL,
            is_no_ball INTEGER NOT NULL,
            is_leg_bye INTEGER NOT NULL,
            is_bye INTEGER NOT NULL,
            is_penalty INTEGER NOT NULL,
            wide_ball_runs INTEGER NOT NULL,
            no_ball_runs INTEGER NOT NULL,
            leg_bye_runs INTEGER NOT NULL,
            bye_runs INTEGER NOT NULL,
            penalty_runs INTEGER NOT NULL,
            wicket_kind TEXT,
            is_super_over INTEGER NOT NULL,
            legal_ball INTEGER NOT NULL,
            timeline_key TEXT NOT NULL,
            validation_errors TEXT NOT NULL DEFAULT '',
            UNIQUE(season_id, match_id, innings, over_number, ball_number)
        );

        CREATE TABLE IF NOT EXISTS seasons (
            season_id INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY,
            season_id INTEGER NOT NULL,
            is_super_over_match INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (season_id) REFERENCES seasons(season_id)
        );

        CREATE TABLE IF NOT EXISTS innings_summary (
            innings_id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            innings INTEGER NOT NULL,
            team_batting TEXT NOT NULL,
            team_bowling TEXT NOT NULL,
            deliveries INTEGER NOT NULL,
            legal_balls INTEGER NOT NULL,
            runs INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            UNIQUE(season_id, match_id, innings)
        );

        CREATE TABLE IF NOT EXISTS batter_stats_agg (
            batter TEXT PRIMARY KEY,
            runs INTEGER NOT NULL,
            balls_faced INTEGER NOT NULL,
            fours INTEGER NOT NULL,
            sixes INTEGER NOT NULL,
            dots INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bowler_stats_agg (
            bowler TEXT PRIMARY KEY,
            runs_conceded INTEGER NOT NULL,
            legal_balls INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            dots INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS batter_bowler_stats_agg (
            batter TEXT NOT NULL,
            bowler TEXT NOT NULL,
            deliveries INTEGER NOT NULL,
            runs INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            PRIMARY KEY (batter, bowler)
        );

        CREATE TABLE IF NOT EXISTS batter_bowler_type_stats_agg (
            batter TEXT NOT NULL,
            bowler_type TEXT,
            deliveries INTEGER NOT NULL,
            runs INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            PRIMARY KEY (batter, bowler_type)
        );

        CREATE TABLE IF NOT EXISTS bowler_batter_type_stats_agg (
            bowler TEXT NOT NULL,
            batsman_type TEXT,
            deliveries INTEGER NOT NULL,
            runs INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            PRIMARY KEY (bowler, batsman_type)
        );

        CREATE TABLE IF NOT EXISTS phase_outcome_stats_agg (
            phase TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            deliveries INTEGER NOT NULL,
            PRIMARY KEY (phase, outcome_label)
        );

        CREATE TABLE IF NOT EXISTS outcome_stats_agg (
            outcome_label TEXT PRIMARY KEY,
            deliveries INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_registry (
            model_version TEXT PRIMARY KEY,
            model_family TEXT NOT NULL,
            config_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS prediction_runs (
            prediction_run_id TEXT PRIMARY KEY,
            model_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            context_json TEXT,
            FOREIGN KEY (model_version) REFERENCES model_registry(model_version)
        );

        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_run_id TEXT NOT NULL,
            season_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            innings INTEGER NOT NULL,
            over_number INTEGER NOT NULL,
            ball_number INTEGER NOT NULL,
            probabilities_json TEXT NOT NULL,
            top_outcome TEXT NOT NULL,
            actual_outcome TEXT,
            is_correct INTEGER,
            FOREIGN KEY (prediction_run_id) REFERENCES prediction_runs(prediction_run_id)
        );

        CREATE TABLE IF NOT EXISTS evaluation_runs (
            evaluation_run_id TEXT PRIMARY KEY,
            evaluation_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            cutoff_json TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            metrics_json TEXT
        );

        CREATE TABLE IF NOT EXISTS evaluation_predictions (
            evaluation_prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_run_id TEXT NOT NULL,
            season_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            innings INTEGER NOT NULL,
            over_number INTEGER NOT NULL,
            ball_number INTEGER NOT NULL,
            predicted_top TEXT NOT NULL,
            actual_outcome TEXT NOT NULL,
            probabilities_json TEXT NOT NULL,
            FOREIGN KEY (evaluation_run_id) REFERENCES evaluation_runs(evaluation_run_id)
        );

        CREATE TABLE IF NOT EXISTS evaluation_metrics (
            evaluation_metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_run_id TEXT NOT NULL,
            metric_scope TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            FOREIGN KEY (evaluation_run_id) REFERENCES evaluation_runs(evaluation_run_id)
        );

        CREATE INDEX IF NOT EXISTS idx_deliveries_timeline
            ON deliveries(timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_match_innings_pos
            ON deliveries(season_id, match_id, innings, over_number, ball_number);

        CREATE INDEX IF NOT EXISTS idx_deliveries_batter_bowler_timeline
            ON deliveries(batter, bowler, timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_types_timeline
            ON deliveries(batsman_type, bowler_type, timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_season_match
            ON deliveries(season_id, match_id);

        CREATE INDEX IF NOT EXISTS idx_deliveries_match_order
            ON deliveries(match_id, innings, over_number, ball_number, source_row_number);

        CREATE INDEX IF NOT EXISTS idx_deliveries_team_timeline
            ON deliveries(team_batting, team_bowling, timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_outcome
            ON deliveries(is_wicket, total_runs);

        CREATE INDEX IF NOT EXISTS idx_batter_bowler_stats_agg
            ON batter_bowler_stats_agg(batter, bowler);

        CREATE INDEX IF NOT EXISTS idx_phase_outcome_stats_agg
            ON phase_outcome_stats_agg(phase);

        CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status
            ON ingestion_runs(status, started_at);
        """
    )

    # Lightweight migrations for pre-existing DBs created by earlier vertical slices.
    _ensure_column(conn, "ingestion_runs", "source_size_bytes", "INTEGER")
    _ensure_column(conn, "ingestion_runs", "source_mtime_ns", "INTEGER")
    _ensure_column(conn, "ingestion_runs", "source_content_sha256", "TEXT")
    _ensure_column(conn, "ingestion_runs", "schema_fingerprint", "TEXT")
    _ensure_column(conn, "ingestion_runs", "row_count", "INTEGER")
    _ensure_column(conn, "ingestion_runs", "error_message", "TEXT")

    _ensure_column(conn, "data_sources", "status", "TEXT NOT NULL DEFAULT 'unknown'")
    _ensure_column(conn, "data_sources", "data_version", "TEXT")

    conn.commit()


def reset_ingested_data(conn: sqlite3.Connection, commit: bool = True) -> None:
    conn.execute("DELETE FROM matches")
    conn.execute("DELETE FROM innings_summary")
    conn.execute("DELETE FROM seasons")
    conn.execute("DELETE FROM teams")
    conn.execute("DELETE FROM players")
    conn.execute("DELETE FROM batter_stats_agg")
    conn.execute("DELETE FROM bowler_stats_agg")
    conn.execute("DELETE FROM batter_bowler_stats_agg")
    conn.execute("DELETE FROM batter_bowler_type_stats_agg")
    conn.execute("DELETE FROM bowler_batter_type_stats_agg")
    conn.execute("DELETE FROM phase_outcome_stats_agg")
    conn.execute("DELETE FROM outcome_stats_agg")
    conn.execute("DELETE FROM deliveries")
    conn.execute("DELETE FROM rejected_deliveries")
    conn.execute("DELETE FROM raw_deliveries")
    if commit:
        conn.commit()


def upsert_ingestion_state(conn: sqlite3.Connection, key: str, value: Any) -> None:
    text_value = "" if value is None else str(value)
    conn.execute(
        """
        INSERT INTO ingestion_state(state_key, state_value)
        VALUES(?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
            state_value = excluded.state_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, text_value),
    )


def get_ingestion_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT state_value FROM ingestion_state WHERE state_key = ?", (key,)).fetchone()
    return None if row is None else str(row["state_value"])


def database_runtime_status(conn: sqlite3.Connection) -> dict[str, Any]:
    values: dict[str, Any] = {
        "dataset_status": get_ingestion_state(conn, "dataset_status") or "unknown",
        "active_run_id": get_ingestion_state(conn, "active_run_id"),
        "last_run_id": get_ingestion_state(conn, "last_run_id"),
        "last_error": get_ingestion_state(conn, "last_error"),
    }
    row = conn.execute("SELECT COUNT(*) AS n FROM deliveries").fetchone()
    values["deliveries"] = int(row["n"])
    return values


