from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.analytics import batter_stats, bowler_stats, dataset_summary, runs_wickets_by_over
from matchgenomeipl.database import connect_db, database_runtime_status
from matchgenomeipl.ingestion import ensure_dataset_ready
from matchgenomeipl.match_state import build_pre_delivery_state
from matchgenomeipl.prediction import predict_next_ball_baseline


def select_target_delivery(conn: sqlite3.Connection) -> tuple[int, int, int, int, int]:
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
    return (int(row["season_id"]), int(row["match_id"]), int(row["innings"]), int(row["over_number"]), int(row["ball_number"]))


def main() -> None:
    csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
    db_path = ROOT / "data" / "ipl.sqlite3"

    conn = connect_db(db_path)
    stats = ensure_dataset_ready(conn, csv_path)
    runtime = database_runtime_status(conn)

    summary = dataset_summary(conn)

    season_id, match_id, innings, over_number, ball_number = select_target_delivery(conn)
    state = build_pre_delivery_state(conn, season_id, match_id, innings, over_number, ball_number)
    prediction = predict_next_ball_baseline(conn, season_id, match_id, innings, over_number, ball_number)

    batter_name = state["observed_state"]["striker"]
    bowler_name = state["observed_state"]["bowler"]
    batter = batter_stats(conn, batter_name)
    bowler = bowler_stats(conn, bowler_name)
    over_split = runs_wickets_by_over(conn, season_id, match_id, innings)[:5]

    report = {
        "ingestion_stats": stats.__dict__,
        "runtime_status": runtime,
        "dataset_summary": summary,
        "example_target": {
            "season_id": season_id,
            "match_id": match_id,
            "innings": innings,
            "over_number": over_number,
            "ball_number": ball_number,
        },
        "pre_delivery_state": state,
        "prediction": prediction,
        "analytics_examples": {
            "batter": batter,
            "bowler": bowler,
            "first_five_over_splits": over_split,
        },
    }

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

