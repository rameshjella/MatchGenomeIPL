from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fixture_data import SAMPLE_CSV
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.enrichment import run_cricsheet_enrichment, run_reference_knowledge_enrichment
from matchgenomeipl.ingestion import ingest_csv_to_sqlite
from matchgenomeipl.time_machine import TimeMachineService


class EnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "test.sqlite3"
        self.csv_path = self.tmp_path / "sample.csv"
        self.csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

        self.project_root = self.tmp_path / "project"
        (self.project_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (self.project_root / "web").mkdir(parents=True, exist_ok=True)
        (self.project_root / "web" / "player_photos.json").write_text("{}", encoding="utf-8")

        self.zip_path = self.project_root / "artifacts" / "ipl_json.zip"
        self._write_zip_fixture(self.zip_path)

        self.conn = connect_db(self.db_path)
        initialize_schema(self.conn)
        ingest_csv_to_sqlite(self.conn, self.csv_path)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _write_zip_fixture(self, path: Path) -> None:
        m1 = {
            "info": {
                "event": {"name": "Indian Premier League", "match_number": 1},
                "dates": ["2020-09-19"],
                "match_type": "T20",
                "teams": ["Kings XI Punjab", "Chennai Super Kings"],
                "venue": "Abu Dhabi Stadium",
                "city": "Abu Dhabi",
                "toss": {"winner": "Chennai Super Kings", "decision": "field"},
                "outcome": {"winner": "Chennai Super Kings", "by": {"wickets": 5}},
                "player_of_match": ["AT Rayudu"],
            },
            "innings": [{"team": "Kings XI Punjab", "overs": []}],
        }
        m2 = {
            "info": {
                "event": {"name": "Indian Premier League", "match_number": 2},
                "dates": ["2021-04-10"],
                "match_type": "T20",
                "teams": ["Delhi Daredevils", "Mumbai Indians"],
                "venue": "Wankhede Stadium",
                "city": "Mumbai",
                "toss": {"winner": "Delhi Daredevils", "decision": "bat"},
                "outcome": {"winner": "Mumbai Indians", "by": {"runs": 7}},
                "player_of_match": ["RG Sharma"],
            },
            "innings": [{"team": "Delhi Daredevils", "overs": []}],
        }
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("1.json", json.dumps(m1))
            zf.writestr("2.json", json.dumps(m2))

    def test_enrichment_persists_identity_metadata_and_is_used_by_service(self) -> None:
        with patch("matchgenomeipl.enrichment.ensure_cricsheet_archive", return_value=self.zip_path):
            stats = run_cricsheet_enrichment(self.conn, self.project_root, force_refresh=False)

        self.assertEqual(stats["matches_enriched"], 2)

        service = TimeMachineService(self.conn)
        matches = service.list_matches(2020)
        self.assertEqual(matches[0]["team_a"], "Kings XI Punjab")
        self.assertEqual(matches[0]["team_b"], "Chennai Super Kings")
        self.assertEqual(matches[0]["match_date"], "2020-09-19")

        match = service.get_match(1)
        self.assertEqual(match["metadata"]["venue"], "Abu Dhabi Stadium")
        self.assertEqual(match["metadata"]["toss"]["winner"], "Chennai Super Kings")

        innings = service.list_innings(1)
        self.assertEqual(innings[0]["team_batting"], "Kings XI Punjab")
        self.assertEqual(innings[0]["team_batting_internal"], "Team1")

        team_row = self.conn.execute(
            "SELECT current_canonical_name FROM team_identity WHERE historical_display_name = ?",
            ("Kings XI Punjab",),
        ).fetchone()
        self.assertIsNotNone(team_row)
        self.assertEqual(team_row["current_canonical_name"], "Punjab Kings")

    def test_reference_knowledge_enrichment_populates_player_and_team_season(self) -> None:
        stats = run_reference_knowledge_enrichment(self.conn)
        self.assertGreaterEqual(stats["players_upserted"], 4)
        self.assertGreaterEqual(stats["team_seasons_upserted"], 3)

        dhoni = self.conn.execute(
            "SELECT full_name, verification_status, source_key FROM player_knowledge WHERE canonical_player_name = ?",
            ("MS Dhoni",),
        ).fetchone()
        self.assertIsNotNone(dhoni)
        self.assertEqual(dhoni["full_name"], "Mahendra Singh Dhoni")
        self.assertEqual(dhoni["verification_status"], "provisional")
        self.assertEqual(dhoni["source_key"], "matchgenome_reference_knowledge_v1")

        team_season = self.conn.execute(
            "SELECT captain, coach, owner, verification_status FROM team_season_knowledge WHERE canonical_team_name = ? AND season_id = ?",
            ("Mumbai Indians", 2024),
        ).fetchone()
        self.assertIsNotNone(team_season)
        self.assertEqual(team_season["captain"], "Hardik Pandya")
        self.assertEqual(team_season["verification_status"], "provisional")


if __name__ == "__main__":
    unittest.main()

