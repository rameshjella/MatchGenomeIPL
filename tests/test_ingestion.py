from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
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
        first = ingest_csv_to_sqlite(self.conn, self.fixture)
        second = ingest_csv_to_sqlite(self.conn, self.fixture)

        row_count = self.conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        self.assertEqual(first.loaded_rows, 8)
        self.assertEqual(second.loaded_rows, 8)
        self.assertEqual(row_count, 8)

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


if __name__ == "__main__":
    unittest.main()



