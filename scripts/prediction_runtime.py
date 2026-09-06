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
from matchgenomeipl.match_state import build_pre_delivery_state
from matchgenomeipl.prediction import (
    SequentialPredictionSession,
    build_prediction_context,
    predict_hierarchical_from_count_map,
    predict_next_ball_baseline,
)


def select_target_delivery(conn) -> tuple[int, int, int, int, int]:
    total = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
    offset = max(1, total // 2)
    row = conn.execute(
        """
        SELECT season_id, match_id, innings, over_number, ball_number
        FROM deliveries
        ORDER BY timeline_key
        LIMIT 1 OFFSET ?
        """,
        (offset,),
    ).fetchone()
    return (
        int(row["season_id"]),
        int(row["match_id"]),
        int(row["innings"]),
        int(row["over_number"]),
        int(row["ball_number"]),
    )


def benchmark_single_prediction(conn, target: tuple[int, int, int, int, int], repeats: int = 5) -> dict:
    season_id, match_id, innings, over_number, ball_number = target

    state_times: list[float] = []
    evidence_times: list[float] = []
    calc_times: list[float] = []
    total_times: list[float] = []

    for _ in range(repeats):
        t0 = time.perf_counter()
        _ = build_pre_delivery_state(conn, season_id, match_id, innings, over_number, ball_number)
        t1 = time.perf_counter()

        context = build_prediction_context(conn, season_id, match_id, innings, over_number, ball_number)
        t2 = time.perf_counter()

        baseline = predict_hierarchical_from_count_map(
            context.feature_values,
            context.context_count_map,
            context.global_counts,
        )
        t3 = time.perf_counter()

        _ = predict_next_ball_baseline(conn, season_id, match_id, innings, over_number, ball_number)
        t4 = time.perf_counter()

        state_times.append(t1 - t0)
        evidence_times.append(t2 - t1)
        calc_times.append(t3 - t2)
        total_times.append(t4 - t3)

    return {
        "target": {
            "season_id": season_id,
            "match_id": match_id,
            "innings": innings,
            "over_number": over_number,
            "ball_number": ball_number,
        },
        "state_retrieval_seconds": round(statistics.mean(state_times), 6),
        "evidence_retrieval_seconds": round(statistics.mean(evidence_times), 6),
        "prediction_calculation_seconds": round(statistics.mean(calc_times), 6),
        "prediction_total_seconds": round(statistics.mean(total_times), 6),
        "prediction_total_seconds_min": round(min(total_times), 6),
        "prediction_total_seconds_max": round(max(total_times), 6),
    }


def benchmark_replay(conn, max_deliveries: int) -> dict:
    max_innings_deliveries = int(
        conn.execute("SELECT COALESCE(MAX(c), 0) AS max_c FROM (SELECT COUNT(*) AS c FROM deliveries GROUP BY season_id, match_id, innings)").fetchone()["max_c"]
    )
    target_deliveries = min(max_deliveries, max_innings_deliveries)
    if target_deliveries <= 0:
        raise RuntimeError("No deliveries found for replay benchmark")

    row = conn.execute(
        """
        SELECT season_id, match_id, innings, COUNT(*) AS n
        FROM deliveries
        GROUP BY season_id, match_id, innings
        HAVING COUNT(*) >= ?
        ORDER BY season_id, match_id, innings
        LIMIT 1
        """,
        (target_deliveries,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No innings has at least {target_deliveries} deliveries")

    session = SequentialPredictionSession(conn, int(row["season_id"]), int(row["match_id"]), int(row["innings"]))

    per_delivery: list[float] = []
    started = time.perf_counter()
    for _ in range(target_deliveries):
        t0 = time.perf_counter()
        session.predict_and_advance()
        per_delivery.append(time.perf_counter() - t0)
    elapsed = time.perf_counter() - started

    return {
        "target_innings": {
            "season_id": int(row["season_id"]),
            "match_id": int(row["match_id"]),
            "innings": int(row["innings"]),
        },
        "deliveries": target_deliveries,
        "requested_deliveries": max_deliveries,
        "total_seconds": round(elapsed, 6),
        "first_prediction_seconds": round(per_delivery[0], 6),
        "steady_state_avg_seconds": round(statistics.mean(per_delivery[1:]), 6) if len(per_delivery) > 1 else round(per_delivery[0], 6),
        "avg_seconds": round(statistics.mean(per_delivery), 6),
        "median_seconds": round(statistics.median(per_delivery), 6),
        "max_seconds": round(max(per_delivery), 6),
    }


def main() -> None:
    conn = connect_db(ROOT / "data" / "ipl.sqlite3")

    single = benchmark_single_prediction(conn, select_target_delivery(conn), repeats=5)
    replay_100 = benchmark_replay(conn, 100)
    replay_500 = benchmark_replay(conn, 500)

    print(
        json.dumps(
            {
                "single_prediction": single,
                "replay_100": replay_100,
                "replay_500": replay_500,
            },
            indent=2,
            sort_keys=True,
        )
    )

    conn.close()


if __name__ == "__main__":
    main()


