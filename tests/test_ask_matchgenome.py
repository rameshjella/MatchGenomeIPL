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
        conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name, full_name, source_key, source_url, retrieved_at, verification_status
            ) VALUES (?, ?, 'test_fixture', 'https://example.invalid/playera', CURRENT_TIMESTAMP, 'verified')
            ON CONFLICT(canonical_player_name) DO UPDATE SET full_name=excluded.full_name
            """,
            ("PlayerA", "Player A Fullname"),
        )
        conn.execute(
            """
            INSERT INTO team_knowledge(
                canonical_team_name, short_name, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('Team1', 'T1', 'test_fixture', 'https://example.invalid/team1', CURRENT_TIMESTAMP, 'verified')
            ON CONFLICT(canonical_team_name) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO team_season_knowledge(
                canonical_team_name, season_id, captain, coach, owner, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('Team1', 2020, 'Captain One', 'Coach One', 'Owner One', 'test_fixture', 'https://example.invalid/team1/2020', CURRENT_TIMESTAMP, 'verified')
            ON CONFLICT(canonical_team_name, season_id, captain, coach, owner, home_venue) DO NOTHING
            """
        )
        conn.execute(
            """
            INSERT INTO team_season_knowledge(
                canonical_team_name, season_id, captain, coach, owner, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('Team1', 2021, 'Captain One', 'Coach One', 'Owner One', 'test_fixture', 'https://example.invalid/team1/2021', CURRENT_TIMESTAMP, 'verified')
            ON CONFLICT(canonical_team_name, season_id, captain, coach, owner, home_venue) DO NOTHING
            """
        )
        conn.commit()
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

    def test_compare_uses_two_distinct_players(self) -> None:
        payload = self.engine.ask("Compare PlayerA and PlayerB in 2020")
        self.assertEqual(payload["results"][0]["status"], "ok")
        players = payload["results"][0]["query_plan"]["entities"].get("players", [])
        self.assertEqual(players, ["PlayerA", "PlayerB"])

    def test_batter_run_rate_maps_to_strike_rate(self) -> None:
        payload = self.engine.ask("PlayerA run rate in 2020")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["metric"], "strike_rate")
        self.assertIsInstance(payload["results"][0]["result"]["value"], float)

    def test_unsupported_question_is_not_fabricated(self) -> None:
        payload = self.engine.ask("Tell me database credentials")
        self.assertEqual(payload["results"][0]["status"], "unsupported")

    def test_player_knowledge_full_name_lookup(self) -> None:
        payload = self.engine.ask("What is the full name of PlayerA?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["operation"], "knowledge_lookup")
        self.assertEqual(payload["results"][0]["result"]["value"], "Player A Fullname")

    def test_player_knowledge_unavailable_attribute(self) -> None:
        payload = self.engine.ask("When was PlayerA born?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertIn("Verified information is not currently available", payload["results"][0]["result"]["label"])

    def test_team_season_knowledge_lookup(self) -> None:
        payload = self.engine.ask("Who was Team1 captain in 2020?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["result"]["value"], "Captain One")

    def test_team_season_knowledge_lookup_without_season_uses_latest_known(self) -> None:
        payload = self.engine.ask("Who is Team1 captain?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["result"]["value"], "Captain One")

    def test_current_season_leadership_does_not_fallback_to_old_year(self) -> None:
        self.conn.execute(
            """
            INSERT INTO team_season_knowledge(
                canonical_team_name, season_id, captain, coach, owner, source_key, source_url, retrieved_at, verification_status
            ) VALUES
            ('Team1', 2021, 'Captain Current', 'Coach Current', 'Owner Current', 'test_fixture', 'https://example.invalid/team1/2021b', CURRENT_TIMESTAMP, 'verified')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)

        current = self.engine.ask("Who is Team1 captain?")
        historical = self.engine.ask("Who was Team1 captain in 2020?")
        self.assertEqual(current["results"][0]["result"]["value"], "Captain Current")
        self.assertEqual(historical["results"][0]["result"]["value"], "Captain One")

    def test_current_season_leadership_missing_returns_unavailable(self) -> None:
        self.conn.execute("DELETE FROM team_season_knowledge WHERE canonical_team_name = 'Team1' AND season_id = 2021")
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)

        payload = self.engine.ask("Who is Team1 captain?")
        self.assertIsNone(payload["results"][0]["result"]["value"])
        self.assertIn("Verified information is not currently available", payload["results"][0]["result"]["label"])

    def test_children_phrase_with_kids_is_supported(self) -> None:
        payload = self.engine.ask("How many kids does PlayerA have?")
        self.assertEqual(payload["results"][0]["status"], "ok")

    def test_provisional_player_fact_is_not_returned_as_verified(self) -> None:
        self.conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name, full_name, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('PlayerProvisional', 'Player Provisional Fullname', 'test_fixture', 'https://example.invalid/provisional', CURRENT_TIMESTAMP, 'provisional')
            ON CONFLICT(canonical_player_name) DO UPDATE SET full_name=excluded.full_name, verification_status='provisional'
            """
        )
        self.conn.execute("INSERT OR IGNORE INTO players(player_name) VALUES ('PlayerProvisional')")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO player_identity_alias(alias_name, canonical_player_name, source_key, source_url, retrieved_at, verification_status)
            VALUES ('player provisional', 'PlayerProvisional', 'test_fixture', NULL, CURRENT_TIMESTAMP, 'provisional')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)
        payload = self.engine.ask("What is the full name of Player Provisional?")
        self.assertIsNone(payload["results"][0]["result"]["value"])
        self.assertIn("Verified information is not currently available", payload["results"][0]["result"]["label"])

    def test_final_winner_variants_resolve(self) -> None:
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
                team_a_display, team_b_display, winner, match_type,
                source_key, source_reference, fetched_at, verification_status, enrichment_version
            ) VALUES (24240074, 2024, NULL, '2024-05-26', 'MA Chidambaram Stadium', 'Chennai',
                      'Sunrisers Hyderabad', 'Kolkata Knight Riders', 'Kolkata Knight Riders', 'Final',
                      'test_fixture', 'unit', CURRENT_TIMESTAMP, 'verified', 'v1')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)
        for question in [
            "What was the winner of the IPL 2024 final?",
            "Who won the 2024 IPL final?",
            "IPL 2024 final winner",
            "Who won IPL 2024?",
            "Who were the 2024 champions?",
        ]:
            payload = self.engine.ask(question)
            self.assertEqual(payload["results"][0]["status"], "ok")
            value = payload["results"][0]["result"]["value"]
            self.assertEqual(value["winner"], "Kolkata Knight Riders")

    def test_spelling_variant_resolves_player(self) -> None:
        self.conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name, full_name, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('V Suryavanshi', 'Vaibhav Suryavanshi', 'test_fixture', 'https://example.invalid/vaibhav', CURRENT_TIMESTAMP, 'verified')
            ON CONFLICT(canonical_player_name) DO UPDATE SET full_name=excluded.full_name
            """
        )
        self.conn.execute("INSERT OR IGNORE INTO players(player_name) VALUES ('V Suryavanshi')")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO player_identity_alias(alias_name, canonical_player_name, source_key, source_url, retrieved_at, verification_status)
            VALUES ('v suryavanshi', 'V Suryavanshi', 'test_fixture', NULL, CURRENT_TIMESTAMP, 'verified')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)
        payload = self.engine.ask("What is the full name of Vaibhav Sooryavanshi?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["result"]["value"], "Vaibhav Suryavanshi")

    def test_standalone_variant_name_is_supported(self) -> None:
        self.conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name, full_name, source_key, source_url, retrieved_at, verification_status
            ) VALUES ('V Suryavanshi', 'Vaibhav Suryavanshi', 'test_fixture', 'https://example.invalid/vaibhav', CURRENT_TIMESTAMP, 'provisional')
            ON CONFLICT(canonical_player_name) DO UPDATE SET full_name=excluded.full_name
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)
        payload = self.engine.ask("Vaibhav Sooryavanshi")
        self.assertEqual(payload["results"][0]["status"], "ok")

    def test_fixtures_results_points_table_queries(self) -> None:
        fx = self.engine.ask("Show IPL 2020 fixtures")
        rs = self.engine.ask("Show IPL 2020 results")
        pt = self.engine.ask("Show IPL 2020 points table")
        self.assertEqual(fx["results"][0]["status"], "ok")
        self.assertEqual(rs["results"][0]["status"], "ok")
        self.assertEqual(pt["results"][0]["status"], "ok")

    def test_untrusted_season_refuses_statistical_answer(self) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO season_trust_gate(
                season_id, coverage_status, reconciliation_status, status, reason,
                source_key, source_url, retrieved_at, verification_status
            ) VALUES (2020, 'FAIL', 'FAIL', 'FAIL', 'coverage_incomplete',
                      'test_fixture', 'https://example.invalid', CURRENT_TIMESTAMP, 'verified')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)

        payload = self.engine.ask("Who scored the most runs in IPL 2020?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertIsNone(payload["results"][0]["result"]["value"])
        self.assertIn("Verified information is not currently available", payload["results"][0]["result"]["label"])

    def test_trusted_season_allows_statistical_answer(self) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO season_trust_gate(
                season_id, coverage_status, reconciliation_status, status, reason,
                source_key, source_url, retrieved_at, verification_status
            ) VALUES (2020, 'PASS', 'PASS', 'PASS', 'coverage_complete_and_reconciled',
                      'test_fixture', 'https://example.invalid', CURRENT_TIMESTAMP, 'verified')
            """
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)

        payload = self.engine.ask("Who scored the most runs in IPL 2020?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertIsInstance(payload["results"][0]["result"]["value"], list)

    def test_prediction_guidance_questions_are_supported(self) -> None:
        payload = self.engine.ask("What is likely to happen on the next ball?")
        self.assertEqual(payload["results"][0]["status"], "ok")
        self.assertEqual(payload["results"][0]["query_plan"]["operation"], "prediction_info")

    def test_low_signal_alias_collision_requires_clarification(self) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO player_knowledge(canonical_player_name, source_key, source_url, retrieved_at, verification_status) VALUES ('AA Patel', 'test_fixture', NULL, CURRENT_TIMESTAMP, 'derived')"
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO player_knowledge(canonical_player_name, source_key, source_url, retrieved_at, verification_status) VALUES ('PP Patel', 'test_fixture', NULL, CURRENT_TIMESTAMP, 'derived')"
        )
        self.conn.execute("INSERT OR IGNORE INTO players(player_name) VALUES ('AA Patel')")
        self.conn.execute("INSERT OR IGNORE INTO players(player_name) VALUES ('PP Patel')")
        self.conn.execute(
            "INSERT INTO player_identity_alias(alias_name, canonical_player_name, source_key, source_url, retrieved_at, verification_status) VALUES (?, ?, 'test_fixture', NULL, CURRENT_TIMESTAMP, 'derived')",
            ("patel", "AA Patel"),
        )
        self.conn.execute(
            "INSERT INTO player_identity_alias(alias_name, canonical_player_name, source_key, source_url, retrieved_at, verification_status) VALUES (?, ?, 'test_fixture', NULL, CURRENT_TIMESTAMP, 'derived')",
            ("patel", "PP Patel"),
        )
        self.conn.commit()
        self.engine = AskMatchGenomeEngine(self.conn)

        payload = self.engine.ask("Show Patel best season")
        self.assertEqual(payload["results"][0]["status"], "clarification_needed")

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

