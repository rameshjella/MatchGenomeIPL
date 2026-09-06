from __future__ import annotations

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
from matchgenomeipl.match_state import build_pre_delivery_state
from fixture_data import SAMPLE_CSV


class MatchStateTests(unittest.TestCase):
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

    def test_state_is_pre_delivery_and_excludes_target_outcome(self) -> None:
        state = build_pre_delivery_state(self.conn, 2020, 1, 1, 0, 4)
        observed = state["observed_state"]

        self.assertEqual(observed["score_before_delivery"], 6)
        self.assertEqual(observed["wickets_before_delivery"], 0)
        self.assertEqual(state["target_outcome"], "wicket")

    def test_recent_outcomes_order(self) -> None:
        state = build_pre_delivery_state(self.conn, 2020, 1, 1, 1, 0)
        recent = state["observed_state"]["recent_delivery_outcomes"]
        self.assertGreaterEqual(len(recent), 1)
        self.assertEqual(recent[-1], "wicket")


if __name__ == "__main__":
    unittest.main()

