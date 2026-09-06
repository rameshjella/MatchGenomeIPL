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

    def test_player_intelligence_returns_overview_and_matchups(self) -> None:
        profile = get_player_intelligence(self.conn, "PlayerA")
        self.assertEqual(profile["player"]["name"], "PlayerA")
        self.assertIn("overview", profile)
        self.assertIn("batting_intelligence", profile)
        self.assertIn("bowling_intelligence", profile)
        self.assertIn("matchups", profile)
        self.assertGreaterEqual(profile["overview"]["batting"]["runs"], 0)

    def test_player_not_found(self) -> None:
        with self.assertRaises(ValueError):
            get_player_intelligence(self.conn, "MissingPlayer")

    def test_db_only_player_intelligence_no_csv_read(self) -> None:
        with patch("pathlib.Path.open", side_effect=AssertionError("CSV access not allowed")):
            profile = get_player_intelligence(self.conn, "PlayerA")
            self.assertEqual(profile["player"]["name"], "PlayerA")


if __name__ == "__main__":
    unittest.main()

