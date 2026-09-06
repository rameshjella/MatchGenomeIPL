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
from matchgenomeipl.player_intelligence import get_player_intelligence, list_players


class PlayerIntelligenceTests(unittest.TestCase):
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

    def test_list_players_returns_photo_fallback(self) -> None:
        players = list_players(self.conn, query="Player", limit=10)
        self.assertGreaterEqual(len(players), 1)
        self.assertIn("photo", players[0])
        self.assertIn(players[0]["photo"]["kind"], {"local", "placeholder"})
        if players[0]["photo"]["kind"] == "placeholder":
            self.assertIn("seed", players[0]["photo"])

    def test_list_players_normalized_query(self) -> None:
        players = list_players(self.conn, query="player a", limit=10)
        names = [item["player_name"] for item in players]
        self.assertIn("PlayerA", names)

    def test_player_intelligence_returns_overview_and_matchups(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        self.assertEqual(profile["player"]["name"], "PlayerA")
        self.assertIn("overview", profile)
        self.assertIn("batting_intelligence", profile)
        self.assertIn("bowling_intelligence", profile)
        self.assertIn("matchups", profile)
        self.assertGreaterEqual(profile["overview"]["batting"]["runs"], 0)
        self.assertTrue(profile["sections"]["has_batting"])

    def test_player_profile_calculations(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        batting = profile["overview"]["batting"]

        self.assertEqual(batting["runs"], 8)
        self.assertEqual(batting["balls"], 5)
        self.assertEqual(batting["fours"], 1)
        self.assertEqual(batting["sixes"], 0)
        self.assertEqual(batting["dismissals"], 0)
        self.assertEqual(batting["strike_rate"], 160.0)

    def test_player_season_and_phase_metrics(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        batting_seasons = profile["batting_intelligence"]["by_season"]
        bowling_seasons = profile["bowling_intelligence"]["by_season"]

        self.assertEqual(len(batting_seasons), 2)
        self.assertEqual([item["season_id"] for item in batting_seasons], [2020, 2021])
        self.assertEqual(len(profile["batting_intelligence"]["by_phase"]), 1)
        self.assertEqual(profile["batting_intelligence"]["by_phase"][0]["phase"], "powerplay")
        self.assertEqual(len(bowling_seasons), 0)

    def test_matchup_metrics_and_evidence_tier(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        matchups = profile["matchups"]["batter_vs_bowler"]
        self.assertGreaterEqual(len(matchups), 1)
        first = matchups[0]
        self.assertEqual(first["opponent"], "BowlerX")
        self.assertEqual(first["sample_size"], 6)
        self.assertIn(first["evidence_tier"], {"small", "low", "medium", "high"})

    def test_outcome_distribution_shape(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        outcomes = profile["batting_intelligence"]["outcome_distribution"]
        self.assertEqual(set(outcomes.keys()), {"0", "1", "2", "3+", "4", "6", "wicket"})

    def test_player_not_found(self) -> None:
        with self.assertRaises(ValueError):
            get_player_intelligence(self.conn, "MissingPlayer")

    def test_db_only_player_intelligence_no_csv_read(self) -> None:
        with patch("pathlib.Path.open", side_effect=AssertionError("CSV access not allowed")):
            profile = get_player_intelligence(self.conn, "PlayerA")
            self.assertEqual(profile["player"]["name"], "PlayerA")


if __name__ == "__main__":
    unittest.main()

