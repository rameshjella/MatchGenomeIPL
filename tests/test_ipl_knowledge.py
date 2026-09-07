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
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
from matchgenomeipl.ipl_knowledge import points_table, season_leaderboards, season_stats_overview


class IplKnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)
        ingest_csv_to_sqlite(self.conn, self.fixture)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_season_stats_overview_contains_canonical_fields(self) -> None:
        report = season_stats_overview(self.conn, 2020)
        self.assertEqual(report["season_id"], 2020)
        self.assertGreaterEqual(report["runs"], 0)
        self.assertIn("dot_ball_percentage", report)
        self.assertIn("coverage", report)
        self.assertIn("definitions", report)

    def test_season_leaderboards_include_primary_tracks(self) -> None:
        board = season_leaderboards(self.conn, 2020, limit=3)
        keys = set(board["leaderboards"].keys())
        self.assertIn("orange_cap_runs", keys)
        self.assertIn("purple_cap_wickets", keys)
        self.assertIn("most_sixes", keys)
        self.assertIn("best_economy", keys)

    def test_points_table_nrr_uses_full_quota_for_all_out(self) -> None:
        # Build a compact synthetic season where TeamA is all out in 10 overs.
        self.conn.execute(
            """
            INSERT OR IGNORE INTO enrichment_source(
                source_key, source_name, source_url, source_type, source_version, status, last_checked_at
            ) VALUES ('test_fixture', 'Test Fixture', 'https://example.invalid', 'unit', 'v1', 'ready', CURRENT_TIMESTAMP)
            """
        )
        self.conn.execute(
            """
            INSERT INTO match_metadata(
                match_id, season_id, match_number, match_date, venue, city,
                team_a_display, team_b_display, winner,
                source_key, source_reference, fetched_at, verification_status, enrichment_version
            ) VALUES (1001, 2099, 1, '2099-04-01', 'Test Ground', 'Test City', 'TeamA', 'TeamB', 'TeamB',
                      'test_fixture', 'unit', CURRENT_TIMESTAMP, 'derived', 'v1')
            """
        )
        self.conn.execute(
            """
            INSERT INTO innings_summary(
                season_id, match_id, innings, team_batting, team_bowling, deliveries, legal_balls, runs, wickets
            ) VALUES
            (2099, 1001, 1, 'TeamA', 'TeamB', 60, 60, 120, 10),
            (2099, 1001, 2, 'TeamB', 'TeamA', 120, 120, 121, 3)
            """
        )
        self.conn.commit()

        table = points_table(self.conn, 2099)
        team_a = next(row for row in table if row["team"] == "TeamA")
        team_b = next(row for row in table if row["team"] == "TeamB")

        # Canonical T20 NRR treatment uses full 20 overs (120 balls) for all-out innings.
        self.assertAlmostEqual(float(team_a["net_run_rate"]), -0.05, places=3)
        self.assertAlmostEqual(float(team_b["net_run_rate"]), 0.05, places=3)


if __name__ == "__main__":
    unittest.main()

