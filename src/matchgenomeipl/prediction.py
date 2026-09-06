from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .analytics import classify_delivery_outcome
from .constants import OUTCOME_LABELS
from .match_state import build_pre_delivery_state, get_target_delivery


HIERARCHICAL_CONTEXTS = [
    ("batter_bowler", 25, ("batter", "bowler")),
    ("batter_bowler_type", 35, ("batter", "bowler_type")),
    ("bowler_batter_type", 35, ("bowler", "batsman_type")),
    ("batter_type_bowler_type", 100, ("batsman_type", "bowler_type")),
]


def _smoothed_probabilities(counts: Counter[str], alpha: float = 1.0) -> dict[str, float]:
    total = float(sum(counts.values()))
    k = float(len(OUTCOME_LABELS))
    return {
        label: round((counts.get(label, 0) + alpha) / (total + alpha * k), 6)
        for label in OUTCOME_LABELS
    }


def _top_outcome(probabilities: dict[str, float]) -> str:
    return sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def probabilities_from_counts(counts: Counter[str]) -> dict[str, float]:
    return _smoothed_probabilities(counts)


def top_outcome(probabilities: dict[str, float]) -> str:
    return _top_outcome(probabilities)


def _counts_from_query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    rows = conn.execute(sql, params).fetchall()
    for row in rows:
        counts[classify_delivery_outcome(row)] += 1
    return counts


def predict_global_baseline_from_counts(global_counts: Counter[str]) -> dict[str, Any]:
    probabilities = probabilities_from_counts(global_counts)
    return {
        "model_version": "baseline_global_v1",
        "chosen_evidence_level": "global",
        "evidence_sample_size": int(sum(global_counts.values())),
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top_outcome(probabilities),
    }


def predict_phase_baseline_from_counts(phase_counts: Counter[str], phase: str) -> dict[str, Any]:
    probabilities = probabilities_from_counts(phase_counts)
    return {
        "model_version": "baseline_phase_v1",
        "chosen_evidence_level": f"phase:{phase}",
        "evidence_sample_size": int(sum(phase_counts.values())),
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top_outcome(probabilities),
    }


def predict_hierarchical_from_count_map(
    feature_values: dict[str, Any],
    context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]],
    global_counts: Counter[str],
) -> dict[str, Any]:
    chosen_level = "global"
    chosen_counts: Counter[str] = Counter()

    for level_name, min_samples, fields in HIERARCHICAL_CONTEXTS:
        key = tuple(feature_values.get(field) for field in fields)
        counts = context_count_map.get((level_name, key), Counter())
        if sum(counts.values()) >= min_samples:
            chosen_level = level_name
            chosen_counts = counts
            break

    if not chosen_counts:
        chosen_level = "global"
        chosen_counts = global_counts

    probabilities = probabilities_from_counts(chosen_counts)
    sample_size = int(sum(chosen_counts.values()))
    reliability = "low"
    if sample_size >= 100:
        reliability = "high"
    elif sample_size >= 30:
        reliability = "medium"

    return {
        "model_version": "baseline_hierarchical_v1",
        "chosen_evidence_level": chosen_level,
        "evidence_sample_size": sample_size,
        "reliability": reliability,
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top_outcome(probabilities),
    }


def predict_next_ball_baseline(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
) -> dict[str, Any]:
    target = get_target_delivery(conn, season_id, match_id, innings, over_number, ball_number)
    state = build_pre_delivery_state(conn, season_id, match_id, innings, over_number, ball_number)

    timeline = target["timeline_key"]
    phase = state["observed_state"]["innings_phase"]
    legal_balls_before = state["observed_state"]["legal_balls_before_delivery"]

    global_counts = _counts_from_query(conn, "SELECT * FROM deliveries WHERE timeline_key < ?", (timeline,))
    context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]] = {}
    for level_name, _, fields in HIERARCHICAL_CONTEXTS:
        if level_name == "batter_bowler":
            counts = _counts_from_query(
                conn,
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler = ?",
                (timeline, target["batter"], target["bowler"]),
            )
        elif level_name == "batter_bowler_type":
            counts = _counts_from_query(
                conn,
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler_type = ?",
                (timeline, target["batter"], target["bowler_type"]),
            )
        elif level_name == "bowler_batter_type":
            counts = _counts_from_query(
                conn,
                "SELECT * FROM deliveries WHERE timeline_key < ? AND bowler = ? AND batsman_type = ?",
                (timeline, target["bowler"], target["batsman_type"]),
            )
        else:
            counts = _counts_from_query(
                conn,
                "SELECT * FROM deliveries WHERE timeline_key < ? AND batsman_type = ? AND bowler_type = ?",
                (timeline, target["batsman_type"], target["bowler_type"]),
            )

        key = tuple(target[field] for field in fields)
        context_count_map[(level_name, key)] = counts

    baseline = predict_hierarchical_from_count_map(
        {
            "batter": target["batter"],
            "bowler": target["bowler"],
            "batsman_type": target["batsman_type"],
            "bowler_type": target["bowler_type"],
        },
        context_count_map,
        global_counts,
    )

    probabilities = baseline["outcome_probabilities"]
    top = baseline["predicted_top_outcome"]
    actual = classify_delivery_outcome(target)

    return {
        "target_identity": state["target_identity"],
        "state_identity": {
            "timeline_key": target["timeline_key"],
            "legal_balls_before": legal_balls_before,
            "innings_phase": phase,
        },
        "prediction_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": baseline["model_version"],
        "chosen_evidence_level": baseline["chosen_evidence_level"],
        "evidence_sample_size": baseline["evidence_sample_size"],
        "reliability": baseline["reliability"],
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top,
        "actual_outcome": actual,
        "top_prediction_correct": top == actual,
    }

