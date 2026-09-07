from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any

from .analytics import classify_delivery_outcome
from .constants import OUTCOME_LABELS
from .match_state import get_legal_balls_before_delivery, get_target_delivery, innings_phase
from .runtime_logging import log_sql


HIERARCHICAL_CONTEXTS = [
    ("batter_bowler", 25, ("batter", "bowler")),
    ("batter_bowler_type", 35, ("batter", "bowler_type")),
    ("bowler_batter_type", 35, ("bowler", "batsman_type")),
    ("batter_type_bowler_type", 100, ("batsman_type", "bowler_type")),
]

DEFAULT_RUNTIME_MODEL_VERSION = "contextual_hybrid_v1"
DEFAULT_FEATURE_VERSION = "context_features_v1"
DEFAULT_EVIDENCE_VERSION = "evidence_contract_v1"


def _smoothed_probabilities(counts: Counter[str], alpha: float = 1.0) -> dict[str, float]:
    total = float(sum(counts.values()))
    k = float(len(OUTCOME_LABELS))
    return {
        label: round((counts.get(label, 0) + alpha) / (total + alpha * k), 6)
        for label in OUTCOME_LABELS
    }


def _top_outcome(probabilities: dict[str, float]) -> str:
    return sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _outcome_case_sql() -> str:
    return (
        "CASE "
        "WHEN is_wicket = 1 THEN 'wicket' "
        "WHEN total_runs = 0 THEN '0' "
        "WHEN total_runs = 1 THEN '1' "
        "WHEN total_runs = 2 THEN '2' "
        "WHEN total_runs = 4 THEN '4' "
        "WHEN total_runs = 6 THEN '6' "
        "ELSE '3+' END"
    )


def _phase_over_clause(phase: str) -> str:
    if phase == "powerplay":
        return "over_number < 6"
    if phase == "middle":
        return "over_number BETWEEN 6 AND 14"
    return "over_number >= 15"


def probabilities_from_counts(counts: Counter[str]) -> dict[str, float]:
    return _smoothed_probabilities(counts)


def top_outcome(probabilities: dict[str, float]) -> str:
    return _top_outcome(probabilities)


def _counts_from_query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Counter[str]:
    started = time.perf_counter()
    counts: Counter[str] = Counter()
    rows = conn.execute(sql, params).fetchall()
    log_sql("prediction_counts", sql, params, started, row_count=len(rows))
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
    contextual_features: dict[str, Any]


def _counter_to_probability_payload(counts: Counter[str], alpha: float = 1.0) -> dict[str, Any]:
    sample_size = int(sum(counts.values()))
    return {
        "sample_size": sample_size,
        "outcome_probabilities": _smoothed_probabilities(counts, alpha=alpha),
    }


def _normalize_probabilities(raw: dict[str, float]) -> dict[str, float]:
    total = sum(raw.values())
    if total <= 0.0:
        uniform = round(1.0 / float(len(OUTCOME_LABELS)), 6)
        return {label: uniform for label in OUTCOME_LABELS}
    normalized = {label: round(raw.get(label, 0.0) / total, 6) for label in OUTCOME_LABELS}
    residue = round(1.0 - sum(normalized.values()), 6)
    if residue != 0.0:
        best = _top_outcome(normalized)
        normalized[best] = round(normalized[best] + residue, 6)
    return normalized


def _weighted_blend(
    components: list[tuple[str, dict[str, float], float]],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    filtered = [(name, probs, weight) for name, probs, weight in components if weight > 0.0]
    if not filtered:
        return _normalize_probabilities({label: 1.0 for label in OUTCOME_LABELS}), []

    weight_total = sum(weight for _, _, weight in filtered)
    blended = {label: 0.0 for label in OUTCOME_LABELS}
    contribution: list[dict[str, Any]] = []
    for name, probs, raw_weight in filtered:
        normalized_weight = raw_weight / weight_total
        contribution.append({"source": name, "weight": round(normalized_weight, 6)})
        for label in OUTCOME_LABELS:
            blended[label] += normalized_weight * probs[label]
    return _normalize_probabilities(blended), contribution


def _compute_reliability(sample_size: int) -> str:
    if sample_size >= 180:
        return "high"
    if sample_size >= 60:
        return "medium"
    if sample_size >= 20:
        return "low"
    return "small"


def _bucket_wickets(wickets_before: int) -> str:
    if wickets_before <= 2:
        return "0-2"
    if wickets_before <= 5:
        return "3-5"
    return "6+"


def _bucket_over_window(legal_balls_before: int) -> str:
    over_index = max(0, legal_balls_before // 6)
    low = (over_index // 3) * 3
    high = low + 2
    return f"{low}-{high}"


def _compute_rr(score: int, legal_balls: int) -> float:
    return round((score / (legal_balls / 6.0)), 2) if legal_balls else 0.0


def _sample_reliability(sample_size: int) -> str:
    if sample_size >= 1200:
        return "high"
    if sample_size >= 250:
        return "medium"
    if sample_size >= 40:
        return "low"
    return "small"


def _venue_evidence_tier(sample_size: int) -> str:
    if sample_size >= 2500:
        return "strong"
    if sample_size >= 600:
        return "moderate"
    if sample_size >= 120:
        return "weak"
    return "fallback"


def _fetch_outcome_counts(
    conn: sqlite3.Connection,
    timeline: str,
    where_clause: str = "",
    params: tuple[Any, ...] = (),
) -> Counter[str]:
    sql = (
        f"""
        SELECT {_outcome_case_sql()} AS outcome_label, COUNT(*) AS deliveries
        FROM deliveries
        WHERE timeline_key < ?
        """
        + where_clause
        + "\nGROUP BY outcome_label"
    )
    return _counts_from_query(conn, sql, (timeline,) + params)


def _fetch_recent_outcomes(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
    limit: int = 6,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT *
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND (over_number < ? OR (over_number = ? AND ball_number < ?))
        ORDER BY over_number DESC, ball_number DESC, source_row_number DESC
        LIMIT ?
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number, limit),
    ).fetchall()
    return [classify_delivery_outcome(row) for row in reversed(rows)]


def _fetch_player_recent_match_form(
    conn: sqlite3.Connection,
    timeline: str,
    player: str,
    role: str,
    n_matches: int = 3,
) -> dict[str, Any]:
    selector = "batter" if role == "batter" else "bowler"
    matches = conn.execute(
        f"""
        SELECT season_id, match_id
        FROM deliveries
        WHERE timeline_key < ? AND {selector} = ?
        GROUP BY season_id, match_id
        ORDER BY season_id DESC, match_id DESC
        LIMIT ?
        """,
        (timeline, player, n_matches),
    ).fetchall()
    if not matches:
        return {
            "matches": 0,
            "runs": 0,
            "balls": 0,
            "boundaries": 0,
            "dismissals": 0,
            "wickets": 0,
            "strike_rate": 0.0,
            "economy": 0.0,
        }

    runs = 0
    balls = 0
    boundaries = 0
    dismissals = 0
    wickets = 0
    for match in matches:
        season_id = int(match["season_id"])
        match_id = int(match["match_id"])
        if role == "batter":
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(batter_runs), 0) AS runs,
                    COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls,
                    COALESCE(SUM(CASE WHEN batter_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries,
                    COALESCE(SUM(CASE WHEN is_wicket = 1 AND player_out = ? THEN 1 ELSE 0 END), 0) AS dismissals
                FROM deliveries
                WHERE season_id = ? AND match_id = ? AND batter = ?
                """,
                (player, season_id, match_id, player),
            ).fetchone()
            runs += int(row["runs"])
            balls += int(row["balls"])
            boundaries += int(row["boundaries"])
            dismissals += int(row["dismissals"])
        else:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs,
                    COALESCE(SUM(legal_ball), 0) AS balls,
                    COALESCE(SUM(CASE WHEN total_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries,
                    COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets
                FROM deliveries
                WHERE season_id = ? AND match_id = ? AND bowler = ?
                """,
                (season_id, match_id, player),
            ).fetchone()
            runs += int(row["runs"])
            balls += int(row["balls"])
            boundaries += int(row["boundaries"])
            wickets += int(row["wickets"])

    strike_rate = round((runs * 100.0 / balls), 2) if balls else 0.0
    economy = round((runs / (balls / 6.0)), 2) if balls else 0.0
    return {
        "matches": len(matches),
        "runs": runs,
        "balls": balls,
        "boundaries": boundaries,
        "dismissals": dismissals,
        "wickets": wickets,
        "strike_rate": strike_rate,
        "economy": economy,
    }


def _collect_contextual_features(conn: sqlite3.Connection, target: sqlite3.Row, timeline: str, phase: str) -> dict[str, Any]:
    batter = str(target["batter"])
    bowler = str(target["bowler"])
    season_id = int(target["season_id"])
    match_id = int(target["match_id"])
    innings = int(target["innings"])
    over_number = int(target["over_number"])
    ball_number = int(target["ball_number"])

    batter_hist = conn.execute(
        """
        SELECT
            COALESCE(SUM(batter_runs), 0) AS runs,
            COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls,
            COALESCE(SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END), 0) AS fours,
            COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes,
            COALESCE(SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS dots,
            COALESCE(SUM(CASE WHEN is_wicket = 1 AND player_out = ? THEN 1 ELSE 0 END), 0) AS dismissals
        FROM deliveries
        WHERE timeline_key < ? AND batter = ?
        """,
        (batter, timeline, batter),
    ).fetchone()
    bowler_hist = conn.execute(
        """
        SELECT
            COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs_conceded,
            COALESCE(SUM(legal_ball), 0) AS legal_balls,
            COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets,
            COALESCE(SUM(CASE WHEN total_runs = 0 THEN 1 ELSE 0 END), 0) AS dots,
            COALESCE(SUM(CASE WHEN total_runs = 4 THEN 1 ELSE 0 END), 0) AS fours_conceded,
            COALESCE(SUM(CASE WHEN total_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes_conceded
        FROM deliveries
        WHERE timeline_key < ? AND bowler = ?
        """,
        (timeline, bowler),
    ).fetchone()

    innings_state = conn.execute(
        """
        SELECT
            COALESCE(SUM(total_runs), 0) AS score_before,
            COALESCE(SUM(is_wicket), 0) AS wickets_before,
            COALESCE(SUM(legal_ball), 0) AS legal_balls_before
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ?
          AND (over_number < ? OR (over_number = ? AND ball_number < ?))
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number),
    ).fetchone()

    striker_innings = conn.execute(
        """
        SELECT
            COALESCE(SUM(batter_runs), 0) AS runs,
            COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls,
            COALESCE(SUM(CASE WHEN batter_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ? AND batter = ?
          AND (over_number < ? OR (over_number = ? AND ball_number < ?))
        """,
        (season_id, match_id, innings, batter, over_number, over_number, ball_number),
    ).fetchone()

    bowler_innings = conn.execute(
        """
        SELECT
            COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs,
            COALESCE(SUM(legal_ball), 0) AS balls,
            COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets,
            COALESCE(SUM(CASE WHEN total_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries
        FROM deliveries
        WHERE season_id = ? AND match_id = ? AND innings = ? AND bowler = ?
          AND (over_number < ? OR (over_number = ? AND ball_number < ?))
        """,
        (season_id, match_id, innings, bowler, over_number, over_number, ball_number),
    ).fetchone()

    legal_balls_before = int(innings_state["legal_balls_before"])
    score_before = int(innings_state["score_before"])
    wickets_before = int(innings_state["wickets_before"])
    current_run_rate = round((score_before / (legal_balls_before / 6.0)), 2) if legal_balls_before else 0.0
    target_runs = None
    required_run_rate = None
    if innings == 2:
        first_innings = conn.execute(
            """
            SELECT runs
            FROM innings_summary
            WHERE season_id = ? AND match_id = ? AND innings = 1
            """,
            (season_id, match_id),
        ).fetchone()
        if first_innings is not None:
            target_runs = int(first_innings["runs"]) + 1
            remaining_runs = max(0, target_runs - score_before)
            remaining_balls = max(1, 120 - legal_balls_before)
            required_run_rate = round((remaining_runs * 6.0) / remaining_balls, 2)

    recent_window = conn.execute(
        """
        SELECT
            COALESCE(SUM(total_runs), 0) AS runs,
            COALESCE(SUM(is_wicket), 0) AS wickets,
            COALESCE(SUM(legal_ball), 0) AS legal_balls,
            COALESCE(SUM(CASE WHEN total_runs IN (4, 6) THEN 1 ELSE 0 END), 0) AS boundaries,
            COALESCE(SUM(CASE WHEN total_runs = 0 AND is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS dots
        FROM (
            SELECT total_runs, is_wicket, legal_ball, is_wide_ball
            FROM deliveries
            WHERE season_id = ? AND match_id = ? AND innings = ?
              AND (over_number < ? OR (over_number = ? AND ball_number < ?))
            ORDER BY over_number DESC, ball_number DESC, source_row_number DESC
            LIMIT 12
        ) recent
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number),
    ).fetchone()

    partnership = conn.execute(
        """
        WITH prior AS (
            SELECT
                total_runs,
                legal_ball,
                CASE WHEN total_runs IN (4, 6) THEN 1 ELSE 0 END AS boundary,
                COALESCE(
                    SUM(is_wicket) OVER (
                        PARTITION BY season_id, match_id, innings
                        ORDER BY over_number, ball_number, source_row_number
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ),
                    0
                ) AS wickets_before_delivery
            FROM deliveries
            WHERE season_id = ? AND match_id = ? AND innings = ?
              AND (over_number < ? OR (over_number = ? AND ball_number < ?))
        )
        SELECT
            COALESCE(SUM(total_runs), 0) AS runs,
            COALESCE(SUM(legal_ball), 0) AS balls,
            COALESCE(SUM(boundary), 0) AS boundaries,
            COUNT(*) AS deliveries
        FROM prior
        WHERE wickets_before_delivery = ?
        """,
        (season_id, match_id, innings, over_number, over_number, ball_number, wickets_before),
    ).fetchone()

    batter_counts = _fetch_outcome_counts(conn, timeline, " AND batter = ?", (batter,))
    bowler_counts = _fetch_outcome_counts(conn, timeline, " AND bowler = ?", (bowler,))
    matchup_counts = _fetch_outcome_counts(conn, timeline, " AND batter = ? AND bowler = ?", (batter, bowler))
    phase_counts = _fetch_outcome_counts(conn, timeline, " AND " + _phase_over_clause(phase))
    batter_vs_type_counts = _fetch_outcome_counts(
        conn,
        timeline,
        " AND batter = ? AND bowler_type = ?",
        (batter, target["bowler_type"]),
    )
    bowler_vs_batter_type_counts = _fetch_outcome_counts(
        conn,
        timeline,
        " AND bowler = ? AND batsman_type = ?",
        (bowler, target["batsman_type"]),
    )
    team_batting_counts = _fetch_outcome_counts(conn, timeline, " AND team_batting = ?", (target["team_batting"],))
    team_bowling_counts = _fetch_outcome_counts(conn, timeline, " AND team_bowling = ?", (target["team_bowling"],))

    over_bucket = _bucket_over_window(legal_balls_before)
    over_low, over_high = [int(part) for part in over_bucket.split("-")]
    similarity_strategies = [
        {
            "name": "strict_match_state",
            "where": (
                " AND innings = ? AND "
                + _phase_over_clause(phase)
                + " AND batsman_type = ? AND bowler_type = ?"
                + " AND team_batting = ? AND team_bowling = ?"
                + " AND over_number BETWEEN ? AND ?"
            ),
            "params": (
                innings,
                target["batsman_type"],
                target["bowler_type"],
                target["team_batting"],
                target["team_bowling"],
                over_low,
                over_high,
            ),
            "min_samples": 120,
        },
        {
            "name": "state_type_phase",
            "where": (
                " AND innings = ? AND "
                + _phase_over_clause(phase)
                + " AND batsman_type = ? AND bowler_type = ? AND over_number BETWEEN ? AND ?"
            ),
            "params": (innings, target["batsman_type"], target["bowler_type"], over_low, over_high),
            "min_samples": 220,
        },
        {
            "name": "type_phase_fallback",
            "where": " AND " + _phase_over_clause(phase) + " AND batsman_type = ? AND bowler_type = ?",
            "params": (target["batsman_type"], target["bowler_type"]),
            "min_samples": 1,
        },
    ]
    similar_counts = Counter()
    similarity_level = "type_phase_fallback"
    for strategy in similarity_strategies:
        trial = _fetch_outcome_counts(conn, timeline, strategy["where"], strategy["params"])
        if sum(trial.values()) >= int(strategy["min_samples"]):
            similar_counts = trial
            similarity_level = str(strategy["name"])
            break
        if sum(trial.values()) > sum(similar_counts.values()):
            similar_counts = trial
            similarity_level = str(strategy["name"])

    venue_row = conn.execute(
        """
        SELECT venue
        FROM match_metadata
        WHERE match_id = ?
        LIMIT 1
        """,
        (match_id,),
    ).fetchone()
    venue = str(venue_row["venue"]).strip() if venue_row and venue_row["venue"] else None
    if venue:
        venue_counts = _fetch_outcome_counts(
            conn,
            timeline,
            " AND match_id IN (SELECT match_id FROM match_metadata WHERE venue = ?)",
            (venue,),
        )
    else:
        venue_counts = Counter()
    recent_outcomes = _fetch_recent_outcomes(conn, season_id, match_id, innings, over_number, ball_number, limit=6)
    recent_counter = Counter(recent_outcomes)

    batter_recent = _fetch_player_recent_match_form(conn, timeline, batter, role="batter", n_matches=3)
    bowler_recent = _fetch_player_recent_match_form(conn, timeline, bowler, role="bowler", n_matches=3)
    batter_prev_match = _fetch_player_recent_match_form(conn, timeline, batter, role="batter", n_matches=1)
    bowler_prev_match = _fetch_player_recent_match_form(conn, timeline, bowler, role="bowler", n_matches=1)

    balls_remaining = max(0, 120 - legal_balls_before)
    wickets_remaining = max(0, 10 - wickets_before)
    runs_required = None
    pressure_gap = None
    if isinstance(target_runs, int):
        runs_required = max(0, target_runs - score_before)
    if isinstance(required_run_rate, float):
        pressure_gap = round(required_run_rate - current_run_rate, 2)

    return {
        "innings_state": {
            "score_before": score_before,
            "wickets_before": wickets_before,
            "legal_balls_before": legal_balls_before,
            "current_run_rate": current_run_rate,
            "required_run_rate": required_run_rate,
            "runs_required": runs_required,
            "pressure_gap": pressure_gap,
            "balls_remaining": balls_remaining,
            "wickets_remaining": wickets_remaining,
            "target_runs": target_runs,
            "phase": phase,
            "wickets_bucket": _bucket_wickets(wickets_before),
            "over_window": over_bucket,
        },
        "striker_innings": {
            "runs": int(striker_innings["runs"]),
            "balls": int(striker_innings["balls"]),
            "boundaries": int(striker_innings["boundaries"]),
            "strike_rate": round((int(striker_innings["runs"]) * 100.0 / int(striker_innings["balls"])), 2)
            if int(striker_innings["balls"])
            else 0.0,
        },
        "bowler_innings": {
            "runs": int(bowler_innings["runs"]),
            "balls": int(bowler_innings["balls"]),
            "wickets": int(bowler_innings["wickets"]),
            "boundaries": int(bowler_innings["boundaries"]),
            "economy": round((int(bowler_innings["runs"]) / (int(bowler_innings["balls"]) / 6.0)), 2) if int(bowler_innings["balls"]) else 0.0,
        },
        "recent_match_state": {
            "window_deliveries": int(recent_window["legal_balls"]),
            "runs": int(recent_window["runs"]),
            "wickets": int(recent_window["wickets"]),
            "boundaries": int(recent_window["boundaries"]),
            "dots": int(recent_window["dots"]),
        },
        "partnership": {
            "runs": int(partnership["runs"]),
            "balls": int(partnership["balls"]),
            "boundaries": int(partnership["boundaries"]),
            "deliveries": int(partnership["deliveries"]),
        },
        "batter_history": {
            "runs": int(batter_hist["runs"]),
            "balls": int(batter_hist["balls"]),
            "fours": int(batter_hist["fours"]),
            "sixes": int(batter_hist["sixes"]),
            "dots": int(batter_hist["dots"]),
            "dismissals": int(batter_hist["dismissals"]),
            "outcomes": _counter_to_probability_payload(batter_counts),
        },
        "bowler_history": {
            "runs_conceded": int(bowler_hist["runs_conceded"]),
            "legal_balls": int(bowler_hist["legal_balls"]),
            "wickets": int(bowler_hist["wickets"]),
            "dots": int(bowler_hist["dots"]),
            "fours_conceded": int(bowler_hist["fours_conceded"]),
            "sixes_conceded": int(bowler_hist["sixes_conceded"]),
            "outcomes": _counter_to_probability_payload(bowler_counts),
        },
        "matchup": {
            "batter": batter,
            "bowler": bowler,
            "outcomes": _counter_to_probability_payload(matchup_counts),
        },
        "matchups": {
            "batter_vs_bowling_type": _counter_to_probability_payload(batter_vs_type_counts),
            "bowler_vs_batter_type": _counter_to_probability_payload(bowler_vs_batter_type_counts),
        },
        "phase_history": _counter_to_probability_payload(phase_counts),
        "team_context": {
            "batting_team": str(target["team_batting"]),
            "bowling_team": str(target["team_bowling"]),
            "batting_team_outcomes": _counter_to_probability_payload(team_batting_counts),
            "bowling_team_outcomes": _counter_to_probability_payload(team_bowling_counts),
        },
        "venue_context": {
            "venue": venue,
            "evidence_tier": _venue_evidence_tier(int(sum(venue_counts.values()))),
            "outcomes": _counter_to_probability_payload(venue_counts),
        },
        "similar_situations": {
            "definition": "deterministic fallback: state+type+phase -> type+phase",
            "selected_level": similarity_level,
            "outcomes": _counter_to_probability_payload(similar_counts),
        },
        "recent_deliveries": {
            "window": len(recent_outcomes),
            "outcomes": recent_outcomes,
            "counts": dict(sorted(recent_counter.items())),
            "distribution": _counter_to_probability_payload(recent_counter),
        },
        "recent_form": {
            "batter_previous_match": batter_prev_match,
            "bowler_previous_match": bowler_prev_match,
            "batter_recent_matches": batter_recent,
            "bowler_recent_matches": bowler_recent,
        },
    }


def _apply_context_multipliers(probabilities: dict[str, float], contextual_features: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    adjusted = dict(probabilities)
    notes: list[str] = []

    innings_state = contextual_features["innings_state"]
    striker = contextual_features["striker_innings"]
    bowler = contextual_features["bowler_innings"]
    partnership = contextual_features["partnership"]
    recent_state = contextual_features["recent_match_state"]
    venue_context = contextual_features["venue_context"]
    matchup_sample = int(contextual_features["matchup"]["outcomes"]["sample_size"])
    recent = contextual_features["recent_deliveries"]

    current_rr = float(innings_state["current_run_rate"])
    required_rr = innings_state.get("required_run_rate")
    if isinstance(required_rr, (int, float)):
        pressure_delta = float(required_rr) - current_rr
        if pressure_delta >= 2.0:
            adjusted["4"] *= 1.12
            adjusted["6"] *= 1.10
            adjusted["wicket"] *= 1.08
            adjusted["0"] *= 0.92
            notes.append("Required run rate pressure increased attacking outcomes.")
        elif pressure_delta <= -1.5:
            adjusted["0"] *= 1.06
            adjusted["1"] *= 1.08
            adjusted["4"] *= 0.95
            adjusted["6"] *= 0.90
            notes.append("Chase is ahead of rate, so lower-risk outcomes were favored.")

    wickets_remaining = int(innings_state.get("wickets_remaining", 10))
    if wickets_remaining <= 3:
        adjusted["wicket"] *= 1.08
        adjusted["0"] *= 1.04
        adjusted["6"] *= 0.95
        notes.append("Few wickets in hand increased dismissal risk and reduced high-variance shots.")

    striker_balls = int(striker["balls"])
    striker_runs = int(striker["runs"])
    if striker_balls >= 6:
        striker_sr = (striker_runs * 100.0) / striker_balls if striker_balls else 0.0
        if striker_sr >= 150.0:
            adjusted["4"] *= 1.08
            adjusted["6"] *= 1.10
            notes.append("Striker has started quickly in this innings.")
        elif striker_sr <= 90.0:
            adjusted["0"] *= 1.05
            adjusted["1"] *= 1.04
            adjusted["wicket"] *= 1.04
            notes.append("Striker scoring rate is below par in this innings.")

    bowler_balls = int(bowler["balls"])
    bowler_runs = int(bowler["runs"])
    if bowler_balls >= 6:
        econ = bowler_runs / (bowler_balls / 6.0)
        if econ >= 10.0:
            adjusted["4"] *= 1.07
            adjusted["6"] *= 1.06
            notes.append("Bowler has been expensive in this spell.")
        elif econ <= 6.0:
            adjusted["0"] *= 1.06
            adjusted["wicket"] *= 1.05
            notes.append("Bowler has controlled scoring in this spell.")

    recent_counts = Counter(recent.get("outcomes", []))
    if recent_counts.get("4", 0) + recent_counts.get("6", 0) >= 2:
        adjusted["4"] *= 1.05
        adjusted["6"] *= 1.05
        notes.append("Recent boundary momentum was included.")
    if recent_counts.get("wicket", 0) >= 1:
        adjusted["wicket"] *= 1.06
        notes.append("Recent wicket event raised dismissal risk.")

    partnership_balls = int(partnership.get("balls", 0))
    partnership_runs = int(partnership.get("runs", 0))
    if partnership_balls >= 12:
        partnership_sr = (partnership_runs * 100.0) / partnership_balls if partnership_balls else 0.0
        if partnership_sr >= 150.0:
            adjusted["1"] *= 1.05
            adjusted["4"] *= 1.06
            notes.append("Current partnership has positive scoring momentum.")

    recent_legal = int(recent_state.get("window_deliveries", 0))
    recent_runs = int(recent_state.get("runs", 0))
    if recent_legal >= 6:
        recent_rr = (recent_runs * 6.0) / recent_legal if recent_legal else 0.0
        if recent_rr <= 5.0:
            adjusted["0"] *= 1.05
            adjusted["wicket"] *= 1.03
            notes.append("Short-term innings tempo is subdued.")
        elif recent_rr >= 10.0:
            adjusted["4"] *= 1.06
            adjusted["6"] *= 1.05
            notes.append("Short-term innings tempo is aggressive.")

    venue_sample = int(venue_context.get("outcomes", {}).get("sample_size", 0))
    if venue_sample >= 600:
        venue_probs = venue_context.get("outcomes", {}).get("outcome_probabilities", {})
        if float(venue_probs.get("6", 0.0)) >= 0.03:
            adjusted["6"] *= 1.03
            notes.append("Venue history supports six-hitting at this ground.")

    matchup_probs = contextual_features["matchup"]["outcomes"]["outcome_probabilities"]
    if matchup_sample >= 20 and matchup_probs.get("wicket", 0.0) >= 0.1:
        adjusted["wicket"] *= 1.08
        notes.append("Historical batter vs bowler dismissal rate is elevated.")

    return _normalize_probabilities(adjusted), notes


def _feature_snapshot_from_context(context: PredictionContext) -> dict[str, Any]:
    cf = context.contextual_features
    innings_state = cf["innings_state"]
    striker = cf["striker_innings"]
    bowler = cf["bowler_innings"]
    partnership = cf["partnership"]
    recent_state = cf["recent_match_state"]
    venue_context = cf["venue_context"]
    team_context = cf["team_context"]
    matchup = cf["matchup"]["outcomes"]
    similar = cf["similar_situations"]["outcomes"]
    recent = cf["recent_deliveries"]

    return {
        "phase": context.phase,
        "score_before": innings_state["score_before"],
        "wickets_before": innings_state["wickets_before"],
        "legal_balls_before": innings_state["legal_balls_before"],
        "current_run_rate": innings_state["current_run_rate"],
        "required_run_rate": innings_state.get("required_run_rate"),
        "pressure_gap": innings_state.get("pressure_gap"),
        "runs_required": innings_state.get("runs_required"),
        "balls_remaining": innings_state.get("balls_remaining"),
        "wickets_remaining": innings_state.get("wickets_remaining"),
        "striker_runs": striker["runs"],
        "striker_balls": striker["balls"],
        "bowler_spell_runs": bowler["runs"],
        "bowler_spell_balls": bowler["balls"],
        "partnership_runs": partnership.get("runs"),
        "partnership_balls": partnership.get("balls"),
        "recent_window_runs": recent_state.get("runs"),
        "recent_window_wickets": recent_state.get("wickets"),
        "batting_team": team_context.get("batting_team"),
        "bowling_team": team_context.get("bowling_team"),
        "venue": venue_context.get("venue"),
        "venue_sample": venue_context.get("outcomes", {}).get("sample_size", 0),
        "matchup_sample": matchup["sample_size"],
        "similar_sample": similar["sample_size"],
        "recent_outcomes": recent.get("outcomes", []),
    }


def _build_prediction_difference(previous_snapshot: dict[str, Any], current_snapshot: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    tracked_fields = {
        "score_before": "Score before delivery",
        "wickets_before": "Wickets before delivery",
        "legal_balls_before": "Legal balls faced in innings",
        "current_run_rate": "Current run rate",
        "required_run_rate": "Required run rate",
        "pressure_gap": "Run-rate pressure gap",
        "runs_required": "Runs required",
        "balls_remaining": "Balls remaining",
        "wickets_remaining": "Wickets remaining",
        "striker_runs": "Striker runs",
        "striker_balls": "Striker balls",
        "bowler_spell_runs": "Bowler spell runs",
        "bowler_spell_balls": "Bowler spell balls",
        "partnership_runs": "Current partnership runs",
        "partnership_balls": "Current partnership balls",
        "recent_window_runs": "Recent scoring window runs",
        "recent_window_wickets": "Recent scoring window wickets",
        "venue_sample": "Venue evidence sample",
        "matchup_sample": "Batter vs bowler evidence sample",
        "similar_sample": "Comparable situation sample",
    }
    for key, label in tracked_fields.items():
        before = previous_snapshot.get(key)
        after = current_snapshot.get(key)
        if before != after:
            changes.append(f"{label}: {before} -> {after}")

    prev_recent = previous_snapshot.get("recent_outcomes", [])
    curr_recent = current_snapshot.get("recent_outcomes", [])
    if prev_recent != curr_recent:
        changes.append("Recent delivery pattern updated")

    return changes


def predict_contextual_from_context(context: PredictionContext) -> dict[str, Any]:
    baseline = predict_hierarchical_from_count_map(
        context.feature_values,
        context.context_count_map,
        context.global_counts,
    )

    cf = context.contextual_features
    matchup_probs = cf["matchup"]["outcomes"]["outcome_probabilities"]
    matchup_sample = int(cf["matchup"]["outcomes"]["sample_size"])
    batter_probs = cf["batter_history"]["outcomes"]["outcome_probabilities"]
    batter_sample = int(cf["batter_history"]["outcomes"]["sample_size"])
    bowler_probs = cf["bowler_history"]["outcomes"]["outcome_probabilities"]
    bowler_sample = int(cf["bowler_history"]["outcomes"]["sample_size"])
    phase_probs = cf["phase_history"]["outcome_probabilities"]
    phase_sample = int(cf["phase_history"]["sample_size"])
    similar_probs = cf["similar_situations"]["outcomes"]["outcome_probabilities"]
    similar_sample = int(cf["similar_situations"]["outcomes"]["sample_size"])
    recent_probs = cf["recent_deliveries"]["distribution"]["outcome_probabilities"]
    recent_sample = int(cf["recent_deliveries"]["distribution"]["sample_size"])

    components: list[tuple[str, dict[str, float], float]] = [
        ("hierarchical_baseline", baseline["outcome_probabilities"], 0.28),
        ("global_history", _smoothed_probabilities(context.global_counts), 0.10),
        ("phase_history", phase_probs, min(0.14, 0.14 * (phase_sample / 8000.0))),
        ("batter_history", batter_probs, min(0.18, 0.18 * (batter_sample / 1600.0))),
        ("bowler_history", bowler_probs, min(0.16, 0.16 * (bowler_sample / 1600.0))),
        ("batter_bowler_matchup", matchup_probs, min(0.20, 0.20 * (matchup_sample / 140.0))),
        (
            "batter_vs_bowling_type",
            cf["matchups"]["batter_vs_bowling_type"]["outcome_probabilities"],
            min(0.10, 0.10 * (int(cf["matchups"]["batter_vs_bowling_type"]["sample_size"]) / 220.0)),
        ),
        (
            "bowler_vs_batter_type",
            cf["matchups"]["bowler_vs_batter_type"]["outcome_probabilities"],
            min(0.09, 0.09 * (int(cf["matchups"]["bowler_vs_batter_type"]["sample_size"]) / 220.0)),
        ),
        (
            "batting_team_context",
            cf["team_context"]["batting_team_outcomes"]["outcome_probabilities"],
            min(0.08, 0.08 * (int(cf["team_context"]["batting_team_outcomes"]["sample_size"]) / 4000.0)),
        ),
        (
            "bowling_team_context",
            cf["team_context"]["bowling_team_outcomes"]["outcome_probabilities"],
            min(0.08, 0.08 * (int(cf["team_context"]["bowling_team_outcomes"]["sample_size"]) / 4000.0)),
        ),
        (
            "venue_context",
            cf["venue_context"]["outcomes"]["outcome_probabilities"],
            min(0.07, 0.07 * (int(cf["venue_context"]["outcomes"]["sample_size"]) / 2400.0)),
        ),
        ("similar_situations", similar_probs, min(0.14, 0.14 * (similar_sample / 2000.0))),
        ("recent_innings_window", recent_probs, min(0.08, 0.08 * (recent_sample / 6.0))),
    ]

    blended_probs, blend_contribution = _weighted_blend(components)
    adjusted_probs, adjustment_notes = _apply_context_multipliers(blended_probs, cf)

    evidence_sample = int(
        matchup_sample
        + similar_sample
        + min(batter_sample, 400)
        + min(bowler_sample, 400)
        + recent_sample
    )
    reliability = _compute_reliability(evidence_sample)
    top = _top_outcome(adjusted_probs)

    looked_at = [
        "batter historical scoring profile",
        "bowler historical concession profile",
        "batter vs bowler matchup",
        "batter-vs-bowling-type and bowler-vs-batter-type matchups",
        "team batting and bowling context",
        "venue outcomes with reliability-aware fallback",
        "phase-specific history",
        "current innings pressure and recent ball pattern",
        f"comparable situations ({cf['similar_situations'].get('selected_level', 'fallback')})",
    ]

    def ledger_item(
        feature: str,
        value: Any,
        source: str,
        sample_size: int,
        influence: str,
    ) -> dict[str, Any]:
        return {
            "feature": feature,
            "value": value,
            "source": source,
            "historical_cutoff": context.timeline_key,
            "sample_size": sample_size,
            "strength": _sample_reliability(sample_size),
            "influence": influence,
        }

    feature_ledger = [
        ledger_item("current_score", cf["innings_state"]["score_before"], "match_state", 1, "state_input"),
        ledger_item("wickets_before", cf["innings_state"]["wickets_before"], "match_state", 1, "state_input"),
        ledger_item("current_run_rate", cf["innings_state"]["current_run_rate"], "derived_match_state", 1, "tempo_signal"),
        ledger_item("required_run_rate", cf["innings_state"].get("required_run_rate"), "derived_match_state", 1, "pressure_signal"),
        ledger_item("pressure_gap", cf["innings_state"].get("pressure_gap"), "derived_match_state", 1, "pressure_signal"),
        ledger_item("batter_history_distribution", batter_probs, "deliveries.timeline_key", batter_sample, "blend_component"),
        ledger_item("bowler_history_distribution", bowler_probs, "deliveries.timeline_key", bowler_sample, "blend_component"),
        ledger_item("batter_bowler_matchup_distribution", matchup_probs, "deliveries.timeline_key", matchup_sample, "blend_component"),
        ledger_item(
            "similar_situations_distribution",
            similar_probs,
            f"deliveries.timeline_key[{cf['similar_situations'].get('selected_level', 'fallback')}]",
            similar_sample,
            "blend_component",
        ),
        ledger_item(
            "venue_distribution",
            cf["venue_context"]["outcomes"]["outcome_probabilities"],
            "match_metadata+deliveries",
            int(cf["venue_context"]["outcomes"]["sample_size"]),
            f"venue_{cf['venue_context'].get('evidence_tier', 'fallback')}",
        ),
    ]

    return {
        "model_version": DEFAULT_RUNTIME_MODEL_VERSION,
        "feature_version": DEFAULT_FEATURE_VERSION,
        "evidence_version": DEFAULT_EVIDENCE_VERSION,
        "chosen_evidence_level": "contextual_blend",
        "evidence_sample_size": evidence_sample,
        "reliability": reliability,
        "outcome_probabilities": adjusted_probs,
        "predicted_top_outcome": top,
        "evidence": {
            "looked_at": looked_at,
            "comparable_deliveries": similar_sample,
            "matchup_deliveries": matchup_sample,
            "blend_contribution": blend_contribution,
            "adjustment_notes": adjustment_notes,
            "feature_ledger": feature_ledger,
        },
        "feature_snapshot": _feature_snapshot_from_context(context),
        "debug": {
            "baseline": baseline,
            "components": {
                "matchup_sample": matchup_sample,
                "batter_sample": batter_sample,
                "bowler_sample": bowler_sample,
                "phase_sample": phase_sample,
                "similar_sample": similar_sample,
                "recent_sample": recent_sample,
            },
        },
    }


class SequentialPredictionSession:
    def __init__(
        self,
        conn: sqlite3.Connection,
        season_id: int,
        match_id: int,
        innings: int,
        model_version: str = DEFAULT_RUNTIME_MODEL_VERSION,
        start_over_number: int | None = None,
        start_ball_number: int | None = None,
    ) -> None:
        self.conn = conn
        self.season_id = season_id
        self.match_id = match_id
        self.innings = innings
        load_sql = """
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
            """
        load_started = time.perf_counter()
        self.rows = conn.execute(load_sql, (season_id, match_id, innings)).fetchall()
        log_sql(
            "replay_load_innings",
            load_sql,
            (season_id, match_id, innings),
            load_started,
            row_count=len(self.rows),
        )
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
        self.model_version = model_version
        self._previous_feature_snapshot: dict[str, Any] | None = None

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
        contextual_features = _collect_contextual_features(self.conn, row, str(row["timeline_key"]), phase)
        context = PredictionContext(
            target=row,
            target_identity={
                "season_id": int(row["season_id"]),
                "match_id": int(row["match_id"]),
                "innings": int(row["innings"]),
                "over_number": int(row["over_number"]),
                "ball_number": int(row["ball_number"]),
            },
            timeline_key=str(row["timeline_key"]),
            legal_balls_before=int(row["legal_balls_before"]),
            phase=phase,
            feature_values=feature_values,
            global_counts=self.global_counts,
            context_count_map=self.context_count_map,
            contextual_features=contextual_features,
        )

        if self.model_version == "baseline_hierarchical_v1":
            model_payload = predict_hierarchical_from_count_map(feature_values, self.context_count_map, self.global_counts)
            model_payload["feature_snapshot"] = _feature_snapshot_from_context(context)
            model_payload["evidence"] = {
                "looked_at": ["hierarchical batter/bowler/type contexts"],
                "comparable_deliveries": 0,
                "matchup_deliveries": int(sum(self.context_count_map.get(("batter_bowler", (row["batter"], row["bowler"])), Counter()).values())),
                "blend_contribution": [{"source": "hierarchical_baseline", "weight": 1.0}],
                "adjustment_notes": [],
            }
        else:
            model_payload = predict_contextual_from_context(context)

        probabilities = model_payload["outcome_probabilities"]
        top = model_payload["predicted_top_outcome"]
        actual = classify_delivery_outcome(row)
        prediction_difference = None
        current_snapshot = dict(model_payload.get("feature_snapshot", {}))
        if self._previous_feature_snapshot is not None:
            changes = _build_prediction_difference(self._previous_feature_snapshot, current_snapshot)
            prediction_difference = {
                "changed_features": changes,
                "change_detected": len(changes) > 0,
            }
        self._previous_feature_snapshot = current_snapshot

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
            "model_version": model_payload["model_version"],
            "feature_version": model_payload.get("feature_version", DEFAULT_FEATURE_VERSION),
            "evidence_version": model_payload.get("evidence_version", DEFAULT_EVIDENCE_VERSION),
            "chosen_evidence_level": model_payload["chosen_evidence_level"],
            "evidence_sample_size": model_payload["evidence_sample_size"],
            "reliability": model_payload["reliability"],
            "outcome_probabilities": probabilities,
            "predicted_top_outcome": top,
            "evidence": model_payload.get("evidence", {}),
            "feature_snapshot": current_snapshot,
            "prediction_difference": prediction_difference,
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
        contextual_features=_collect_contextual_features(conn, target, timeline, phase),
    )


def predict_global_baseline_from_counts(global_counts: Counter[str]) -> dict[str, Any]:
    probabilities = probabilities_from_counts(global_counts)
    return {
        "model_version": "baseline_global_v1",
        "feature_version": "baseline_features_v1",
        "evidence_version": "baseline_evidence_v1",
        "chosen_evidence_level": "global",
        "evidence_sample_size": int(sum(global_counts.values())),
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top_outcome(probabilities),
    }


def predict_phase_baseline_from_counts(phase_counts: Counter[str], phase: str) -> dict[str, Any]:
    probabilities = probabilities_from_counts(phase_counts)
    return {
        "model_version": "baseline_phase_v1",
        "feature_version": "baseline_features_v1",
        "evidence_version": "baseline_evidence_v1",
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
        "feature_version": "baseline_features_v1",
        "evidence_version": "baseline_evidence_v1",
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
        "feature_version": baseline["feature_version"],
        "evidence_version": baseline["evidence_version"],
        "chosen_evidence_level": baseline["chosen_evidence_level"],
        "evidence_sample_size": baseline["evidence_sample_size"],
        "reliability": baseline["reliability"],
        "outcome_probabilities": probabilities,
        "predicted_top_outcome": top,
        "actual_outcome": actual,
        "top_prediction_correct": top == actual,
    }


def predict_next_ball(
    conn: sqlite3.Connection,
    season_id: int,
    match_id: int,
    innings: int,
    over_number: int,
    ball_number: int,
    model_version: str = DEFAULT_RUNTIME_MODEL_VERSION,
) -> dict[str, Any]:
    context = build_prediction_context(conn, season_id, match_id, innings, over_number, ball_number)
    if model_version == "baseline_hierarchical_v1":
        return predict_next_ball_baseline(conn, season_id, match_id, innings, over_number, ball_number)

    model_payload = predict_contextual_from_context(context)
    top = model_payload["predicted_top_outcome"]
    actual = classify_delivery_outcome(context.target)

    return {
        "target_identity": context.target_identity,
        "state_identity": {
            "timeline_key": context.timeline_key,
            "legal_balls_before": context.legal_balls_before,
            "innings_phase": context.phase,
        },
        "prediction_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model_version": model_payload["model_version"],
        "feature_version": model_payload.get("feature_version", DEFAULT_FEATURE_VERSION),
        "evidence_version": model_payload.get("evidence_version", DEFAULT_EVIDENCE_VERSION),
        "chosen_evidence_level": model_payload["chosen_evidence_level"],
        "evidence_sample_size": model_payload["evidence_sample_size"],
        "reliability": model_payload["reliability"],
        "outcome_probabilities": model_payload["outcome_probabilities"],
        "predicted_top_outcome": top,
        "evidence": model_payload.get("evidence", {}),
        "feature_snapshot": model_payload.get("feature_snapshot", {}),
        "actual_outcome": actual,
        "top_prediction_correct": top == actual,
    }


