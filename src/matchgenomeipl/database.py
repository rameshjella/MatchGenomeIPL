from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_db(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            run_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            stats_json TEXT,
            status TEXT NOT NULL
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

        CREATE INDEX IF NOT EXISTS idx_deliveries_timeline
            ON deliveries(timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_match_innings_pos
            ON deliveries(season_id, match_id, innings, over_number, ball_number);

        CREATE INDEX IF NOT EXISTS idx_deliveries_batter_bowler_timeline
            ON deliveries(batter, bowler, timeline_key);

        CREATE INDEX IF NOT EXISTS idx_deliveries_types_timeline
            ON deliveries(batsman_type, bowler_type, timeline_key);
        """
    )
    conn.commit()


def reset_ingested_data(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM deliveries")
    conn.execute("DELETE FROM rejected_deliveries")
    conn.execute("DELETE FROM raw_deliveries")
    conn.commit()

