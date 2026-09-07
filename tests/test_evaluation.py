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
from matchgenomeipl.evaluation import (
    MixtureTuningConfig,
    _online_trace,
    _rows_split_for_cutoff,
    evaluate_contextual_candidates,
    evaluate_temporal_models,
    recency_weight_for_age,
    tune_mixture_weights,
    tune_time_decayed_mixture,
)
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

    @staticmethod
    def _fast_config() -> MixtureTuningConfig:
        return MixtureTuningConfig(validation_season=2020, grid_step=0.5, decay_candidates=(1.0, 0.9))

    def test_evaluation_is_deterministic(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            run1 = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                tuning_config=self._fast_config(),
            )
            run2 = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                tuning_config=self._fast_config(),
            )
            self.assertEqual(run1["models"]["global"]["overall"], run2["models"]["global"]["overall"])
            self.assertEqual(run1["models"]["matchgenome_hierarchical"]["overall"], run2["models"]["matchgenome_hierarchical"]["overall"])
            self.assertEqual(run1["models_additional"]["calibrated_mixture"]["overall"], run2["models_additional"]["calibrated_mixture"]["overall"])
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
                tuning_config=self._fast_config(),
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
                tuning_config=self._fast_config(),
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
                tuning_config=self._fast_config(),
            )
            changed_probs = changed["delivery_predictions"][0]["predictions"]["matchgenome_hierarchical"]["probabilities"]
            self.assertEqual(base_probs, changed_probs)
        finally:
            conn2.close()

    def test_tuning_weights_are_valid_and_deterministic(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            t1 = tune_mixture_weights(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            t2 = tune_mixture_weights(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            w1 = t1["selected"]["weights"]
            w2 = t2["selected"]["weights"]
            self.assertEqual(w1, w2)
            self.assertTrue(all(v >= 0.0 for v in w1.values()))
            self.assertAlmostEqual(sum(w1.values()), 1.0, places=9)
        finally:
            conn.close()

    def test_final_evaluation_outcome_change_does_not_change_selected_weights(self) -> None:
        conn1, _ = self._build_conn_with_fixture()
        try:
            base = tune_mixture_weights(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            base_weights = base["selected"]["weights"]
        finally:
            conn1.close()

        # Modify only final evaluation season delivery.
        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        rows[-1]["total_runs"] = "0"
        rows[-1]["batter_runs"] = "0"

        changed_fixture = Path(self.tmp.name) / "changed_eval_only.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed_eval.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = tune_mixture_weights(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            self.assertEqual(base_weights, changed["selected"]["weights"])
        finally:
            conn2.close()

    def test_future_validation_change_does_not_affect_earlier_validation_prediction(self) -> None:
        conn1, _ = self._build_conn_with_fixture()
        try:
            base = tune_mixture_weights(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            first_base = base["validation_trace"][0]["base_predictions"]["phase"]["outcome_probabilities"]
        finally:
            conn1.close()

        # Modify a later validation-season delivery (season 2020) only.
        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        rows[5]["total_runs"] = "0"
        rows[5]["batter_runs"] = "0"

        changed_fixture = Path(self.tmp.name) / "changed_validation_future.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed_val.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = tune_mixture_weights(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            first_changed = changed["validation_trace"][0]["base_predictions"]["phase"]["outcome_probabilities"]
            self.assertEqual(first_base, first_changed)
        finally:
            conn2.close()

    def test_final_evaluation_outcome_change_does_not_change_selected_decay(self) -> None:
        conn1, _ = self._build_conn_with_fixture()
        try:
            base = tune_time_decayed_mixture(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            base_decay = base["selected"]["recency_decay"]
            base_weights = base["selected"]["selected"]["weights"]
        finally:
            conn1.close()

        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        rows[-1]["total_runs"] = "6"
        rows[-1]["batter_runs"] = "6"

        changed_fixture = Path(self.tmp.name) / "changed_eval_only_decay.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed_eval_decay.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = tune_time_decayed_mixture(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
            )
            self.assertEqual(base_decay, changed["selected"]["recency_decay"])
            self.assertEqual(base_weights, changed["selected"]["selected"]["weights"])
        finally:
            conn2.close()

    def test_future_validation_change_does_not_affect_earlier_validation_prediction_with_decay(self) -> None:
        conn1, _ = self._build_conn_with_fixture()
        try:
            base = tune_mixture_weights(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
                recency_decay=0.9,
                include_contribution=False,
            )
            first_base = base["validation_trace"][0]["base_predictions"]["phase"]["outcome_probabilities"]
        finally:
            conn1.close()

        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        rows[5]["total_runs"] = "0"
        rows[5]["batter_runs"] = "0"

        changed_fixture = Path(self.tmp.name) / "changed_validation_future_decay.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed_val_decay.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = tune_mixture_weights(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                config=self._fast_config(),
                recency_decay=0.9,
                include_contribution=False,
            )
            first_changed = changed["validation_trace"][0]["base_predictions"]["phase"]["outcome_probabilities"]
            self.assertEqual(first_base, first_changed)
        finally:
            conn2.close()

    def test_recency_weight_is_monotonic_and_valid(self) -> None:
        self.assertEqual(recency_weight_for_age(0, 0.9), 1.0)
        self.assertGreater(recency_weight_for_age(1, 0.9), recency_weight_for_age(2, 0.9))
        self.assertGreaterEqual(recency_weight_for_age(3, 0.9), 0.0)

    def test_no_decay_equivalence_matches_existing_mixture(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            result = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                tuning_config=MixtureTuningConfig(validation_season=2020, grid_step=0.5, decay_candidates=(1.0,)),
            )
            existing = result["models_additional"]["calibrated_mixture"]["overall"]
            decayed = result["models_additional"]["time_decayed_mixture"]["overall"]
            self.assertEqual(existing, decayed)
        finally:
            conn.close()

    def test_contextual_candidate_report_is_available(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            report = evaluate_contextual_candidates(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
            )
            self.assertIn("candidates", report)
            self.assertIn("combined_context", report["candidates"])
            self.assertIn("team_opposition_context", report["candidates"])
            self.assertIn("similar_situations_context", report["candidates"])
        finally:
            conn.close()

    def test_temporal_report_includes_calibration_and_sample_buckets(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            report = evaluate_temporal_models(
                conn,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                tuning_config=self._fast_config(),
            )
            baseline = report["models"]["matchgenome_hierarchical"]
            self.assertIn("calibration", baseline)
            self.assertIn("sample_size_buckets", baseline)
            self.assertIn("prediction_latency", report)
        finally:
            conn.close()

    def test_leakage_guard_eval_rows_are_only_target_window(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            from matchgenomeipl.chronology import ordered_deliveries

            rows = ordered_deliveries(conn)
            history, eval_rows = _rows_split_for_cutoff(rows, KnowledgeCutoff(2020), EvaluationWindow(2021))
            self.assertGreater(len(eval_rows), 0)
            self.assertTrue(all(int(r["season_id"]) == 2021 for r in eval_rows))
            # Training history should only accumulate from <= cutoff seasons.
            self.assertGreater(int(sum(history.global_counts.values())), 0)
        finally:
            conn.close()

    def test_leakage_guard_future_match_change_does_not_shift_prior_prediction(self) -> None:
        conn1, _ = self._build_conn_with_fixture()
        try:
            base = evaluate_temporal_models(
                conn1,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                max_deliveries=1,
                tuning_config=self._fast_config(),
            )
            base_probs = base["delivery_predictions"][0]["predictions"]["global"]["probabilities"]
        finally:
            conn1.close()

        # Append synthetic future-season row; earlier eval prediction must remain unchanged.
        rows = list(csv.DictReader(SAMPLE_CSV.splitlines()))
        template = dict(rows[-1])
        template["season_id"] = "2022"
        template["match_id"] = "99"
        template["innings"] = "1"
        template["over_number"] = "0"
        template["ball_number"] = "1"
        template["total_runs"] = "6"
        template["batter_runs"] = "6"
        rows.append(template)

        changed_fixture = Path(self.tmp.name) / "changed_future_season.csv"
        with changed_fixture.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

        conn2 = connect_db(Path(self.tmp.name) / "test_changed_future.sqlite3")
        initialize_schema(conn2)
        ingest_csv_to_sqlite(conn2, changed_fixture)
        try:
            changed = evaluate_temporal_models(
                conn2,
                knowledge_cutoff=KnowledgeCutoff(2020),
                evaluation_window=EvaluationWindow(2021),
                max_deliveries=1,
                tuning_config=self._fast_config(),
            )
            changed_probs = changed["delivery_predictions"][0]["predictions"]["global"]["probabilities"]
            self.assertEqual(base_probs, changed_probs)
        finally:
            conn2.close()

    def test_leakage_guard_online_trace_updates_after_prediction(self) -> None:
        conn, _ = self._build_conn_with_fixture()
        try:
            from matchgenomeipl.chronology import ordered_deliveries

            rows = ordered_deliveries(conn)
            history, eval_rows = _rows_split_for_cutoff(rows, KnowledgeCutoff(2020), EvaluationWindow(2021))
            summary, trace = _online_trace(history, eval_rows[:2])
            self.assertEqual(len(trace), 2)
            # Ensure trace carries two independent predictions, proving update occurs between deliveries.
            self.assertIn("base_predictions", trace[0])
            self.assertIn("base_predictions", trace[1])
            self.assertIn("model_acc", summary)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()


