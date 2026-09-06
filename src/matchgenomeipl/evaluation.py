from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import sqlite3
import time
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
    top_outcome,
)

BASE_MODELS = ("global", "phase", "matchgenome_hierarchical")
MIXTURE_MODEL = "calibrated_mixture"
TIME_DECAYED_MIXTURE_MODEL = "time_decayed_mixture"


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
    global_last_step: int
    phase_counts: dict[str, Counter[str]]
    phase_last_step: dict[str, int]
    context_counts: dict[tuple[str, tuple[Any, ...]], Counter[str]]
    context_last_step: dict[tuple[str, tuple[Any, ...]], int]
    step: int
    recency_decay: float


@dataclass(frozen=True)
class MixtureTuningConfig:
    validation_season: int | None = None
    grid_step: float = 0.05
    decay_candidates: tuple[float, ...] = (1.0, 0.995)
    include_contribution_scores: bool = False


def recency_weight_for_age(age: int, decay_factor: float) -> float:
    if age < 0:
        raise ValueError("age must be non-negative")
    if not (0.0 < decay_factor <= 1.0):
        raise ValueError("decay_factor must be in (0, 1]")
    return decay_factor ** age


def _empty_history() -> HistoryState:
    return HistoryState(
        global_counts=Counter(),
        global_last_step=0,
        phase_counts={"powerplay": Counter(), "middle": Counter(), "death": Counter()},
        phase_last_step={"powerplay": 0, "middle": 0, "death": 0},
        context_counts=defaultdict(Counter),
        context_last_step={},
        step=0,
        recency_decay=1.0,
    )


def _clone_history(history: HistoryState) -> HistoryState:
    cloned_context: defaultdict[tuple[str, tuple[Any, ...]], Counter[str]] = defaultdict(Counter)
    for key, value in history.context_counts.items():
        cloned_context[key] = Counter(value)
    return HistoryState(
        global_counts=Counter(history.global_counts),
        global_last_step=history.global_last_step,
        phase_counts={k: Counter(v) for k, v in history.phase_counts.items()},
        phase_last_step=dict(history.phase_last_step),
        context_counts=cloned_context,
        context_last_step=dict(history.context_last_step),
        step=history.step,
        recency_decay=history.recency_decay,
    )


def _scaled_counter(counter: Counter[str], factor: float) -> Counter[str]:
    if factor == 1.0:
        return Counter(counter)
    return Counter({k: v * factor for k, v in counter.items() if abs(v * factor) >= 1e-15})


def _counter_to_step(counter: Counter[str], last_step: int, current_step: int, decay_factor: float) -> Counter[str]:
    age = max(0, current_step - last_step)
    return _scaled_counter(counter, recency_weight_for_age(age, decay_factor))


def _update_history(
    history: HistoryState,
    row: sqlite3.Row,
    outcome: str,
    phase: str,
    recency_decay: float = 1.0,
) -> None:
    history.recency_decay = recency_decay
    history.step += 1
    current_step = history.step

    history.global_counts = _counter_to_step(
        history.global_counts,
        history.global_last_step,
        current_step,
        history.recency_decay,
    )
    history.global_last_step = current_step
    history.global_counts[outcome] += 1.0

    history.phase_counts[phase] = _counter_to_step(
        history.phase_counts[phase],
        history.phase_last_step.get(phase, 0),
        current_step,
        history.recency_decay,
    )
    history.phase_last_step[phase] = current_step
    history.phase_counts[phase][outcome] += 1.0

    for level_name, _, fields in HIERARCHICAL_CONTEXTS:
        context_key = tuple(row[field] for field in fields)
        scoped_key = (level_name, context_key)
        last_step = history.context_last_step.get(scoped_key, 0)
        history.context_counts[scoped_key] = _counter_to_step(
            history.context_counts[scoped_key],
            last_step,
            current_step,
            history.recency_decay,
        )
        history.context_last_step[scoped_key] = current_step
        history.context_counts[scoped_key][outcome] += 1.0


def _predict_all_models(history: HistoryState, row: sqlite3.Row, phase: str) -> dict[str, dict[str, Any]]:
    global_counts = _counter_to_step(
        history.global_counts,
        history.global_last_step,
        history.step,
        history.recency_decay,
    )
    global_pred = predict_global_baseline_from_counts(global_counts)

    selected_phase_counts = _counter_to_step(
        history.phase_counts.get(phase, Counter()),
        history.phase_last_step.get(phase, 0),
        history.step,
        history.recency_decay,
    )
    if sum(selected_phase_counts.values()) == 0:
        selected_phase_counts = global_counts
    phase_pred = predict_phase_baseline_from_counts(selected_phase_counts, phase)

    context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]] = {}
    for level_name, _, fields in HIERARCHICAL_CONTEXTS:
        context_key = tuple(row[field] for field in fields)
        scoped_key = (level_name, context_key)
        raw_counter = history.context_counts.get(scoped_key, Counter())
        context_count_map[scoped_key] = _counter_to_step(
            raw_counter,
            history.context_last_step.get(scoped_key, 0),
            history.step,
            history.recency_decay,
        )

    hierarchical_pred = predict_hierarchical_from_count_map(
        {
            "batter": row["batter"],
            "bowler": row["bowler"],
            "batsman_type": row["batsman_type"],
            "bowler_type": row["bowler_type"],
        },
        context_count_map,
        global_counts,
    )

    return {
        "global": global_pred,
        "phase": phase_pred,
        "matchgenome_hierarchical": hierarchical_pred,
    }


def _mix_probabilities(weights: dict[str, float], predictions: dict[str, dict[str, Any]]) -> dict[str, float]:
    mixed = {label: 0.0 for label in OUTCOME_LABELS}
    for model in BASE_MODELS:
        model_probs = predictions[model]["outcome_probabilities"]
        weight = weights.get(model, 0.0)
        for label in OUTCOME_LABELS:
            mixed[label] += weight * model_probs[label]
    total = sum(mixed.values())
    if total > 0:
        for label in OUTCOME_LABELS:
            mixed[label] = round(mixed[label] / total, 6)
    return mixed


def _weight_grid(active_models: tuple[str, ...], step: float) -> list[dict[str, float]]:
    units = int(round(1.0 / step))
    candidates: list[dict[str, float]] = []

    if len(active_models) == 1:
        only = active_models[0]
        candidates.append({
            "global": 1.0 if only == "global" else 0.0,
            "phase": 1.0 if only == "phase" else 0.0,
            "matchgenome_hierarchical": 1.0 if only == "matchgenome_hierarchical" else 0.0,
        })
        return candidates

    if len(active_models) == 2:
        left, right = active_models
        for u in range(units + 1):
            lw = u / units
            rw = 1.0 - lw
            candidate = {"global": 0.0, "phase": 0.0, "matchgenome_hierarchical": 0.0}
            candidate[left] = round(lw, 6)
            candidate[right] = round(rw, 6)
            candidates.append(candidate)
        return candidates

    for g in range(units + 1):
        for p in range(units - g + 1):
            h = units - g - p
            candidates.append(
                {
                    "global": round(g / units, 6),
                    "phase": round(p / units, 6),
                    "matchgenome_hierarchical": round(h / units, 6),
                }
            )
    return candidates


def _rows_split_for_cutoff(
    rows: list[sqlite3.Row],
    knowledge_cutoff: KnowledgeCutoff,
    evaluation_window: EvaluationWindow,
    recency_decay: float = 1.0,
) -> tuple[HistoryState, list[sqlite3.Row]]:
    history = _empty_history()
    history.recency_decay = recency_decay
    eval_rows: list[sqlite3.Row] = []

    for row in rows:
        row_phase = innings_phase(int(row["legal_balls_before"]))
        outcome = classify_delivery_outcome(row)
        season_id = int(row["season_id"])

        if knowledge_cutoff.allows_season(season_id):
            _update_history(history, row, outcome, row_phase, recency_decay=recency_decay)
            continue

        if season_id == evaluation_window.season_id:
            eval_rows.append(row)

    return history, eval_rows


def _evaluate_mixture_on_trace(trace: list[dict[str, Any]], weights: dict[str, float]) -> MetricAccumulator:
    acc = MetricAccumulator()
    for item in trace:
        probs = _mix_probabilities(weights, item["base_predictions"])
        acc.add(probs, item["actual_outcome"])
    return acc


def _tune_weights_from_trace(trace: list[dict[str, Any]], active_models: tuple[str, ...], step: float) -> dict[str, Any]:
    best_weights: dict[str, float] | None = None
    best_primary: tuple[float, float] | None = None
    candidates = _weight_grid(active_models, step)

    label_to_idx = {name: idx for idx, name in enumerate(OUTCOME_LABELS)}
    compact: list[tuple[int, tuple[float, ...], tuple[float, ...], tuple[float, ...]]] = []
    for item in trace:
        actual_idx = label_to_idx[item["actual_outcome"]]
        gp = tuple(item["base_predictions"]["global"]["outcome_probabilities"][label] for label in OUTCOME_LABELS)
        pp = tuple(item["base_predictions"]["phase"]["outcome_probabilities"][label] for label in OUTCOME_LABELS)
        hp = tuple(item["base_predictions"]["matchgenome_hierarchical"]["outcome_probabilities"][label] for label in OUTCOME_LABELS)
        compact.append((actual_idx, gp, pp, hp))

    for weights in candidates:
        wg = float(weights["global"])
        wp = float(weights["phase"])
        wh = float(weights["matchgenome_hierarchical"])
        log_loss_sum = 0.0
        brier_sum = 0.0
        for actual_idx, gp, pp, hp in compact:
            mixed = [wg * gp[i] + wp * pp[i] + wh * hp[i] for i in range(len(OUTCOME_LABELS))]
            p_actual = max(min(mixed[actual_idx], 1.0 - 1e-15), 1e-15)
            log_loss_sum += -math.log(p_actual)

            brier = 0.0
            for idx, p in enumerate(mixed):
                t = 1.0 if idx == actual_idx else 0.0
                brier += (p - t) ** 2
            brier_sum += brier / float(len(OUTCOME_LABELS))

        count = max(1, len(compact))
        mean_log = round(log_loss_sum / count, 6)
        mean_brier = round(brier_sum / count, 6)

        score = (
            mean_log,
            mean_brier,
            -float(weights["phase"]),
            -float(weights["matchgenome_hierarchical"]),
            -float(weights["global"]),
        )
        if best_weights is None or best_primary is None:
            best_weights = weights
            best_primary = (mean_log, mean_brier)
            continue

        best_score = (
            best_primary[0],
            best_primary[1],
            -float(best_weights["phase"]),
            -float(best_weights["matchgenome_hierarchical"]),
            -float(best_weights["global"]),
        )
        if score < best_score:
            best_weights = weights
            best_primary = (mean_log, mean_brier)

    assert best_weights is not None
    best_acc = _evaluate_mixture_on_trace(trace, best_weights)
    return {
        "weights": best_weights,
        "validation_metrics": best_acc.as_metrics(),
        "candidate_count": len(candidates),
        "active_models": list(active_models),
    }


def _online_trace(
    initial_history: HistoryState,
    eval_rows: list[sqlite3.Row],
    recency_decay: float = 1.0,
    clone_history: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    history = _clone_history(initial_history) if clone_history else initial_history
    history.recency_decay = recency_decay

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
    trace: list[dict[str, Any]] = []

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

        trace.append(
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
                "base_predictions": predictions,
            }
        )

        # Online replay update happens only after prediction is recorded.
        _update_history(history, row, actual_outcome, row_phase, recency_decay=recency_decay)

    summary = {
        "model_acc": model_acc,
        "phase_acc": phase_acc,
        "outcome_acc": outcome_acc,
        "evidence_bucket_acc": evidence_bucket_acc,
    }
    return summary, trace


def tune_mixture_weights(
    conn: sqlite3.Connection,
    knowledge_cutoff: KnowledgeCutoff,
    evaluation_window: EvaluationWindow,
    config: MixtureTuningConfig | None = None,
    recency_decay: float = 1.0,
    include_contribution: bool | None = None,
) -> dict[str, Any]:
    tuning_config = config or MixtureTuningConfig()
    validation_season = tuning_config.validation_season or knowledge_cutoff.season_id_inclusive
    if validation_season >= evaluation_window.season_id:
        raise ValueError("validation_season must be strictly before evaluation season")

    rows = ordered_deliveries(conn)
    inner_train_cutoff = KnowledgeCutoff(validation_season - 1)
    inner_eval_window = EvaluationWindow(validation_season)
    initial_history, validation_rows = _rows_split_for_cutoff(
        rows,
        inner_train_cutoff,
        inner_eval_window,
        recency_decay=recency_decay,
    )
    _, validation_trace = _online_trace(initial_history, validation_rows, recency_decay=recency_decay)

    overall_choice = _tune_weights_from_trace(
        validation_trace,
        active_models=("global", "phase", "matchgenome_hierarchical"),
        step=tuning_config.grid_step,
    )

    should_include_contribution = tuning_config.include_contribution_scores if include_contribution is None else include_contribution
    contribution: dict[str, Any] = {}
    if should_include_contribution:
        combinations = {
            "global_only": ("global",),
            "phase_only": ("phase",),
            "hierarchical_only": ("matchgenome_hierarchical",),
            "global_phase": ("global", "phase"),
            "phase_hierarchical": ("phase", "matchgenome_hierarchical"),
            "global_phase_hierarchical": ("global", "phase", "matchgenome_hierarchical"),
        }
        contribution = {
            name: _tune_weights_from_trace(validation_trace, active_models=models, step=tuning_config.grid_step)
            for name, models in combinations.items()
        }

    return {
        "validation_season": validation_season,
        "inner_training_cutoff_season": validation_season - 1,
        "grid_step": tuning_config.grid_step,
        "recency_decay": recency_decay,
        "selected": overall_choice,
        "combination_validation_scores": contribution,
        "validation_trace": validation_trace,
    }


def tune_time_decayed_mixture(
    conn: sqlite3.Connection,
    knowledge_cutoff: KnowledgeCutoff,
    evaluation_window: EvaluationWindow,
    config: MixtureTuningConfig | None = None,
    no_decay_tuning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tuning_config = config or MixtureTuningConfig()
    candidates = tuple(dict.fromkeys(tuning_config.decay_candidates))
    if not candidates:
        raise ValueError("At least one decay candidate is required")

    runs: list[dict[str, Any]] = []
    for decay in candidates:
        if not (0.0 < decay <= 1.0):
            raise ValueError(f"invalid decay candidate: {decay}")
        if decay == 1.0 and no_decay_tuning is not None:
            runs.append(no_decay_tuning)
            continue
        run = tune_mixture_weights(
            conn,
            knowledge_cutoff,
            evaluation_window,
            config=tuning_config,
            recency_decay=decay,
            include_contribution=False,
        )
        runs.append(run)

    def ranking_key(run: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
        metrics = run["selected"]["validation_metrics"]
        weights = run["selected"]["weights"]
        # Tie-break prefers simpler no-decay setting if scores are identical.
        return (
            float(metrics["log_loss"]),
            float(metrics["brier_score"]),
            abs(1.0 - float(run["recency_decay"])),
            -float(weights["phase"]),
            -float(weights["matchgenome_hierarchical"]),
            -float(weights["global"]),
        )

    selected = min(runs, key=ranking_key)
    return {
        "selected": selected,
        "candidates": [
            {
                "recency_decay": run["recency_decay"],
                "weights": run["selected"]["weights"],
                "validation_metrics": run["selected"]["validation_metrics"],
            }
            for run in runs
        ],
    }


def evaluate_temporal_models(
    conn: sqlite3.Connection,
    knowledge_cutoff: KnowledgeCutoff,
    evaluation_window: EvaluationWindow,
    max_deliveries: int | None = None,
    tuning_config: MixtureTuningConfig | None = None,
) -> dict[str, Any]:
    rows = ordered_deliveries(conn)
    history, eval_rows = _rows_split_for_cutoff(rows, knowledge_cutoff, evaluation_window)

    if max_deliveries is not None:
        eval_rows = eval_rows[:max_deliveries]

    tuning_started = time.perf_counter()
    tuning = tune_mixture_weights(
        conn,
        knowledge_cutoff,
        evaluation_window,
        config=tuning_config,
        include_contribution=False,
    )
    tuning_runtime = round(time.perf_counter() - tuning_started, 3)
    selected_weights = tuning["selected"]["weights"]

    decay_tuning_started = time.perf_counter()
    decayed_tuning = tune_time_decayed_mixture(
        conn,
        knowledge_cutoff,
        evaluation_window,
        config=tuning_config,
        no_decay_tuning=tuning,
    )
    decayed_tuning_runtime = round(time.perf_counter() - decay_tuning_started, 3)
    selected_decay = float(decayed_tuning["selected"]["recency_decay"])
    selected_decay_weights = decayed_tuning["selected"]["selected"]["weights"]

    summary, trace = _online_trace(history, eval_rows)
    model_acc = summary["model_acc"]
    phase_acc = summary["phase_acc"]
    outcome_acc = summary["outcome_acc"]
    evidence_bucket_acc = summary["evidence_bucket_acc"]

    mixture_acc = MetricAccumulator()
    mixture_phase_acc = {"powerplay": MetricAccumulator(), "middle": MetricAccumulator(), "death": MetricAccumulator()}
    mixture_outcome_acc = {label: MetricAccumulator() for label in OUTCOME_LABELS}

    decayed_history, decayed_eval_rows = _rows_split_for_cutoff(
        rows,
        knowledge_cutoff,
        evaluation_window,
        recency_decay=selected_decay,
    )
    if max_deliveries is not None:
        decayed_eval_rows = decayed_eval_rows[:max_deliveries]
    time_decayed_mixture_acc = MetricAccumulator()
    time_decayed_mixture_phase_acc = {"powerplay": MetricAccumulator(), "middle": MetricAccumulator(), "death": MetricAccumulator()}
    time_decayed_mixture_outcome_acc = {label: MetricAccumulator() for label in OUTCOME_LABELS}

    per_delivery_predictions: list[dict[str, Any]] = []
    for item in trace:
        mixed_probs = _mix_probabilities(selected_weights, item["base_predictions"])
        mixture_acc.add(mixed_probs, item["actual_outcome"])
        mixture_phase_acc[item["phase"]].add(mixed_probs, item["actual_outcome"])
        mixture_outcome_acc[item["actual_outcome"]].add(mixed_probs, item["actual_outcome"])

        predictions = {
            name: {
                "top": payload["predicted_top_outcome"],
                "sample_size": payload["evidence_sample_size"],
                "probabilities": payload["outcome_probabilities"],
            }
            for name, payload in item["base_predictions"].items()
        }
        predictions[MIXTURE_MODEL] = {
            "top": top_outcome(mixed_probs),
            "sample_size": 0,
            "probabilities": mixed_probs,
        }

        per_delivery_predictions.append(
            {
                "target": item["target"],
                "phase": item["phase"],
                "actual_outcome": item["actual_outcome"],
                "predictions": predictions,
            }
        )

    no_decay_equivalent = (
        abs(selected_decay - 1.0) < 1e-12
        and all(abs(float(selected_decay_weights[k]) - float(selected_weights[k])) < 1e-12 for k in BASE_MODELS)
    )
    if no_decay_equivalent:
        for payload in per_delivery_predictions:
            base_mix_probs = payload["predictions"][MIXTURE_MODEL]["probabilities"]
            actual = payload["actual_outcome"]
            phase_name = payload["phase"]
            time_decayed_mixture_acc.add(base_mix_probs, actual)
            time_decayed_mixture_phase_acc[phase_name].add(base_mix_probs, actual)
            time_decayed_mixture_outcome_acc[actual].add(base_mix_probs, actual)
            payload["predictions"][TIME_DECAYED_MIXTURE_MODEL] = {
                "top": payload["predictions"][MIXTURE_MODEL]["top"],
                "sample_size": 0,
                "probabilities": base_mix_probs,
            }
    else:
        _, decayed_trace = _online_trace(decayed_history, decayed_eval_rows, recency_decay=selected_decay)
        decayed_predictions_by_target = {
            (
                item["target"]["season_id"],
                item["target"]["match_id"],
                item["target"]["innings"],
                item["target"]["over_number"],
                item["target"]["ball_number"],
            ): item
            for item in decayed_trace
        }
        for payload in per_delivery_predictions:
            target = payload["target"]
            key = (target["season_id"], target["match_id"], target["innings"], target["over_number"], target["ball_number"])
            decayed_item = decayed_predictions_by_target[key]
            decayed_probs = _mix_probabilities(selected_decay_weights, decayed_item["base_predictions"])
            actual = payload["actual_outcome"]
            phase_name = payload["phase"]

            time_decayed_mixture_acc.add(decayed_probs, actual)
            time_decayed_mixture_phase_acc[phase_name].add(decayed_probs, actual)
            time_decayed_mixture_outcome_acc[actual].add(decayed_probs, actual)

            payload["predictions"][TIME_DECAYED_MIXTURE_MODEL] = {
                "top": top_outcome(decayed_probs),
                "sample_size": 0,
                "probabilities": decayed_probs,
            }

    phase_overall = model_acc["phase"].as_metrics()
    hier_overall = model_acc["matchgenome_hierarchical"].as_metrics()
    mix_overall = mixture_acc.as_metrics()
    time_decayed_mix_overall = time_decayed_mixture_acc.as_metrics()

    def _delta(new: float, old: float) -> dict[str, float]:
        absolute = round(new - old, 6)
        relative = round((absolute / old) if old else 0.0, 6)
        return {"absolute": absolute, "relative": relative}

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
        "mixture_tuning": {
            "validation_season": tuning["validation_season"],
            "inner_training_cutoff_season": tuning["inner_training_cutoff_season"],
            "grid_step": tuning["grid_step"],
            "selected_weights": selected_weights,
            "validation_metrics": tuning["selected"]["validation_metrics"],
            "candidate_count": tuning["selected"]["candidate_count"],
            "combination_validation_scores": {
                name: {
                    "weights": block["weights"],
                    "validation_metrics": block["validation_metrics"],
                }
                for name, block in tuning["combination_validation_scores"].items()
            },
            "runtime_seconds": tuning_runtime,
        },
        "time_decayed_mixture_tuning": {
            "selected_decay": selected_decay,
            "selected_weights": selected_decay_weights,
            "validation_metrics": decayed_tuning["selected"]["selected"]["validation_metrics"],
            "validation_season": decayed_tuning["selected"]["validation_season"],
            "inner_training_cutoff_season": decayed_tuning["selected"]["inner_training_cutoff_season"],
            "grid_step": decayed_tuning["selected"]["grid_step"],
            "decay_candidates": list((tuning_config or MixtureTuningConfig()).decay_candidates),
            "candidate_summaries": decayed_tuning["candidates"],
            "runtime_seconds": decayed_tuning_runtime,
            "chronology_recency_note": (
                "Recency weighting is chronology-based using delivery order, "
                "not wall-clock date/time."
            ),
        },
        "models_additional": {
            MIXTURE_MODEL: {
                "version": "baseline_mixture_v1",
                "overall": mix_overall,
                "phase_breakdown": {phase: mixture_phase_acc[phase].as_metrics() for phase in ("powerplay", "middle", "death")},
                "outcome_breakdown": {label: mixture_outcome_acc[label].as_metrics() for label in OUTCOME_LABELS},
            },
            TIME_DECAYED_MIXTURE_MODEL: {
                "version": "baseline_time_decayed_mixture_v1",
                "overall": time_decayed_mix_overall,
                "phase_breakdown": {phase: time_decayed_mixture_phase_acc[phase].as_metrics() for phase in ("powerplay", "middle", "death")},
                "outcome_breakdown": {label: time_decayed_mixture_outcome_acc[label].as_metrics() for label in OUTCOME_LABELS},
            },
        },
        "improvement_vs_phase": {
            "log_loss": _delta(mix_overall["log_loss"], phase_overall["log_loss"]),
            "brier_score": _delta(mix_overall["brier_score"], phase_overall["brier_score"]),
            "top1_accuracy": _delta(mix_overall["top1_accuracy"], phase_overall["top1_accuracy"]),
            "top3_coverage": _delta(mix_overall["top3_coverage"], phase_overall["top3_coverage"]),
        },
        "improvement_vs_hierarchical": {
            "log_loss": _delta(mix_overall["log_loss"], hier_overall["log_loss"]),
            "brier_score": _delta(mix_overall["brier_score"], hier_overall["brier_score"]),
            "top1_accuracy": _delta(mix_overall["top1_accuracy"], hier_overall["top1_accuracy"]),
            "top3_coverage": _delta(mix_overall["top3_coverage"], hier_overall["top3_coverage"]),
        },
        "time_decayed_vs_existing_mixture": {
            "log_loss": _delta(time_decayed_mix_overall["log_loss"], mix_overall["log_loss"]),
            "brier_score": _delta(time_decayed_mix_overall["brier_score"], mix_overall["brier_score"]),
            "top1_accuracy": _delta(time_decayed_mix_overall["top1_accuracy"], mix_overall["top1_accuracy"]),
            "top3_coverage": _delta(time_decayed_mix_overall["top3_coverage"], mix_overall["top3_coverage"]),
        },
        "hierarchical_evidence_breakdown": {
            bucket: evidence_bucket_acc["matchgenome_hierarchical"][bucket].as_metrics()
            for bucket in ("low", "medium", "high")
        },
        "delivery_predictions": per_delivery_predictions,
    }

