from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.chronology import EvaluationWindow, KnowledgeCutoff, chronology_diagnostics
from matchgenomeipl.database import connect_db
from matchgenomeipl.evaluation import evaluate_temporal_models
from matchgenomeipl.ingestion import ingest_csv_to_sqlite


def summarize_model_block(block: dict) -> dict:
    overall = block["overall"]
    return {
        "deliveries": overall["deliveries"],
        "log_loss": overall["log_loss"],
        "brier_score": overall["brier_score"],
        "top1_accuracy": overall["top1_accuracy"],
        "top3_coverage": overall["top3_coverage"],
    }


def run_experiment(conn, cutoff_season: int, eval_season: int, max_deliveries: int | None = None) -> dict:
    started = time.perf_counter()
    result = evaluate_temporal_models(
        conn,
        knowledge_cutoff=KnowledgeCutoff(cutoff_season),
        evaluation_window=EvaluationWindow(eval_season),
        max_deliveries=max_deliveries,
    )
    elapsed = round(time.perf_counter() - started, 3)

    return {
        "name": result["evaluation_name"],
        "knowledge_cutoff": result["knowledge_cutoff"],
        "evaluation_period": result["evaluation_period"],
        "chronology_method": result["chronology_method"],
        "evaluated_deliveries": result["evaluated_deliveries"],
        "runtime_seconds": elapsed,
        "models": {
            "global": summarize_model_block(result["models"]["global"]),
            "phase": summarize_model_block(result["models"]["phase"]),
            "matchgenome_hierarchical": summarize_model_block(result["models"]["matchgenome_hierarchical"]),
        },
        "phase_breakdown": {
            model_name: result["models"][model_name]["phase_breakdown"]
            for model_name in ("global", "phase", "matchgenome_hierarchical")
        },
        "hierarchical_evidence_breakdown": result["hierarchical_evidence_breakdown"],
    }


def main() -> None:
    csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
    db_path = ROOT / "data" / "ipl.sqlite3"

    conn = connect_db(db_path)
    ingest_stats = ingest_csv_to_sqlite(conn, csv_path)

    chronology = chronology_diagnostics(conn)

    exp_2024_2025 = run_experiment(conn, cutoff_season=2024, eval_season=2025)

    # Secondary split to check stability.
    exp_2023_2024 = run_experiment(conn, cutoff_season=2023, eval_season=2024)

    report = {
        "ingestion": ingest_stats.__dict__,
        "chronology": chronology,
        "experiments": [exp_2024_2025, exp_2023_2024],
    }

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

