from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fixture_data import SAMPLE_CSV
from matchgenomeipl.chronology import EvaluationWindow, KnowledgeCutoff
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.evaluation import evaluate_temporal_models
from matchgenomeipl.ingestion import ingest_csv_to_sqlite


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample_deliveries.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build_conn_with_fixture(self) -> tuple[sqlite3.Connection, Path]:
        conn = connect_db(self.db_path)
        initialize_schema(conn)
        ingest_csv_to_sqlite(conn, self.fixture)
        return conn, self.fixture

    def test_evaluation_is_deterministic(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            run1 = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
            )
            run2 = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
            )
            self.assertEqual(run1["models"]["global"]["overall"], run2["models"]["global"]["overall"])
            self.assertEqual(run1["models"]["matchgenome_hierarchical"]["overall"], run2["models"]["matchgenome_hierarchical"]["overall"])
        finally:
            conn.close()

    def test_target_outcome_is_not_used_before_prediction(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            result = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                max_deliveries=1,
            )
            first = result["delivery_predictions"][0]
            p1 = first["predictions"]["global"]["probabilities"]["1"]
            self.assertAlmostEqual(p1, 0.230769, places=6)
        finally:
            conn.close()

    def test_future_delivery_change_does_not_affect_earlier_prediction(self) -> None:
        conn1, fixture1 = self._build_conn_with_fixture()
        try:
            base = evaluate_temporal_models(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                max_deliveries=1,
            )
            base_probs = base["delivery_predictions"][0]["predictions"]["matchgenome_hierarchical"]["probabilities"]
        finally:
            conn1.close()

        # Change a future delivery (second evaluation row) and rebuild DB.
        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        rows[-1]["total_runs"] = "6"
        rows[-1]["batter_runs"] = "6"
        rows[-1]["is_wicket"] = "FALSE"

        changed_fixture = Path(self.tmp.name) / "changed_sample.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = evaluate_temporal_models(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                max_deliveries=1,
            )
            changed_probs = changed["delivery_predictions"][0]["predictions"]["matchgenome_hierarchical"]["probabilities"]
            self.assertEqual(base_probs, changed_probs)
        finally:
            conn2.close()


if __name__ == "__main__":
    unittest.main()


