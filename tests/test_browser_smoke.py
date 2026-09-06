from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.http_transport import create_http_server
from matchgenomeipl.ingestion import ensure_dataset_ready
from matchgenomeipl.database import connect_db


class BrowserSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.sqlite3"

        src_db = connect_db(ROOT / "data" / "ipl.sqlite3")
        dst_db = connect_db(self.db_path)
        try:
            src_db.backup(dst_db)
        finally:
            src_db.close()
            dst_db.close()

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

    def _get_json(self, path: str) -> dict:
        with urlopen(self._url(path)) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict | None = None) -> dict:
        req = Request(
            self._url(path),
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_time_machine_browser_smoke_path(self) -> None:
        # Open app and validate the reveal-first placeholder is rendered.
        with urlopen(self._url("/")) as response:
            html = response.read().decode("utf-8")
        self.assertIn("Reveal the ball to see actual outcome.", html)
        self.assertIn("Cricket Intelligence Studio", html)
        self.assertIn("Players", html)
        self.assertIn("Match Discovery", html)
        self.assertIn("matchCards", html)

        seasons = self._get_json("/api/seasons")["seasons"]
        season_id = int(seasons[-1]["season_id"])
        matches = self._get_json(f"/api/seasons/{season_id}/matches")["matches"]
        match_id = int(matches[0]["match_id"])
        innings = self._get_json(f"/api/matches/{match_id}/innings")["innings"]
        innings_id = int(innings[0]["innings"])

        replay = self._post_json("/api/replays", {"match_id": match_id, "innings": innings_id})
        session_id = replay["session_id"]

        first_prediction = self._post_json(f"/api/replays/{session_id}/predict")
        self.assertIn("prediction", first_prediction)
        self.assertNotIn("actual", first_prediction)

        reveal = self._post_json(f"/api/replays/{session_id}/reveal")
        self.assertIn("actual", reveal)
        self.assertIn("comparison", reveal)

        next_prediction = self._post_json(f"/api/replays/{session_id}/predict")
        self.assertIn("prediction", next_prediction)

        batter_name = quote(str(next_prediction["delivery"]["batter"]))
        player = self._get_json(f"/api/players/{batter_name}?session_id={session_id}")
        self.assertEqual(str(player["player"]["name"]), str(next_prediction["delivery"]["batter"]))
        self.assertIn("entry_points", player)
        self.assertEqual(player["entry_points"]["return_to_replay"]["session_id"], session_id)

        self._post_json(f"/api/replays/{session_id}/restart")
        replayed_first = self._post_json(f"/api/replays/{session_id}/predict")
        self.assertEqual(first_prediction["prediction"], replayed_first["prediction"])

        with self.assertRaises(HTTPError):
            urlopen(self._url("/data/ipl_ball_by_ball_data.csv"))

    def test_startup_skip_unchanged_dataset(self) -> None:
        conn = connect_db(self.db_path)
        try:
            csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
            first = ensure_dataset_ready(conn, csv_path)
            second = ensure_dataset_ready(conn, csv_path)
            self.assertTrue(second.skipped)
            self.assertIn(first.status, {"ready", "skipped_unchanged"})
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

