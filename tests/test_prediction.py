from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
from matchgenomeipl.match_state import build_pre_delivery_state, get_target_delivery
from matchgenomeipl.prediction import (
    SequentialPredictionSession,
    build_prediction_context,
    predict_hierarchical_from_count_map,
    predict_next_ball,
    predict_next_ball_baseline,
)
from matchgenomeipl.analytics import classify_delivery_outcome
from collections import Counter
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
        pred = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        probs = pred["outcome_probabilities"]

        self.assertTrue(all(v >= 0 for v in probs.values()))
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=5)

    def test_prediction_is_deterministic(self) -> None:
        p1 = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        p2 = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        self.assertEqual(p1["chosen_evidence_level"], p2["chosen_evidence_level"])
        self.assertEqual(p1["outcome_probabilities"], p2["outcome_probabilities"])

    def test_prediction_context_matches_prediction_contract(self) -> None:
        context = build_prediction_context(self.conn, 2021, 2, 1, 0, 1)
        pred = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        self.assertEqual(pred["state_identity"]["timeline_key"], context.timeline_key)
        self.assertEqual(pred["state_identity"]["legal_balls_before"], context.legal_balls_before)
        self.assertEqual(pred["state_identity"]["innings_phase"], context.phase)
        self.assertIn("evidence", pred)
        self.assertIn("looked_at", pred["evidence"])

    def test_sequential_replay_matches_direct_predictions(self) -> None:
        rows = self.conn.execute(
            """
            SELECT over_number, ball_number
            FROM deliveries
            WHERE season_id = 2021 AND match_id = 2 AND innings = 1
            ORDER BY over_number, ball_number, source_row_number
            LIMIT 4
            """
        ).fetchall()

        direct = [
            predict_next_ball(self.conn, 2021, 2, 1, int(r["over_number"]), int(r["ball_number"]))
            for r in rows
        ]

        session = SequentialPredictionSession(self.conn, 2021, 2, 1)
        replay = [session.predict_and_advance() for _ in range(len(rows))]

        self.assertEqual(
            [item["predicted_top_outcome"] for item in direct],
            [item["predicted_top_outcome"] for item in replay],
        )
        self.assertEqual(
            [item["outcome_probabilities"] for item in direct],
            [item["outcome_probabilities"] for item in replay],
        )

    def test_prediction_path_does_not_read_csv(self) -> None:
        with patch("pathlib.Path.open", side_effect=AssertionError("CSV should not be read during prediction")):
            pred = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        self.assertIn("outcome_probabilities", pred)

    def test_baseline_mode_is_preserved_for_regression(self) -> None:
        p = predict_next_ball(self.conn, 2021, 2, 1, 0, 1, model_version="baseline_hierarchical_v1")
        self.assertEqual(p["model_version"], "baseline_hierarchical_v1")

    def test_contextual_prediction_exposes_feature_snapshot(self) -> None:
        pred = predict_next_ball(self.conn, 2021, 2, 1, 0, 1)
        self.assertEqual(pred["model_version"], "contextual_hybrid_v1")
        self.assertIn("feature_snapshot", pred)
        self.assertIn("matchup_sample", pred["feature_snapshot"])

    def test_optimized_prediction_matches_legacy_semantics(self) -> None:
        season_id, match_id, innings, over_number, ball_number = (2021, 2, 1, 0, 1)
        optimized = predict_next_ball_baseline(self.conn, season_id, match_id, innings, over_number, ball_number)

        target = get_target_delivery(self.conn, season_id, match_id, innings, over_number, ball_number)
        state = build_pre_delivery_state(self.conn, season_id, match_id, innings, over_number, ball_number)
        timeline = target["timeline_key"]

        def legacy_counts(sql: str, params: tuple) -> Counter[str]:
            counts: Counter[str] = Counter()
            for row in self.conn.execute(sql, params).fetchall():
                counts[classify_delivery_outcome(row)] += 1
            return counts

        global_counts = legacy_counts("SELECT * FROM deliveries WHERE timeline_key < ?", (timeline,))
        context_count_map = {
            ("batter_bowler", (target["batter"], target["bowler"])): legacy_counts(
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler = ?",
                (timeline, target["batter"], target["bowler"]),
            ),
            ("batter_bowler_type", (target["batter"], target["bowler_type"])): legacy_counts(
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler_type = ?",
                (timeline, target["batter"], target["bowler_type"]),
            ),
            ("bowler_batter_type", (target["bowler"], target["batsman_type"])): legacy_counts(
                "SELECT * FROM deliveries WHERE timeline_key < ? AND bowler = ? AND batsman_type = ?",
                (timeline, target["bowler"], target["batsman_type"]),
            ),
            (("batter_type_bowler_type"), (target["batsman_type"], target["bowler_type"])): legacy_counts(
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batsman_type = ? AND bowler_type = ?",
                (timeline, target["batsman_type"], target["bowler_type"]),
            ),
        }

        legacy = predict_hierarchical_from_count_map(
            {
                "batter": target["batter"],
                "bowler": target["bowler"],
                "batsman_type": target["batsman_type"],
                "bowler_type": target["bowler_type"],
            },
            context_count_map,
            global_counts,
        )

        self.assertEqual(optimized["outcome_probabilities"], legacy["outcome_probabilities"])
        self.assertEqual(optimized["predicted_top_outcome"], legacy["predicted_top_outcome"])
        self.assertEqual(optimized["chosen_evidence_level"], legacy["chosen_evidence_level"])
        self.assertEqual(optimized["evidence_sample_size"], legacy["evidence_sample_size"])
        self.assertEqual(optimized["reliability"], legacy["reliability"])
        self.assertEqual(optimized["state_identity"]["legal_balls_before"], state["observed_state"]["legal_balls_before_delivery"])
        self.assertEqual(optimized["state_identity"]["innings_phase"], state["observed_state"]["innings_phase"])


if __name__ == "__main__":
    unittest.main()

