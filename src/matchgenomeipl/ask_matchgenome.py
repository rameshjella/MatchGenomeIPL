from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
import time
from typing import Any, Protocol

from .runtime_logging import log_sql

ALLOWED_INTENTS = {
    "PLAYER_SEASON_STAT",
    "PLAYER_BEST_SEASON",
    "MATCH_PLAYER_OF_MATCH",
    "MOST_SIXES_AGAINST_BOWLER",
    "PLAYER_PHASE_COMPARISON",
}

READONLY_BLOCKLIST = re.compile(r"\b(insert|update|delete|drop|alter|attach|pragma|vacuum|create|replace)\b", re.IGNORECASE)


@dataclass(frozen=True)
class QueryPlan:
    question: str
    intent: str
    entities: dict[str, Any]
    metric: str | None = None
    aggregation: str | None = None
    scope: str | None = None


class AskPlanProvider(Protocol):
    def build_plan(self, question: str, semantic: "SemanticResolver") -> QueryPlan | None:
        ...


class RuleBasedPlanProvider:
    def build_plan(self, question: str, semantic: "SemanticResolver") -> QueryPlan | None:
        q = question.strip()
        lowered = q.lower()
        season = semantic.extract_season(lowered)
        player = semantic.resolve_player(lowered)

        if ("player of the match" in lowered or "man of the match" in lowered) and season is not None:
            return QueryPlan(
                question=q,
                intent="MATCH_PLAYER_OF_MATCH",
                entities={"season": season, "stage": "final" if "final" in lowered else None},
                metric="player_of_match",
                aggregation="lookup",
                scope="match_metadata",
            )

        if "most sixes" in lowered and "against" in lowered:
            bowler = semantic.resolve_player_after_keyword(lowered, "against")
            if bowler:
                return QueryPlan(
                    question=q,
                    intent="MOST_SIXES_AGAINST_BOWLER",
                    entities={"bowler": bowler, "season": season},
                    metric="sixes",
                    aggregation="max",
                    scope="batting",
                )

        if "compare" in lowered and ("death" in lowered or "powerplay" in lowered or "middle" in lowered):
            players = semantic.resolve_players_from_text(lowered)
            if len(players) >= 2:
                return QueryPlan(
                    question=q,
                    intent="PLAYER_PHASE_COMPARISON",
                    entities={"players": players[:2], "season": season},
                    metric="strike_rate",
                    aggregation="compare",
                    scope="phase",
                )

        if "best season" in lowered and player:
            return QueryPlan(
                question=q,
                intent="PLAYER_BEST_SEASON",
                entities={"player": player},
                metric="runs",
                aggregation="max",
                scope="batting",
            )

        metric = semantic.resolve_metric(lowered)
        if player and season is not None and metric in {"sixes", "runs", "strike_rate", "wickets", "economy"}:
            return QueryPlan(
                question=q,
                intent="PLAYER_SEASON_STAT",
                entities={"player": player, "season": season},
                metric=metric,
                aggregation="sum" if metric in {"sixes", "runs", "wickets"} else "rate",
                scope="batting" if metric in {"sixes", "runs", "strike_rate"} else "bowling",
            )

        return None


class SemanticResolver:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._players = [str(r["player_name"]) for r in conn.execute("SELECT player_name FROM players ORDER BY player_name").fetchall()]
        self._players_by_token: dict[str, list[str]] = {}
        for name in self._players:
            lowered = name.lower()
            tokens = set(lowered.replace(".", " ").split())
            tokens.add(lowered.replace(" ", ""))
            for token in tokens:
                self._players_by_token.setdefault(token, []).append(name)

        self.metric_map = {
            "six": "sixes",
            "sixes": "sixes",
            "runs": "runs",
            "run": "runs",
            "strike rate": "strike_rate",
            "sr": "strike_rate",
            "wickets": "wickets",
            "wicket": "wickets",
            "economy": "economy",
            "eco": "economy",
        }

    def extract_season(self, text: str) -> int | None:
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else None

    def resolve_metric(self, text: str) -> str | None:
        for key, value in self.metric_map.items():
            if key in text:
                return value
        return None

    def resolve_player(self, text: str) -> str | None:
        players = self.resolve_players_from_text(text)
        return players[0] if players else None

    def resolve_players_from_text(self, text: str) -> list[str]:
        hits: list[str] = []
        lowered = text.lower()
        for player in self._players:
            p = player.lower()
            if p in lowered or p.replace(" ", "") in lowered:
                hits.append(player)

        if hits:
            return sorted(set(hits), key=hits.index)

        for token, mapped in self._players_by_token.items():
            if len(token) < 3:
                continue
            if re.search(rf"\b{re.escape(token)}\b", lowered):
                if len(mapped) == 1:
                    hits.append(mapped[0])
        return sorted(set(hits), key=hits.index)

    def resolve_player_after_keyword(self, text: str, keyword: str) -> str | None:
        idx = text.find(keyword)
        if idx < 0:
            return None
        tail = text[idx + len(keyword):].strip()
        return self.resolve_player(tail)


class QueryExecutor:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _safe_readonly(self, sql: str) -> None:
        stripped = sql.strip().lower()
        if not stripped.startswith("select"):
            raise ValueError("Only read-only SELECT queries are permitted")
        if READONLY_BLOCKLIST.search(stripped):
            raise ValueError("Blocked SQL keyword detected")

    def _run(self, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        self._safe_readonly(sql)
        started = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        log_sql("ask_query", sql, params, started, row_count=len(rows))
        return rows

    def execute(self, plan: QueryPlan) -> dict[str, Any]:
        if plan.intent not in ALLOWED_INTENTS:
            raise ValueError("Unsupported intent")

        if plan.intent == "PLAYER_SEASON_STAT":
            return self._player_season_stat(plan)
        if plan.intent == "PLAYER_BEST_SEASON":
            return self._player_best_season(plan)
        if plan.intent == "MATCH_PLAYER_OF_MATCH":
            return self._match_player_of_match(plan)
        if plan.intent == "MOST_SIXES_AGAINST_BOWLER":
            return self._most_sixes_against_bowler(plan)
        if plan.intent == "PLAYER_PHASE_COMPARISON":
            return self._player_phase_comparison(plan)

        raise ValueError("Unsupported intent")

    def _player_season_stat(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        season = int(plan.entities["season"])
        metric = str(plan.metric)

        if metric == "sixes":
            rows = self._run(
                """
                SELECT COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS value,
                       COUNT(*) AS deliveries
                FROM deliveries
                WHERE season_id = ? AND batter = ?
                """,
                (season, player),
            )
        elif metric == "runs":
            rows = self._run(
                """
                SELECT COALESCE(SUM(batter_runs), 0) AS value,
                       COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls
                FROM deliveries
                WHERE season_id = ? AND batter = ?
                """,
                (season, player),
            )
        elif metric == "strike_rate":
            rows = self._run(
                """
                SELECT
                    COALESCE(SUM(batter_runs), 0) AS runs,
                    COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls
                FROM deliveries
                WHERE season_id = ? AND batter = ?
                """,
                (season, player),
            )
        elif metric == "wickets":
            rows = self._run(
                """
                SELECT COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS value,
                       COALESCE(SUM(legal_ball), 0) AS balls
                FROM deliveries
                WHERE season_id = ? AND bowler = ?
                """,
                (season, player),
            )
        elif metric == "economy":
            rows = self._run(
                """
                SELECT
                    COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs,
                    COALESCE(SUM(legal_ball), 0) AS balls
                FROM deliveries
                WHERE season_id = ? AND bowler = ?
                """,
                (season, player),
            )
        else:
            raise ValueError("Unsupported metric")

        row = rows[0]
        if metric == "strike_rate":
            balls = int(row["balls"])
            value = round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0
        elif metric == "economy":
            balls = int(row["balls"])
            value = round(int(row["runs"]) / (balls / 6.0), 2) if balls else 0.0
        else:
            value = int(row["value"])

        return {
            "value": value,
            "label": f"{player} {metric.replace('_', ' ')} in IPL {season}",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"season={season}, player={player}",
            },
        }

    def _player_best_season(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        rows = self._run(
            """
            SELECT season_id,
                   COALESCE(SUM(batter_runs), 0) AS runs,
                   COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls
            FROM deliveries
            WHERE batter = ?
            GROUP BY season_id
            ORDER BY runs DESC, season_id ASC
            LIMIT 1
            """,
            (player,),
        )
        if not rows:
            raise ValueError("No records found for player")

        row = rows[0]
        balls = int(row["balls"])
        sr = round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0
        return {
            "value": {
                "season": int(row["season_id"]),
                "runs": int(row["runs"]),
                "strike_rate": sr,
            },
            "label": f"Best batting season for {player}",
            "evidence": {"source": "MatchGenome IPL database", "scope": f"all seasons, player={player}"},
        }

    def _match_player_of_match(self, plan: QueryPlan) -> dict[str, Any]:
        season = int(plan.entities["season"])
        final_only = bool(plan.entities.get("stage") == "final")
        stage_filter = " AND LOWER(COALESCE(match_type, '')) = 'final'" if final_only else ""
        rows = self._run(
            """
            SELECT match_id, match_date, player_of_match, team_a_display, team_b_display
            FROM match_metadata
            WHERE season_id = ?
            """
            + stage_filter
            + " ORDER BY match_date, match_id LIMIT 1",
            (season,),
        )
        if not rows:
            raise ValueError("No matching match metadata found")

        row = rows[0]
        return {
            "value": {
                "player_of_match": row["player_of_match"],
                "match_id": int(row["match_id"]),
                "match_date": row["match_date"],
                "teams": [row["team_a_display"], row["team_b_display"]],
            },
            "label": f"Player of the match in IPL {season}{' final' if final_only else ''}",
            "evidence": {"source": "MatchGenome IPL database", "scope": f"match_metadata season={season}"},
        }

    def _most_sixes_against_bowler(self, plan: QueryPlan) -> dict[str, Any]:
        bowler = str(plan.entities["bowler"])
        season = plan.entities.get("season")
        season_filter = " AND season_id = ?" if isinstance(season, int) else ""
        params: tuple[Any, ...]
        if isinstance(season, int):
            params = (bowler, int(season))
        else:
            params = (bowler,)

        rows = self._run(
            """
            SELECT batter,
                   COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes,
                   COUNT(*) AS balls
            FROM deliveries
            WHERE bowler = ?
            """
            + season_filter
            + " GROUP BY batter ORDER BY sixes DESC, balls DESC, batter ASC LIMIT 1",
            params,
        )
        if not rows:
            raise ValueError("No batter vs bowler history found")
        row = rows[0]
        return {
            "value": {
                "batter": row["batter"],
                "sixes": int(row["sixes"]),
                "balls": int(row["balls"]),
            },
            "label": f"Most sixes against {bowler}",
            "evidence": {"source": "MatchGenome IPL database", "scope": f"bowler={bowler}"},
        }

    def _player_phase_comparison(self, plan: QueryPlan) -> dict[str, Any]:
        players = [str(p) for p in plan.entities["players"]]
        season = plan.entities.get("season")
        season_filter = " AND season_id = ?" if isinstance(season, int) else ""

        result_rows: list[dict[str, Any]] = []
        for player in players:
            params: tuple[Any, ...]
            if isinstance(season, int):
                params = (player, int(season))
            else:
                params = (player,)
            rows = self._run(
                """
                WITH t AS (
                    SELECT *,
                           CASE WHEN over_number < 6 THEN 'powerplay'
                                WHEN over_number < 15 THEN 'middle'
                                ELSE 'death' END AS phase
                    FROM deliveries
                    WHERE batter = ?
                    """
                + season_filter
                + """
                )
                SELECT phase,
                       COALESCE(SUM(batter_runs), 0) AS runs,
                       COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls
                FROM t
                GROUP BY phase
                ORDER BY CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END
                """,
                params,
            )

            phases = []
            for row in rows:
                balls = int(row["balls"])
                phases.append(
                    {
                        "phase": row["phase"],
                        "runs": int(row["runs"]),
                        "balls": balls,
                        "strike_rate": round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0,
                    }
                )
            result_rows.append({"player": player, "phases": phases})

        return {
            "value": result_rows,
            "label": "Phase comparison",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"players={', '.join(players)}" + (f", season={season}" if isinstance(season, int) else ""),
            },
        }


class AskMatchGenomeEngine:
    def __init__(self, conn: sqlite3.Connection, provider: AskPlanProvider | None = None) -> None:
        self.conn = conn
        self.semantic = SemanticResolver(conn)
        self.provider = provider or RuleBasedPlanProvider()
        self.executor = QueryExecutor(conn)

    def _split_questions(self, text: str) -> list[str]:
        canonical = text.strip()
        if not canonical:
            return []
        chunks = re.split(r"\?|\n", canonical)
        parts: list[str] = []
        for chunk in chunks:
            c = chunk.strip(" ,")
            if not c:
                continue
            comma_split = re.split(r",\s*(?=how many|who|what|compare|show me|show|which)", c, flags=re.IGNORECASE)
            sub: list[str] = []
            for item in comma_split:
                sub.extend(
                    re.split(
                        r"\s+and\s+(?=how many|who|what|compare|show me|show|which)",
                        item,
                        flags=re.IGNORECASE,
                    )
                )
            for item in sub:
                item = item.strip(" ,")
                if item:
                    parts.append(item)
        return parts

    def ask(self, question: str) -> dict[str, Any]:
        sub_questions = self._split_questions(question)
        if not sub_questions:
            raise ValueError("Question is empty")

        responses: list[dict[str, Any]] = []
        last_player: str | None = None
        for sub in sub_questions:
            rewritten = sub
            if last_player and re.search(r"\b(his|her|their)\b", sub, flags=re.IGNORECASE):
                rewritten = re.sub(r"\b(his|her|their)\b", last_player, sub, flags=re.IGNORECASE)

            plan = self.provider.build_plan(rewritten, self.semantic)
            if plan is None:
                responses.append(
                    {
                        "question": sub,
                        "status": "unsupported",
                        "message": "I could not map this question to a supported IPL query yet.",
                    }
                )
                continue

            try:
                result = self.executor.execute(plan)
                if isinstance(plan.entities.get("player"), str):
                    last_player = str(plan.entities["player"])
                responses.append(
                    {
                        "question": sub,
                        "normalized_question": rewritten,
                        "status": "ok",
                        "query_plan": {
                            "intent": plan.intent,
                            "entities": plan.entities,
                            "metric": plan.metric,
                            "aggregation": plan.aggregation,
                            "scope": plan.scope,
                        },
                        "result": result,
                    }
                )
            except Exception as exc:
                responses.append(
                    {
                        "question": sub,
                        "normalized_question": rewritten,
                        "status": "error",
                        "query_plan": {
                            "intent": plan.intent,
                            "entities": plan.entities,
                            "metric": plan.metric,
                            "aggregation": plan.aggregation,
                            "scope": plan.scope,
                        },
                        "message": str(exc),
                    }
                )

        ok_count = sum(1 for item in responses if item["status"] == "ok")
        return {
            "question": question,
            "sub_questions": len(sub_questions),
            "answered": ok_count,
            "results": responses,
            "source": "local_sqlite",
        }

