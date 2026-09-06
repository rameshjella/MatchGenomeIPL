from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fixture_data import SAMPLE_CSV
from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.http_transport import create_http_server
from matchgenomeipl.ingestion import ingest_csv_to_sqlite


class HttpTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self.tmp.name) / "sample.csv"
        self.fixture.write_text(SAMPLE_CSV, encoding="utf-8")
        self.db_path = Path(self.tmp.name) / "test.sqlite3"

        conn = connect_db(self.db_path)
        initialize_schema(conn)
        ingest_csv_to_sqlite(conn, self.fixture)
        conn.close()

        self.server = create_http_server(self.db_path, host="127.0.0.1", port=0, static_dir=ROOT / "web")
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server.conn.close()  # type: ignore[attr-defined]
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path: str) -> tuple[int, dict]:
        with urlopen(self._url(path)) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload or {}).encode("utf-8")
        req = Request(self._url(path), data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_discovery_endpoints(self) -> None:
        status, seasons = self._get("/api/seasons")
        self.assertEqual(status, 200)
        self.assertEqual(len(seasons["seasons"]), 2)

        status, matches = self._get("/api/seasons/2020/matches")
        self.assertEqual(status, 200)
        self.assertEqual(matches["matches"][0]["match_id"], 1)
        self.assertIn("team_a", matches["matches"][0])
        self.assertIn("team_b", matches["matches"][0])
        self.assertIn("season_match_number", matches["matches"][0])

        status, innings = self._get("/api/matches/1/innings")
        self.assertEqual(status, 200)
        self.assertEqual(innings["innings"][0]["innings"], 1)

    def test_static_index_is_served(self) -> None:
        with urlopen(self._url("/")) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("See the prediction before you see the outcome.", body)

    def test_local_player_asset_is_served(self) -> None:
        with urlopen(self._url("/assets/players/tm_head.svg")) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("<svg", body)

    def test_player_endpoints(self) -> None:
        status, players = self._get("/api/players")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(players["players"]), 1)
        name = quote(players["players"][0]["player_name"])
        self.assertIn("asset_type", players["players"][0]["photo"])
        self.assertIn("is_verified_photo", players["players"][0]["photo"])

        status, profile = self._get(f"/api/players/{name}")
        self.assertEqual(status, 200)
        self.assertIn("overview", profile)
        self.assertIn("player", profile)
        self.assertIn("asset_type", profile["player"]["photo"])

    def test_player_search_partial_name(self) -> None:
        status, players = self._get("/api/players?query=yerA&limit=10")
        self.assertEqual(status, 200)
        names = [item["player_name"] for item in players["players"]]
        self.assertIn("PlayerA", names)

    def test_player_endpoint_with_session_context(self) -> None:
        status, created = self._post("/api/replays", {"match_id": 1, "innings": 1})
        self.assertEqual(status, 201)
        session_id = created["session_id"]

        status, profile = self._get(f"/api/players/{quote('PlayerA')}?session_id={session_id}")
        self.assertEqual(status, 200)
        self.assertIn("entry_points", profile)
        self.assertEqual(profile["entry_points"]["return_to_replay"]["session_id"], session_id)

    def test_replay_predict_reveal_and_completion(self) -> None:
        status, created = self._post("/api/replays", {"match_id": 1, "innings": 1})
        self.assertEqual(status, 201)
        session_id = created["session_id"]

        status, p1 = self._post(f"/api/replays/{session_id}/predict")
        self.assertEqual(status, 200)
        status, p2 = self._post(f"/api/replays/{session_id}/predict")
        self.assertEqual(p1, p2)

        status, r1 = self._post(f"/api/replays/{session_id}/reveal")
        self.assertEqual(status, 200)
        status, r2 = self._post(f"/api/replays/{session_id}/reveal")
        self.assertEqual(r1, r2)

        while True:
            status, replay = self._get(f"/api/replays/{session_id}")
            self.assertEqual(status, 200)
            if replay["status"] == "COMPLETED":
                break
            self._post(f"/api/replays/{session_id}/predict")
            self._post(f"/api/replays/{session_id}/reveal")

        self.assertEqual(replay["status"], "COMPLETED")

    def test_invalid_session_returns_controlled_error(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self._get("/api/replays/missing")
        payload = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", payload)

    def test_db_only_predict_reveal_no_csv_read(self) -> None:
        status, created = self._post("/api/replays", {"match_id": 1, "innings": 1})
        self.assertEqual(status, 201)
        session_id = created["session_id"]

        with patch("pathlib.Path.open", side_effect=AssertionError("CSV access not allowed")):
            self._post(f"/api/replays/{session_id}/predict")
            self._post(f"/api/replays/{session_id}/reveal")

    def test_csv_is_not_served(self) -> None:
        with self.assertRaises(HTTPError):
            urlopen(self._url("/data/ipl_ball_by_ball_data.csv"))

    def test_assets_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(HTTPError):
            urlopen(self._url("/assets/../data/ipl_ball_by_ball_data.csv"))


if __name__ == "__main__":
    unittest.main()


