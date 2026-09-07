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

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_single_question_plan_and_answer(self) -> None:
        payload = self.engine.ask("How many sixes did PlayerC hit in 2020?")
        self.assertEqual(payload["answered"], 1)
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["intent"], "PLAYER_SEASON_STAT")

    def test_alias_resolution_by_token(self) -> None:
        payload = self.engine.ask("How many runs did PlayerA score in 2020?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["entities"]["player"], "PlayerA")

    def test_compound_question_split(self) -> None:
        payload = self.engine.ask("How many runs did PlayerA score in 2020, what was his strike rate in 2020?")
        self.assertGreaterEqual(payload["sub_questions"], 2)
        self.assertGreaterEqual(payload["answered"], 2)

    def test_unsupported_question_is_not_fabricated(self) -> None:
        payload = self.engine.ask("Tell me database credentials")
        self.assertEqual(payload["results"][0]["status"], "unsupported")

    def test_executor_rejects_non_select_sql(self) -> None:
        executor = QueryExecutor(self.conn)
        with self.assertRaises(ValueError):
            executor._safe_readonly("DELETE FROM deliveries")

    def test_unknown_intent_rejected(self) -> None:
        executor = QueryExecutor(self.conn)
        with self.assertRaises(ValueError):
            executor.execute(QueryPlan(question="x", intent="BAD", entities={}))

    def test_validator_rejects_extra_entity_fields(self) -> None:
        validator = QueryPlanValidator()
        with self.assertRaises(ValueError):
            validator.validate(
                QueryPlan(
                    question="x",
                    intent="PLAYER_SEASON_STAT",
                    entities={"player": "PlayerA", "season": 2020, "hack": "x"},
                    metric="runs",
                )
            )

    def test_validator_rejects_non_integer_season(self) -> None:
        validator = QueryPlanValidator()
        with self.assertRaises(ValueError):
            validator.validate(
                QueryPlan(
                    question="x",
                    intent="PLAYER_SEASON_STAT",
                    entities={"player": "PlayerA", "season": "2020"},
                    metric="runs",
                )
            )

    def test_validator_rejects_limit_out_of_range(self) -> None:
        validator = QueryPlanValidator()
        with self.assertRaises(ValueError):
            validator.validate(
                QueryPlan(
                    question="x",
                    intent="RANKING_STAT",
                    entities={"season": 2020},
                    metric="runs",
                    limit=100,
                )
            )


if __name__ == "__main__":
    unittest.main()

