from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import sqlite3
import time
from typing import Any
from uuid import uuid4

from .ask_matchgenome import AskMatchGenomeEngine
from .player_intelligence import get_player_intelligence, list_players
from .prediction import DEFAULT_RUNTIME_MODEL_VERSION, SequentialPredictionSession
from .runtime_logging import log_sql


class ReplayStatus(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    PREDICTION_AVAILABLE = "PREDICTION_AVAILABLE"
    PREDICTION_REVEALED = "PREDICTION_REVEALED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ReplayLedgerEntry:
    session_id: str
    delivery_sequence: int
    target_identity: dict[str, int]
    state_identity: dict[str, Any]
    model_version: str
    feature_version: str
    evidence_version: str
    outcome_probabilities: dict[str, float]
    predicted_top_outcome: str
    chosen_evidence_level: str
    evidence_sample_size: int
    reliability: str
    actual_outcome: str | None = None
    correct: bool | None = None
    reveal_status: str = "pending"


@dataclass
class ReplaySession:
    session_id: str
    season_id: int
    match_id: int
    innings: int
    start_over_number: int | None
    start_ball_number: int | None
    model_version: str
    sequence: SequentialPredictionSession
    status: ReplayStatus
    created_at_utc: str
    predictions_made: int = 0
    predictions_revealed: int = 0
    _pending_prediction: dict[str, Any] | None = None
    _pending_delivery_sequence: int | None = None
    _last_reveal_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.ledger: list[ReplayLedgerEntry] = []

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def current_replay_state(self) -> dict[str, Any]:
        state = self.sequence.current_state()
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "season_id": self.season_id,
            "match_id": self.match_id,
            "innings": self.innings,
            "start_delivery": {
                "over_number": self.start_over_number,
                "ball_number": self.start_ball_number,
            },
            "created_at_utc": self.created_at_utc,
            "model_version": self.model_version,
            "predictions_made": self.predictions_made,
            "predictions_revealed": self.predictions_revealed,
            "remaining_deliveries": self.sequence.remaining_deliveries(),
            "current_state": state,
            "summary": self.summary(),
        }

    def predict_next(self) -> dict[str, Any]:
        if self.status == ReplayStatus.COMPLETED:
            raise ValueError("Replay session is already completed")
        if self.status == ReplayStatus.FAILED:
            raise ValueError("Replay session is in failed state")

        if self._pending_prediction is not None:
            return self._pending_prediction

        if not self.sequence.has_next():
            self.status = ReplayStatus.COMPLETED
            raise StopIteration("Replay session has no remaining deliveries")

        raw = self.sequence.predict_next()
        prediction_payload = {
            "session_id": self.session_id,
            "session_sequence": self.predictions_made + 1,
            "prediction_timestamp_utc": raw["prediction_timestamp_utc"],
            "delivery": {
                **raw["target_identity"],
                "batter": raw["observed_state"]["striker"],
                "non_striker": raw["observed_state"]["non_striker"],
                "bowler": raw["observed_state"]["bowler"],
            },
            "pre_delivery_state": {
                "team_batting": raw["observed_state"]["team_batting"],
                "team_bowling": raw["observed_state"]["team_bowling"],
                "score": raw["observed_state"]["score_before_delivery"],
                "wickets": raw["observed_state"]["wickets_before_delivery"],
                "legal_balls": raw["observed_state"]["legal_balls_before_delivery"],
                "phase": raw["observed_state"]["innings_phase"],
            },
            "prediction": {
                "model_version": raw["model_version"],
                "feature_version": raw.get("feature_version"),
                "evidence_version": raw.get("evidence_version"),
                "chosen_evidence_level": raw["chosen_evidence_level"],
                "evidence_sample_size": raw["evidence_sample_size"],
                "reliability": raw["reliability"],
                "outcome_probabilities": raw["outcome_probabilities"],
                "predicted_top_outcome": raw["predicted_top_outcome"],
                "evidence": raw.get("evidence", {}),
                "feature_snapshot": raw.get("feature_snapshot", {}),
                "prediction_difference": raw.get("prediction_difference"),
            },
        }

        self.predictions_made += 1
        self._pending_delivery_sequence = self.predictions_made
        self._pending_prediction = prediction_payload
        self.status = ReplayStatus.PREDICTION_AVAILABLE

        self.ledger.append(
            ReplayLedgerEntry(
                session_id=self.session_id,
                delivery_sequence=self.predictions_made,
                target_identity=dict(raw["target_identity"]),
                state_identity=dict(raw["state_identity"]),
                model_version=str(raw["model_version"]),
                feature_version=str(raw.get("feature_version", "unknown")),
                evidence_version=str(raw.get("evidence_version", "unknown")),
                outcome_probabilities=dict(raw["outcome_probabilities"]),
                predicted_top_outcome=str(raw["predicted_top_outcome"]),
                chosen_evidence_level=str(raw["chosen_evidence_level"]),
                evidence_sample_size=int(raw["evidence_sample_size"]),
                reliability=str(raw["reliability"]),
            )
        )

        return prediction_payload

    def reveal_next(self) -> dict[str, Any]:
        if self.status == ReplayStatus.COMPLETED and self._last_reveal_payload is not None:
            return self._last_reveal_payload
        if self.status == ReplayStatus.FAILED:
            raise ValueError("Replay session is in failed state")
        if self._pending_prediction is None or self._pending_delivery_sequence is None:
            if self._last_reveal_payload is not None:
                return self._last_reveal_payload
            raise ValueError("No pending prediction to reveal")

        actual = self.sequence.reveal_current_delivery()
        self.sequence.advance_with_actual()

        entry = self.ledger[-1]
        actual_outcome = str(actual["actual_outcome"])
        entry.actual_outcome = actual_outcome
        entry.correct = bool(entry.predicted_top_outcome == actual_outcome)
        entry.reveal_status = "revealed"

        self.predictions_revealed += 1
        self._pending_prediction = None
        self._pending_delivery_sequence = None

        if self.sequence.has_next():
            self.status = ReplayStatus.PREDICTION_REVEALED
        else:
            self.status = ReplayStatus.COMPLETED

        payload = {
            "session_id": self.session_id,
            "reveal_timestamp_utc": self._now(),
            "delivery": actual["target_identity"],
            "participants": actual["participants"],
            "actual": {
                "actual_outcome": actual_outcome,
                "delivery_facts": actual["delivery_facts"],
            },
            "comparison": {
                "predicted_top_outcome": entry.predicted_top_outcome,
                "is_correct": entry.correct,
            },
            "updated_state": self.sequence.current_state(),
            "summary": self.summary(),
        }
        self._last_reveal_payload = payload
        return payload

    def summary(self) -> dict[str, Any]:
        correct = sum(1 for item in self.ledger if item.correct is True)
        incorrect = sum(1 for item in self.ledger if item.correct is False)
        revealed = sum(1 for item in self.ledger if item.actual_outcome is not None)
        by_outcome: Counter[str] = Counter(item.actual_outcome for item in self.ledger if item.actual_outcome is not None)
        by_phase: Counter[str] = Counter(str(item.state_identity.get("innings_phase", "unknown")) for item in self.ledger if item.actual_outcome is not None)

        return {
            "predictions_made": self.predictions_made,
            "predictions_revealed": revealed,
            "correct_predictions": correct,
            "incorrect_predictions": incorrect,
            "accuracy": round(correct / revealed, 6) if revealed else 0.0,
            "actual_outcomes": dict(sorted(by_outcome.items())),
            "phase_breakdown": dict(sorted(by_phase.items())),
        }

    def restart(self) -> None:
        self.sequence = SequentialPredictionSession(
            self.sequence.conn,
            self.season_id,
            self.match_id,
            self.innings,
            start_over_number=self.start_over_number,
            start_ball_number=self.start_ball_number,
        )
        self.status = ReplayStatus.READY
        self.predictions_made = 0
        self.predictions_revealed = 0
        self._pending_prediction = None
        self._pending_delivery_sequence = None
        self._last_reveal_payload = None
        self.ledger = []


class TimeMachineService:
    DEFAULT_MODEL_VERSION = DEFAULT_RUNTIME_MODEL_VERSION

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._sessions: dict[str, ReplaySession] = {}
        self._ask_engine = AskMatchGenomeEngine(conn)

    def _fetchall(self, operation: str, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        started = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        log_sql(operation, sql, params, started, row_count=len(rows))
        return rows

    def _fetchone(self, operation: str, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        started = time.perf_counter()
        row = self.conn.execute(sql, params).fetchone()
        log_sql(operation, sql, params, started, row_count=0 if row is None else 1)
        return row

    def _resolve_team_label(self, match_id: int, internal_team_code: Any) -> str:
        raw = "" if internal_team_code is None else str(internal_team_code)
        row = self._fetchone(
            "resolve_team_label",
            """
            SELECT historical_display_name
            FROM match_team_map
            WHERE match_id = ? AND internal_team_code = ?
            """,
            (match_id, raw),
        )
        if row is None:
            return raw
        return str(row["historical_display_name"])

    def list_seasons(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "list_seasons",
            """
            SELECT season_id, COUNT(DISTINCT match_id) AS match_count, COUNT(*) AS delivery_count
            FROM deliveries
            GROUP BY season_id
            ORDER BY season_id
            """,
        )
        return [
            {
                "season_id": int(r["season_id"]),
                "match_count": int(r["match_count"]),
                "delivery_count": int(r["delivery_count"]),
            }
            for r in rows
        ]

    def list_matches(self, season_id: int) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "list_matches",
            """
            WITH season_match_ids AS (
                SELECT
                    m.match_id,
                    m.season_id,
                    m.is_super_over_match,
                    DENSE_RANK() OVER (PARTITION BY m.season_id ORDER BY m.match_id) AS season_match_number
                FROM matches m
                WHERE m.season_id = ?
            )
            SELECT
                s.match_id,
                s.season_id,
                s.is_super_over_match,
                s.season_match_number,
                COALESCE(mm.team_a_display, mtm_a.historical_display_name, i1.team_batting, i_any.team_batting) AS team_a,
                COALESCE(mm.team_b_display, mtm_b.historical_display_name, i1.team_bowling, i_any.team_bowling) AS team_b,
                COALESCE(mm.match_number, s.season_match_number) AS match_number,
                mm.match_date,
                mm.venue,
                mm.city,
                COUNT(DISTINCT i.innings) AS innings_count,
                COALESCE(SUM(i.deliveries), 0) AS deliveries
            FROM season_match_ids s
            LEFT JOIN innings_summary i
              ON i.match_id = s.match_id AND i.season_id = s.season_id
            LEFT JOIN innings_summary i1
              ON i1.match_id = s.match_id AND i1.season_id = s.season_id AND i1.innings = 1
            LEFT JOIN innings_summary i_any
              ON i_any.match_id = s.match_id AND i_any.season_id = s.season_id
            LEFT JOIN match_metadata mm
              ON mm.match_id = s.match_id
            LEFT JOIN match_team_map mtm_a
              ON mtm_a.match_id = s.match_id AND mtm_a.internal_team_code = i1.team_batting
            LEFT JOIN match_team_map mtm_b
              ON mtm_b.match_id = s.match_id AND mtm_b.internal_team_code = i1.team_bowling
            GROUP BY s.match_id, s.season_id, s.is_super_over_match, s.season_match_number, team_a, team_b, match_number, mm.match_date, mm.venue, mm.city
            ORDER BY s.match_id
            """,
            (season_id,),
        )
        return [
            {
                "season_id": int(r["season_id"]),
                "match_id": int(r["match_id"]),
                "season_match_number": int(r["season_match_number"]),
                "team_a": r["team_a"],
                "team_b": r["team_b"],
                "match_number": int(r["match_number"]) if r["match_number"] is not None else None,
                "match_date": r["match_date"],
                "venue": r["venue"],
                "city": r["city"],
                "is_super_over_match": int(r["is_super_over_match"]),
                "innings_count": int(r["innings_count"]),
                "deliveries": int(r["deliveries"]),
            }
            for r in rows
        ]

    def get_match(self, match_id: int) -> dict[str, Any]:
        row = self._fetchone(
            "get_match",
            """
            SELECT m.match_id, m.season_id, m.is_super_over_match
            FROM matches m
            WHERE m.match_id = ?
            """,
            (match_id,),
        )
        if row is None:
            raise ValueError("match_id not found")

        meta = self._fetchone(
            "get_match_metadata",
            """
            SELECT
                match_number,
                match_date,
                venue,
                city,
                toss_winner,
                toss_decision,
                winner,
                result_type,
                result_margin,
                match_type,
                player_of_match,
                team_a_display,
                team_b_display
            FROM match_metadata
            WHERE match_id = ?
            """,
            (match_id,),
        )

        return {
            "match_id": int(row["match_id"]),
            "season_id": int(row["season_id"]),
            "is_super_over_match": int(row["is_super_over_match"]),
            "metadata": {
                "venue": meta["venue"] if meta else None,
                "city": meta["city"] if meta else None,
                "match_date": meta["match_date"] if meta else None,
                "match_number": int(meta["match_number"]) if meta and meta["match_number"] is not None else None,
                "match_type": meta["match_type"] if meta else None,
                "team_a_display": meta["team_a_display"] if meta else None,
                "team_b_display": meta["team_b_display"] if meta else None,
                "toss": {
                    "winner": meta["toss_winner"] if meta else None,
                    "decision": meta["toss_decision"] if meta else None,
                },
                "outcome": {
                    "winner": meta["winner"] if meta else None,
                    "result_type": meta["result_type"] if meta else None,
                    "result_margin": int(meta["result_margin"]) if meta and meta["result_margin"] is not None else None,
                    "player_of_match": meta["player_of_match"] if meta else None,
                },
            },
        }

    def list_innings(self, match_id: int) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "list_innings",
            """
            SELECT season_id, match_id, innings, team_batting, team_bowling, deliveries, legal_balls, runs, wickets
            FROM innings_summary
            WHERE match_id = ?
            ORDER BY innings
            """,
            (match_id,),
        )
        if not rows:
            raise ValueError("match_id not found")
        payload: list[dict[str, Any]] = []
        for r in rows:
            team_batting_raw = r["team_batting"]
            team_bowling_raw = r["team_bowling"]
            payload.append(
                {
                    "season_id": int(r["season_id"]),
                    "match_id": int(r["match_id"]),
                    "innings": int(r["innings"]),
                    "team_batting": self._resolve_team_label(match_id, team_batting_raw),
                    "team_bowling": self._resolve_team_label(match_id, team_bowling_raw),
                    "team_batting_internal": "" if team_batting_raw is None else str(team_batting_raw),
                    "team_bowling_internal": "" if team_bowling_raw is None else str(team_bowling_raw),
                    "deliveries": int(r["deliveries"]),
                    "legal_balls": int(r["legal_balls"]),
                    "runs": int(r["runs"]),
                    "wickets": int(r["wickets"]),
                }
            )
        return payload

    def create_replay_session(
        self,
        match_id: int,
        innings: int,
        model_version: str = DEFAULT_RUNTIME_MODEL_VERSION,
        start_over_number: int | None = None,
        start_ball_number: int | None = None,
    ) -> dict[str, Any]:
        row = self._fetchone(
            "create_replay_session",
            """
            SELECT season_id
            FROM innings_summary
            WHERE match_id = ? AND innings = ?
            """,
            (match_id, innings),
        )
        if row is None:
            raise ValueError("match_id/innings not found")

        start_over = start_over_number
        start_ball = start_ball_number
        if (start_over is None) != (start_ball is None):
            raise ValueError("starting delivery requires both over_number and ball_number")

        season_id = int(row["season_id"])
        sequence = SequentialPredictionSession(
            self.conn,
            season_id,
            match_id,
            innings,
            model_version=model_version,
            start_over_number=start_over,
            start_ball_number=start_ball,
        )
        session_id = str(uuid4())
        created = ReplaySession(
            session_id=session_id,
            season_id=season_id,
            match_id=match_id,
            innings=innings,
            start_over_number=start_over,
            start_ball_number=start_ball,
            model_version=model_version,
            sequence=sequence,
            status=ReplayStatus.CREATED,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        created.status = ReplayStatus.READY
        self._sessions[session_id] = created
        return created.current_replay_state()

    def get_replay_session(self, session_id: str) -> ReplaySession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("session_id not found")
        return session

    def inspect_replay_session(self, session_id: str) -> dict[str, Any]:
        return self.get_replay_session(session_id).current_replay_state()

    def predict_next(self, session_id: str) -> dict[str, Any]:
        session = self.get_replay_session(session_id)
        return session.predict_next()

    def reveal_next(self, session_id: str) -> dict[str, Any]:
        session = self.get_replay_session(session_id)
        return session.reveal_next()

    def restart_replay_session(self, session_id: str) -> dict[str, Any]:
        session = self.get_replay_session(session_id)
        session.restart()
        return session.current_replay_state()

    def replay_ledger(self, session_id: str) -> list[dict[str, Any]]:
        session = self.get_replay_session(session_id)
        return [entry.__dict__.copy() for entry in session.ledger]

    def list_players(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        return list_players(self.conn, query=query, limit=limit)

    def get_player(self, player_name: str, session_id: str | None = None) -> dict[str, Any]:
        payload = get_player_intelligence(self.conn, player_name)
        if session_id is not None:
            session = self.get_replay_session(session_id)
            payload["entry_points"] = {
                "return_to_replay": {
                    "session_id": session.session_id,
                    "season_id": session.season_id,
                    "match_id": session.match_id,
                    "innings": session.innings,
                    "status": session.status.value,
                }
            }
        return payload

    def ask(self, question: str) -> dict[str, Any]:
        return self._ask_engine.ask(question)

