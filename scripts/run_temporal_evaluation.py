from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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


def _delta(candidate: float, baseline: float) -> dict:
    absolute = round(candidate - baseline, 6)
    relative = round((absolute / baseline), 6) if baseline else 0.0
    return {"absolute": absolute, "relative": relative}


def _leakage_audit(conn, cutoff_season: int, eval_season: int) -> dict:
    rows = conn.execute(
        """
        SELECT season_id, timeline_key
        FROM deliveries
        ORDER BY timeline_key
        """
    ).fetchall()
    train = [r for r in rows if int(r["season_id"]) <= cutoff_season]
    eval_rows = [r for r in rows if int(r["season_id"]) == eval_season]
    if not train or not eval_rows:
        return {
            "cutoff_season": cutoff_season,
            "eval_season": eval_season,
            "status": "insufficient_data",
        }
    max_train_timeline = str(train[-1]["timeline_key"])
    min_eval_timeline = str(eval_rows[0]["timeline_key"])
    return {
        "cutoff_season": cutoff_season,
        "eval_season": eval_season,
        "train_rows": len(train),
        "eval_rows": len(eval_rows),
        "max_train_timeline": max_train_timeline,
        "min_eval_timeline": min_eval_timeline,
        "strict_ordering_ok": max_train_timeline < min_eval_timeline,
        "future_season_in_training_rows": int(
            conn.execute("SELECT COUNT(*) FROM deliveries WHERE season_id > ?", (cutoff_season,)).fetchone()[0]
        ),
    }


def _feature_family_deltas(contextual: dict[str, dict], baseline_log_loss: float, baseline_brier: float, baseline_top1: float) -> dict:
    out: dict[str, dict] = {}
    for family, block in contextual.items():
        overall = block.get("overall", {})
        out[family] = {
            "name": block.get("name", family),
            "sample_size": int(overall.get("deliveries", 0)),
            "coverage_ratio": block.get("coverage_ratio", 0.0),
            "log_loss": overall.get("log_loss", 0.0),
            "brier_score": overall.get("brier_score", 0.0),
            "top1_accuracy": overall.get("top1_accuracy", 0.0),
            "top3_coverage": overall.get("top3_coverage", 0.0),
            "delta_vs_baseline": {
                "log_loss": _delta(float(overall.get("log_loss", 0.0)), baseline_log_loss),
                "brier_score": _delta(float(overall.get("brier_score", 0.0)), baseline_brier),
                "top1_accuracy": _delta(float(overall.get("top1_accuracy", 0.0)), baseline_top1),
            },
        }
    return out


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
        "baseline_global": summarize_model_block(result["models"]["global"]),
        "baseline_phase": summarize_model_block(result["models"]["phase"]),
        "baseline_hierarchical": summarize_model_block(result["models"]["matchgenome_hierarchical"]),
        "calibrated_mixture": summarize_model_block(result["models_additional"]["calibrated_mixture"]),
        "contextual_hybrid": {
            "deliveries": contextual_combined.get("deliveries", 0),
            "log_loss": contextual_combined.get("log_loss", 0.0),
            "brier_score": contextual_combined.get("brier_score", 0.0),
            "top1_accuracy": contextual_combined.get("top1_accuracy", 0.0),
            "top3_coverage": contextual_combined.get("top3_coverage", 0.0),
            "calibration": [],
            "sample_size_buckets": {},
        },
    }

    baseline = model_versions["baseline_hierarchical"]
    feature_families = contextual.get("feature_families", {})
    family_deltas = _feature_family_deltas(
        feature_families,
        float(baseline["log_loss"]),
        float(baseline["brier_score"]),
        float(baseline["top1_accuracy"]),
    )

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
        "pressure_breakdown": contextual.get("pressure_breakdown", {}),
        "mixture_tuning": result["mixture_tuning"],
        "time_decayed_mixture_tuning": result["time_decayed_mixture_tuning"],
        "improvement_vs_phase": result["improvement_vs_phase"],
        "improvement_vs_hierarchical": result["improvement_vs_hierarchical"],
        "time_decayed_vs_existing_mixture": result["time_decayed_vs_existing_mixture"],
        "hierarchical_evidence_breakdown": result["hierarchical_evidence_breakdown"],
        "feature_family_candidates": {name: block["overall"] for name, block in contextual.get("candidates", {}).items()},
        "feature_family_az": family_deltas,
        "feature_family_phase_breakdown": {
            name: block.get("phase_breakdown", {}) for name, block in contextual.get("candidates", {}).items()
        },
        "feature_family_runtime_seconds": contextual_elapsed,
        "leakage_audit": _leakage_audit(conn, cutoff_season, eval_season),
    }


def _select_model(experiments: list[dict]) -> dict:
    model_names = ["baseline_global", "baseline_phase", "baseline_hierarchical", "calibrated_mixture", "contextual_hybrid"]
    aggregate: dict[str, dict[str, float]] = {}
    for model in model_names:
        logs: list[float] = []
        briers: list[float] = []
        tops: list[float] = []
        for exp in experiments:
            block = exp["model_versions"][model]
            logs.append(float(block["log_loss"]))
            briers.append(float(block["brier_score"]))
            tops.append(float(block["top1_accuracy"]))
        aggregate[model] = {
            "mean_log_loss": round(sum(logs) / len(logs), 6),
            "mean_brier": round(sum(briers) / len(briers), 6),
            "mean_top1": round(sum(tops) / len(tops), 6),
            "stability_log_loss": round(max(logs) - min(logs), 6),
            "stability_brier": round(max(briers) - min(briers), 6),
        }

    ranked = sorted(
        aggregate.items(),
        key=lambda item: (
            item[1]["mean_log_loss"],
            item[1]["mean_brier"],
            item[1]["stability_log_loss"],
            item[1]["stability_brier"],
            -item[1]["mean_top1"],
            0 if item[0] in {"baseline_global", "baseline_phase", "baseline_hierarchical"} else 1,
        ),
    )
    selected_model = ranked[0][0]
    return {
        "selected_model": selected_model,
        "selection_priority": ["log_loss", "calibration_proxy_brier", "brier", "top1"],
        "aggregate_scores": aggregate,
        "ranking": [name for name, _ in ranked],
    }


def _feature_family_stability(experiments: list[dict]) -> dict:
    by_family: dict[str, list[dict]] = {}
    for exp in experiments:
        for fam, block in exp.get("feature_family_az", {}).items():
            by_family.setdefault(fam, []).append(block)
    out: dict[str, dict] = {}
    for fam, blocks in by_family.items():
        log_deltas = [float(b["delta_vs_baseline"]["log_loss"]["absolute"]) for b in blocks]
        brier_deltas = [float(b["delta_vs_baseline"]["brier_score"]["absolute"]) for b in blocks]
        out[fam] = {
            "name": blocks[0].get("name", fam),
            "windows": len(blocks),
            "mean_delta_log_loss": round(sum(log_deltas) / len(log_deltas), 6),
            "mean_delta_brier": round(sum(brier_deltas) / len(brier_deltas), 6),
            "stable_direction": (all(x <= 0 for x in log_deltas) or all(x >= 0 for x in log_deltas)),
            "log_loss_delta_range": round(max(log_deltas) - min(log_deltas), 6),
        }
    return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strict temporal IPL prediction evaluation")
    parser.add_argument("--max-deliveries", type=int, default=None, help="Optional cap for faster diagnostic runs")
    parser.add_argument("--output", type=str, default="", help="Optional output artifact path")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
    db_path = ROOT / "data" / "ipl.sqlite3"

    conn = connect_db(db_path)
    ingest_stats = ensure_dataset_ready(conn, csv_path)

    chronology = chronology_diagnostics(conn)
    runtime = database_runtime_status(conn)

    exp_2024_2025 = run_experiment(conn, cutoff_season=2024, eval_season=2025, max_deliveries=args.max_deliveries)

    # Secondary split to check stability.
    exp_2023_2024 = run_experiment(conn, cutoff_season=2023, eval_season=2024, max_deliveries=args.max_deliveries)

    experiments = [exp_2024_2025, exp_2023_2024]
    report = {
        "ingestion": ingest_stats.__dict__,
        "runtime_status": runtime,
        "chronology": chronology,
        "baseline_freeze": {
            "control_models": ["baseline_global", "baseline_phase", "baseline_hierarchical", "calibrated_mixture", "contextual_hybrid"],
            "selection_rule": "Prefer lower log_loss and brier; require calibration and latency sanity; keep simpler model when equivalent.",
            "generated_at_unix": int(time.time()),
        },
        "experiments": experiments,
        "feature_family_stability": _feature_family_stability(experiments),
        "model_selection": _select_model(experiments),
    }

    artifact_dir = ROOT / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = Path(args.output) if args.output else (artifact_dir / "temporal_eval_current.json")
    archive_path = artifact_dir / f"temporal_eval_{timestamp}.json"
    artifact_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    archive_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved artifact: {artifact_path}")
    print(f"Saved artifact archive: {archive_path}")


if __name__ == "__main__":
    main()

