from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fixture_data import SAMPLE_CSV
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ensure_dataset_ready


class DatabaseFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample_deliveries.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)
        ensure_dataset_ready(self.conn, self.fixture)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_core_entities_materialized(self) -> None:
        seasons = self.conn.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
        teams = self.conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        players = self.conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        matches = self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        innings = self.conn.execute("SELECT COUNT(*) FROM innings_summary").fetchone()[0]

        self.assertEqual(seasons, 2)
        self.assertEqual(teams, 4)
        self.assertGreaterEqual(players, 6)
        self.assertEqual(matches, 2)
        self.assertEqual(innings, 2)

    def test_delivery_identity_uniqueness(self) -> None:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT season_id || '-' || match_id || '-' || innings || '-' || over_number || '-' || ball_number) AS uniq
            FROM deliveries
            """
        ).fetchone()
        self.assertEqual(int(row["total"]), int(row["uniq"]))

    def test_aggregate_values(self) -> None:
        batter = self.conn.execute(
            "SELECT runs, balls_faced, fours, sixes FROM batter_stats_agg WHERE batter = 'PlayerA'"
        ).fetchone()
        bowler = self.conn.execute(
            "SELECT runs_conceded, legal_balls, wickets FROM bowler_stats_agg WHERE bowler = 'BowlerX'"
        ).fetchone()

        self.assertEqual(int(batter["runs"]), 8)
        self.assertEqual(int(batter["balls_faced"]), 5)
        self.assertEqual(int(batter["fours"]), 1)
        self.assertEqual(int(batter["sixes"]), 0)
        self.assertGreater(int(bowler["legal_balls"]), 0)


if __name__ == "__main__":
    unittest.main()

