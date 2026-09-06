from __future__ import annotations

import csv
import tempfile
import time
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ensure_dataset_ready, ingest_csv_to_sqlite
from fixture_data import SAMPLE_CSV


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample_deliveries.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_ingestion_is_repeatable_without_duplication(self) -> None:
        first = ensure_dataset_ready(self.conn, self.fixture)
        second = ensure_dataset_ready(self.conn, self.fixture)

        row_count = self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        self.assertEqual(first.loaded_rows, 8)
        self.assertEqual(second.loaded_rows, 0)
        self.assertTrue(second.skipped)
        self.assertEqual(row_count, 8)

    def test_source_change_detection_triggers_refresh(self) -> None:
        ensure_dataset_ready(self.conn, self.fixture)

        with self.fixture.open("a", encoding="utf-8", newline="") as out:
            out.write(
                "2022,3,PlayerZ,BowlerZ,PlayerY,Team5,Team6,0,0,1,0,1,right-hand,right-arm-fast,,,FALSE,FALSE,FALSE,FALSE,FALSE,FALSE,0,0,0,0,0,,FALSE,1\n"
            )
        time.sleep(0.01)

        refreshed = ensure_dataset_ready(self.conn, self.fixture)
        self.assertFalse(refreshed.skipped)
        self.assertTrue(refreshed.source_changed)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 9)

    def test_manifest_tables_are_populated(self) -> None:
        stats = ensure_dataset_ready(self.conn, self.fixture)
        self.assertEqual(stats.status, "ready")
        source_row = self.conn.execute("SELECT status, row_count, content_sha256 FROM data_sources").fetchone()
        self.assertEqual(source_row["status"], "ready")
        self.assertEqual(source_row["row_count"], 8)
        self.assertTrue(source_row["content_sha256"])

    def test_schema_validation_fails_when_required_column_missing(self) -> None:
        bad_csv = Path(self.tmp.name) / "missing_col.csv"
        with self.fixture.open("r", encoding="utf-8-sig", newline="") as src:
            reader = csv.DictReader(src)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)

        columns = [c for c in fieldnames if c != "batter"]
        with bad_csv.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                row.pop("batter", None)
                writer.writerow(row)

        with self.assertRaises(ValueError):
            ingest_csv_to_sqlite(self.conn, bad_csv)

    def test_malformed_row_is_rejected_and_preserved_in_raw(self) -> None:
        malformed_csv = Path(self.tmp.name) / "malformed.csv"
        with self.fixture.open("r", encoding="utf-8-sig", newline="") as src:
            rows = list(csv.DictReader(src))
        rows[0]["total_runs"] = "7"

        with malformed_csv.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        stats = ingest_csv_to_sqlite(self.conn, malformed_csv)

        self.assertEqual(stats.rejected_rows, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM raw_deliveries").fetchone()[0], 8)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 7)

    def test_refresh_failure_preserves_last_known_good_database(self) -> None:
        ensure_dataset_ready(self.conn, self.fixture)
        baseline_count = self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]

        bad_csv = """season_id,match_id,bowler,non_striker,team_batting,team_bowling,over_number,ball_number,batter_runs,extras,total_runs,batsman_type,bowler_type,player_out,fielders_involved,is_wicket,is_wide_ball,is_no_ball,is_leg_bye,is_bye,is_penalty,wide_ball_runs,no_ball_runs,leg_bye_runs,bye_runs,penalty_runs,wicket_kind,is_super_over,innings\n"""
        self.fixture.write_text(bad_csv, encoding="utf-8")

        with self.assertRaises(ValueError):
            ingest_csv_to_sqlite(self.conn, self.fixture, force_refresh=True)

        after_failure_count = self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        self.assertEqual(after_failure_count, baseline_count)


if __name__ == "__main__":
    unittest.main()



