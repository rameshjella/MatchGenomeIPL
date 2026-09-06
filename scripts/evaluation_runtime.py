from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.chronology import EvaluationWindow, KnowledgeCutoff
from matchgenomeipl.database import connect_db
from matchgenomeipl.evaluation import MixtureTuningConfig, evaluate_temporal_models


def run_split(conn, cutoff: int, evaluation: int) -> dict:
    cfg = MixtureTuningConfig(
        validation_season=cutoff,
        grid_step=0.1,
        decay_candidates=(1.0, 0.995),
        include_contribution_scores=False,
    )

    start = time.perf_counter()
    result = evaluate_temporal_models(
        conn,
        knowledge_cutoff=KnowledgeCutoff(cutoff),
        evaluation_window=EvaluationWindow(evaluation),
        tuning_config=cfg,
    )
    elapsed = time.perf_counter() - start

    return {
        "split": f"{cutoff}->{evaluation}",
        "runtime_seconds": round(elapsed, 3),
        "evaluated_deliveries": result["evaluated_deliveries"],
        "mixture_tuning_seconds": result["mixture_tuning"]["runtime_seconds"],
        "time_decayed_tuning_seconds": result["time_decayed_mixture_tuning"]["runtime_seconds"],
        "selected_decay": result["time_decayed_mixture_tuning"]["selected_decay"],
    }


def main() -> None:
    conn = connect_db(ROOT / "data" / "ipl.sqlite3")
    total_start = time.perf_counter()

    split_2024_2025 = run_split(conn, 2024, 2025)
    split_2023_2024 = run_split(conn, 2023, 2024)

    total_elapsed = time.perf_counter() - total_start
    print(
        json.dumps(
            {
                "split_2024_2025": split_2024_2025,
                "split_2023_2024": split_2023_2024,
                "combined_runtime_seconds": round(total_elapsed, 3),
            },
            indent=2,
            sort_keys=True,
        )
    )
    conn.close()


if __name__ == "__main__":
    main()

