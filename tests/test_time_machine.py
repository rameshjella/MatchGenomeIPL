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

from fixture_data import SAMPLE_CSV
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
from matchgenomeipl.prediction import SequentialPredictionSession
from matchgenomeipl.time_machine import TimeMachineService
from matchgenomeipl.time_machine_api import TimeMachineAPI


class TimeMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample_deliveries.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"
        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)
        ingest_csv_to_sqlite(self.conn, self.fixture)
        self.service = TimeMachineService(self.conn)
        self.api = TimeMachineAPI(self.service)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _create_default_session_id(self) -> str:
        payload = self.api.post_replays(match_id=1, innings=1)
        return str(payload["session_id"])

    def test_match_discovery_contract(self) -> None:
        seasons = self.api.get_seasons()["seasons"]
        self.assertEqual([s["season_id"] for s in seasons], [2020, 2021])

        matches_2020 = self.api.get_season_matches(2020)["matches"]
        self.assertEqual(len(matches_2020), 1)
        self.assertEqual(matches_2020[0]["match_id"], 1)
        self.assertIn("team_a", matches_2020[0])
        self.assertIn("team_b", matches_2020[0])
        self.assertIn("season_match_number", matches_2020[0])

        innings = self.api.get_match_innings(1)["innings"]
        self.assertEqual(len(innings), 1)
        self.assertEqual(innings[0]["innings"], 1)

    def test_create_and_inspect_session(self) -> None:
        created = self.api.post_replays(match_id=1, innings=1)
        self.assertEqual(created["status"], "READY")
        self.assertEqual(created["current_state"]["next_delivery"]["over_number"], 0)
        self.assertEqual(created["current_state"]["next_delivery"]["ball_number"], 0)

        inspected = self.api.get_replay(created["session_id"])
        self.assertEqual(inspected["session_id"], created["session_id"])
        self.assertEqual(inspected["status"], "READY")

    def test_predict_is_deterministic_until_reveal(self) -> None:
        session_id = self._create_default_session_id()
        p1 = self.api.post_replay_predict(session_id)
        p2 = self.api.post_replay_predict(session_id)
        self.assertEqual(p1, p2)

    def test_reveal_requires_prediction(self) -> None:
        session_id = self._create_default_session_id()
        with self.assertRaises(ValueError):
            self.api.post_replay_reveal(session_id)

    def test_predict_then_reveal_updates_state(self) -> None:
        session_id = self._create_default_session_id()
        pred = self.api.post_replay_predict(session_id)
        reveal = self.api.post_replay_reveal(session_id)

        self.assertEqual(pred["delivery"]["over_number"], 0)
        self.assertEqual(pred["delivery"]["ball_number"], 0)
        self.assertEqual(reveal["delivery"]["over_number"], 0)
        self.assertEqual(reveal["delivery"]["ball_number"], 0)
        self.assertEqual(reveal["actual"]["actual_outcome"], "0")
        self.assertEqual(reveal["updated_state"]["score_before_delivery"], 0)
        self.assertEqual(reveal["updated_state"]["legal_balls_before_delivery"], 1)

    def test_reveal_is_idempotent_after_same_prediction(self) -> None:
        session_id = self._create_default_session_id()
        self.api.post_replay_predict(session_id)
        r1 = self.api.post_replay_reveal(session_id)
        r2 = self.api.post_replay_reveal(session_id)
        self.assertEqual(r1, r2)

    def test_starting_delivery_reconstructs_pre_delivery_knowledge(self) -> None:
        created = self.api.post_replays(match_id=1, innings=1, start_over_number=0, start_ball_number=3)
        session_id = str(created["session_id"])
        pred = self.api.post_replay_predict(session_id)

        self.assertEqual(pred["delivery"]["over_number"], 0)
        self.assertEqual(pred["delivery"]["ball_number"], 3)
        self.assertEqual(pred["pre_delivery_state"]["score"], 5)
        self.assertEqual(pred["pre_delivery_state"]["wickets"], 0)
        self.assertEqual(pred["pre_delivery_state"]["legal_balls"], 2)

    def test_wide_delivery_does_not_advance_legal_ball_count(self) -> None:
        session_id = self._create_default_session_id()
        self.api.post_replay_predict(session_id)
        self.api.post_replay_reveal(session_id)
        self.api.post_replay_predict(session_id)
        self.api.post_replay_reveal(session_id)
        self.api.post_replay_predict(session_id)
        reveal_wide = self.api.post_replay_reveal(session_id)

        self.assertEqual(reveal_wide["actual"]["actual_outcome"], "1")
        self.assertEqual(reveal_wide["actual"]["delivery_facts"]["is_wide_ball"], 1)
        self.assertEqual(reveal_wide["updated_state"]["legal_balls_before_delivery"], 2)

    def test_wicket_delivery_is_reported(self) -> None:
        session_id = self._create_default_session_id()
        reveal = None
        for _ in range(5):
            self.api.post_replay_predict(session_id)
            reveal = self.api.post_replay_reveal(session_id)
        self.assertIsNotNone(reveal)
        self.assertEqual(reveal["actual"]["actual_outcome"], "wicket")
        self.assertEqual(reveal["actual"]["delivery_facts"]["is_wicket"], 1)

    def test_session_completion_and_post_completion_predict(self) -> None:
        session_id = self._create_default_session_id()
        while True:
            try:
                self.api.post_replay_predict(session_id)
                self.api.post_replay_reveal(session_id)
            except StopIteration:
                break
            except ValueError as exc:
                if "completed" in str(exc).lower():
                    break
                raise

        state = self.api.get_replay(session_id)
        self.assertEqual(state["status"], "COMPLETED")
        with self.assertRaises(ValueError):
            self.api.post_replay_predict(session_id)

    def test_restart_replay_session_is_deterministic(self) -> None:
        created = self.api.post_replays(match_id=1, innings=1)
        session_id = str(created["session_id"])

        first = self.api.post_replay_predict(session_id)
        self.api.post_replay_reveal(session_id)

        restarted = self.api.post_replay_restart(session_id)
        self.assertEqual(restarted["status"], "READY")

        second = self.api.post_replay_predict(session_id)
        self.assertEqual(first["delivery"], second["delivery"])
        self.assertEqual(first["prediction"], second["prediction"])

    def test_invalid_session_handling(self) -> None:
        with self.assertRaises(ValueError):
            self.api.get_replay("missing")

    def test_replay_ledger_and_summary(self) -> None:
        session_id = self._create_default_session_id()
        for _ in range(3):
            self.api.post_replay_predict(session_id)
            self.api.post_replay_reveal(session_id)

        ledger = self.api.get_replay_ledger(session_id)["entries"]
        state = self.api.get_replay(session_id)

        self.assertEqual(len(ledger), 3)
        self.assertEqual(state["summary"]["predictions_revealed"], 3)
        self.assertIn("accuracy", state["summary"])

    def test_replay_matches_direct_session_sequence(self) -> None:
        session_id = self._create_default_session_id()
        replay_payloads = []
        for _ in range(4):
            pred = self.api.post_replay_predict(session_id)
            replay_payloads.append(pred["prediction"])
            self.api.post_replay_reveal(session_id)

        direct = SequentialPredictionSession(self.conn, 2020, 1, 1)
        direct_payloads = []
        for _ in range(4):
            pred = direct.predict_next()
            direct_payloads.append(
                {
                    "model_version": pred["model_version"],
                    "chosen_evidence_level": pred["chosen_evidence_level"],
                    "evidence_sample_size": pred["evidence_sample_size"],
                    "reliability": pred["reliability"],
                    "outcome_probabilities": pred["outcome_probabilities"],
                    "predicted_top_outcome": pred["predicted_top_outcome"],
                }
            )
            direct.advance_with_actual()

        self.assertEqual(replay_payloads, direct_payloads)

    def test_db_only_replay_does_not_read_csv(self) -> None:
        session_id = self._create_default_session_id()
        with patch("pathlib.Path.open", side_effect=AssertionError("CSV access is not allowed during replay")):
            self.api.post_replay_predict(session_id)
            self.api.post_replay_reveal(session_id)

    def test_player_profile_can_include_replay_entry_point(self) -> None:
        session_id = self._create_default_session_id()
        player = self.api.get_player("PlayerA", session_id=session_id)
        self.assertEqual(player["entry_points"]["return_to_replay"]["session_id"], session_id)


if __name__ == "__main__":
    unittest.main()


