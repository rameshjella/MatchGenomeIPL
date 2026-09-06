from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.http_transport import create_http_server


def _get(base: str, path: str) -> tuple[float, Any]:
    t0 = time.perf_counter()
    with urlopen(base + path) as resp:
        data = resp.read().decode("utf-8")
        elapsed = time.perf_counter() - t0
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return elapsed, json.loads(data)
        return elapsed, data


def _post(base: str, path: str, payload: dict | None = None) -> tuple[float, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = Request(base + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return time.perf_counter() - t0, data


def main() -> None:
    server = create_http_server(ROOT / "data" / "ipl.sqlite3", host="127.0.0.1", port=0, static_dir=ROOT / "web")
    try:
        import threading

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        home_t, home = _get(base, "/")
        seasons_t, seasons = _get(base, "/api/seasons")
        season_id = int(seasons["seasons"][-1]["season_id"])

        matches_t, matches = _get(base, f"/api/seasons/{season_id}/matches")
        match_id = int(matches["matches"][0]["match_id"])

        innings_t, innings = _get(base, f"/api/matches/{match_id}/innings")
        innings_id = int(innings["innings"][0]["innings"])

        create_t, created = _post(base, "/api/replays", {"match_id": match_id, "innings": innings_id})
        session_id = created["session_id"]

        predict_t, _ = _post(base, f"/api/replays/{session_id}/predict")
        reveal_t, _ = _post(base, f"/api/replays/{session_id}/reveal")
        next_predict_t, _ = _post(base, f"/api/replays/{session_id}/predict")

        step_times = []
        for _ in range(10):
            p, _ = _post(base, f"/api/replays/{session_id}/predict")
            r, _ = _post(base, f"/api/replays/{session_id}/reveal")
            step_times.append(p + r)

        report = {
            "frontend_initial_load_seconds": round(home_t, 6),
            "frontend_initial_payload_bytes": len(home),
            "season_loading_seconds": round(seasons_t, 6),
            "match_loading_seconds": round(matches_t, 6),
            "innings_loading_seconds": round(innings_t, 6),
            "replay_creation_seconds": round(create_t, 6),
            "prediction_request_seconds": round(predict_t, 6),
            "reveal_request_seconds": round(reveal_t, 6),
            "next_prediction_request_seconds": round(next_predict_t, 6),
            "ten_step_replay": {
                "total_seconds": round(sum(step_times), 6),
                "average_seconds": round(sum(step_times) / len(step_times), 6),
                "max_seconds": round(max(step_times), 6),
            },
            "selected": {
                "season_id": season_id,
                "match_id": match_id,
                "innings": innings_id,
            },
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        server.shutdown()
        server.server_close()
        server.conn.close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

