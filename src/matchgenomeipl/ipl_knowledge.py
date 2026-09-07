from __future__ import annotations

from dataclasses import dataclass
import ast
from datetime import date
import re
import sqlite3
from typing import Any


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
        return None, []

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
            label="MatchGenome does not currently have verified information for that attribute.",
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
    if value is None or str(value).strip() == "":
        return KnowledgeAnswer(
            value=None,
            label="MatchGenome does not currently have verified information for that attribute.",
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
        "SELECT bowler AS player, SUM(CASE WHEN is_wicket = 1 THEN 1 ELSE 0 END) AS wickets FROM deliveries"
        + season_sql
        + " GROUP BY bowler ORDER BY wickets DESC, player ASC LIMIT ?",
        tuple(params + [limit]),
    ).fetchall()

    return {
        "runs": [{"player": str(r["player"]), "value": int(r["runs"])} for r in runs],
        "wickets": [{"player": str(r["player"]), "value": int(r["wickets"])} for r in wickets],
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
        SELECT team,
               SUM(runs_for) AS runs_for,
               SUM(balls_for) AS balls_for,
               SUM(runs_against) AS runs_against,
               SUM(balls_against) AS balls_against
        FROM (
            SELECT i.team_batting AS team,
                   i.runs AS runs_for,
                   i.legal_balls AS balls_for,
                   i2.runs AS runs_against,
                   i2.legal_balls AS balls_against
            FROM innings_summary i
            JOIN innings_summary i2
              ON i2.match_id = i.match_id AND i2.season_id = i.season_id AND i2.innings != i.innings
            WHERE i.season_id = ?
        ) x
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
        ORDER BY retrieved_at DESC
        LIMIT 1
        """,
        (team, season),
    ).fetchone()
    if row is None:
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

