from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, database_runtime_status
from matchgenomeipl.time_machine import TimeMachineService
from matchgenomeipl.time_machine_api import TimeMachineAPI


def main() -> None:
    conn = connect_db(ROOT / "data" / "ipl.sqlite3")
    api = TimeMachineAPI(TimeMachineService(conn))

    seasons = api.get_seasons()["seasons"]
    selected_season = seasons[-1]["season_id"]
    matches = api.get_season_matches(selected_season)["matches"]
    selected_match = matches[0]["match_id"]
    innings = api.get_match_innings(selected_match)["innings"]
    selected_innings = innings[0]["innings"]

    created = api.post_replays(match_id=selected_match, innings=selected_innings)
    session_id = created["session_id"]

    steps = []
    for _ in range(10):
        prediction = api.post_replay_predict(session_id)
        reveal = api.post_replay_reveal(session_id)
        steps.append(
            {
                "delivery": prediction["delivery"],
                "pre_delivery_state": prediction["pre_delivery_state"],
                "prediction": prediction["prediction"],
                "actual": reveal["actual"],
                "comparison": reveal["comparison"],
            }
        )

    final_state = api.get_replay(session_id)

    report = {
        "runtime_status": database_runtime_status(conn),
        "selected": {
            "season_id": selected_season,
            "match_id": selected_match,
            "innings": selected_innings,
        },
        "session": {
            "session_id": session_id,
            "status": final_state["status"],
            "summary": final_state["summary"],
        },
        "steps": steps,
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    conn.close()


if __name__ == "__main__":
    main()

