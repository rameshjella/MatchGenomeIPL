from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .analytics import classify_delivery_outcome
from .constants import OUTCOME_LABELS
from .match_state import build_pre_delivery_state, get_target_delivery


def _smoothed_probabilities(counts: Counter[str], alpha: float = 1.0) -> dict[str, float]:
    total = float(sum(counts.values()))
    k = float(len(OUTCOME_LABELS))
    return {
        label: round((counts.get(label, 0) + alpha) / (total + alpha * k), 6)
        for label in OUTCOME_LABELS
    }


def _top_outcome(probabilities: dict[str, float]) -> str:
    return sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _counts_from_query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    rows = conn.execute(sql, params).fetchall()
    for row in rows:
        counts[classify_delivery_outcome(row)] += 1
    return counts


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

    # Hierarchical fallback from specific context to broad baseline.
    contexts = [
        (
            "batter_bowler",
            25,
            "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler = ?",
            (timeline, target["batter"], target["bowler"]),
        ),
        (
            "batter_bowler_type",
            35,
            "SELECT * FROM deliveries WHERE timeline_key < ? AND batter = ? AND bowler_type = ?",
            (timeline, target["batter"], target["bowler_type"]),
        ),
        (
            "bowler_batter_type",
            35,
            "SELECT * FROM deliveries WHERE timeline_key < ? AND bowler = ? AND batsman_type = ?",
            (timeline, target["bowler"], target["batsman_type"]),
        ),
        (
            "batter_type_bowler_type",
            100,
            "SELECT * FROM deliveries WHERE timeline_key < ? AND batsman_type = ? AND bowler_type = ?",
            (timeline, target["batsman_type"], target["bowler_type"]),
        ),
        (
            "global",
            0,
            "SELECT * FROM deliveries WHERE timeline_key < ?",
            (timeline,),
        ),
    ]

    chosen_level = "global"
    chosen_counts: Counter[str] = Counter()

    for name, min_samples, sql, params in contexts:
        counts = _counts_from_query(conn, sql, params)

        if sum(counts.values()) >= min_samples:
            chosen_level = name
            chosen_counts = counts
            break

    if not chosen_counts:
        chosen_counts = _counts_from_query(conn, "SELECT * FROM deliveries WHERE timeline_key < ?", (timeline,))
        chosen_level = "global"

    probabilities = _smoothed_probabilities(chosen_counts)
    top = _top_outcome(probabilities)
    actual = classify_delivery_outcome(target)

    sample_size = int(sum(chosen_counts.values()))
    reliability = "low"
    if sample_size >= 100:
        reliability = "high"
    elif sample_size >= 30:
        reliability = "medium"

    return {
        "target_identity": state["target_identity"],
        "state_identity": {
            "timeline_key": target["timeline_key"],
            "legal_balls_before": legal_balls_before,
            "innings_phase": phase,
        },
        "prediction_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": "baseline_hierarchical_v1",
        "chosen_evidence_level": chosen_level,
        "evidence_sample_size": sample_size,
        "reliability": reliability,
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top,
        "actual_outcome": actual,
        "top_prediction_correct": top == actual,
    }

