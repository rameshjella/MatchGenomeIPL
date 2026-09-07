from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import sqlite3
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from .runtime_logging import log_sql

ALLOWED_INTENTS = {
    "PLAYER_SEASON_STAT",
    "PLAYER_BEST_SEASON",
    "PLAYER_PHASE_COMPARISON",
    "MOST_SIXES_AGAINST_BOWLER",
    "BOWLER_WICKETS_VS_TEAM",
    "COMPARE_TWO_PLAYERS",
    "RANKING_STAT",
    "MATCH_PLAYER_OF_MATCH",
    "MULTI_HOP_POM_RUNS_FINAL",
}

ALLOWED_METRICS = {
    "runs",
    "sixes",
    "wickets",
    "strike_rate",
    "economy",
}

READONLY_BLOCKLIST = re.compile(
    r"\b(insert|update|delete|drop|alter|attach|pragma|vacuum|create|replace)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryPlan:
    question: str
    intent: str
    entities: dict[str, Any]
    metric: str | None = None
    aggregation: str | None = None
    scope: str | None = None
    group_by: list[str] | None = None
    order_by: str | None = None
    limit: int | None = None
    evidence_required: bool = True


@dataclass
class ConversationContext:
    last_plan: QueryPlan | None = None


class AskPlanProvider(Protocol):
    def build_plan(self, question: str, semantic: "SemanticResolver", context: ConversationContext) -> QueryPlan | None:
        ...


class SemanticResolver:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.players = [str(r["player_name"]) for r in conn.execute("SELECT player_name FROM players ORDER BY player_name").fetchall()]
        self.players_lower = {p.lower(): p for p in self.players}

        self.player_aliases = {
            "dhoni": "MS Dhoni",
            "msd": "MS Dhoni",
            "mahi": "MS Dhoni",
            "virat": "V Kohli",
            "kohli": "V Kohli",
            "king kohli": "V Kohli",
            "rohit": "RG Sharma",
            "hitman": "RG Sharma",
            "bumrah": "JJ Bumrah",
            "jasprit": "JJ Bumrah",
        }

        self.metric_map = {
            "six": "sixes",
            "sixes": "sixes",
            "maximum": "sixes",
            "maximums": "sixes",
            "run": "runs",
            "runs": "runs",
            "strike rate": "strike_rate",
            "sr": "strike_rate",
            "wicket": "wickets",
            "wickets": "wickets",
            "economy": "economy",
            "eco": "economy",
        }

        team_rows = conn.execute(
            "SELECT DISTINCT historical_display_name FROM match_team_map WHERE historical_display_name IS NOT NULL ORDER BY historical_display_name"
        ).fetchall()
        teams = [str(r["historical_display_name"]) for r in team_rows]
        self.team_alias = {t.lower(): t for t in teams}
        self.team_alias.update({
            "csk": "Chennai Super Kings",
            "mi": "Mumbai Indians",
            "rcb": "Royal Challengers Bangalore",
            "srh": "Sunrisers Hyderabad",
            "kkr": "Kolkata Knight Riders",
            "rr": "Rajasthan Royals",
            "dc": "Delhi Capitals",
            "pbks": "Punjab Kings",
            "kxip": "Kings XI Punjab",
            "gt": "Gujarat Titans",
            "lsg": "Lucknow Super Giants",
        })

    def extract_season(self, text: str) -> int | None:
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else None

    def extract_limit(self, text: str) -> int:
        m = re.search(r"\btop\s+(\d{1,2})\b", text)
        if m:
            return max(1, min(25, int(m.group(1))))
        return 10

    def extract_phase(self, text: str) -> str | None:
        lowered = text.lower()
        if "powerplay" in lowered:
            return "powerplay"
        if "middle" in lowered:
            return "middle"
        if "death" in lowered:
            return "death"
        return None

    def resolve_metric(self, text: str) -> str | None:
        lowered = text.lower()
        for key, value in self.metric_map.items():
            if key in lowered:
                return value
        return None

    def resolve_players_from_text(self, text: str) -> list[str]:
        lowered = text.lower()
        found: list[str] = []

        for alias, mapped in self.player_aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                if mapped in self.players:
                    found.append(mapped)

        for player in self.players:
            p = player.lower()
            if p in lowered or p.replace(" ", "") in lowered:
                found.append(player)

        dedup: list[str] = []
        for name in found:
            if name not in dedup:
                dedup.append(name)
        return dedup

    def resolve_player(self, text: str) -> str | None:
        players = self.resolve_players_from_text(text)
        if len(players) == 1:
            return players[0]
        return players[0] if players else None

    def resolve_team(self, text: str) -> str | None:
        lowered = text.lower()
        for alias, canonical in self.team_alias.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return canonical
        return None


class RuleBasedPlanProvider:
    def build_plan(self, question: str, semantic: SemanticResolver, context: ConversationContext) -> QueryPlan | None:
        raw = question.strip()
        lowered = raw.lower()

        # Follow-up continuation: "What about 2015?"
        if lowered.startswith("what about") and context.last_plan is not None:
            season = semantic.extract_season(lowered)
            if season is not None:
                entities = dict(context.last_plan.entities)
                entities["season"] = season
                return QueryPlan(
                    question=raw,
                    intent=context.last_plan.intent,
                    entities=entities,
                    metric=context.last_plan.metric,
                    aggregation=context.last_plan.aggregation,
                    scope=context.last_plan.scope,
                    group_by=context.last_plan.group_by,
                    order_by=context.last_plan.order_by,
                    limit=context.last_plan.limit,
                )

        season = semantic.extract_season(lowered)
        metric = semantic.resolve_metric(lowered)
        phase = semantic.extract_phase(lowered)
        players = semantic.resolve_players_from_text(lowered)
        player = players[0] if players else None

        # Lightweight conversational carry-forward for pronoun follow-ups.
        if player is None and context.last_plan is not None and re.search(r"\b(his|her|their)\b", lowered):
            last_player = context.last_plan.entities.get("player")
            if isinstance(last_player, str) and last_player:
                player = last_player

        if not players and context.last_plan is not None and re.search(r"\b(his|her|their)\b", lowered):
            last_players = context.last_plan.entities.get("players")
            if isinstance(last_players, list):
                players = [str(x) for x in last_players if str(x)]

        if ("man of the match" in lowered or "player of the match" in lowered) and "how many runs" in lowered and "final" in lowered:
            if season is None:
                return None
            return QueryPlan(
                question=raw,
                intent="MULTI_HOP_POM_RUNS_FINAL",
                entities={"season": season},
                metric="runs",
                aggregation="lookup",
                scope="match",
            )

        if "who hit more" in lowered or ("compare" in lowered and metric in {"sixes", "runs", "strike_rate", "wickets", "economy"}):
            if len(players) >= 2:
                return QueryPlan(
                    question=raw,
                    intent="COMPARE_TWO_PLAYERS",
                    entities={"players": players[:2], "season": season, "phase": phase},
                    metric=metric or "runs",
                    aggregation="compare",
                    scope="batting" if (metric or "runs") in {"runs", "sixes", "strike_rate"} else "bowling",
                )

        if ("top" in lowered or "most" in lowered or "highest" in lowered) and season is not None and metric in {"sixes", "runs", "wickets", "strike_rate"}:
            return QueryPlan(
                question=raw,
                intent="RANKING_STAT",
                entities={"season": season, "phase": phase},
                metric=metric,
                aggregation="rank",
                scope="batting" if metric in {"runs", "sixes", "strike_rate"} else "bowling",
                order_by="desc",
                limit=semantic.extract_limit(lowered),
            )

        if "most sixes" in lowered and "against" in lowered:
            bowler = semantic.resolve_player(lowered.split("against", 1)[1]) if "against" in lowered else None
            if bowler:
                return QueryPlan(
                    question=raw,
                    intent="MOST_SIXES_AGAINST_BOWLER",
                    entities={"bowler": bowler, "season": season},
                    metric="sixes",
                    aggregation="max",
                    scope="batting",
                )

        if metric == "wickets" and "against" in lowered and player:
            team = semantic.resolve_team(lowered.split("against", 1)[1])
            if team:
                return QueryPlan(
                    question=raw,
                    intent="BOWLER_WICKETS_VS_TEAM",
                    entities={"bowler": player, "team": team, "season": season},
                    metric="wickets",
                    aggregation="sum",
                    scope="bowling",
                )

        if "best season" in lowered and player:
            return QueryPlan(
                question=raw,
                intent="PLAYER_BEST_SEASON",
                entities={"player": player},
                metric="runs",
                aggregation="max",
                scope="batting",
            )

        if "compare" in lowered and phase and len(players) >= 2:
            return QueryPlan(
                question=raw,
                intent="PLAYER_PHASE_COMPARISON",
                entities={"players": players[:2], "season": season, "phase": phase},
                metric="strike_rate",
                aggregation="compare",
                scope="phase",
            )

        if ("man of the match" in lowered or "player of the match" in lowered) and season is not None:
            return QueryPlan(
                question=raw,
                intent="MATCH_PLAYER_OF_MATCH",
                entities={"season": season, "stage": "final" if "final" in lowered else None},
                metric="player_of_match",
                aggregation="lookup",
                scope="match_metadata",
            )

        if player and season is not None and metric in ALLOWED_METRICS:
            return QueryPlan(
                question=raw,
                intent="PLAYER_SEASON_STAT",
                entities={"player": player, "season": season, "phase": phase},
                metric=metric,
                aggregation="sum" if metric in {"runs", "sixes", "wickets"} else "rate",
                scope="batting" if metric in {"runs", "sixes", "strike_rate"} else "bowling",
            )

        return None


class LlmAskPlanProvider:
    """Optional LLM provider that returns strict JSON query plans.

    This provider never executes SQL. It only proposes structured plans, which are validated.
    """

    def __init__(self) -> None:
        self.provider = os.getenv("MATCHGENOME_LLM_PROVIDER", "openai_compatible").strip().lower()
        self.base_url = os.getenv("MATCHGENOME_LLM_BASE_URL", "").strip()
        self.model = os.getenv("MATCHGENOME_LLM_MODEL", "").strip()
        self.api_key = os.getenv("MATCHGENOME_LLM_API_KEY", "").strip()
        self.anthropic_version = os.getenv("MATCHGENOME_ANTHROPIC_VERSION", "2023-06-01").strip()
        self.timeout_seconds = float(os.getenv("MATCHGENOME_LLM_TIMEOUT_SECONDS", "8"))

    def enabled(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def _post_openai_compatible(self, question: str, system_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with urlopen(req, timeout=self.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

    def _post_anthropic_compatible(self, question: str, system_prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": question}],
            "temperature": 0,
            "max_tokens": 512,
        }

        url = self.base_url.rstrip("/") + "/v1/messages"
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
            },
            method="POST",
        )

        with urlopen(req, timeout=self.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        content_blocks = body.get("content", [])
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        return text
        return ""

    def _normalize_entities(self, entities: dict[str, Any], semantic: SemanticResolver) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        def _to_int(value: Any) -> int | None:
            try:
                return int(str(value))
            except Exception:
                return None

        for key, value in entities.items():
            canonical_key = "season" if key == "year" else key
            if canonical_key == "season":
                season = _to_int(value)
                if season is not None:
                    normalized[canonical_key] = season
            elif canonical_key in {"player", "batter", "bowler", "striker", "non_striker"} and isinstance(value, str):
                resolved = semantic.resolve_player(value)
                normalized[canonical_key] = resolved or value
            elif canonical_key == "players" and isinstance(value, list):
                out: list[str] = []
                for item in value:
                    if not isinstance(item, str):
                        continue
                    resolved = semantic.resolve_player(item)
                    out.append(resolved or item)
                if out:
                    normalized[canonical_key] = out
            elif canonical_key in {"team", "opponent"} and isinstance(value, str):
                resolved_team = semantic.resolve_team(value)
                normalized["team"] = resolved_team or value
            elif canonical_key in {"phase", "stage"} and isinstance(value, str):
                normalized[canonical_key] = value.strip().lower()
            elif canonical_key == "limit":
                limit = _to_int(value)
                if limit is not None:
                    normalized[canonical_key] = limit
            else:
                normalized[canonical_key] = value

        return normalized

    def build_plan(self, question: str, semantic: SemanticResolver, context: ConversationContext) -> QueryPlan | None:
        if not self.enabled():
            return None

        system_prompt = (
            "You convert IPL natural language questions into a strict JSON query plan. "
            "Return JSON only with keys: intent, entities, metric, aggregation, scope, limit. "
            "Use supported intents only: "
            + ",".join(sorted(ALLOWED_INTENTS))
            + "."
        )

        try:
            if self.provider in {"anthropic", "anthropic_compatible"}:
                content = self._post_anthropic_compatible(question, system_prompt)
            else:
                content = self._post_openai_compatible(question, system_prompt)
        except Exception:
            return None

        if not content:
            return None

        try:
            parsed = json.loads(content)
        except Exception:
            return None

        if "questions" in parsed and isinstance(parsed["questions"], list) and parsed["questions"]:
            parsed = parsed["questions"][0]

        if not isinstance(parsed, dict):
            return None

        intent = str(parsed.get("intent", "")).strip()
        entities = parsed.get("entities", {})
        if not isinstance(entities, dict):
            entities = {}
        entities = self._normalize_entities(entities, semantic)

        return QueryPlan(
            question=question,
            intent=intent,
            entities=entities,
            metric=str(parsed.get("metric")) if parsed.get("metric") is not None else None,
            aggregation=str(parsed.get("aggregation")) if parsed.get("aggregation") is not None else None,
            scope=str(parsed.get("scope")) if parsed.get("scope") is not None else None,
            limit=int(parsed.get("limit")) if parsed.get("limit") is not None else None,
        )


class CompositePlanProvider:
    def __init__(self, primary: AskPlanProvider, fallback: AskPlanProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def build_plan(self, question: str, semantic: SemanticResolver, context: ConversationContext) -> QueryPlan | None:
        first = self.primary.build_plan(question, semantic, context)
        if first is not None:
            return first
        return self.fallback.build_plan(question, semantic, context)


class QueryPlanValidator:
    def validate(self, plan: QueryPlan) -> None:
        if plan.intent not in ALLOWED_INTENTS:
            raise ValueError("Unsupported intent")
        if plan.metric is not None and plan.metric not in ALLOWED_METRICS and plan.metric != "player_of_match":
            raise ValueError("Unsupported metric")

        entities = plan.entities
        if not isinstance(entities, dict):
            raise ValueError("entities must be an object")

        def _require(keys: list[str]) -> None:
            missing = [k for k in keys if k not in entities or entities[k] in (None, "")]
            if missing:
                raise ValueError(f"Missing required entities: {', '.join(missing)}")

        allowed_entity_keys: dict[str, set[str]] = {
            "PLAYER_SEASON_STAT": {"player", "season", "phase"},
            "PLAYER_BEST_SEASON": {"player"},
            "PLAYER_PHASE_COMPARISON": {"players", "season", "phase"},
            "MOST_SIXES_AGAINST_BOWLER": {"bowler", "season"},
            "BOWLER_WICKETS_VS_TEAM": {"bowler", "team", "season"},
            "COMPARE_TWO_PLAYERS": {"players", "season", "phase"},
            "RANKING_STAT": {"season", "phase"},
            "MATCH_PLAYER_OF_MATCH": {"season", "stage"},
            "MULTI_HOP_POM_RUNS_FINAL": {"season"},
        }

        extras = [k for k in entities if k not in allowed_entity_keys.get(plan.intent, set())]
        if extras:
            raise ValueError(f"Unsupported entity fields: {', '.join(sorted(extras))}")

        if plan.limit is not None and (plan.limit < 1 or plan.limit > 25):
            raise ValueError("limit must be between 1 and 25")

        season = entities.get("season")
        if season is not None and not isinstance(season, int):
            raise ValueError("season must be an integer")

        if plan.intent == "PLAYER_SEASON_STAT":
            _require(["player", "season"])
        elif plan.intent == "PLAYER_BEST_SEASON":
            _require(["player"])
        elif plan.intent == "PLAYER_PHASE_COMPARISON":
            _require(["players"])
        elif plan.intent == "MOST_SIXES_AGAINST_BOWLER":
            _require(["bowler"])
        elif plan.intent == "BOWLER_WICKETS_VS_TEAM":
            _require(["bowler", "team"])
        elif plan.intent == "COMPARE_TWO_PLAYERS":
            _require(["players"])
            if not isinstance(entities.get("players"), list) or len(entities.get("players", [])) < 2:
                raise ValueError("players list must have at least two values")
        elif plan.intent == "RANKING_STAT":
            _require(["season"])
        elif plan.intent == "MATCH_PLAYER_OF_MATCH":
            _require(["season"])
        elif plan.intent == "MULTI_HOP_POM_RUNS_FINAL":
            _require(["season"])


class QueryExecutor:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _safe_readonly(self, sql: str) -> None:
        stripped = sql.strip().lower()
        if not stripped.startswith("select"):
            raise ValueError("Only read-only SELECT queries are permitted")
        if READONLY_BLOCKLIST.search(stripped):
            raise ValueError("Blocked SQL keyword detected")

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        self._safe_readonly(sql)
        started = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        log_sql("ask_query", sql, params, started, row_count=len(rows))
        return rows

    def execute(self, plan: QueryPlan) -> dict[str, Any]:
        if plan.intent == "PLAYER_SEASON_STAT":
            return self._player_season_stat(plan)
        if plan.intent == "PLAYER_BEST_SEASON":
            return self._player_best_season(plan)
        if plan.intent == "PLAYER_PHASE_COMPARISON":
            return self._player_phase_comparison(plan)
        if plan.intent == "MOST_SIXES_AGAINST_BOWLER":
            return self._most_sixes_against_bowler(plan)
        if plan.intent == "BOWLER_WICKETS_VS_TEAM":
            return self._bowler_wickets_vs_team(plan)
        if plan.intent == "COMPARE_TWO_PLAYERS":
            return self._compare_two_players(plan)
        if plan.intent == "RANKING_STAT":
            return self._ranking_stat(plan)
        if plan.intent == "MATCH_PLAYER_OF_MATCH":
            return self._match_player_of_match(plan)
        if plan.intent == "MULTI_HOP_POM_RUNS_FINAL":
            return self._multi_hop_pom_runs_final(plan)
        raise ValueError("Unsupported intent")

    def _phase_filter(self, phase: str | None) -> str:
        if phase == "powerplay":
            return " AND over_number < 6"
        if phase == "middle":
            return " AND over_number BETWEEN 6 AND 14"
        if phase == "death":
            return " AND over_number >= 15"
        return ""

    def _player_season_stat(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        season = int(plan.entities["season"])
        metric = str(plan.metric)
        phase = plan.entities.get("phase")
        phase_filter = self._phase_filter(str(phase) if phase else None)

        if metric == "sixes":
            row = self._run(
                "SELECT COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS value FROM deliveries WHERE season_id = ? AND batter = ?" + phase_filter,
                (season, player),
            )[0]
            value: Any = int(row["value"])
        elif metric == "runs":
            row = self._run(
                "SELECT COALESCE(SUM(batter_runs), 0) AS value FROM deliveries WHERE season_id = ? AND batter = ?" + phase_filter,
                (season, player),
            )[0]
            value = int(row["value"])
        elif metric == "strike_rate":
            row = self._run(
                "SELECT COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls FROM deliveries WHERE season_id = ? AND batter = ?" + phase_filter,
                (season, player),
            )[0]
            balls = int(row["balls"])
            value = round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0
        elif metric == "wickets":
            row = self._run(
                "SELECT COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS value FROM deliveries WHERE season_id = ? AND bowler = ?" + phase_filter,
                (season, player),
            )[0]
            value = int(row["value"])
        elif metric == "economy":
            row = self._run(
                "SELECT COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs, COALESCE(SUM(legal_ball), 0) AS balls FROM deliveries WHERE season_id = ? AND bowler = ?" + phase_filter,
                (season, player),
            )[0]
            balls = int(row["balls"])
            value = round(int(row["runs"]) / (balls / 6.0), 2) if balls else 0.0
        else:
            raise ValueError("Unsupported metric")

        return {
            "value": value,
            "label": f"{player} {metric.replace('_', ' ')} in IPL {season}",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"season={season}, player={player}" + (f", phase={phase}" if phase else ""),
            },
        }

    def _player_best_season(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        row = self._run(
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
        )[0]
        balls = int(row["balls"])
        return {
            "value": {
                "season": int(row["season_id"]),
                "runs": int(row["runs"]),
                "strike_rate": round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0,
            },
            "label": f"Best batting season for {player}",
            "evidence": {"source": "MatchGenome IPL database", "scope": f"all seasons, player={player}"},
        }

    def _player_phase_comparison(self, plan: QueryPlan) -> dict[str, Any]:
        players = [str(x) for x in plan.entities["players"][:2]]
        season = plan.entities.get("season")
        phase = plan.entities.get("phase")

        value: list[dict[str, Any]] = []
        for player in players:
            sql = (
                "SELECT CASE WHEN over_number < 6 THEN 'powerplay' WHEN over_number < 15 THEN 'middle' ELSE 'death' END AS phase, "
                "COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls "
                "FROM deliveries WHERE batter = ?"
            )
            params: tuple[Any, ...] = (player,)
            if isinstance(season, int):
                sql += " AND season_id = ?"
                params += (season,)
            sql += " GROUP BY phase ORDER BY CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END"
            rows = self._run(sql, params)
            if phase:
                rows = [r for r in rows if str(r["phase"]) == str(phase)]
            phases = []
            for row in rows:
                balls = int(row["balls"])
                phases.append(
                    {
                        "phase": str(row["phase"]),
                        "runs": int(row["runs"]),
                        "balls": balls,
                        "strike_rate": round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0,
                    }
                )
            value.append({"player": player, "phases": phases})

        return {
            "value": value,
            "label": "Player phase comparison",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"players={players}" + (f", season={season}" if isinstance(season, int) else "") + (f", phase={phase}" if phase else ""),
            },
        }

    def _most_sixes_against_bowler(self, plan: QueryPlan) -> dict[str, Any]:
        bowler = str(plan.entities["bowler"])
        season = plan.entities.get("season")
        sql = (
            "SELECT batter, COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes, COUNT(*) AS balls "
            "FROM deliveries WHERE bowler = ?"
        )
        params: tuple[Any, ...] = (bowler,)
        if isinstance(season, int):
            sql += " AND season_id = ?"
            params += (season,)
        sql += " GROUP BY batter ORDER BY sixes DESC, balls DESC, batter ASC LIMIT 1"
        row = self._run(sql, params)[0]
        return {
            "value": {"batter": row["batter"], "sixes": int(row["sixes"]), "balls": int(row["balls"])},
            "label": f"Most sixes against {bowler}",
            "evidence": {"source": "MatchGenome IPL database", "scope": f"bowler={bowler}"},
        }

    def _bowler_wickets_vs_team(self, plan: QueryPlan) -> dict[str, Any]:
        bowler = str(plan.entities["bowler"])
        team = str(plan.entities["team"])
        season = plan.entities.get("season")

        sql = (
            "SELECT COALESCE(SUM(CASE WHEN d.is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets, COUNT(*) AS balls "
            "FROM deliveries d "
            "LEFT JOIN match_team_map m ON m.match_id = d.match_id AND m.internal_team_code = d.team_batting "
            "WHERE d.bowler = ? AND COALESCE(m.historical_display_name, d.team_batting) = ?"
        )
        params: tuple[Any, ...] = (bowler, team)
        if isinstance(season, int):
            sql += " AND d.season_id = ?"
            params += (season,)
        row = self._run(sql, params)[0]
        return {
            "value": {"wickets": int(row["wickets"]), "balls": int(row["balls"])},
            "label": f"{bowler} wickets against {team}",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"bowler={bowler}, opponent={team}" + (f", season={season}" if isinstance(season, int) else ""),
            },
        }

    def _compare_two_players(self, plan: QueryPlan) -> dict[str, Any]:
        players = [str(x) for x in plan.entities["players"][:2]]
        season = plan.entities.get("season")
        phase = plan.entities.get("phase")
        metric = str(plan.metric or "runs")

        values: list[dict[str, Any]] = []
        for player in players:
            q = QueryPlan(
                question=plan.question,
                intent="PLAYER_SEASON_STAT",
                entities={"player": player, "season": int(season) if isinstance(season, int) else 0, "phase": phase},
                metric=metric,
                aggregation="sum",
                scope=plan.scope,
            )
            if not isinstance(season, int):
                if metric in {"runs", "sixes", "strike_rate"}:
                    sql = "SELECT COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls FROM deliveries WHERE batter = ?"
                    params: tuple[Any, ...] = (player,)
                    sql += self._phase_filter(str(phase) if phase else None)
                    row = self._run(sql, params)[0]
                    if metric == "runs":
                        v = int(row["runs"])
                    elif metric == "sixes":
                        v = int(row["sixes"])
                    else:
                        balls = int(row["balls"])
                        v = round((int(row["runs"]) * 100.0 / balls), 2) if balls else 0.0
                else:
                    sql = "SELECT COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets, COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs, COALESCE(SUM(legal_ball), 0) AS balls FROM deliveries WHERE bowler = ?"
                    params = (player,)
                    sql += self._phase_filter(str(phase) if phase else None)
                    row = self._run(sql, params)[0]
                    if metric == "wickets":
                        v = int(row["wickets"])
                    else:
                        balls = int(row["balls"])
                        v = round(int(row["runs"]) / (balls / 6.0), 2) if balls else 0.0
                values.append({"player": player, "value": v})
            else:
                result = self._player_season_stat(q)
                values.append({"player": player, "value": result["value"]})

        better = values[0]["player"] if values[0]["value"] >= values[1]["value"] else values[1]["player"]
        return {
            "value": {"metric": metric, "players": values, "better": better},
            "label": f"Comparison: {players[0]} vs {players[1]}",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"metric={metric}" + (f", season={season}" if isinstance(season, int) else "") + (f", phase={phase}" if phase else ""),
            },
        }

    def _ranking_stat(self, plan: QueryPlan) -> dict[str, Any]:
        season = int(plan.entities["season"])
        phase = plan.entities.get("phase")
        metric = str(plan.metric)
        limit = int(plan.limit or 10)

        if metric in {"runs", "sixes", "strike_rate"}:
            select = "batter AS player"
            group = "batter"
            phase_filter = self._phase_filter(str(phase) if phase else None)
            sql = (
                "SELECT "
                + select
                + ", COALESCE(SUM(batter_runs), 0) AS runs, "
                "COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes, "
                "COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls "
                "FROM deliveries WHERE season_id = ?"
                + phase_filter
                + f" GROUP BY {group} "
            )
            if metric == "runs":
                sql += "ORDER BY runs DESC, player ASC LIMIT ?"
            elif metric == "sixes":
                sql += "ORDER BY sixes DESC, player ASC LIMIT ?"
            else:
                sql += "HAVING balls >= 24 ORDER BY (runs * 100.0 / balls) DESC, balls DESC, player ASC LIMIT ?"
            rows = self._run(sql, (season, limit))
            ranking = []
            for r in rows:
                balls = int(r["balls"])
                ranking.append(
                    {
                        "player": r["player"],
                        "runs": int(r["runs"]),
                        "sixes": int(r["sixes"]),
                        "balls": balls,
                        "strike_rate": round((int(r["runs"]) * 100.0 / balls), 2) if balls else 0.0,
                    }
                )
        else:
            phase_filter = self._phase_filter(str(phase) if phase else None)
            sql = (
                "SELECT bowler AS player, COALESCE(SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets, "
                "COALESCE(SUM(total_runs - bye_runs - leg_bye_runs), 0) AS runs, COALESCE(SUM(legal_ball), 0) AS balls "
                "FROM deliveries WHERE season_id = ?"
                + phase_filter
                + " GROUP BY bowler "
            )
            if metric == "wickets":
                sql += "ORDER BY wickets DESC, player ASC LIMIT ?"
            else:
                sql += "HAVING balls >= 24 ORDER BY (runs * 1.0 / (balls / 6.0)) ASC, balls DESC, player ASC LIMIT ?"
            rows = self._run(sql, (season, limit))
            ranking = []
            for r in rows:
                balls = int(r["balls"])
                ranking.append(
                    {
                        "player": r["player"],
                        "wickets": int(r["wickets"]),
                        "balls": balls,
                        "economy": round(int(r["runs"]) / (balls / 6.0), 2) if balls else 0.0,
                    }
                )

        return {
            "value": ranking,
            "label": f"Top {limit} by {metric} in IPL {season}",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"season={season}, metric={metric}" + (f", phase={phase}" if phase else ""),
            },
        }

    def _match_player_of_match(self, plan: QueryPlan) -> dict[str, Any]:
        season = int(plan.entities["season"])
        final_only = bool(plan.entities.get("stage") == "final")
        sql = "SELECT match_id, match_date, player_of_match, team_a_display, team_b_display FROM match_metadata WHERE season_id = ?"
        if final_only:
            sql += " AND LOWER(COALESCE(match_type, '')) = 'final'"
        sql += " ORDER BY match_date, match_id LIMIT 1"
        rows = self._run(sql, (season,))
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

    def _multi_hop_pom_runs_final(self, plan: QueryPlan) -> dict[str, Any]:
        season = int(plan.entities["season"])
        match_rows = self._run(
            "SELECT match_id, player_of_match, team_a_display, team_b_display, match_date FROM match_metadata WHERE season_id = ? AND LOWER(COALESCE(match_type, '')) = 'final' ORDER BY match_date, match_id LIMIT 1",
            (season,),
        )
        if not match_rows:
            raise ValueError("No final match metadata found for this season")

        match = match_rows[0]
        pom = str(match["player_of_match"] or "").strip()
        if not pom:
            raise ValueError("Player of the match not available for this final")

        runs_row = self._run(
            "SELECT COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls FROM deliveries WHERE match_id = ? AND batter = ?",
            (int(match["match_id"]), pom),
        )[0]

        runs = int(runs_row["runs"])
        balls = int(runs_row["balls"])
        return {
            "value": {
                "match_id": int(match["match_id"]),
                "player_of_match": pom,
                "runs": runs,
                "balls": balls,
                "strike_rate": round((runs * 100.0 / balls), 2) if balls else 0.0,
                "teams": [match["team_a_display"], match["team_b_display"]],
                "match_date": match["match_date"],
            },
            "label": f"Player of the match in IPL {season} final and his runs",
            "evidence": {
                "source": "MatchGenome IPL database",
                "scope": f"season={season}, final, match_id={int(match['match_id'])}",
            },
        }


class AskMatchGenomeEngine:
    def __init__(self, conn: sqlite3.Connection, provider: AskPlanProvider | None = None) -> None:
        self.conn = conn
        self.semantic = SemanticResolver(conn)
        rule_provider = RuleBasedPlanProvider()
        llm_provider = LlmAskPlanProvider()
        self.provider = provider or CompositePlanProvider(llm_provider, rule_provider)
        self.validator = QueryPlanValidator()
        self.executor = QueryExecutor(conn)
        self.context = ConversationContext()

    def _split_questions(self, text: str) -> list[str]:
        canonical = text.strip()
        if not canonical:
            return []
        chunks = re.split(r"[?\n]", canonical)
        out: list[str] = []
        for chunk in chunks:
            piece = chunk.strip(" ,")
            if not piece:
                continue
            comma_parts = re.split(r",\s*(?=how many|who|what|compare|show|which|in \d{4})", piece, flags=re.IGNORECASE)
            for item in comma_parts:
                and_parts = re.split(r"\s+and\s+(?=how many|who|what|compare|show|which)", item, flags=re.IGNORECASE)
                for sub in and_parts:
                    sub = sub.strip(" ,")
                    if sub:
                        out.append(sub)
        return out

    def ask(self, question: str) -> dict[str, Any]:
        sub_questions = self._split_questions(question)
        if not sub_questions:
            raise ValueError("Question is empty")

        results: list[dict[str, Any]] = []
        for sub in sub_questions:
            plan = self.provider.build_plan(sub, self.semantic, self.context)
            if plan is None:
                results.append(
                    {
                        "question": sub,
                        "status": "unsupported",
                        "message": "MatchGenome does not currently support this question shape with verified local data.",
                    }
                )
                continue

            try:
                self.validator.validate(plan)
                answer = self.executor.execute(plan)
                self.context.last_plan = plan
                results.append(
                    {
                        "question": sub,
                        "status": "ok",
                        "query_plan": {
                            "intent": plan.intent,
                            "entities": plan.entities,
                            "metric": plan.metric,
                            "aggregation": plan.aggregation,
                            "scope": plan.scope,
                            "limit": plan.limit,
                        },
                        "result": answer,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "question": sub,
                        "status": "error",
                        "query_plan": {
                            "intent": plan.intent,
                            "entities": plan.entities,
                            "metric": plan.metric,
                            "aggregation": plan.aggregation,
                            "scope": plan.scope,
                            "limit": plan.limit,
                        },
                        "message": str(exc),
                    }
                )

        answered = sum(1 for item in results if item["status"] == "ok")
        return {
            "question": question,
            "sub_questions": len(sub_questions),
            "answered": answered,
            "results": results,
            "source": "local_sqlite",
            "planner": "llm+rule_fallback" if isinstance(self.provider, CompositePlanProvider) else "custom",
        }

