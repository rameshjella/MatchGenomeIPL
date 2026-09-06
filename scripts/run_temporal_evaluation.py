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
from matchgenomeipl.database import connect_db, database_runtime_status
from matchgenomeipl.evaluation import MixtureTuningConfig, evaluate_temporal_models
from matchgenomeipl.ingestion import ensure_dataset_ready


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
    tuning_config = MixtureTuningConfig(
        validation_season=cutoff_season,
        grid_step=0.1,
        decay_candidates=(1.0, 0.995),
        include_contribution_scores=False,
    )
    result = evaluate_temporal_models(
        conn,
        knowledge_cutoff=KnowledgeCutoff(cutoff_season),
        evaluation_window=EvaluationWindow(eval_season),
        max_deliveries=max_deliveries,
        tuning_config=tuning_config,
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
            "calibrated_mixture": summarize_model_block(result["models_additional"]["calibrated_mixture"]),
            "time_decayed_mixture": summarize_model_block(result["models_additional"]["time_decayed_mixture"]),
        },
        "phase_breakdown": {
            "global": result["models"]["global"]["phase_breakdown"],
            "phase": result["models"]["phase"]["phase_breakdown"],
            "matchgenome_hierarchical": result["models"]["matchgenome_hierarchical"]["phase_breakdown"],
            "calibrated_mixture": result["models_additional"]["calibrated_mixture"]["phase_breakdown"],
            "time_decayed_mixture": result["models_additional"]["time_decayed_mixture"]["phase_breakdown"],
        },
        "mixture_tuning": result["mixture_tuning"],
        "time_decayed_mixture_tuning": result["time_decayed_mixture_tuning"],
        "improvement_vs_phase": result["improvement_vs_phase"],
        "improvement_vs_hierarchical": result["improvement_vs_hierarchical"],
        "time_decayed_vs_existing_mixture": result["time_decayed_vs_existing_mixture"],
        "hierarchical_evidence_breakdown": result["hierarchical_evidence_breakdown"],
    }


def main() -> None:
    csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
    db_path = ROOT / "data" / "ipl.sqlite3"

    conn = connect_db(db_path)
    ingest_stats = ensure_dataset_ready(conn, csv_path)

    chronology = chronology_diagnostics(conn)
    runtime = database_runtime_status(conn)

    exp_2024_2025 = run_experiment(conn, cutoff_season=2024, eval_season=2025)

    # Secondary split to check stability.
    exp_2023_2024 = run_experiment(conn, cutoff_season=2023, eval_season=2024)

    report = {
        "ingestion": ingest_stats.__dict__,
        "runtime_status": runtime,
        "chronology": chronology,
        "experiments": [exp_2024_2025, exp_2023_2024],
    }

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

