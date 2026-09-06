from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.analytics import batter_stats, bowler_stats, classify_delivery_outcome, current_score_at_delivery, innings_progression
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
from fixture_data import SAMPLE_CSV


class AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample_deliveries.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)
        ingest_csv_to_sqlite(self.conn, self.fixture)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_batter_stats(self) -> None:
        stats = batter_stats(self.conn, "PlayerA")
        self.assertEqual(stats["runs"], 8)
        self.assertEqual(stats["balls_faced"], 5)
        self.assertEqual(stats["fours"], 1)
        self.assertEqual(stats["sixes"], 0)

    def test_bowler_stats(self) -> None:
        stats = bowler_stats(self.conn, "BowlerX")
        self.assertEqual(stats["wickets"], 1)
        self.assertGreater(stats["economy"], 0)

    def test_innings_progression_and_score_at_delivery(self) -> None:
        progression = innings_progression(self.conn, 2020, 1, 1)
        self.assertEqual(progression[0]["score"], 0)
        self.assertEqual(progression[1]["score"], 4)

        score = current_score_at_delivery(self.conn, 2020, 1, 1, 0, 3)
        self.assertEqual(score["score"], 6)

    def test_outcome_classifier(self) -> None:
        row = self.conn.execute(
            "SELECT * FROM deliveries WHERE season_id = 2020 AND match_id = 1 AND innings = 1 AND over_number = 0 AND ball_number = 4"
        ).fetchone()
        self.assertEqual(classify_delivery_outcome(row), "wicket")


if __name__ == "__main__":
    unittest.main()

