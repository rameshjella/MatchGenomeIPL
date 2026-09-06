from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .analytics import classify_delivery_outcome
from .constants import OUTCOME_LABELS
from .match_state import get_legal_balls_before_delivery, get_target_delivery, innings_phase


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
        counts[str(row["outcome_label"])] += int(row["deliveries"])
    return counts


def _counts_before_timeline(
    conn: sqlite3.Connection,
    timeline: str,
    where_clause: str = "",
    extra_params: tuple[Any, ...] = (),
) -> Counter[str]:
    sql = (
        """
        SELECT
            CASE
                WHEN is_wicket = 1 THEN 'wicket'
                WHEN total_runs = 0 THEN '0'
                WHEN total_runs = 1 THEN '1'
                WHEN total_runs = 2 THEN '2'
                WHEN total_runs = 4 THEN '4'
                WHEN total_runs = 6 THEN '6'
                ELSE '3+'
            END AS outcome_label,
            COUNT(*) AS deliveries
        FROM deliveries
        WHERE timeline_key < ?
        """
        + where_clause
        + "\nGROUP BY outcome_label"
    )
    return _counts_from_query(conn, sql, (timeline,) + extra_params)


@dataclass(frozen=True)
class PredictionContext:
    target: sqlite3.Row
    target_identity: dict[str, int]
    timeline_key: str
    legal_balls_before: int
    phase: str
    feature_values: dict[str, Any]
    global_counts: Counter[str]
    context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]]


class SequentialPredictionSession:
    def __init__(
        self,
        conn: sqlite3.Connection,
        season_id: int,
        match_id: int,
        innings: int,
        start_over_number: int | None = None,
        start_ball_number: int | None = None,
    ) -> None:
        self.conn = conn
        self.season_id = season_id
        self.match_id = match_id
        self.innings = innings
        self.rows = conn.execute(
            """
            SELECT
                season_id,
                match_id,
                innings,
                over_number,
                ball_number,
                source_row_number,
                team_batting,
                team_bowling,
                batter,
                non_striker,
                bowler,
                batsman_type,
                bowler_type,
                batter_runs,
                extras,
                total_runs,
                is_wicket,
                is_wide_ball,
                is_no_ball,
                is_leg_bye,
                is_bye,
                is_penalty,
                wide_ball_runs,
                no_ball_runs,
                leg_bye_runs,
                bye_runs,
                penalty_runs,
                wicket_kind,
                legal_ball,
                is_super_over,
                timeline_key,
                COALESCE(
                    SUM(total_runs) OVER (
                        PARTITION BY season_id, match_id, innings
                        ORDER BY over_number, ball_number, source_row_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS score_before,
                COALESCE(
                    SUM(is_wicket) OVER (
                        PARTITION BY season_id, match_id, innings
                        ORDER BY over_number, ball_number, source_row_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS wickets_before,
                COALESCE(
                    SUM(legal_ball) OVER (
                        PARTITION BY season_id, match_id, innings
                        ORDER BY over_number, ball_number, source_row_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS legal_balls_before
            FROM deliveries
            WHERE season_id = ? AND match_id = ? AND innings = ?
            ORDER BY over_number, ball_number, source_row_number
            """,
            (season_id, match_id, innings),
        ).fetchall()
        if not self.rows:
            raise ValueError("No deliveries found for replay session")

        self.index = 0
        if start_over_number is not None and start_ball_number is not None:
            found = False
            for idx, row in enumerate(self.rows):
                if int(row["over_number"]) == start_over_number and int(row["ball_number"]) == start_ball_number:
                    self.index = idx
                    found = True
                    break
            if not found:
                raise ValueError("Starting delivery not found in innings")

        self.global_counts: Counter[str] | None = None
        self.context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]] | None = None

    def total_deliveries(self) -> int:
        return len(self.rows)

    def current_delivery_index(self) -> int:
        return self.index

    def remaining_deliveries(self) -> int:
        return max(0, self.total_deliveries() - self.index)

    def current_row(self) -> sqlite3.Row | None:
        if not self.has_next():
            return None
        return self.rows[self.index]

    def current_state(self) -> dict[str, Any]:
        row = self.current_row()
        if row is None:
            if self.rows:
                last = self.rows[-1]
                final_score = int(last["score_before"]) + int(last["total_runs"])
                final_wickets = int(last["wickets_before"]) + int(last["is_wicket"])
                final_legal = int(last["legal_balls_before"]) + int(last["legal_ball"])
            else:
                final_score = 0
                final_wickets = 0
                final_legal = 0
            return {
                "season_id": self.season_id,
                "match_id": self.match_id,
                "innings": self.innings,
                "score_before_delivery": final_score,
                "wickets_before_delivery": final_wickets,
                "legal_balls_before_delivery": final_legal,
                "innings_phase": innings_phase(final_legal),
                "next_delivery": None,
                "remaining_deliveries": 0,
            }

        legal_balls_before = int(row["legal_balls_before"])
        return {
            "season_id": int(row["season_id"]),
            "match_id": int(row["match_id"]),
            "innings": int(row["innings"]),
            "team_batting": row["team_batting"],
            "team_bowling": row["team_bowling"],
            "score_before_delivery": int(row["score_before"]),
            "wickets_before_delivery": int(row["wickets_before"]),
            "legal_balls_before_delivery": legal_balls_before,
            "innings_phase": innings_phase(legal_balls_before),
            "next_delivery": {
                "over_number": int(row["over_number"]),
                "ball_number": int(row["ball_number"]),
                "batter": row["batter"],
                "non_striker": row["non_striker"],
                "bowler": row["bowler"],
            },
            "remaining_deliveries": self.remaining_deliveries(),
        }

    def _initialize_history_for_current(self) -> None:
        row = self.rows[self.index]
        timeline = str(row["timeline_key"])
        self.global_counts = _counts_before_timeline(self.conn, timeline)
        self.context_count_map = {}

        for level_name, _, fields in HIERARCHICAL_CONTEXTS:
            if level_name == "batter_bowler":
                counts = _counts_before_timeline(
                    self.conn,
                    timeline,
                    " AND batter = ? AND bowler = ?",
                    (row["batter"], row["bowler"]),
                )
            elif level_name == "batter_bowler_type":
                counts = _counts_before_timeline(
                    self.conn,
                    timeline,
                    " AND batter = ? AND bowler_type = ?",
                    (row["batter"], row["bowler_type"]),
                )
            elif level_name == "bowler_batter_type":
                counts = _counts_before_timeline(
                    self.conn,
                    timeline,
                    " AND bowler = ? AND batsman_type = ?",
                    (row["bowler"], row["batsman_type"]),
                )
            else:
                counts = _counts_before_timeline(
                    self.conn,
                    timeline,
                    " AND batsman_type = ? AND bowler_type = ?",
                    (row["batsman_type"], row["bowler_type"]),
                )
            key = tuple(row[field] for field in fields)
            self.context_count_map[(level_name, key)] = counts

    def has_next(self) -> bool:
        return self.index < len(self.rows)

    def predict_next(self) -> dict[str, Any]:
        if not self.has_next():
            raise StopIteration("No remaining deliveries in replay session")

        if self.global_counts is None or self.context_count_map is None:
            self._initialize_history_for_current()

        row = self.rows[self.index]
        phase = innings_phase(int(row["legal_balls_before"]))
        feature_values = {
            "batter": row["batter"],
            "bowler": row["bowler"],
            "batsman_type": row["batsman_type"],
            "bowler_type": row["bowler_type"],
        }

        assert self.global_counts is not None
        assert self.context_count_map is not None
        baseline = predict_hierarchical_from_count_map(feature_values, self.context_count_map, self.global_counts)

        probabilities = baseline["outcome_probabilities"]
        top = baseline["predicted_top_outcome"]
        actual = classify_delivery_outcome(row)
        return {
            "target_identity": {
                "season_id": int(row["season_id"]),
                "match_id": int(row["match_id"]),
                "innings": int(row["innings"]),
                "over_number": int(row["over_number"]),
                "ball_number": int(row["ball_number"]),
            },
            "state_identity": {
                "timeline_key": str(row["timeline_key"]),
                "legal_balls_before": int(row["legal_balls_before"]),
                "innings_phase": phase,
            },
            "observed_state": {
                "team_batting": row["team_batting"],
                "team_bowling": row["team_bowling"],
                "over_number": int(row["over_number"]),
                "ball_number": int(row["ball_number"]),
                "striker": row["batter"],
                "non_striker": row["non_striker"],
                "bowler": row["bowler"],
                "score_before_delivery": int(row["score_before"]),
                "wickets_before_delivery": int(row["wickets_before"]),
                "legal_balls_before_delivery": int(row["legal_balls_before"]),
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

    def reveal_current_delivery(self) -> dict[str, Any]:
        row = self.current_row()
        if row is None:
            raise StopIteration("No remaining deliveries in replay session")
        outcome = classify_delivery_outcome(row)
        return {
            "target_identity": {
                "season_id": int(row["season_id"]),
                "match_id": int(row["match_id"]),
                "innings": int(row["innings"]),
                "over_number": int(row["over_number"]),
                "ball_number": int(row["ball_number"]),
                "source_row_number": int(row["source_row_number"]),
            },
            "participants": {
                "batter": row["batter"],
                "non_striker": row["non_striker"],
                "bowler": row["bowler"],
            },
            "delivery_facts": {
                "batter_runs": int(row["batter_runs"]),
                "extras": int(row["extras"]),
                "total_runs": int(row["total_runs"]),
                "is_wicket": int(row["is_wicket"]),
                "wicket_kind": row["wicket_kind"],
                "legal_ball": int(row["legal_ball"]),
                "is_wide_ball": int(row["is_wide_ball"]),
                "is_no_ball": int(row["is_no_ball"]),
                "is_leg_bye": int(row["is_leg_bye"]),
                "is_bye": int(row["is_bye"]),
                "is_penalty": int(row["is_penalty"]),
                "wide_ball_runs": int(row["wide_ball_runs"]),
                "no_ball_runs": int(row["no_ball_runs"]),
                "leg_bye_runs": int(row["leg_bye_runs"]),
                "bye_runs": int(row["bye_runs"]),
                "penalty_runs": int(row["penalty_runs"]),
                "is_super_over": int(row["is_super_over"]),
            },
            "actual_outcome": outcome,
        }

    def advance_with_actual(self) -> None:
        if not self.has_next():
            raise StopIteration("No remaining deliveries in replay session")
        if self.global_counts is None or self.context_count_map is None:
            self._initialize_history_for_current()

        row = self.rows[self.index]
        outcome = classify_delivery_outcome(row)
        assert self.global_counts is not None
        assert self.context_count_map is not None
        context_map = self.context_count_map
        self.global_counts[outcome] += 1
        for level_name, _, fields in HIERARCHICAL_CONTEXTS:
            key = tuple(row[field] for field in fields)
            scoped_key = (level_name, key)
            context_map.setdefault(scoped_key, Counter())
            context_map[scoped_key][outcome] += 1

        self.index += 1

        if self.has_next():
            next_row = self.rows[self.index]
            for level_name, _, fields in HIERARCHICAL_CONTEXTS:
                next_key = tuple(next_row[field] for field in fields)
                context_map.setdefault((level_name, next_key), Counter())

    def predict_and_advance(self) -> dict[str, Any]:
        payload = self.predict_next()
        self.advance_with_actual()
        return payload


def build_prediction_context(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
) -> PredictionContext:
    target = get_target_delivery(conn, season_id, match_id, innings, over_number, ball_number)
    timeline = str(target["timeline_key"])
    legal_balls_before = get_legal_balls_before_delivery(conn, season_id, match_id, innings, over_number, ball_number)
    phase = innings_phase(legal_balls_before)

    global_counts = _counts_before_timeline(conn, timeline)
    context_count_map: dict[tuple[str, tuple[Any, ...]], Counter[str]] = {}
    for level_name, _, fields in HIERARCHICAL_CONTEXTS:
        if level_name == "batter_bowler":
            counts = _counts_before_timeline(
                conn,
                timeline,
                " AND batter = ? AND bowler = ?",
                (target["batter"], target["bowler"]),
            )
        elif level_name == "batter_bowler_type":
            counts = _counts_before_timeline(
                conn,
                timeline,
                " AND batter = ? AND bowler_type = ?",
                (target["batter"], target["bowler_type"]),
            )
        elif level_name == "bowler_batter_type":
            counts = _counts_before_timeline(
                conn,
                timeline,
                " AND bowler = ? AND batsman_type = ?",
                (target["bowler"], target["batsman_type"]),
            )
        else:
            counts = _counts_before_timeline(
                conn,
                timeline,
                " AND batsman_type = ? AND bowler_type = ?",
                (target["batsman_type"], target["bowler_type"]),
            )

        key = tuple(target[field] for field in fields)
        context_count_map[(level_name, key)] = counts

    return PredictionContext(
        target=target,
        target_identity={
            "season_id": int(target["season_id"]),
            "match_id": int(target["match_id"]),
            "innings": int(target["innings"]),
            "over_number": int(target["over_number"]),
            "ball_number": int(target["ball_number"]),
        },
        timeline_key=timeline,
        legal_balls_before=legal_balls_before,
        phase=phase,
        feature_values={
            "batter": target["batter"],
            "bowler": target["bowler"],
            "batsman_type": target["batsman_type"],
            "bowler_type": target["bowler_type"],
        },
        global_counts=global_counts,
        context_count_map=context_count_map,
    )


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
    context = build_prediction_context(conn, season_id, match_id, innings, over_number, ball_number)

    baseline = predict_hierarchical_from_count_map(
        context.feature_values,
        context.context_count_map,
        context.global_counts,
    )

    probabilities = baseline["outcome_probabilities"]
    top = baseline["predicted_top_outcome"]
    actual = classify_delivery_outcome(context.target)

    return {
        "target_identity": context.target_identity,
        "state_identity": {
            "timeline_key": context.timeline_key,
            "legal_balls_before": context.legal_balls_before,
            "innings_phase": context.phase,
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

