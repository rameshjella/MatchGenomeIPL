from __future__ import annotations

from dataclasses import dataclass, field
import ast
import difflib
import json
import os
import re
import sqlite3
import time
from typing import Any, Protocol
from urllib.request import Request, urlopen

from .ipl_knowledge import (
    ensure_knowledge_bootstrap,
    list_fixtures,
    list_results,
    lookup_player_fact,
    points_table,
    top_performers,
)
from .runtime_logging import log_sql

READONLY_BLOCKLIST = re.compile(
    r"\b(insert|update|delete|drop|alter|attach|pragma|vacuum|create|replace|reindex|analyze)\b",
    re.IGNORECASE,
)

MAX_LIMIT = 25
ALLOWED_OPERATIONS = {
    "aggregate",
    "lookup",
    "rank",
    "compare",
    "trend",
    "distribution",
    "clarify",
    "knowledge_lookup",
    "fixtures",
    "results",
    "points_table",
    "team_season_info",
    "top_performers",
    "prediction_info",
}


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    aliases: tuple[str, ...]
    entity_scopes: tuple[str, ...]
    unit: str
    description: str


@dataclass(frozen=True)
class QueryPlan:
    question: str
    operation: str
    entity: str
    entities: dict[str, Any] = field(default_factory=dict)
    metric: str | None = None
    metrics: list[str] | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    group_by: list[str] | None = None
    order_by: str | None = None
    limit: int | None = None
    threshold: dict[str, Any] | None = None


@dataclass
class ConversationContext:
    last_plan: QueryPlan | None = None
    last_entities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityResolution:
    value: str | None
    candidates: list[str]
    ambiguous: bool


class AskPlanProvider(Protocol):
    def build_plan(self, question: str, semantic: "SemanticResolver", context: ConversationContext) -> QueryPlan | None:
        ...


class SemanticResolver:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.metric_registry = self._build_metric_registry()
        self.player_aliases = self._build_player_aliases()
        self.team_aliases = self._build_team_aliases()
        self.player_activity = self._build_player_activity()
        self.player_knowledge_rank = self._build_player_knowledge_rank()

    def _build_metric_registry(self) -> dict[str, MetricDefinition]:
        defs = [
            MetricDefinition("runs", ("run", "runs", "scored"), ("batting",), "runs", "Total batter runs."),
            MetricDefinition("balls", ("ball", "balls"), ("batting", "bowling"), "balls", "Balls faced/bowled."),
            MetricDefinition("fours", ("four", "fours", "boundaries"), ("batting",), "count", "Fours hit by batter."),
            MetricDefinition("sixes", ("six", "sixes", "maximum", "maximums"), ("batting",), "count", "Sixes hit by batter."),
            MetricDefinition("dot_balls", ("dot", "dots", "dot balls", "dot-ball"), ("batting", "bowling"), "count", "Dot balls."),
            MetricDefinition("dot_ball_pct", ("dot ball percentage", "dot percentage"), ("batting", "bowling"), "percent", "Dot-ball percentage."),
            MetricDefinition("strike_rate", ("strike rate", "sr", "batting strike rate", "scoring rate", "run rate"), ("batting",), "runs/100 balls", "Batting strike rate."),
            MetricDefinition("average", ("average", "batting average"), ("batting",), "runs/dismissal", "Batting average."),
            MetricDefinition("wickets", ("wicket", "wickets"), ("bowling",), "count", "Wickets taken."),
            MetricDefinition("runs_conceded", ("runs conceded", "conceded"), ("bowling",), "runs", "Runs conceded by bowler."),
            MetricDefinition("legal_balls", ("legal balls", "valid balls"), ("bowling",), "balls", "Legal balls bowled."),
            MetricDefinition("economy", ("economy", "economy rate", "econ"), ("bowling",), "runs/over", "Bowling economy."),
            MetricDefinition("bowling_strike_rate", ("bowling strike rate",), ("bowling",), "balls/wicket", "Balls per wicket."),
            MetricDefinition("run_rate", ("team run rate", "innings run rate", "run rate"), ("team", "innings"), "runs/over", "Team/innings run rate."),
            MetricDefinition("player_of_match", ("player of the match", "man of the match"), ("match",), "text", "Player of the match lookup."),
            MetricDefinition("result", ("result", "winner", "what happened"), ("match",), "text", "Match result summary lookup."),
        ]
        return {d.name: d for d in defs}

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().replace("\u2019", "'")
        lowered = re.sub(r"\b([a-z]+)'s\b", r"\1", lowered)
        lowered = re.sub(r"[^a-z0-9\s.]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in re.split(r"\s+", SemanticResolver._normalize_text(text)) if t]

    def _build_player_aliases(self) -> dict[str, list[str]]:
        alias_map: dict[str, list[str]] = {}

        def normalize_player_name(raw: str) -> str | None:
            value = raw.strip()
            if not value:
                return None
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = ast.literal_eval(value)
                except Exception:
                    return None
                if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], str):
                    value = parsed[0].strip()
                else:
                    return None
            if "'," in value or value.startswith("["):
                return None
            return value

        def add(alias: str, player: str) -> None:
            key = self._normalize_text(alias)
            if not key:
                return
            bucket = alias_map.setdefault(key, [])
            if player not in bucket:
                bucket.append(player)

        rows = self.conn.execute("SELECT player_name FROM players ORDER BY player_name").fetchall()
        for row in rows:
            maybe_player = normalize_player_name(str(row["player_name"]))
            if maybe_player is None:
                continue
            player = maybe_player
            tokens = self._tokenize(player)
            if not tokens:
                continue
            first = tokens[0]
            surname = tokens[-1]
            add(" ".join(tokens), player)
            add("".join(tokens), player)
            add(surname, player)
            if len(first) >= 3:
                add(first, player)
            add(f"{first} {surname}", player)
            add(f"{first[0]} {surname}", player)
            add(f"{first[0]}. {surname}", player)
            if len(first) <= 3 and first.isalpha():
                add(f"{first[0]} {surname}", player)
                if len(first) >= 2:
                    add(f"{first}{surname[0]}", player)

        # Prefer curated/enriched identity aliases when available.
        try:
            rows = self.conn.execute(
                "SELECT alias_name, canonical_player_name FROM player_identity_alias ORDER BY canonical_player_name"
            ).fetchall()
            for row in rows:
                add(str(row["alias_name"]), str(row["canonical_player_name"]))
        except sqlite3.Error:
            pass
        return alias_map

    def _build_team_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        raw_rows = self.conn.execute(
            "SELECT DISTINCT team_batting AS team_name FROM deliveries UNION SELECT DISTINCT team_bowling AS team_name FROM deliveries"
        ).fetchall()
        for row in raw_rows:
            team = str(row["team_name"])
            key = self._normalize_text(team)
            aliases[key] = team

        rows = self.conn.execute(
            "SELECT DISTINCT historical_display_name FROM match_team_map WHERE historical_display_name IS NOT NULL"
        ).fetchall()
        for row in rows:
            team = str(row["historical_display_name"])
            key = self._normalize_text(team)
            aliases[key] = team
            acronym = "".join(word[0] for word in key.split() if word)
            if len(acronym) >= 2:
                aliases[acronym] = team

        try:
            rows = self.conn.execute(
                "SELECT alias_name, current_canonical_name FROM team_alias ta JOIN team_identity ti ON ti.team_identity_id = ta.team_identity_id"
            ).fetchall()
            for row in rows:
                alias_name = str(row["alias_name"])
                canonical = str(row["current_canonical_name"] or alias_name)
                aliases[self._normalize_text(alias_name)] = canonical
        except sqlite3.Error:
            pass

        return aliases

    def _build_player_activity(self) -> dict[str, int]:
        activity: dict[str, int] = {}
        rows = self.conn.execute(
            "SELECT batter AS player, COUNT(*) AS appearances FROM deliveries GROUP BY batter"
        ).fetchall()
        for row in rows:
            activity[str(row["player"])] = int(row["appearances"])

        rows = self.conn.execute(
            "SELECT bowler AS player, COUNT(*) AS appearances FROM deliveries GROUP BY bowler"
        ).fetchall()
        for row in rows:
            player = str(row["player"])
            activity[player] = activity.get(player, 0) + int(row["appearances"])
        return activity

    def _build_player_knowledge_rank(self) -> dict[str, float]:
        rank: dict[str, float] = {}
        try:
            rows = self.conn.execute(
                "SELECT canonical_player_name, verification_status FROM player_knowledge"
            ).fetchall()
        except sqlite3.Error:
            return rank
        for row in rows:
            player = str(row["canonical_player_name"])
            status = str(row["verification_status"] or "").strip().lower()
            if status == "verified":
                rank[player] = 16.0
            elif status == "provisional":
                rank[player] = 10.0
            elif status == "derived":
                rank[player] = 3.0
            else:
                rank[player] = 0.0
        return rank

    @staticmethod
    def _alias_specificity(alias: str) -> float:
        token_count = len(alias.split())
        if token_count >= 2:
            return 14.0
        return 8.0 if len(alias) >= 5 else 3.0

    def _score_player_candidate(self, lowered_query: str, candidate: str) -> float:
        score = min(self.player_activity.get(candidate, 0), 6000) / 220.0
        candidate_tokens = self._tokenize(candidate)
        query_tokens = set(lowered_query.split())
        overlap = len(query_tokens.intersection(candidate_tokens))
        score += overlap * 18.0
        score += self.player_knowledge_rank.get(candidate, 0.0)
        return score

    def extract_season(self, text: str) -> int | None:
        m = re.search(r"\b(20\d{2})\b", self._normalize_text(text))
        return int(m.group(1)) if m else None

    def extract_season_range(self, text: str) -> tuple[int, int] | None:
        normalized = self._normalize_text(text)
        m = re.search(r"\bfrom\s+(20\d{2})\s+to\s+(20\d{2})\b", normalized)
        if not m:
            m = re.search(r"\b(20\d{2})\s*[-/]\s*(20\d{2})\b", normalized)
        if not m:
            return None
        start = int(m.group(1))
        end = int(m.group(2))
        return (start, end) if start <= end else (end, start)

    def extract_phase(self, text: str) -> str | None:
        lowered = self._normalize_text(text)
        if "powerplay" in lowered:
            return "powerplay"
        if "death" in lowered:
            return "death"
        if "middle" in lowered:
            return "middle"
        return None

    def extract_limit(self, text: str, default: int = 10) -> int:
        lowered = self._normalize_text(text)
        m = re.search(r"\b(top|bottom)\s+(\d{1,2})\b", lowered)
        if m:
            return max(1, min(MAX_LIMIT, int(m.group(2))))
        return default

    def extract_bowling_type(self, text: str) -> str | None:
        lowered = self._normalize_text(text)
        if "left arm pace" in lowered or "left-arm pace" in lowered:
            return "left-arm pace"
        if "left arm spin" in lowered or "left-arm spin" in lowered:
            return "left-arm spin"
        if "right arm pace" in lowered or "right-arm pace" in lowered:
            return "right-arm pace"
        if "right arm spin" in lowered or "right-arm spin" in lowered:
            return "right-arm spin"
        return None

    def resolve_metrics(self, text: str, has_player_context: bool) -> list[str]:
        lowered = self._normalize_text(text)
        found: list[str] = []

        # Phrase-level disambiguation first to avoid "run" token overriding "run rate" intent.
        if "run rate" in lowered or "scoring rate" in lowered:
            found.append("strike_rate" if has_player_context else "run_rate")

        for name, definition in self.metric_registry.items():
            for alias in definition.aliases:
                if re.search(rf"\b{re.escape(alias)}\b", lowered):
                    if name == "run_rate":
                        if has_player_context:
                            found.append("strike_rate")
                        else:
                            found.append("run_rate")
                    else:
                        found.append(name)
                    break

        if not found and "run rate" in lowered and has_player_context:
            found.append("strike_rate")

        dedup: list[str] = []
        for metric in found:
            if metric not in dedup:
                dedup.append(metric)

        if ("run rate" in lowered or "scoring rate" in lowered) and "strike_rate" in dedup and len(dedup) > 1:
            dedup = [m for m in dedup if m != "runs"]
        return dedup

    def resolve_player_candidates(self, text: str) -> list[str]:
        lowered = self._normalize_text(text)
        tokens = lowered.split()
        hits: list[str] = []

        for width in (3, 2, 1):
            for i in range(len(tokens) - width + 1):
                alias = " ".join(tokens[i : i + width])
                for player in self.player_aliases.get(alias, []):
                    if player not in hits:
                        hits.append(player)

        # Full name fallback: "virat kohli" -> players with surname "kohli" and first initial "v"
        for i in range(len(tokens) - 1):
            first_token = tokens[i]
            surname = tokens[i + 1]
            surname_matches = self.player_aliases.get(surname, [])
            if len(surname_matches) > 1 and first_token:
                initial = first_token[0]
                filtered = [p for p in surname_matches if self._tokenize(p)[0].startswith(initial)]
                if filtered:
                    for player in filtered:
                        if player not in hits:
                            hits.append(player)

        return hits

    def resolve_player(self, text: str) -> EntityResolution:
        lowered = self._normalize_text(text)
        tokens = lowered.split()

        # Surname-only references with many collisions should not auto-resolve.
        for token in tokens:
            token_candidates = self.player_aliases.get(token, [])
            if len(token_candidates) < 2:
                continue
            surname_candidates = [p for p in token_candidates if self._tokenize(p) and self._tokenize(p)[-1] == token]
            if len(surname_candidates) >= 3:
                return EntityResolution(None, surname_candidates[:6], True)

        # Prefer explicit "firstname surname" -> first-initial + surname resolution when unique.
        for i in range(len(tokens) - 1):
            first_token = tokens[i]
            surname = tokens[i + 1]
            surname_matches = self.player_aliases.get(surname, [])
            if len(surname_matches) > 1 and first_token:
                initial = first_token[0]
                filtered = [p for p in surname_matches if self._tokenize(p)[0].startswith(initial)]
                if len(filtered) == 1:
                    return EntityResolution(filtered[0], filtered, False)

        candidates = self.resolve_player_candidates(text)
        if not candidates:
            # Possessive-name fallback: "Rohit's" -> dominant player for initial "r" when reliable.
            possessive_tokens = [m.group(1).lower() for m in re.finditer(r"\b([A-Za-z]{4,})'s\b", text)]
            for token in possessive_tokens:
                initial = token[0]
                initial_candidates = [
                    p for p in self.player_activity.keys() if self._tokenize(p) and self._tokenize(p)[0].startswith(initial)
                ]
                if len(initial_candidates) < 2:
                    continue
                ranked_initial = sorted(initial_candidates, key=lambda p: self.player_activity.get(p, 0), reverse=True)
                best = self.player_activity.get(ranked_initial[0], 0)
                next_best = self.player_activity.get(ranked_initial[1], 0)
                if best >= 500 and best >= (next_best * 2):
                    return EntityResolution(ranked_initial[0], ranked_initial[:6], False)
            return EntityResolution(None, [], False)
        if len(candidates) == 1:
            return EntityResolution(candidates[0], candidates, False)

        score_map: dict[str, float] = {}
        for width in (3, 2, 1):
            for i in range(len(tokens) - width + 1):
                alias = " ".join(tokens[i : i + width])
                for player in self.player_aliases.get(alias, []):
                    score_map[player] = score_map.get(player, 0.0) + self._alias_specificity(alias)

        ranked = sorted(
            candidates,
            key=lambda player: (-(score_map.get(player, 0.0) + self._score_player_candidate(lowered, player)), player),
        )
        if len(ranked) >= 2:
            best_score = score_map.get(ranked[0], 0.0) + self._score_player_candidate(lowered, ranked[0])
            next_score = score_map.get(ranked[1], 0.0) + self._score_player_candidate(lowered, ranked[1])
            if best_score >= 24.0 and best_score >= next_score + 12.0:
                return EntityResolution(ranked[0], ranked, False)

        # Token-similarity fallback for known spelling variants (for example: sooryavanshi/suryavanshi).
        if len(tokens) >= 2:
            fuzzy_scores: dict[str, float] = {}
            candidate_players: set[str] = set(self.player_activity.keys())
            for values in self.player_aliases.values():
                candidate_players.update(values)
            for player in candidate_players:
                p_tokens = self._tokenize(player)
                if len(p_tokens) < 2:
                    continue
                last_ratio = difflib.SequenceMatcher(None, tokens[-1], p_tokens[-1]).ratio()
                first_ratio = difflib.SequenceMatcher(None, tokens[0], p_tokens[0]).ratio()
                if last_ratio < 0.82 or first_ratio < 0.34:
                    continue
                fuzzy_scores[player] = (last_ratio * 80.0) + (first_ratio * 20.0) + self._score_player_candidate(lowered, player)
            if fuzzy_scores:
                ranked_fuzzy = sorted(fuzzy_scores.items(), key=lambda item: (-item[1], item[0]))
                if len(ranked_fuzzy) == 1 or ranked_fuzzy[0][1] >= ranked_fuzzy[1][1] + 16.0:
                    return EntityResolution(ranked_fuzzy[0][0], [name for name, _ in ranked_fuzzy[:6]], False)
        return EntityResolution(None, candidates[:6], True)

    def resolve_team(self, text: str) -> EntityResolution:
        lowered = self._normalize_text(text)
        hits: list[str] = []
        for alias, canonical in self.team_aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                if canonical not in hits:
                    hits.append(canonical)
        if not hits:
            return EntityResolution(None, [], False)
        if len(hits) == 1:
            return EntityResolution(hits[0], hits, False)
        return EntityResolution(None, hits[:6], True)


class RuleBasedPlanProvider:
    def _apply_follow_up_context(self, question: str, plan_entities: dict[str, Any], context: ConversationContext) -> None:
        lowered = SemanticResolver._normalize_text(question)
        if context.last_plan is None:
            return

        uses_pronoun = bool(re.search(r"\b(his|her|their|them|that season|that year)\b", lowered))
        if not uses_pronoun:
            return

        for key in ("player", "players", "team", "season", "season_start", "season_end"):
            if key not in plan_entities and key in context.last_entities:
                plan_entities[key] = context.last_entities[key]
            elif key not in plan_entities and key in context.last_plan.entities:
                plan_entities[key] = context.last_plan.entities[key]

    def build_plan(self, question: str, semantic: SemanticResolver, context: ConversationContext) -> QueryPlan | None:
        raw = question.strip()
        lowered = SemanticResolver._normalize_text(raw)
        tokens = lowered.split()
        if not raw:
            return None

        if any(token in lowered for token in ("weather", "pitch moisture", "humidity", "temperature")):
            return None

        # Lightweight follow-up season carry-forward: "What about 2015?"
        if lowered.startswith("what about") and context.last_plan is not None:
            season = semantic.extract_season(lowered)
            if season is not None:
                entities = dict(context.last_plan.entities)
                entities["season"] = season
                return QueryPlan(
                    question=raw,
                    operation=context.last_plan.operation,
                    entity=context.last_plan.entity,
                    entities=entities,
                    metric=context.last_plan.metric,
                    metrics=context.last_plan.metrics,
                    filters=dict(context.last_plan.filters),
                    group_by=context.last_plan.group_by,
                    order_by=context.last_plan.order_by,
                    limit=context.last_plan.limit,
                    threshold=context.last_plan.threshold,
                )

        season = semantic.extract_season(lowered)
        season_range = semantic.extract_season_range(lowered)
        phase = semantic.extract_phase(lowered)

        all_players = semantic.resolve_player_candidates(raw)
        player_resolution = semantic.resolve_player(raw)
        team_resolution = semantic.resolve_team(lowered)

        entities: dict[str, Any] = {}
        if season is not None:
            entities["season"] = season
        if season_range is not None:
            entities["season_start"] = season_range[0]
            entities["season_end"] = season_range[1]
        if phase is not None:
            entities["phase"] = phase

        if team_resolution.ambiguous:
            return QueryPlan(
                question=raw,
                operation="clarify",
                entity="team",
                entities={"candidates": team_resolution.candidates, "reason": "ambiguous_team"},
            )

        if team_resolution.value:
            entities["team"] = team_resolution.value

        if "compare" in lowered or "between" in lowered:
            compare_match = re.search(r"(?:compare|between)\s+(.+?)\s+(?:and|vs|versus|with)\s+(.+)", lowered)
            if compare_match:
                left_resolution = semantic.resolve_player(compare_match.group(1))
                right_resolution = semantic.resolve_player(compare_match.group(2))
                if left_resolution.ambiguous or right_resolution.ambiguous:
                    candidates = (left_resolution.candidates + right_resolution.candidates)[:6]
                    return QueryPlan(
                        question=raw,
                        operation="clarify",
                        entity="player",
                        entities={"candidates": candidates, "reason": "ambiguous_player_compare"},
                    )
                if left_resolution.value and right_resolution.value and left_resolution.value != right_resolution.value:
                    entities["players"] = [left_resolution.value, right_resolution.value]
            if "players" not in entities and len(all_players) >= 2:
                dedup_players: list[str] = []
                for player in all_players:
                    if player not in dedup_players:
                        dedup_players.append(player)
                if len(dedup_players) >= 2:
                    entities["players"] = dedup_players[:2]
                else:
                    return QueryPlan(
                        question=raw,
                        operation="clarify",
                        entity="player",
                        entities={"candidates": dedup_players, "reason": "ambiguous_player_compare"},
                    )
        elif player_resolution.ambiguous:
            return QueryPlan(
                question=raw,
                operation="clarify",
                entity="player",
                entities={"candidates": player_resolution.candidates, "reason": "ambiguous_player"},
            )
        elif player_resolution.value:
            entities["player"] = player_resolution.value

        self._apply_follow_up_context(raw, entities, context)

        has_player_context = "player" in entities or "players" in entities
        metrics = semantic.resolve_metrics(lowered, has_player_context=has_player_context)
        primary_metric = metrics[0] if metrics else None

        # Player knowledge domain (bio-data and identity attributes).
        bio_attr = None
        if "full name" in lowered or "complete name" in lowered:
            bio_attr = "full_name"
        elif "born" in lowered or "date of birth" in lowered or "dob" in lowered:
            bio_attr = "date_of_birth"
        elif "wife" in lowered or "spouse" in lowered:
            bio_attr = "spouse_name"
        elif "children" in lowered or "kids" in lowered or "child" in lowered:
            bio_attr = "children_count"
        elif "bowling style" in lowered:
            bio_attr = "bowling_style"
        elif "batting style" in lowered:
            bio_attr = "batting_style"
        elif "role" in lowered:
            bio_attr = "role"
        elif "nationality" in lowered:
            bio_attr = "nationality"

        if bio_attr is not None:
            if "player" not in entities:
                trailing_match = re.search(r"(?:of|does|for)\s+([a-z0-9 .'-]+)$", lowered)
                if trailing_match:
                    candidate_phrase = trailing_match.group(1).strip()
                    resolved = semantic.resolve_player(candidate_phrase)
                    if resolved.value:
                        entities["player"] = resolved.value
                    elif candidate_phrase:
                        entities["player"] = candidate_phrase
            if "player" not in entities:
                return None
            return QueryPlan(
                question=raw,
                operation="knowledge_lookup",
                entity="player_knowledge",
                entities=entities,
                metric=bio_attr,
                metrics=[bio_attr],
                filters=dict(entities),
            )

        if "captain" in lowered or "coach" in lowered or "owner" in lowered or "owned" in lowered or "owns" in lowered:
            if "team" not in entities:
                return None
            leadership_metric = "captain" if "captain" in lowered else "coach" if "coach" in lowered else "owner"
            return QueryPlan(
                question=raw,
                operation="team_season_info",
                entity="team_season",
                entities=entities,
                metric=leadership_metric,
                metrics=[leadership_metric],
                filters=dict(entities),
            )

        if season is not None and "final" in lowered and any(token in lowered for token in ("happened", "result", "winner")):
            entities["match_type"] = "final"
            return QueryPlan(
                question=raw,
                operation="lookup",
                entity="match_result_summary",
                entities=entities,
                metric="result",
                metrics=["result"],
                filters=dict(entities),
                limit=1,
            )

        if "next ball" in lowered or "prediction change" in lowered or "likely to happen" in lowered:
            metric = "prediction_change" if "prediction change" in lowered else "next_ball"
            return QueryPlan(
                question=raw,
                operation="prediction_info",
                entity="prediction",
                entities=entities,
                metric=metric,
                metrics=[metric],
                filters=dict(entities),
            )

        if "fixture" in lowered or "fixtures" in lowered:
            return QueryPlan(
                question=raw,
                operation="fixtures",
                entity="fixtures",
                entities=entities,
                filters=dict(entities),
                limit=semantic.extract_limit(lowered, default=10),
            )

        if "result" in lowered or "results" in lowered or "completed matches" in lowered:
            return QueryPlan(
                question=raw,
                operation="results",
                entity="results",
                entities=entities,
                filters=dict(entities),
                limit=semantic.extract_limit(lowered, default=10),
            )

        if "points table" in lowered or "team table" in lowered or "standings" in lowered:
            if season is None:
                return None
            return QueryPlan(
                question=raw,
                operation="points_table",
                entity="points_table",
                entities=entities,
                filters=dict(entities),
            )

        if "top performers" in lowered:
            return QueryPlan(
                question=raw,
                operation="top_performers",
                entity="top_performers",
                entities=entities,
                filters=dict(entities),
                limit=semantic.extract_limit(lowered, default=5),
            )

        if "player of the match" in lowered or "man of the match" in lowered:
            if "final" in lowered:
                entities["match_type"] = "final"
            return QueryPlan(
                question=raw,
                operation="lookup",
                entity="match_metadata",
                entities=entities,
                metric="player_of_match",
                metrics=["player_of_match"],
                filters=dict(entities),
                limit=1,
            )

        if "last three matches" in lowered or "last 3 matches" in lowered:
            if "player" not in entities:
                return None
            return QueryPlan(
                question=raw,
                operation="trend",
                entity="player_recent_matches",
                entities=entities,
                metric=primary_metric or "runs",
                metrics=metrics or ["runs", "strike_rate"],
                filters=dict(entities),
                limit=3,
            )

        bowling_type = semantic.extract_bowling_type(lowered)
        if bowling_type and "player" in entities:
            entities["bowling_type"] = bowling_type
            return QueryPlan(
                question=raw,
                operation="aggregate",
                entity="player_vs_bowling_type",
                entities=entities,
                metric=primary_metric or "strike_rate",
                metrics=metrics or [primary_metric or "strike_rate"],
                filters=dict(entities),
            )

        if "compare" in lowered and "players" not in entities and "player" in entities and context.last_entities.get("player"):
            entities["players"] = [str(context.last_entities["player"]), str(entities["player"])]

        if "compare" in lowered and "players" in entities:
            return QueryPlan(
                question=raw,
                operation="compare",
                entity="player_comparison",
                entities=entities,
                metric=primary_metric or "runs",
                metrics=metrics or [primary_metric or "runs"],
                filters=dict(entities),
            )

        if any(word in lowered for word in ("top", "most", "highest", "best", "lowest", "bottom")):
            is_best_season = ("best season" in lowered) or ("best" in lowered and "season" in lowered)
            limit = semantic.extract_limit(lowered, default=1 if is_best_season else 10)
            order = "asc" if any(word in lowered for word in ("lowest", "bottom", "best economy")) else "desc"
            group_by = ["season"] if is_best_season and "player" in entities else ["player"]
            threshold: dict[str, Any] | None = None
            threshold_match = re.search(r"more than\s+(\d+)\s+runs", lowered)
            if threshold_match:
                threshold = {"metric": "runs", "op": ">", "value": int(threshold_match.group(1))}
            return QueryPlan(
                question=raw,
                operation="rank",
                entity="bowling" if (primary_metric in {"wickets", "economy", "runs_conceded", "bowling_strike_rate"}) else "batting",
                entities=entities,
                metric=primary_metric or "runs",
                metrics=metrics or [primary_metric or "runs"],
                filters=dict(entities),
                group_by=group_by,
                order_by=order,
                limit=limit,
                threshold=threshold,
            )

        if "team" in entities and ((primary_metric in {"wickets", "economy", "bowling_strike_rate", "runs_conceded"}) or ("player" in entities and primary_metric is None)):
            if "player" in entities:
                entities["bowler"] = entities.pop("player")
            return QueryPlan(
                question=raw,
                operation="aggregate",
                entity="bowler_vs_team",
                entities=entities,
                metric=primary_metric or "wickets",
                metrics=metrics or [primary_metric or "wickets"],
                filters=dict(entities),
            )

        if "player" in entities and primary_metric is not None:
            return QueryPlan(
                question=raw,
                operation="aggregate",
                entity="player",
                entities=entities,
                metric=primary_metric,
                metrics=metrics,
                filters=dict(entities),
            )

        if "player" in entities and phase is not None and primary_metric is None:
            return QueryPlan(
                question=raw,
                operation="aggregate",
                entity="player",
                entities=entities,
                metric="runs",
                metrics=["runs", "strike_rate"],
                filters=dict(entities),
            )

        if season is not None and primary_metric is not None:
            return QueryPlan(
                question=raw,
                operation="rank",
                entity="bowling" if primary_metric in {"wickets", "economy", "runs_conceded", "bowling_strike_rate"} else "batting",
                entities=entities,
                metric=primary_metric,
                metrics=metrics or [primary_metric],
                filters=dict(entities),
                group_by=["player"],
                order_by="desc",
                limit=semantic.extract_limit(lowered),
            )

        if "player" in entities and primary_metric is None:
            return QueryPlan(
                question=raw,
                operation="knowledge_lookup",
                entity="player_knowledge",
                entities=entities,
                metric="full_name",
                metrics=["full_name"],
                filters=dict(entities),
            )

        blocked_tokens = {
            "tell",
            "show",
            "what",
            "who",
            "when",
            "where",
            "how",
            "why",
            "database",
            "credentials",
            "table",
            "drop",
            "delete",
        }
        if re.fullmatch(r"[a-z0-9 .'-]+", lowered) and len(tokens) <= 4 and not any(t in blocked_tokens for t in tokens):
            return QueryPlan(
                question=raw,
                operation="knowledge_lookup",
                entity="player_knowledge",
                entities={"player": raw},
                metric="full_name",
                metrics=["full_name"],
                filters={"player": raw},
            )

        return None


class LlmAskPlanProvider:
    """Optional provider that returns structured plans only; SQL is never model-generated."""

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
        req = Request(
            self.base_url.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urlopen(req, timeout=self.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _post_anthropic_compatible(self, question: str, system_prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": question}],
            "temperature": 0,
            "max_tokens": 512,
        }
        req = Request(
            self.base_url.rstrip("/") + "/v1/messages",
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
        for block in body.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                return block["text"]
        return ""

    def _normalize_plan_dict(self, parsed: dict[str, Any], semantic: SemanticResolver) -> QueryPlan | None:
        op = str(parsed.get("operation", "")).strip().lower()
        entity = str(parsed.get("entity", "")).strip().lower()
        if not op or not entity:
            return None

        entities_raw = parsed.get("entities", {})
        entities = entities_raw if isinstance(entities_raw, dict) else {}

        player = entities.get("player")
        if isinstance(player, str):
            r = semantic.resolve_player(player)
            entities["player"] = r.value or player

        players = entities.get("players")
        if isinstance(players, list):
            normalized_players: list[str] = []
            for item in players:
                if not isinstance(item, str):
                    continue
                r = semantic.resolve_player(item)
                normalized_players.append(r.value or item)
            entities["players"] = normalized_players

        team = entities.get("team")
        if isinstance(team, str):
            t = semantic.resolve_team(team)
            entities["team"] = t.value or team

        season = entities.get("season")
        if season is not None:
            try:
                entities["season"] = int(str(season))
            except Exception:
                pass

        metric = parsed.get("metric")
        metrics = parsed.get("metrics")
        metric_value = str(metric) if metric is not None else None
        metrics_value: list[str] | None = None
        if isinstance(metrics, list):
            metrics_value = [str(m) for m in metrics if str(m)]

        return QueryPlan(
            question=str(parsed.get("question") or ""),
            operation=op,
            entity=entity,
            entities=entities,
            metric=metric_value,
            metrics=metrics_value,
            filters=parsed.get("filters") if isinstance(parsed.get("filters"), dict) else dict(entities),
            group_by=parsed.get("group_by") if isinstance(parsed.get("group_by"), list) else None,
            order_by=str(parsed.get("order_by")) if parsed.get("order_by") is not None else None,
            limit=int(parsed.get("limit")) if parsed.get("limit") is not None else None,
            threshold=parsed.get("threshold") if isinstance(parsed.get("threshold"), dict) else None,
        )

    def build_plan(self, question: str, semantic: SemanticResolver, context: ConversationContext) -> QueryPlan | None:
        if not self.enabled():
            return None

        metric_names = ", ".join(sorted(semantic.metric_registry.keys()))
        system_prompt = (
            "Convert IPL analytics NL questions into JSON only with keys: "
            "operation, entity, entities, metric, metrics, filters, group_by, order_by, limit, threshold. "
            "Never output SQL. "
            f"Allowed operations: {', '.join(sorted(ALLOWED_OPERATIONS))}. "
            f"Known metrics: {metric_names}."
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

        if isinstance(parsed, dict) and "questions" in parsed and isinstance(parsed["questions"], list) and parsed["questions"]:
            first = parsed["questions"][0]
            if isinstance(first, dict):
                parsed = first

        if not isinstance(parsed, dict):
            return None
        parsed["question"] = question
        return self._normalize_plan_dict(parsed, semantic)


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
    def __init__(self, semantic: SemanticResolver) -> None:
        self.semantic = semantic

    def validate(self, plan: QueryPlan) -> None:
        if plan.operation not in ALLOWED_OPERATIONS:
            raise ValueError("Unsupported semantic operation")

        if plan.limit is not None and (plan.limit < 1 or plan.limit > MAX_LIMIT):
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

        if plan.operation == "clarify":
            return

        if plan.operation in {"knowledge_lookup", "fixtures", "results", "points_table", "team_season_info", "top_performers", "prediction_info"}:
            return

        metric_names = set(self.semantic.metric_registry.keys())
        metrics = list(plan.metrics or [])
        if plan.metric:
            metrics.append(plan.metric)
        for metric in metrics:
            if metric not in metric_names:
                raise ValueError(f"Unsupported metric: {metric}")

        entities = plan.entities
        if not isinstance(entities, dict):
            raise ValueError("entities must be an object")

        season = entities.get("season")
        if season is not None and not isinstance(season, int):
            raise ValueError("season must be an integer")

        for key in ("season_start", "season_end"):
            if key in entities and not isinstance(entities[key], int):
                raise ValueError(f"{key} must be an integer")

        if plan.operation == "compare":
            players = entities.get("players")
            if not isinstance(players, list) or len(players) < 2:
                raise ValueError("compare requires at least two players")

        if plan.operation == "aggregate" and plan.entity == "player" and "player" not in entities:
            raise ValueError("player aggregate requires a resolved player")


class QueryExecutor:
    TABLE_ALLOWLIST = {
        "deliveries": {
            "season_id",
            "match_id",
            "innings",
            "over_number",
            "ball_number",
            "batter",
            "bowler",
            "non_striker",
            "team_batting",
            "team_bowling",
            "batter_runs",
            "total_runs",
            "is_wicket",
            "is_wide_ball",
            "legal_ball",
            "bye_runs",
            "leg_bye_runs",
            "bowler_type",
            "wicket_kind",
            "player_out",
        },
        "match_metadata": {
            "match_id",
            "season_id",
            "match_date",
            "venue",
            "city",
            "toss_winner",
            "toss_decision",
            "winner",
            "result_type",
            "result_margin",
            "match_type",
            "player_of_match",
            "team_a_display",
            "team_b_display",
        },
        "match_team_map": {"match_id", "internal_team_code", "historical_display_name"},
    }

    def __init__(self, conn: sqlite3.Connection, semantic: SemanticResolver) -> None:
        self.conn = conn
        self.semantic = semantic

    def _safe_readonly(self, sql: str) -> None:
        stripped = sql.strip().lower()
        if not stripped.startswith("select"):
            raise ValueError("Only read-only SELECT queries are permitted")
        if READONLY_BLOCKLIST.search(stripped):
            raise ValueError("Blocked SQL keyword detected")

    def _compile_select(
        self,
        *,
        table: str,
        select_columns: list[str],
        where: list[tuple[str, str, Any]] | None = None,
        group_by: list[str] | None = None,
        having_sql: str | None = None,
        order_by_sql: str | None = None,
        limit: int | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        if table not in self.TABLE_ALLOWLIST:
            raise ValueError("Unknown table")

        allowed_cols = self.TABLE_ALLOWLIST[table]
        for col in select_columns:
            if col != "*" and col not in allowed_cols:
                raise ValueError(f"Unknown column: {col}")

        where = where or []
        params: list[Any] = []
        predicates: list[str] = []
        for col, op, value in where:
            if col not in allowed_cols:
                raise ValueError(f"Unknown column: {col}")
            if op not in {"=", ">", ">=", "<", "<=", "between"}:
                raise ValueError("Unsafe expression operator")
            if op == "between":
                if not isinstance(value, tuple) or len(value) != 2:
                    raise ValueError("between requires tuple(value1, value2)")
                predicates.append(f"{col} BETWEEN ? AND ?")
                params.extend([value[0], value[1]])
            else:
                predicates.append(f"{col} {op} ?")
                params.append(value)

        if group_by:
            for col in group_by:
                if col not in allowed_cols:
                    raise ValueError(f"Unknown group_by column: {col}")

        if limit is not None and (limit < 1 or limit > MAX_LIMIT):
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

        sql = f"SELECT {', '.join(select_columns)} FROM {table}"
        if predicates:
            sql += " WHERE " + " AND ".join(predicates)
        if group_by:
            sql += " GROUP BY " + ", ".join(group_by)
        if having_sql:
            if ";" in having_sql or "--" in having_sql:
                raise ValueError("Unsafe expressions rejected")
            sql += " HAVING " + having_sql
        if order_by_sql:
            if ";" in order_by_sql or "--" in order_by_sql:
                raise ValueError("Unsafe expressions rejected")
            sql += " ORDER BY " + order_by_sql
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return sql, tuple(params)

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        self._safe_readonly(sql)
        started = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        log_sql("ask_query", sql, params, started, row_count=len(rows))
        return rows

    @staticmethod
    def _phase_filter(phase: str | None) -> str:
        if phase == "powerplay":
            return " AND d.over_number < 6"
        if phase == "middle":
            return " AND d.over_number BETWEEN 6 AND 14"
        if phase == "death":
            return " AND d.over_number >= 15"
        return ""

    def _build_batting_metrics_expr(self) -> dict[str, str]:
        return {
            "runs": "COALESCE(SUM(d.batter_runs), 0)",
            "balls": "COALESCE(SUM(CASE WHEN d.is_wide_ball = 0 THEN 1 ELSE 0 END), 0)",
            "fours": "COALESCE(SUM(CASE WHEN d.batter_runs = 4 THEN 1 ELSE 0 END), 0)",
            "sixes": "COALESCE(SUM(CASE WHEN d.batter_runs = 6 THEN 1 ELSE 0 END), 0)",
            "dot_balls": "COALESCE(SUM(CASE WHEN d.total_runs = 0 AND d.is_wide_ball = 0 THEN 1 ELSE 0 END), 0)",
            "dismissals": "COALESCE(SUM(CASE WHEN d.is_wicket = 1 AND d.player_out = d.batter THEN 1 ELSE 0 END), 0)",
        }

    def _batting_metric_value(self, metric: str, base: dict[str, int]) -> float | int:
        runs = base.get("runs", 0)
        balls = base.get("balls", 0)
        dismissals = base.get("dismissals", 0)
        dots = base.get("dot_balls", 0)
        if metric == "runs":
            return runs
        if metric == "balls":
            return balls
        if metric == "fours":
            return base.get("fours", 0)
        if metric == "sixes":
            return base.get("sixes", 0)
        if metric == "dot_balls":
            return dots
        if metric == "dot_ball_pct":
            return round((dots * 100.0 / balls), 2) if balls else 0.0
        if metric == "strike_rate":
            return round((runs * 100.0 / balls), 2) if balls else 0.0
        if metric == "average":
            return round((runs / dismissals), 2) if dismissals else 0.0
        return runs

    def _aggregate_player(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        season = plan.entities.get("season")
        phase = plan.entities.get("phase")
        season_range = (plan.entities.get("season_start"), plan.entities.get("season_end"))

        metric_aliases = self._build_batting_metrics_expr()
        sql = (
            "SELECT "
            + ", ".join(f"{expr} AS {name}" for name, expr in metric_aliases.items())
            + " FROM deliveries d WHERE d.batter = ?"
        )
        params: list[Any] = [player]

        if isinstance(season, int):
            sql += " AND d.season_id = ?"
            params.append(season)
        elif isinstance(season_range[0], int) and isinstance(season_range[1], int):
            sql += " AND d.season_id BETWEEN ? AND ?"
            params.extend([season_range[0], season_range[1]])

        sql += self._phase_filter(str(phase) if isinstance(phase, str) else None)

        row = self._run(sql, tuple(params))[0]
        base = {k: int(row[k]) for k in metric_aliases}

        requested_metrics = plan.metrics or ([plan.metric] if plan.metric else ["runs"])
        values = {m: self._batting_metric_value(m, base) for m in requested_metrics}
        scalar = values[requested_metrics[0]] if len(requested_metrics) == 1 else values

        scope_parts = [f"player={player}"]
        if isinstance(season, int):
            scope_parts.append(f"season={season}")
        if isinstance(season_range[0], int) and isinstance(season_range[1], int):
            scope_parts.append(f"season_range={season_range[0]}-{season_range[1]}")
        if phase:
            scope_parts.append(f"phase={phase}")

        return {
            "value": scalar,
            "label": f"{player} {requested_metrics[0].replace('_', ' ')}",
            "evidence": {
                "interpretation": "player batting aggregate",
                "resolved_entities": {"player": player},
                "filters": plan.entities,
                "metric": requested_metrics,
                "source_tables": ["deliveries"],
                "season_scope": scope_parts,
                "sample_size": base.get("balls", 0),
                "calculation": "parameterized SQL aggregate over deliveries",
            },
        }

    def _aggregate_bowler_vs_team(self, plan: QueryPlan) -> dict[str, Any]:
        bowler = str(plan.entities.get("bowler") or plan.entities.get("player"))
        team = str(plan.entities["team"])
        season = plan.entities.get("season")

        sql = (
            "SELECT "
            "COALESCE(SUM(CASE WHEN d.is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets, "
            "COALESCE(SUM(d.total_runs - d.bye_runs - d.leg_bye_runs), 0) AS runs_conceded, "
            "COALESCE(SUM(d.legal_ball), 0) AS legal_balls, "
            "COALESCE(SUM(CASE WHEN d.total_runs = 0 THEN 1 ELSE 0 END), 0) AS dot_balls "
            "FROM deliveries d "
            "LEFT JOIN match_team_map m ON m.match_id = d.match_id AND m.internal_team_code = d.team_batting "
            "WHERE d.bowler = ? AND COALESCE(m.historical_display_name, d.team_batting) = ?"
        )
        params: list[Any] = [bowler, team]
        if isinstance(season, int):
            sql += " AND d.season_id = ?"
            params.append(season)

        row = self._run(sql, tuple(params))[0]
        wickets = int(row["wickets"])
        runs_conceded = int(row["runs_conceded"])
        legal_balls = int(row["legal_balls"])
        dot_balls = int(row["dot_balls"])

        metric = str(plan.metric or "wickets")
        if metric == "economy":
            value: float | int = round(runs_conceded / (legal_balls / 6.0), 2) if legal_balls else 0.0
        elif metric == "bowling_strike_rate":
            value = round(legal_balls / wickets, 2) if wickets else 0.0
        elif metric == "runs_conceded":
            value = runs_conceded
        elif metric == "dot_balls":
            value = dot_balls
        elif metric == "dot_ball_pct":
            value = round(dot_balls * 100.0 / legal_balls, 2) if legal_balls else 0.0
        else:
            value = wickets

        return {
            "value": value,
            "label": f"{bowler} {metric.replace('_', ' ')} against {team}",
            "evidence": {
                "interpretation": "bowler against opponent aggregate",
                "resolved_entities": {"bowler": bowler, "team": team},
                "filters": plan.entities,
                "metric": metric,
                "source_tables": ["deliveries", "match_team_map"],
                "sample_size": legal_balls,
                "calculation": "aggregate by bowler against batting team mapping",
            },
        }

    def _rank(self, plan: QueryPlan) -> dict[str, Any]:
        metric = str(plan.metric or "runs")
        limit = int(plan.limit or 10)
        phase = plan.entities.get("phase")
        season = plan.entities.get("season")

        if plan.entity == "batting":
            if plan.group_by == ["season"] and "player" in plan.entities:
                player = str(plan.entities["player"])
                sql = (
                    "SELECT d.season_id AS season, "
                    "COALESCE(SUM(d.batter_runs), 0) AS runs, "
                    "COALESCE(SUM(CASE WHEN d.is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls "
                    "FROM deliveries d WHERE d.batter = ?"
                )
                params: list[Any] = [player]
                sql += " GROUP BY d.season_id"
                order_sql = "runs DESC, season ASC"
                if metric == "strike_rate":
                    order_sql = "(runs * 100.0 / CASE WHEN balls = 0 THEN 1 ELSE balls END) DESC, balls DESC, season ASC"
                sql += f" ORDER BY {order_sql} LIMIT 1"
                row = self._run(sql, tuple(params))[0]
                balls = int(row["balls"])
                return {
                    "value": {
                        "season": int(row["season"]),
                        "runs": int(row["runs"]),
                        "strike_rate": round(int(row["runs"]) * 100.0 / balls, 2) if balls else 0.0,
                    },
                    "label": f"Best season for {player}",
                    "evidence": {
                        "interpretation": "season ranking within player",
                        "resolved_entities": {"player": player},
                        "filters": plan.entities,
                        "metric": metric,
                        "source_tables": ["deliveries"],
                        "sample_size": balls,
                        "calculation": "group by season and rank",
                    },
                }

            sql = (
                "SELECT d.batter AS player, "
                "COALESCE(SUM(d.batter_runs), 0) AS runs, "
                "COALESCE(SUM(CASE WHEN d.batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes, "
                "COALESCE(SUM(CASE WHEN d.is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls "
                "FROM deliveries d WHERE 1=1"
            )
            params: list[Any] = []
            if isinstance(season, int):
                sql += " AND d.season_id = ?"
                params.append(season)
            sql += self._phase_filter(str(phase) if isinstance(phase, str) else None)
            sql += " GROUP BY d.batter"

            if plan.threshold and plan.threshold.get("metric") == "runs" and plan.threshold.get("op") == ">":
                threshold_value = plan.threshold.get("value")
                if threshold_value is None:
                    raise ValueError("threshold value is required")
                threshold = int(threshold_value)
                sql += " HAVING runs > ?"
                params.append(threshold)

            if metric == "sixes":
                sql += " ORDER BY sixes DESC, runs DESC, player ASC"
            elif metric == "strike_rate":
                sql += " HAVING balls >= 24 ORDER BY (runs * 100.0 / balls) DESC, balls DESC, player ASC"
            else:
                sql += " ORDER BY runs DESC, player ASC"

            sql += " LIMIT ?"
            params.append(limit)
            rows = self._run(sql, tuple(params))
            ranked = []
            for row in rows:
                balls = int(row["balls"])
                ranked.append(
                    {
                        "player": row["player"],
                        "runs": int(row["runs"]),
                        "sixes": int(row["sixes"]),
                        "balls": balls,
                        "strike_rate": round(int(row["runs"]) * 100.0 / balls, 2) if balls else 0.0,
                    }
                )
            return {
                "value": ranked,
                "label": f"Top {limit} batting by {metric}",
                "evidence": {
                    "interpretation": "batting ranking",
                    "filters": plan.entities,
                    "metric": metric,
                    "source_tables": ["deliveries"],
                    "sample_size": sum(int(r["balls"]) for r in rows),
                    "calculation": "group by batter with bounded limit",
                },
            }

        # bowling ranking
        sql = (
            "SELECT d.bowler AS player, "
            "COALESCE(SUM(CASE WHEN d.is_wicket = 1 THEN 1 ELSE 0 END), 0) AS wickets, "
            "COALESCE(SUM(d.total_runs - d.bye_runs - d.leg_bye_runs), 0) AS runs_conceded, "
            "COALESCE(SUM(d.legal_ball), 0) AS legal_balls "
            "FROM deliveries d WHERE 1=1"
        )
        params = []
        if isinstance(season, int):
            sql += " AND d.season_id = ?"
            params.append(season)
        if "team" in plan.entities:
            sql += (
                " AND EXISTS (SELECT 1 FROM match_team_map m WHERE m.match_id = d.match_id "
                "AND m.internal_team_code = d.team_batting AND m.historical_display_name = ?)"
            )
            params.append(str(plan.entities["team"]))

        sql += self._phase_filter(str(phase) if isinstance(phase, str) else None)
        sql += " GROUP BY d.bowler"

        if metric == "economy":
            sql += " HAVING legal_balls >= 24 ORDER BY (runs_conceded * 1.0 / (legal_balls / 6.0)) ASC, legal_balls DESC, player ASC"
        else:
            sql += " ORDER BY wickets DESC, legal_balls DESC, player ASC"

        sql += " LIMIT ?"
        params.append(limit)
        rows = self._run(sql, tuple(params))
        ranked = []
        for row in rows:
            legal_balls = int(row["legal_balls"])
            wickets = int(row["wickets"])
            runs_conceded = int(row["runs_conceded"])
            ranked.append(
                {
                    "player": row["player"],
                    "wickets": wickets,
                    "legal_balls": legal_balls,
                    "economy": round(runs_conceded / (legal_balls / 6.0), 2) if legal_balls else 0.0,
                    "bowling_strike_rate": round(legal_balls / wickets, 2) if wickets else 0.0,
                }
            )

        return {
            "value": ranked,
            "label": f"Top {limit} bowling by {metric}",
            "evidence": {
                "interpretation": "bowling ranking",
                "filters": plan.entities,
                "metric": metric,
                "source_tables": ["deliveries", "match_team_map"],
                "sample_size": sum(int(r["legal_balls"]) for r in rows),
                "calculation": "group by bowler with bounded limit",
            },
        }

    def _compare_players(self, plan: QueryPlan) -> dict[str, Any]:
        players = [str(p) for p in plan.entities.get("players", [])[:2]]
        metric = str(plan.metric or "runs")
        values = []
        for player in players:
            sub = QueryPlan(
                question=plan.question,
                operation="aggregate",
                entity="player",
                entities={
                    "player": player,
                    **({"season": plan.entities["season"]} if "season" in plan.entities else {}),
                    **(
                        {
                            "season_start": plan.entities["season_start"],
                            "season_end": plan.entities["season_end"],
                        }
                        if "season_start" in plan.entities and "season_end" in plan.entities
                        else {}
                    ),
                    **({"phase": plan.entities["phase"]} if "phase" in plan.entities else {}),
                },
                metric=metric,
                metrics=[metric],
            )
            answer = self._aggregate_player(sub)
            values.append({"player": player, "value": answer["value"]})

        better = values[0]["player"] if values[0]["value"] >= values[1]["value"] else values[1]["player"]
        return {
            "value": {"metric": metric, "players": values, "better": better},
            "label": f"Comparison of {players[0]} vs {players[1]}",
            "evidence": {
                "interpretation": "player comparison",
                "resolved_entities": {"players": players},
                "filters": plan.entities,
                "metric": metric,
                "source_tables": ["deliveries"],
                "calculation": "two independent aggregates compared",
            },
        }

    def _lookup_match_metadata(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season")
        match_type = plan.entities.get("match_type")
        if not isinstance(season, int):
            raise ValueError("season is required for match metadata lookup")

        sql = (
            "SELECT match_id, match_date, team_a_display, team_b_display, player_of_match, match_type "
            "FROM match_metadata WHERE season_id = ?"
        )
        params: list[Any] = [season]
        if match_type == "final":
            sql += " AND LOWER(COALESCE(match_type, '')) = 'final'"
        sql += " ORDER BY match_date, match_id LIMIT 1"
        rows = self._run(sql, tuple(params))
        if not rows:
            raise ValueError("No matching match metadata found")
        row = rows[0]
        return {
            "value": {
                "match_id": int(row["match_id"]),
                "match_date": row["match_date"],
                "teams": [row["team_a_display"], row["team_b_display"]],
                "player_of_match": row["player_of_match"],
            },
            "label": "Match metadata lookup",
            "evidence": {
                "interpretation": "match metadata lookup",
                "filters": plan.entities,
                "metric": "player_of_match",
                "source_tables": ["match_metadata"],
                "calculation": "filtered metadata lookup",
            },
        }

    def _player_recent_matches(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        limit = int(plan.limit or 3)
        matches = self._run(
            "SELECT season_id, match_id FROM deliveries WHERE batter = ? GROUP BY season_id, match_id ORDER BY season_id DESC, match_id DESC LIMIT ?",
            (player, limit),
        )
        rows_out: list[dict[str, Any]] = []
        for row in matches:
            season = int(row["season_id"])
            match_id = int(row["match_id"])
            agg = self._run(
                "SELECT COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls, COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes FROM deliveries WHERE season_id = ? AND match_id = ? AND batter = ?",
                (season, match_id, player),
            )[0]
            balls = int(agg["balls"])
            runs = int(agg["runs"])
            rows_out.append(
                {
                    "season": season,
                    "match_id": match_id,
                    "runs": runs,
                    "balls": balls,
                    "sixes": int(agg["sixes"]),
                    "strike_rate": round(runs * 100.0 / balls, 2) if balls else 0.0,
                }
            )

        return {
            "value": rows_out,
            "label": f"Recent matches for {player}",
            "evidence": {
                "interpretation": "recent match trend",
                "filters": plan.entities,
                "metric": plan.metrics or [plan.metric or "runs"],
                "source_tables": ["deliveries"],
                "sample_size": len(rows_out),
                "calculation": "latest grouped matches then per-match aggregate",
            },
        }

    def _player_vs_bowling_type(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities["player"])
        bowling_type = str(plan.entities["bowling_type"])
        metric = str(plan.metric or "strike_rate")
        like_value = "%left%pace%" if bowling_type == "left-arm pace" else "%left%spin%" if bowling_type == "left-arm spin" else "%right%pace%" if bowling_type == "right-arm pace" else "%right%spin%"
        row = self._run(
            "SELECT COALESCE(SUM(batter_runs), 0) AS runs, COALESCE(SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END), 0) AS balls, COALESCE(SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END), 0) AS sixes FROM deliveries WHERE batter = ? AND LOWER(COALESCE(bowler_type, '')) LIKE ?",
            (player, like_value),
        )[0]
        runs = int(row["runs"])
        balls = int(row["balls"])
        sixes = int(row["sixes"])
        if metric == "runs":
            value: float | int = runs
        elif metric == "sixes":
            value = sixes
        else:
            value = round(runs * 100.0 / balls, 2) if balls else 0.0

        return {
            "value": value,
            "label": f"{player} vs {bowling_type}",
            "evidence": {
                "interpretation": "player versus bowling type",
                "filters": plan.entities,
                "metric": metric,
                "source_tables": ["deliveries"],
                "sample_size": balls,
                "calculation": "bowler_type filtered batting aggregate",
            },
        }

    def _knowledge_lookup(self, plan: QueryPlan) -> dict[str, Any]:
        player = str(plan.entities.get("player", "")).strip()
        if not player:
            raise ValueError("player is required")
        attribute = str(plan.metric or "full_name")
        answer = lookup_player_fact(self.conn, player, attribute)
        return {"value": answer.value, "label": answer.label, "evidence": answer.evidence}

    def _team_season_info(self, plan: QueryPlan) -> dict[str, Any]:
        team = str(plan.entities.get("team", "")).strip()
        season = plan.entities.get("season")
        if not team:
            raise ValueError("team is required")
        if isinstance(season, int):
            row = self._run(
                """
                SELECT season_id, captain, coach, owner, home_venue, source_key, source_url, retrieved_at, verification_status
                FROM team_season_knowledge
                WHERE canonical_team_name = ? AND season_id = ?
                ORDER BY retrieved_at DESC
                LIMIT 1
                """,
                (team, season),
            )
        else:
            row = self._run(
                """
                SELECT season_id, captain, coach, owner, home_venue, source_key, source_url, retrieved_at, verification_status
                FROM team_season_knowledge
                WHERE canonical_team_name = ?
                ORDER BY season_id DESC, retrieved_at DESC
                LIMIT 1
                """,
                (team,),
            )
        if not row:
            return {
                "value": None,
                "label": "Verified information is not currently available.",
                "evidence": {
                    "interpretation": "team season knowledge lookup",
                    "team": team,
                    "season": season,
                    "source_tables": ["team_season_knowledge"],
                },
            }
        item = row[0]
        attribute = str(plan.metric or "captain")
        resolved_season = int(item["season_id"])
        value = item[attribute] if attribute in item.keys() else None
        if value is None or str(value).strip() == "":
            label = "Verified information is not currently available."
        else:
            label = f"{team} {attribute} in {resolved_season}"
        return {
            "value": value,
            "label": label,
            "evidence": {
                "interpretation": "team season knowledge lookup",
                "team": team,
                "season": resolved_season,
                "attribute": attribute,
                "source": item["source_key"],
                "source_url": item["source_url"],
                "retrieved_at": item["retrieved_at"],
                "verification_status": item["verification_status"],
            },
        }

    def _match_result_summary(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season")
        if not isinstance(season, int):
            raise ValueError("season is required")
        match_type = str(plan.entities.get("match_type") or "").lower().strip()
        sql = (
            "SELECT match_id, match_date, match_number, team_a_display, team_b_display, winner, result_type, result_margin, venue, city "
            "FROM match_metadata WHERE season_id = ?"
        )
        params: list[Any] = [season]
        if match_type == "final":
            sql += " AND LOWER(COALESCE(match_type, '')) = 'final'"
        sql += " ORDER BY match_date DESC, match_id DESC LIMIT 1"
        rows = self._run(sql, tuple(params))
        if not rows:
            return {
                "value": None,
                "label": "Verified information is not currently available.",
                "evidence": {
                    "interpretation": "match result summary lookup",
                    "season": season,
                    "match_type": match_type or None,
                    "source_tables": ["match_metadata"],
                },
            }
        row = rows[0]
        return {
            "value": {
                "match_id": int(row["match_id"]),
                "match_number": row["match_number"],
                "date": row["match_date"],
                "teams": [row["team_a_display"], row["team_b_display"]],
                "winner": row["winner"],
                "margin": f"{row['result_margin']} {row['result_type']}" if row["result_margin"] else None,
                "venue": row["venue"],
                "city": row["city"],
            },
            "label": "Match result summary",
            "evidence": {
                "interpretation": "match result summary lookup",
                "season": season,
                "match_type": match_type or None,
                "source_tables": ["match_metadata"],
            },
        }

    def _fixtures(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season") if isinstance(plan.entities.get("season"), int) else None
        team = str(plan.entities.get("team")) if plan.entities.get("team") else None
        fixtures = list_fixtures(self.conn, season=season, team=team, status=None)
        limited = fixtures[: int(plan.limit or 10)]
        return {
            "value": limited,
            "label": f"Fixtures ({len(limited)} shown)",
            "evidence": {
                "interpretation": "fixture listing",
                "filters": {"season": season, "team": team},
                "source_tables": ["match_metadata"],
                "sample_size": len(fixtures),
            },
        }

    def _results(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season") if isinstance(plan.entities.get("season"), int) else None
        team = str(plan.entities.get("team")) if plan.entities.get("team") else None
        rows = list_results(self.conn, season=season, team=team)
        limited = rows[: int(plan.limit or 10)]
        return {
            "value": limited,
            "label": f"Results ({len(limited)} shown)",
            "evidence": {
                "interpretation": "result listing",
                "filters": {"season": season, "team": team},
                "source_tables": ["match_metadata"],
                "sample_size": len(rows),
            },
        }

    def _points_table(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season")
        if not isinstance(season, int):
            raise ValueError("season is required")
        table = points_table(self.conn, season)
        return {
            "value": table,
            "label": f"Points table {season}",
            "evidence": {
                "interpretation": "computed season standings",
                "filters": {"season": season},
                "source_tables": ["match_metadata", "innings_summary"],
                "sample_size": len(table),
            },
        }

    def _top_performers(self, plan: QueryPlan) -> dict[str, Any]:
        season = plan.entities.get("season") if isinstance(plan.entities.get("season"), int) else None
        limit = int(plan.limit or 5)
        top = top_performers(self.conn, season=season, limit=limit)
        return {
            "value": top,
            "label": "Top performers",
            "evidence": {
                "interpretation": "season top performer aggregates",
                "filters": {"season": season, "limit": limit},
                "source_tables": ["deliveries"],
            },
        }

    def _prediction_info(self, plan: QueryPlan) -> dict[str, Any]:
        metric = str(plan.metric or "next_ball")
        if metric == "prediction_change":
            label = "Prediction changes when pre-ball state changes (score, wickets, striker, bowler, pressure, or recent pattern)."
        else:
            label = "Next-ball probability requires an active Time Machine replay context. Start replay and ask again for the current ball."
        return {
            "value": None,
            "label": label,
            "evidence": {
                "interpretation": "prediction guidance",
                "requested_metric": metric,
                "source_tables": ["deliveries", "replay_session"],
            },
        }

    def execute(self, plan: QueryPlan) -> dict[str, Any]:
        if plan.operation == "clarify":
            reason = str(plan.entities.get("reason", "ambiguous_entity"))
            return {
                "value": {"candidates": plan.entities.get("candidates", [])},
                "label": "Need clarification",
                "evidence": {
                    "interpretation": "entity disambiguation",
                    "reason": reason,
                    "source_tables": ["players", "match_team_map", "team_alias"],
                },
            }

        if plan.operation in {"aggregate", "lookup"}:
            if plan.entity == "player":
                return self._aggregate_player(plan)
            if plan.entity == "bowler_vs_team":
                return self._aggregate_bowler_vs_team(plan)
            if plan.entity == "match_metadata":
                return self._lookup_match_metadata(plan)
            if plan.entity == "match_result_summary":
                return self._match_result_summary(plan)
            if plan.entity == "player_vs_bowling_type":
                return self._player_vs_bowling_type(plan)

        if plan.operation == "knowledge_lookup" and plan.entity == "player_knowledge":
            return self._knowledge_lookup(plan)

        if plan.operation == "team_season_info" and plan.entity == "team_season":
            return self._team_season_info(plan)

        if plan.operation == "fixtures" and plan.entity == "fixtures":
            return self._fixtures(plan)

        if plan.operation == "results" and plan.entity == "results":
            return self._results(plan)

        if plan.operation == "points_table" and plan.entity == "points_table":
            return self._points_table(plan)

        if plan.operation == "top_performers" and plan.entity == "top_performers":
            return self._top_performers(plan)

        if plan.operation == "prediction_info" and plan.entity == "prediction":
            return self._prediction_info(plan)

        if plan.operation == "rank":
            return self._rank(plan)

        if plan.operation == "compare":
            return self._compare_players(plan)

        if plan.operation == "trend" and plan.entity == "player_recent_matches":
            return self._player_recent_matches(plan)

        raise ValueError("Unsupported semantic operation/entity combination")


class AskMatchGenomeEngine:
    def __init__(self, conn: sqlite3.Connection, provider: AskPlanProvider | None = None) -> None:
        self.conn = conn
        ensure_knowledge_bootstrap(self.conn)
        self.semantic = SemanticResolver(conn)
        rule_provider = RuleBasedPlanProvider()
        llm_provider = LlmAskPlanProvider()
        self.provider = provider or CompositePlanProvider(llm_provider, rule_provider)
        self.validator = QueryPlanValidator(self.semantic)
        self.executor = QueryExecutor(conn, self.semantic)
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
            comma_parts = re.split(r",\s*(?=how|who|what|compare|show|which|in\s+\d{4})", piece, flags=re.IGNORECASE)
            for item in comma_parts:
                and_parts = re.split(r"\s+and\s+(?=how|who|what|compare|show|which)", item, flags=re.IGNORECASE)
                for sub in and_parts:
                    trimmed = sub.strip(" ,")
                    if trimmed:
                        out.append(trimmed)
        return out

    def _plan_to_payload(self, plan: QueryPlan) -> dict[str, Any]:
        return {
            "operation": plan.operation,
            "entity": plan.entity,
            "entities": plan.entities,
            "metric": plan.metric,
            "metrics": plan.metrics,
            "filters": plan.filters,
            "group_by": plan.group_by,
            "order_by": plan.order_by,
            "limit": plan.limit,
            "threshold": plan.threshold,
        }

    @staticmethod
    def _extract_context_entities(plan: QueryPlan, answer: dict[str, Any]) -> dict[str, Any]:
        entities = dict(plan.entities)
        value = answer.get("value")
        if isinstance(value, dict):
            if isinstance(value.get("player"), str):
                entities["player"] = value["player"]
            if isinstance(value.get("player_of_match"), str):
                entities["player"] = value["player_of_match"]
            players = value.get("players")
            if isinstance(players, list) and players:
                first = players[0]
                if isinstance(first, dict) and isinstance(first.get("player"), str):
                    entities["player"] = first["player"]
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict) and isinstance(first.get("player"), str):
                entities["player"] = first["player"]
        return entities

    def ask(self, question: str) -> dict[str, Any]:
        sub_questions = self._split_questions(question)
        if not sub_questions:
            raise ValueError("Question is empty")

        results: list[dict[str, Any]] = []
        for sub in sub_questions:
            started = time.perf_counter()
            plan = self.provider.build_plan(sub, self.semantic, self.context)
            if plan is None:
                results.append(
                    {
                        "question": sub,
                        "status": "unsupported",
                        "message": "MatchGenome does not currently have a verified knowledge path for this question.",
                    }
                )
                continue

            try:
                self.validator.validate(plan)
                answer = self.executor.execute(plan)
                elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
                self.context.last_plan = plan
                self.context.last_entities = self._extract_context_entities(plan, answer)

                status = "clarification_needed" if plan.operation == "clarify" else "ok"
                results.append(
                    {
                        "question": sub,
                        "status": status,
                        "query_plan": self._plan_to_payload(plan),
                        "result": answer,
                        "latency_ms": elapsed_ms,
                    }
                )
            except Exception as exc:
                message = str(exc)
                if "No matching" in message or "not available" in message or "required" in message:
                    results.append(
                        {
                            "question": sub,
                            "status": "unsupported",
                            "query_plan": self._plan_to_payload(plan),
                            "message": message,
                        }
                    )
                    continue
                results.append(
                    {
                        "question": sub,
                        "status": "error",
                        "query_plan": self._plan_to_payload(plan),
                        "message": message,
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

