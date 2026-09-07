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
from matchgenomeipl.evaluation import MixtureTuningConfig, evaluate_contextual_candidates, evaluate_temporal_models
from matchgenomeipl.ingestion import ensure_dataset_ready


def summarize_model_block(block: dict) -> dict:
    overall = block["overall"]
    return {
        "deliveries": overall["deliveries"],
        "log_loss": overall["log_loss"],
        "brier_score": overall["brier_score"],
        "top1_accuracy": overall["top1_accuracy"],
        "top3_coverage": overall["top3_coverage"],
        "calibration": block.get("calibration", []),
        "sample_size_buckets": block.get("sample_size_buckets", {}),
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

    contextual_started = time.perf_counter()
    contextual = evaluate_contextual_candidates(
        conn,
        knowledge_cutoff=KnowledgeCutoff(cutoff_season),
        evaluation_window=EvaluationWindow(eval_season),
        max_deliveries=max_deliveries,
    )
    contextual_elapsed = round(time.perf_counter() - contextual_started, 3)

    contextual_combined = contextual.get("candidates", {}).get("combined_context", {}).get("overall", {})
    model_versions = {
        "baseline_hierarchical_v1": summarize_model_block(result["models"]["matchgenome_hierarchical"]),
        "calibrated_mixture": summarize_model_block(result["models_additional"]["calibrated_mixture"]),
        "time_decayed_mixture": summarize_model_block(result["models_additional"]["time_decayed_mixture"]),
        "contextual_hybrid_v1": {
            "deliveries": contextual_combined.get("deliveries", 0),
            "log_loss": contextual_combined.get("log_loss", 0.0),
            "brier_score": contextual_combined.get("brier_score", 0.0),
            "top1_accuracy": contextual_combined.get("top1_accuracy", 0.0),
            "top3_coverage": contextual_combined.get("top3_coverage", 0.0),
            "calibration": [],
            "sample_size_buckets": {},
        },
    }

    return {
        "name": result["evaluation_name"],
        "knowledge_cutoff": result["knowledge_cutoff"],
        "evaluation_period": result["evaluation_period"],
        "chronology_method": result["chronology_method"],
        "evaluated_deliveries": result["evaluated_deliveries"],
        "runtime_seconds": elapsed,
        "prediction_latency": result.get("prediction_latency", {}),
        "model_versions": model_versions,
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
        "feature_family_candidates": {
            name: block["overall"] for name, block in contextual.get("candidates", {}).items()
        },
        "feature_family_phase_breakdown": {
            name: block.get("phase_breakdown", {}) for name, block in contextual.get("candidates", {}).items()
        },
        "feature_family_runtime_seconds": contextual_elapsed,
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
        "baseline_freeze": {
            "control_models": ["baseline_hierarchical_v1", "calibrated_mixture", "time_decayed_mixture", "contextual_hybrid_v1"],
            "selection_rule": "Prefer lower log_loss and brier; require calibration and latency sanity; keep simpler model when equivalent.",
            "generated_at_unix": int(time.time()),
        },
        "experiments": [exp_2024_2025, exp_2023_2024],
    }

    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "temporal_eval_current.json"
    artifact_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved artifact: {artifact_path}")


if __name__ == "__main__":
    main()

