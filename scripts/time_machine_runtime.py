from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db
from matchgenomeipl.time_machine import TimeMachineService


def _select_long_innings(service: TimeMachineService, min_deliveries: int) -> tuple[int, int, int, int]:
    row = service.conn.execute(
        """
        SELECT season_id, match_id, innings, deliveries
        FROM innings_summary
        WHERE deliveries >= ?
        ORDER BY deliveries DESC, season_id, match_id, innings
        LIMIT 1
        """,
        (min_deliveries,),
    ).fetchone()
    if row is None:
        fallback = service.conn.execute(
            """
            SELECT season_id, match_id, innings, deliveries
            FROM innings_summary
            ORDER BY deliveries DESC, season_id, match_id, innings
            LIMIT 1
            """
        ).fetchone()
        if fallback is None:
            raise RuntimeError("No innings available for replay benchmark")
        return int(fallback["season_id"]), int(fallback["match_id"]), int(fallback["innings"]), int(fallback["deliveries"])
    return int(row["season_id"]), int(row["match_id"]), int(row["innings"]), int(row["deliveries"])


def benchmark(service: TimeMachineService, deliveries: int) -> dict:
    season_id, match_id, innings, innings_deliveries = _select_long_innings(service, deliveries)
    steps = min(deliveries, innings_deliveries)

    t0 = time.perf_counter()
    session_state = service.create_replay_session(match_id=match_id, innings=innings)
    init_seconds = time.perf_counter() - t0
    session_id = str(session_state["session_id"])

    t1 = time.perf_counter()
    service.predict_next(session_id)
    first_predict_seconds = time.perf_counter() - t1

    t2 = time.perf_counter()
    service.reveal_next(session_id)
    first_reveal_seconds = time.perf_counter() - t2

    predict_times: list[float] = []
    reveal_times: list[float] = []

    for _ in range(max(0, steps - 1)):
        p0 = time.perf_counter()
        service.predict_next(session_id)
        predict_times.append(time.perf_counter() - p0)

        r0 = time.perf_counter()
        service.reveal_next(session_id)
        reveal_times.append(time.perf_counter() - r0)

    session = service.get_replay_session(session_id)
    return {
        "target": {
            "season_id": season_id,
            "match_id": match_id,
            "innings": innings,
            "innings_deliveries": innings_deliveries,
            "steps_executed": steps,
        },
        "init_seconds": round(init_seconds, 6),
        "first_predict_seconds": round(first_predict_seconds, 6),
        "first_reveal_seconds": round(first_reveal_seconds, 6),
        "predict_avg_seconds": round(statistics.mean(predict_times), 6) if predict_times else 0.0,
        "predict_max_seconds": round(max(predict_times), 6) if predict_times else round(first_predict_seconds, 6),
        "reveal_avg_seconds": round(statistics.mean(reveal_times), 6) if reveal_times else 0.0,
        "reveal_max_seconds": round(max(reveal_times), 6) if reveal_times else round(first_reveal_seconds, 6),
        "summary": session.summary(),
    }


def main() -> None:
    conn = connect_db(ROOT / "data" / "ipl.sqlite3")
    service = TimeMachineService(conn)

    report = {
        "benchmark_10": benchmark(service, 10),
        "benchmark_50": benchmark(service, 50),
        "benchmark_100": benchmark(service, 100),
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    conn.close()


if __name__ == "__main__":
    main()

