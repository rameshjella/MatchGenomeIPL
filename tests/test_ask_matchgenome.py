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
from matchgenomeipl.ask_matchgenome import AskMatchGenomeEngine, QueryExecutor, QueryPlan, QueryPlanValidator
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ingest_csv_to_sqlite


class AskMatchGenomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"

        conn = connect_db(self.db_path)
        initialize_schema(conn)
        ingest_csv_to_sqlite(conn, self.fixture)
        self.conn = conn
        self.engine = AskMatchGenomeEngine(conn)
        self.validator = QueryPlanValidator(self.engine.semantic)
        self.executor = QueryExecutor(self.conn, self.engine.semantic)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_single_question_plan_and_answer(self) -> None:
        payload = self.engine.ask("How many sixes did PlayerC hit in 2020?")
        self.assertEqual(payload["answered"], 1)
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["operation"], "aggregate")
        self.assertEqual(payload["results"][0]["query_plan"]["entity"], "player")

    def test_alias_resolution_by_token(self) -> None:
        payload = self.engine.ask("How many runs did PlayerA score in 2020?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["entities"]["player"], "PlayerA")

    def test_compound_question_split(self) -> None:
        payload = self.engine.ask("How many runs did PlayerA score in 2020, what was his strike rate in 2020?")
        self.assertGreaterEqual(payload["sub_questions"], 2)
        self.assertGreaterEqual(payload["answered"], 2)

    def test_batter_run_rate_maps_to_strike_rate(self) -> None:
        payload = self.engine.ask("PlayerA run rate in 2020")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["metric"], "strike_rate")
        self.assertIsInstance(payload["results"][0]["result"]["value"], float)

    def test_unsupported_question_is_not_fabricated(self) -> None:
        payload = self.engine.ask("Tell me database credentials")
        self.assertEqual(payload["results"][0]["status"], "unsupported")

    def test_executor_rejects_non_select_sql(self) -> None:
        with self.assertRaises(ValueError):
            self.executor._safe_readonly("DELETE FROM deliveries")

    def test_validator_rejects_unknown_operation(self) -> None:
        with self.assertRaises(ValueError):
            self.validator.validate(QueryPlan(question="x", operation="hack", entity="player", entities={"player": "PlayerA"}))

    def test_validator_rejects_non_integer_season(self) -> None:
        with self.assertRaises(ValueError):
            self.validator.validate(
                QueryPlan(
                    question="x",
                    operation="aggregate",
                    entity="player",
                    entities={"player": "PlayerA", "season": "2020"},
                    metric="runs",
                )
            )

    def test_validator_rejects_limit_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            self.validator.validate(
                QueryPlan(
                    question="x",
                    operation="rank",
                    entity="batting",
                    entities={"season": 2020},
                    metric="runs",
                    limit=100,
                )
            )

    def test_compile_rejects_unknown_table(self) -> None:
        with self.assertRaises(ValueError):
            self.executor._compile_select(table="not_a_table", select_columns=["x"])

    def test_compile_rejects_unknown_column(self) -> None:
        with self.assertRaises(ValueError):
            self.executor._compile_select(table="deliveries", select_columns=["season_id", "unknown_col"])

    def test_compile_rejects_unsafe_expression(self) -> None:
        with self.assertRaises(ValueError):
            self.executor._compile_select(table="deliveries", select_columns=["season_id"], where=[("season_id", "like", "2020")])


if __name__ == "__main__":
    unittest.main()

