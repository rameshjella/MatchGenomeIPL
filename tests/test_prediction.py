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
from matchgenomeipl.prediction import predict_next_ball_baseline
from fixture_data import SAMPLE_CSV


class PredictionTests(unittest.TestCase):
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

    def test_probabilities_are_valid(self) -> None:
        pred = predict_next_ball_baseline(self.conn, 2021, 2, 1, 0, 1)
        probs = pred["outcome_probabilities"]

        self.assertTrue(all(v >= 0 for v in probs.values()))
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=5)

    def test_prediction_is_deterministic(self) -> None:
        p1 = predict_next_ball_baseline(self.conn, 2021, 2, 1, 0, 1)
        p2 = predict_next_ball_baseline(self.conn, 2021, 2, 1, 0, 1)
        self.assertEqual(p1["chosen_evidence_level"], p2["chosen_evidence_level"])
        self.assertEqual(p1["outcome_probabilities"], p2["outcome_probabilities"])


if __name__ == "__main__":
    unittest.main()

