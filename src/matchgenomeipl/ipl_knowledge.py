from __future__ import annotations

from dataclasses import dataclass
import ast
from datetime import date
import json
import difflib
import re
import sqlite3
from typing import Any

from .constants import NON_BOWLER_WICKETS


def _norm(value: str | None) -> str:
    raw = "" if value is None else str(value)
    lowered = raw.lower().replace(".", " ").replace("'", " ")
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _today_iso() -> str:
    return date.today().isoformat()


def _verification_rank(status: str | None) -> int:
    value = (status or "").strip().lower()
    if value == "verified":
        return 3
    if value == "provisional":
        return 2
    if value == "derived":
        return 1
    return 0


def _is_verified(status: str | None) -> bool:
    return (status or "").strip().lower() == "verified"


def season_coverage_status(conn: sqlite3.Connection, season: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT expected_matches, local_matches, missing_matches, status,
               verification_status, source_key, source_url, retrieved_at
        FROM season_source_coverage
        WHERE season_id = ? AND source_key = 'cricsheet_ipl_json'
        LIMIT 1
        """,
        (season,),
    ).fetchone()
    if row is None:
        return None
    return {
        "expected_matches": int(row["expected_matches"] or 0),
        "local_matches": int(row["local_matches"] or 0),
        "missing_matches": int(row["missing_matches"] or 0),
        "status": str(row["status"] or "unknown"),
        "verification_status": str(row["verification_status"] or "unknown"),
        "source": str(row["source_key"] or ""),
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
    }


def season_trust_status(conn: sqlite3.Connection, season: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT season_id, coverage_status, reconciliation_status, status, reason,
               source_key, source_url, retrieved_at, verification_status
        FROM season_trust_gate
        WHERE season_id = ?
        LIMIT 1
        """,
        (season,),
    ).fetchone()
    if row is None:
        return None
    return {
        "season_id": int(row["season_id"]),
        "coverage_status": str(row["coverage_status"]),
        "reconciliation_status": str(row["reconciliation_status"]),
        "status": str(row["status"]),
        "reason": str(row["reason"]),
        "source": str(row["source_key"]),
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
        "verification_status": str(row["verification_status"]),
    }


def season_has_verified_complete_coverage(conn: sqlite3.Connection, season: int) -> tuple[bool, dict[str, Any]]:
    trust = season_trust_status(conn, season)
    if trust is not None:
        trusted = trust["status"] in {"PASS", "PASS_WITH_DEFINITION_NOTE"}
        return trusted, {
            "reason": "ok" if trusted else str(trust.get("reason") or "season_not_trusted"),
            "season_id": season,
            "trust": trust,
            "coverage": season_coverage_status(conn, season),
        }

    coverage = season_coverage_status(conn, season)
    if coverage is None:
        return False, {
            "reason": "coverage_not_recorded",
            "season_id": season,
        }
    is_complete = coverage["status"] == "complete" and _is_verified(coverage["verification_status"])
    return is_complete, {
        "reason": "ok" if is_complete else "coverage_incomplete",
        "season_id": season,
        "coverage": coverage,
    }


def _player_activity_map(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in conn.execute("SELECT batter AS player, COUNT(*) AS c FROM deliveries GROUP BY batter").fetchall():
        counts[str(row["player"])] = int(row["c"])
    for row in conn.execute("SELECT bowler AS player, COUNT(*) AS c FROM deliveries GROUP BY bowler").fetchall():
        player = str(row["player"])
        counts[player] = counts.get(player, 0) + int(row["c"])
    return counts


def _normalize_player_name_for_identity(raw: str) -> str | None:
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


def ensure_knowledge_bootstrap(conn: sqlite3.Connection) -> None:
    # Canonical rows for known players in dataset; facts remain empty until verified enrichment writes them.
    conn.execute("DELETE FROM player_identity_alias WHERE source_key = 'dataset_players' AND canonical_player_name LIKE '[%'")
    conn.execute("DELETE FROM player_knowledge WHERE source_key = 'dataset_players' AND canonical_player_name LIKE '[%'")

    players = conn.execute("SELECT player_name FROM players ORDER BY player_name").fetchall()
    for row in players:
        normalized_player = _normalize_player_name_for_identity(str(row["player_name"]))
        if normalized_player is None:
            continue
        player = normalized_player
        conn.execute(
            """
            INSERT INTO player_knowledge(
                canonical_player_name,
                source_key,
                source_url,
                retrieved_at,
                verification_status
            )
            VALUES (?, 'dataset_players', NULL, CURRENT_TIMESTAMP, 'derived')
            ON CONFLICT(canonical_player_name) DO NOTHING
            """,
            (player,),
        )

        aliases = {player}
        tokens = _norm(player).split()
        if tokens:
            aliases.add(" ".join(tokens))
            aliases.add("".join(tokens))
            aliases.add(tokens[-1])
            if len(tokens) >= 2:
                aliases.add(f"{tokens[0]} {tokens[-1]}")
                aliases.add(f"{tokens[0][0]} {tokens[-1]}")

        for alias in sorted(a for a in aliases if a):
            conn.execute(
                """
                INSERT INTO player_identity_alias(
                    alias_name,
                    canonical_player_name,
                    source_key,
                    source_url,
                    retrieved_at,
                    verification_status
                )
                VALUES (?, ?, 'dataset_players', NULL, CURRENT_TIMESTAMP, 'derived')
                ON CONFLICT(alias_name, canonical_player_name) DO NOTHING
                """,
                (alias, player),
            )

        identity_id = f"player:{_norm(player).replace(' ', '_')}"
        aliases_json = json.dumps(sorted(a for a in aliases if a))
        conn.execute(
            """
            INSERT INTO player_identity(
                player_id,
                canonical_name,
                full_name,
                display_name,
                short_name,
                initials,
                role,
                batting_style,
                bowling_style,
                aliases_json,
                source_names_json,
                source_identifiers_json,
                identity_confidence,
                verification_status,
                source,
                source_url,
                retrieved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, 'derived', 'dataset_players', NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(player_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                full_name = COALESCE(player_identity.full_name, excluded.full_name),
                display_name = excluded.display_name,
                short_name = excluded.short_name,
                initials = excluded.initials,
                aliases_json = excluded.aliases_json,
                source_names_json = excluded.source_names_json,
                source_identifiers_json = excluded.source_identifiers_json,
                identity_confidence = MAX(player_identity.identity_confidence, excluded.identity_confidence),
                retrieved_at = CURRENT_TIMESTAMP
            """,
            (
                identity_id,
                player,
                player,
                player,
                tokens[-1] if tokens else player,
                "".join(t[0].upper() for t in tokens if t),
                aliases_json,
                json.dumps([player]),
                json.dumps([]),
                0.65,
            ),
        )

    # Team bootstrap from enriched identity tables when present.
    teams = conn.execute(
        """
        SELECT DISTINCT COALESCE(current_canonical_name, historical_display_name) AS team_name,
                        short_name
        FROM team_identity
        """
    ).fetchall()
    for row in teams:
        team = str(row["team_name"])
        conn.execute(
            """
            INSERT INTO team_knowledge(
                canonical_team_name,
                short_name,
                source_key,
                source_url,
                retrieved_at,
                verification_status
            )
            VALUES (?, ?, 'team_identity', NULL, CURRENT_TIMESTAMP, 'derived')
            ON CONFLICT(canonical_team_name) DO NOTHING
            """,
            (team, row["short_name"]),
        )

    conn.commit()


def resolve_player_identity(conn: sqlite3.Connection, query: str) -> tuple[str | None, list[str]]:
    normalized = _norm(query)
    if not normalized:
        return None, []

    def fuzzy_match() -> tuple[str | None, list[str]]:
        query_tokens = normalized.split()
        if len(query_tokens) < 2:
            return None, []
        fuzzy_rows = conn.execute("SELECT DISTINCT canonical_player_name FROM player_knowledge").fetchall()
        fuzzy_scored: list[tuple[str, float]] = []
        for row in fuzzy_rows:
            name = str(row["canonical_player_name"])
            tokens = _norm(name).split()
            if len(tokens) < 2:
                continue
            last_ratio = difflib.SequenceMatcher(None, query_tokens[-1], tokens[-1]).ratio()
            if len(tokens[0]) == 1 and query_tokens[0]:
                first_ratio = 1.0 if tokens[0] == query_tokens[0][0] else 0.0
            else:
                first_ratio = difflib.SequenceMatcher(None, query_tokens[0], tokens[0]).ratio()
            if last_ratio < 0.82 or first_ratio < 0.34:
                continue
            fuzzy_scored.append((name, (last_ratio * 80.0) + (first_ratio * 20.0)))
        fuzzy_scored.sort(key=lambda item: (-item[1], item[0]))
        if not fuzzy_scored:
            return None, []
        candidates = [name for name, _ in fuzzy_scored[:8]]
        if len(fuzzy_scored) == 1 or fuzzy_scored[0][1] >= fuzzy_scored[1][1] + 16.0:
            return fuzzy_scored[0][0], candidates
        return None, candidates

    activity = _player_activity_map(conn)
    token_set = set(normalized.split())
    rows = conn.execute(
        """
        SELECT alias_name, canonical_player_name, verification_status
        FROM player_identity_alias
        WHERE alias_name = ? OR alias_name LIKE ?
        """,
        (normalized, f"%{normalized}%"),
    ).fetchall()
    if not rows:
        return fuzzy_match()

    ranked: dict[str, float] = {}
    for row in rows:
        alias = _norm(str(row["alias_name"]))
        canonical = str(row["canonical_player_name"])
        score = float(_verification_rank(row["verification_status"]) * 25)
        if alias == normalized:
            score += 120.0
        elif alias.startswith(normalized):
            score += 35.0
        elif normalized in alias:
            score += 18.0

        canonical_tokens = set(_norm(canonical).split())
        overlap = len(token_set & canonical_tokens)
        score += overlap * 16.0
        score += min(activity.get(canonical, 0), 5000) / 250.0
        ranked[canonical] = max(ranked.get(canonical, 0.0), score)

    ordered = sorted(ranked.items(), key=lambda item: (-item[1], item[0]))
    candidates = [name for name, _ in ordered[:8]]
    if len(ordered) == 1:
        return ordered[0][0], candidates

    top_score = ordered[0][1]
    second_score = ordered[1][1]
    if top_score >= 130.0 and top_score >= second_score + 24.0:
        return ordered[0][0], candidates

    # Fuzzy fallback for known source spelling variants; keep strict ambiguity checks.
    fuzzy_canonical, fuzzy_candidates = fuzzy_match()
    if fuzzy_canonical:
        return fuzzy_canonical, fuzzy_candidates
    return None, candidates


@dataclass(frozen=True)
class KnowledgeAnswer:
    value: Any
    label: str
    evidence: dict[str, Any]


def lookup_player_fact(conn: sqlite3.Connection, player_query: str, attribute: str) -> KnowledgeAnswer:
    canonical, candidates = resolve_player_identity(conn, player_query)
    if canonical is None:
        if candidates:
            return KnowledgeAnswer(
                value={"candidates": candidates},
                label="Need clarification",
                evidence={
                    "interpretation": "player identity disambiguation",
                    "attribute": attribute,
                    "source_tables": ["player_identity_alias"],
                },
            )
        return KnowledgeAnswer(
            value=None,
            label="Player not found",
            evidence={
                "interpretation": "player identity lookup",
                "attribute": attribute,
                "source_tables": ["player_identity_alias"],
            },
        )

    row = conn.execute(
        """
        SELECT *
        FROM player_knowledge
        WHERE canonical_player_name = ?
        """,
        (canonical,),
    ).fetchone()
    if row is None:
        return KnowledgeAnswer(
            value=None,
            label="Verified information is not currently available.",
            evidence={
                "interpretation": "player knowledge lookup",
                "player": canonical,
                "attribute": attribute,
                "source_tables": ["player_knowledge"],
            },
        )

    column = {
        "full_name": "full_name",
        "date_of_birth": "date_of_birth",
        "spouse_name": "spouse_name",
        "children_count": "children_count",
        "batting_style": "batting_style",
        "bowling_style": "bowling_style",
        "role": "role",
        "biography": "biography",
        "nationality": "nationality",
    }.get(attribute, attribute)

    value = row[column] if column in row.keys() else None
    if not _is_verified(str(row["verification_status"])):
        return KnowledgeAnswer(
            value=None,
            label="Verified information is not currently available.",
            evidence={
                "interpretation": "player knowledge lookup",
                "player": canonical,
                "attribute": attribute,
                "source": row["source_key"],
                "source_url": row["source_url"],
                "verification_status": row["verification_status"],
                "retrieved_at": row["retrieved_at"],
                "reason": "only_provisional_or_unverified_data_available",
            },
        )
    if value is None or str(value).strip() == "":
        return KnowledgeAnswer(
            value=None,
            label="Verified information is not currently available.",
            evidence={
                "interpretation": "player knowledge lookup",
                "player": canonical,
                "attribute": attribute,
                "source": row["source_key"],
                "source_url": row["source_url"],
                "verification_status": row["verification_status"],
                "retrieved_at": row["retrieved_at"],
            },
        )

    return KnowledgeAnswer(
        value=value,
        label=f"{canonical} {attribute.replace('_', ' ')}",
        evidence={
            "interpretation": "player knowledge lookup",
            "player": canonical,
            "attribute": attribute,
            "source": row["source_key"],
            "source_url": row["source_url"],
            "verification_status": row["verification_status"],
            "retrieved_at": row["retrieved_at"],
        },
    )


def list_fixtures(conn: sqlite3.Connection, season: int | None = None, team: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    today = _today_iso()
    sql = (
        "SELECT match_id, season_id, match_number, match_date, venue, city, team_a_display, team_b_display, winner, result_type, result_margin "
        "FROM match_metadata WHERE 1=1"
    )
    params: list[Any] = []
    if season is not None:
        sql += " AND season_id = ?"
        params.append(season)
    if team:
        sql += " AND (team_a_display = ? OR team_b_display = ?)"
        params.extend([team, team])
    rows = conn.execute(sql + " ORDER BY match_date, match_id", tuple(params)).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        match_date = row["match_date"]
        is_completed = bool(row["winner"])
        derived_status = "completed" if is_completed else ("upcoming" if (match_date and str(match_date) >= today) else "scheduled")
        if status and derived_status != status:
            continue
        out.append(
            {
                "match_id": int(row["match_id"]),
                "season_id": int(row["season_id"]),
                "match_number": row["match_number"],
                "match_date": match_date,
                "team_a": row["team_a_display"],
                "team_b": row["team_b_display"],
                "venue": row["venue"],
                "city": row["city"],
                "status": derived_status,
                "winner": row["winner"],
                "result_type": row["result_type"],
                "result_margin": row["result_margin"],
            }
        )
    return out


def list_results(conn: sqlite3.Connection, season: int | None = None, team: str | None = None) -> list[dict[str, Any]]:
    rows = list_fixtures(conn, season=season, team=team)
    return [row for row in rows if row["status"] == "completed"]


def top_performers(conn: sqlite3.Connection, season: int | None = None, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    params: list[Any] = []
    season_sql = ""
    if season is not None:
        season_sql = " WHERE season_id = ?"
        params.append(season)

    runs = conn.execute(
        "SELECT batter AS player, SUM(batter_runs) AS runs FROM deliveries"
        + season_sql
        + " GROUP BY batter ORDER BY runs DESC, player ASC LIMIT ?",
        tuple(params + [limit]),
    ).fetchall()
    wickets = conn.execute(
        "SELECT bowler AS player, SUM(CASE WHEN is_wicket = 1 AND COALESCE(wicket_kind, '') NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 ELSE 0 END) AS wickets FROM deliveries"
        + season_sql
        + " GROUP BY bowler ORDER BY wickets DESC, player ASC LIMIT ?",
        tuple(params + [limit]),
    ).fetchall()

    return {
        "runs": [{"player": str(r["player"]), "value": int(r["runs"])} for r in runs],
        "wickets": [{"player": str(r["player"]), "value": int(r["wickets"])} for r in wickets],
    }


def season_stats_overview(conn: sqlite3.Connection, season: int) -> dict[str, Any]:
    non_bowler = tuple(sorted(NON_BOWLER_WICKETS))
    placeholders = ",".join("?" for _ in non_bowler)
    row = conn.execute(
        f"""
        SELECT
            COUNT(DISTINCT match_id) AS matches,
            COUNT(DISTINCT season_id || '-' || match_id || '-' || innings) AS innings,
            SUM(batter_runs) AS runs,
            SUM(CASE WHEN legal_ball = 1 THEN 1 ELSE 0 END) AS legal_balls,
            SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END) AS sixes,
            SUM(CASE WHEN legal_ball = 1 AND total_runs = 0 THEN 1 ELSE 0 END) AS dot_balls,
            SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets
        FROM deliveries
        WHERE season_id = ?
        """,
        non_bowler + (season,),
    ).fetchone()
    matches = int(row["matches"] or 0)
    innings = int(row["innings"] or 0)
    runs = int(row["runs"] or 0)
    legal_balls = int(row["legal_balls"] or 0)
    dot_balls = int(row["dot_balls"] or 0)
    coverage = conn.execute(
        """
        SELECT
            COUNT(*) AS metadata_matches,
            SUM(CASE WHEN winner IS NOT NULL AND TRIM(winner) <> '' THEN 1 ELSE 0 END) AS completed_matches
        FROM match_metadata
        WHERE season_id = ?
        """,
        (season,),
    ).fetchone()
    authoritative_coverage = season_coverage_status(conn, season)
    trust_status = season_trust_status(conn, season)

    return {
        "season_id": season,
        "matches": matches,
        "innings": innings,
        "runs": runs,
        "legal_balls": legal_balls,
        "fours": int(row["fours"] or 0),
        "sixes": int(row["sixes"] or 0),
        "wickets": int(row["wickets"] or 0),
        "dot_balls": dot_balls,
        "dot_ball_percentage": round((dot_balls / legal_balls) * 100.0, 2) if legal_balls else 0.0,
        "source": "deliveries",
        "coverage": {
            "deliveries_matches": matches,
            "metadata_matches": int((coverage["metadata_matches"] if coverage else 0) or 0),
            "completed_matches": int((coverage["completed_matches"] if coverage else 0) or 0),
            "authoritative": authoritative_coverage,
            "trust_gate": trust_status,
        },
        "definitions": {
            "dot_balls": "legal deliveries where total_runs == 0",
            "wickets": "bowler-credited wickets excluding run out/retired/obstructing dismissals",
        },
    }


def season_leaderboards(conn: sqlite3.Connection, season: int, limit: int = 5) -> dict[str, Any]:
    non_bowler = tuple(sorted(NON_BOWLER_WICKETS))
    placeholders = ",".join("?" for _ in non_bowler)
    safe_limit = max(1, min(int(limit), 25))

    runs_rows = conn.execute(
        """
        SELECT batter AS player,
               SUM(batter_runs) AS runs,
               SUM(CASE WHEN is_wide_ball = 0 THEN 1 ELSE 0 END) AS balls,
               SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END) AS fours,
               SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END) AS sixes,
               SUM(CASE WHEN is_wicket = 1 AND player_out = batter AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('retired hurt', 'retired out', 'obstructing the field') THEN 1 ELSE 0 END) AS outs
        FROM deliveries
        WHERE season_id = ?
        GROUP BY batter
        """,
        (season,),
    ).fetchall()
    by_player: list[dict[str, Any]] = []
    for row in runs_rows:
        runs = int(row["runs"] or 0)
        balls = int(row["balls"] or 0)
        outs = int(row["outs"] or 0)
        by_player.append(
            {
                "player": str(row["player"]),
                "runs": runs,
                "balls": balls,
                "fours": int(row["fours"] or 0),
                "sixes": int(row["sixes"] or 0),
                "strike_rate": round((runs * 100.0 / balls), 2) if balls else None,
                "average": round((runs / outs), 2) if outs else None,
            }
        )

    wickets_rows = conn.execute(
        f"""
        SELECT bowler AS player,
               SUM(total_runs - bye_runs - leg_bye_runs) AS runs_conceded,
               SUM(legal_ball) AS legal_balls,
               SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ({placeholders}) THEN 1 ELSE 0 END) AS wickets
        FROM deliveries
        WHERE season_id = ?
        GROUP BY bowler
        """,
        non_bowler + (season,),
    ).fetchall()
    bowlers: list[dict[str, Any]] = []
    for row in wickets_rows:
        wickets = int(row["wickets"] or 0)
        legal_balls = int(row["legal_balls"] or 0)
        runs_conceded = int(row["runs_conceded"] or 0)
        bowlers.append(
            {
                "player": str(row["player"]),
                "wickets": wickets,
                "runs_conceded": runs_conceded,
                "legal_balls": legal_balls,
                "economy": round((runs_conceded * 6.0 / legal_balls), 2) if legal_balls else None,
                "bowling_average": round((runs_conceded / wickets), 2) if wickets else None,
                "bowling_strike_rate": round((legal_balls / wickets), 2) if wickets else None,
            }
        )

    player_scores = conn.execute(
        """
        SELECT batter AS player, match_id, innings, SUM(batter_runs) AS runs
        FROM deliveries
        WHERE season_id = ?
        GROUP BY batter, match_id, innings
        """,
        (season,),
    ).fetchall()
    highest_score: dict[str, int] = {}
    for row in player_scores:
        player = str(row["player"])
        score = int(row["runs"] or 0)
        highest_score[player] = max(score, highest_score.get(player, 0))

    def _top(items: list[dict[str, Any]], metric: str, *, descending: bool = True, require: Any = None) -> list[dict[str, Any]]:
        selected = [item for item in items if require(item)] if require else list(items)
        ordered = sorted(
            selected,
            key=lambda row: (
                row.get(metric) is None,
                -(float(row.get(metric) or 0.0)) if descending else float(row.get(metric) or 0.0),
                str(row.get("player", "")),
            ),
        )
        return [{"player": row["player"], "value": row.get(metric)} for row in ordered[:safe_limit]]

    strike_rate_qualifier = lambda row: int(row.get("balls") or 0) >= 120 and row.get("strike_rate") is not None
    economy_qualifier = lambda row: int(row.get("legal_balls") or 0) >= 120 and row.get("economy") is not None

    highest_score_rows = sorted(
        [{"player": p, "value": v} for p, v in highest_score.items()],
        key=lambda row: (-int(row["value"]), row["player"]),
    )[:safe_limit]

    return {
        "season_id": season,
        "qualification": {
            "best_strike_rate": "minimum 120 balls faced",
            "best_economy": "minimum 120 legal balls bowled",
        },
        "leaderboards": {
            "orange_cap_runs": _top(by_player, "runs"),
            "purple_cap_wickets": _top(bowlers, "wickets"),
            "most_sixes": _top(by_player, "sixes"),
            "most_fours": _top(by_player, "fours"),
            "highest_score": highest_score_rows,
            "best_strike_rate": _top(by_player, "strike_rate", require=strike_rate_qualifier),
            "best_economy": _top(bowlers, "economy", descending=False, require=economy_qualifier),
        },
    }


def points_table(conn: sqlite3.Connection, season: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT match_id, team_a_display, team_b_display, winner
        FROM match_metadata
        WHERE season_id = ?
        """,
        (season,),
    ).fetchall()

    standings: dict[str, dict[str, Any]] = {}

    def ensure(team: str) -> dict[str, Any]:
        if team not in standings:
            standings[team] = {
                "team": team,
                "matches": 0,
                "wins": 0,
                "losses": 0,
                "no_result": 0,
                "points": 0,
            }
        return standings[team]

    for row in rows:
        a = str(row["team_a_display"])
        b = str(row["team_b_display"])
        winner = row["winner"]
        ta = ensure(a)
        tb = ensure(b)
        ta["matches"] += 1
        tb["matches"] += 1
        if winner is None or str(winner).strip() == "":
            ta["no_result"] += 1
            tb["no_result"] += 1
            ta["points"] += 1
            tb["points"] += 1
            continue
        w = str(winner)
        if w == a:
            ta["wins"] += 1
            ta["points"] += 2
            tb["losses"] += 1
        elif w == b:
            tb["wins"] += 1
            tb["points"] += 2
            ta["losses"] += 1

    nrr_rows = conn.execute(
        """
        WITH innings_nrr AS (
            SELECT
                i.season_id,
                i.match_id,
                i.innings,
                i.team_batting AS team,
                i.runs AS runs_for,
                CASE
                    WHEN i.wickets >= 10 AND i.legal_balls < 120 THEN 120
                    ELSE i.legal_balls
                END AS balls_for,
                i2.runs AS runs_against,
                CASE
                    WHEN i2.wickets >= 10 AND i2.legal_balls < 120 THEN 120
                    ELSE i2.legal_balls
                END AS balls_against
            FROM innings_summary i
            JOIN innings_summary i2
              ON i2.match_id = i.match_id
             AND i2.season_id = i.season_id
             AND i2.innings != i.innings
            WHERE i.season_id = ?
        )
        SELECT
            team,
            SUM(runs_for) AS runs_for,
            SUM(balls_for) AS balls_for,
            SUM(runs_against) AS runs_against,
            SUM(balls_against) AS balls_against
        FROM innings_nrr
        GROUP BY team
        """,
        (season,),
    ).fetchall()
    nrr_map = {str(r["team"]): r for r in nrr_rows}

    for team, row in standings.items():
        nrr = nrr_map.get(team)
        if nrr:
            rf = int(nrr["runs_for"])
            bf = int(nrr["balls_for"])
            ra = int(nrr["runs_against"])
            ba = int(nrr["balls_against"])
            for_rr = (rf * 6.0 / bf) if bf else 0.0
            against_rr = (ra * 6.0 / ba) if ba else 0.0
            row["net_run_rate"] = round(for_rr - against_rr, 3)
        else:
            row["net_run_rate"] = 0.0

    return sorted(
        standings.values(),
        key=lambda r: (-int(r["points"]), -float(r["net_run_rate"]), r["team"]),
    )


def team_season_info(conn: sqlite3.Connection, team: str, season: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT canonical_team_name, season_id, captain, coach, owner, home_venue,
               source_key, source_url, retrieved_at, verification_status
        FROM team_season_knowledge
        WHERE canonical_team_name = ? AND season_id = ?
        ORDER BY retrieved_at DESC, team_season_id DESC
        LIMIT 1
        """,
        (team, season),
    ).fetchone()
    if row is None:
        return None
    if not _is_verified(str(row["verification_status"])):
        return None
    return {
        "team": row["canonical_team_name"],
        "season_id": int(row["season_id"]),
        "captain": row["captain"],
        "coach": row["coach"],
        "owner": row["owner"],
        "home_venue": row["home_venue"],
        "source": row["source_key"],
        "source_url": row["source_url"],
        "retrieved_at": row["retrieved_at"],
        "verification_status": row["verification_status"],
    }

