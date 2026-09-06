from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import sqlite3
from typing import Any

from .analytics import classify_delivery_outcome
from .chronology import CHRONOLOGY_METHOD, EvaluationWindow, KnowledgeCutoff, ordered_deliveries
from .constants import OUTCOME_LABELS
from .match_state import innings_phase
from .prediction import (
    HIERARCHICAL_CONTEXTS,
    predict_global_baseline_from_counts,
    predict_hierarchical_from_count_map,
    predict_phase_baseline_from_counts,
)


@dataclass
class MetricAccumulator:
    count: int = 0
    log_loss_sum: float = 0.0
    brier_sum: float = 0.0
    top1_hits: int = 0
    top3_hits: int = 0

    def add(self, probabilities: dict[str, float], actual: str) -> None:
        self.count += 1
        p_actual = max(min(probabilities.get(actual, 0.0), 1.0 - 1e-15), 1e-15)
        self.log_loss_sum += -math.log(p_actual)

        brier = 0.0
        for label in OUTCOME_LABELS:
            target = 1.0 if label == actual else 0.0
            brier += (probabilities.get(label, 0.0) - target) ** 2
        self.brier_sum += brier / float(len(OUTCOME_LABELS))

        sorted_labels = sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))
        self.top1_hits += 1 if sorted_labels[0][0] == actual else 0
        top3 = {name for name, _ in sorted_labels[:3]}
        self.top3_hits += 1 if actual in top3 else 0

    def as_metrics(self) -> dict[str, float | int]:
        if self.count == 0:
            return {
                "deliveries": 0,
                "log_loss": 0.0,
                "brier_score": 0.0,
                "top1_accuracy": 0.0,
                "top3_coverage": 0.0,
            }
        return {
            "deliveries": self.count,
            "log_loss": round(self.log_loss_sum / self.count, 6),
            "brier_score": round(self.brier_sum / self.count, 6),
            "top1_accuracy": round(self.top1_hits / self.count, 6),
            "top3_coverage": round(self.top3_hits / self.count, 6),
        }


@dataclass
class HistoryState:
    global_counts: Counter[str]
    phase_counts: dict[str, Counter[str]]
    context_counts: dict[tuple[str, tuple[Any, ...]], Counter[str]]


def _empty_history() -> HistoryState:
    return HistoryState(
        global_counts=Counter(),
        phase_counts={"powerplay": Counter(), "middle": Counter(), "death": Counter()},
        context_counts=defaultdict(Counter),
    )


def _update_history(history: HistoryState, row: sqlite3.Row, outcome: str, phase: str) -> None:
    history.global_counts[outcome] += 1
    history.phase_counts[phase][outcome] += 1

    for level_name, _, fields in HIERARCHICAL_CONTEXTS:
        context_key = tuple(row[field] for field in fields)
        history.context_counts[(level_name, context_key)][outcome] += 1


def _predict_all_models(history: HistoryState, row: sqlite3.Row, phase: str) -> dict[str, dict[str, Any]]:
    global_pred = predict_global_baseline_from_counts(history.global_counts)

    selected_phase_counts = history.phase_counts.get(phase, Counter())
    if sum(selected_phase_counts.values()) == 0:
        selected_phase_counts = history.global_counts
    phase_pred = predict_phase_baseline_from_counts(selected_phase_counts, phase)

    hierarchical_pred = predict_hierarchical_from_count_map(
        {
            "batter": row["batter"],
            "bowler": row["bowler"],
            "batsman_type": row["batsman_type"],
            "bowler_type": row["bowler_type"],
        },
        history.context_counts,
        history.global_counts,
    )

    return {
        "global": global_pred,
        "phase": phase_pred,
        "matchgenome_hierarchical": hierarchical_pred,
    }


def evaluate_temporal_models(
    conn: sqlite3.Connection,
    knowledge_cutoff: KnowledgeCutoff,
    evaluation_window: EvaluationWindow,
    max_deliveries: int | None = None,
) -> dict[str, Any]:
    rows = ordered_deliveries(conn)

    history = _empty_history()
    eval_rows: list[sqlite3.Row] = []

    for row in rows:
        row_phase = innings_phase(int(row["legal_balls_before"]))
        outcome = classify_delivery_outcome(row)
        season_id = int(row["season_id"])

        if knowledge_cutoff.allows_season(season_id):
            _update_history(history, row, outcome, row_phase)
            continue

        if season_id == evaluation_window.season_id:
            eval_rows.append(row)

    if max_deliveries is not None:
        eval_rows = eval_rows[:max_deliveries]

    model_acc = {
        "global": MetricAccumulator(),
        "phase": MetricAccumulator(),
        "matchgenome_hierarchical": MetricAccumulator(),
    }
    phase_acc = {
        model: {"powerplay": MetricAccumulator(), "middle": MetricAccumulator(), "death": MetricAccumulator()}
        for model in model_acc
    }
    outcome_acc = {
        model: {label: MetricAccumulator() for label in OUTCOME_LABELS}
        for model in model_acc
    }
    evidence_bucket_acc = {
        "matchgenome_hierarchical": {"low": MetricAccumulator(), "medium": MetricAccumulator(), "high": MetricAccumulator()}
    }

    per_delivery_predictions: list[dict[str, Any]] = []

    for row in eval_rows:
        row_phase = innings_phase(int(row["legal_balls_before"]))
        actual_outcome = classify_delivery_outcome(row)
        predictions = _predict_all_models(history, row, row_phase)

        for model_name, payload in predictions.items():
            probs = payload["outcome_probabilities"]
            model_acc[model_name].add(probs, actual_outcome)
            phase_acc[model_name][row_phase].add(probs, actual_outcome)
            outcome_acc[model_name][actual_outcome].add(probs, actual_outcome)

            if model_name == "matchgenome_hierarchical":
                bucket = payload.get("reliability", "low")
                evidence_bucket_acc[model_name][bucket].add(probs, actual_outcome)

        per_delivery_predictions.append(
            {
                "target": {
                    "season_id": int(row["season_id"]),
                    "match_id": int(row["match_id"]),
                    "innings": int(row["innings"]),
                    "over_number": int(row["over_number"]),
                    "ball_number": int(row["ball_number"]),
                },
                "phase": row_phase,
                "actual_outcome": actual_outcome,
                "predictions": {
                    name: {
                        "top": pred["predicted_top_outcome"],
                        "sample_size": pred["evidence_sample_size"],
                        "probabilities": pred["outcome_probabilities"],
                    }
                    for name, pred in predictions.items()
                },
            }
        )

        # Online replay update happens only after prediction is recorded.
        _update_history(history, row, actual_outcome, row_phase)

    return {
        "evaluation_name": f"cutoff_{knowledge_cutoff.season_id_inclusive}_to_{evaluation_window.season_id}",
        "knowledge_cutoff": {
            "season_id_inclusive": knowledge_cutoff.season_id_inclusive,
        },
        "evaluation_period": {
            "season_id": evaluation_window.season_id,
        },
        "chronology_method": CHRONOLOGY_METHOD,
        "deterministic_seed": None,
        "evaluated_deliveries": len(eval_rows),
        "valid_predictions": len(eval_rows),
        "models": {
            model_name: {
                "version": {
                    "global": "baseline_global_v1",
                    "phase": "baseline_phase_v1",
                    "matchgenome_hierarchical": "baseline_hierarchical_v1",
                }[model_name],
                "overall": acc.as_metrics(),
                "phase_breakdown": {phase: phase_acc[model_name][phase].as_metrics() for phase in ("powerplay", "middle", "death")},
                "outcome_breakdown": {label: outcome_acc[model_name][label].as_metrics() for label in OUTCOME_LABELS},
            }
            for model_name, acc in model_acc.items()
        },
        "hierarchical_evidence_breakdown": {
            bucket: evidence_bucket_acc["matchgenome_hierarchical"][bucket].as_metrics()
            for bucket in ("low", "medium", "high")
        },
        "delivery_predictions": per_delivery_predictions,
    }

