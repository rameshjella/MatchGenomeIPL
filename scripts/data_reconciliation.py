from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.ask_matchgenome import AskMatchGenomeEngine
from matchgenomeipl.time_machine import TimeMachineService
from matchgenomeipl.time_machine_api import TimeMachineAPI
from matchgenomeipl.ipl_knowledge import season_stats_overview


def _season_from_info(raw: Any) -> int | None:
    value = str(raw or "").strip()
    if not value:
        return None
    if value == "2020/21":
        return 2020
    split = re.search(r"(20\d{2})\s*/\s*(\d{2})", value)
    if split:
        first = int(split.group(1))
        suffix = int(split.group(2))
        candidate = ((first // 100) * 100) + suffix
        if candidate < first:
            candidate += 100
        return candidate
    years = [int(v) for v in re.findall(r"(20\d{2})", value)]
    return max(years) if years else None


def _source_match_delivery_counts(zip_path: Path) -> tuple[dict[int, set[int]], dict[int, int]]:
    by_season_matches: dict[int, set[int]] = defaultdict(set)
    by_season_deliveries: dict[int, int] = defaultdict(int)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not (name.endswith(".json") and name[:-5].isdigit()):
                continue
            match_id = int(name[:-5])
            with zf.open(name) as handle:
                payload = json.load(handle)
            season = _season_from_info(payload.get("info", {}).get("season"))
            if season is None:
                continue
            by_season_matches[season].add(match_id)
            innings_list = payload.get("innings", []) if isinstance(payload.get("innings"), list) else []
            for innings in innings_list:
                if not isinstance(innings, dict):
                    continue
                overs = innings.get("overs", []) if isinstance(innings.get("overs"), list) else []
                for over in overs:
                    if not isinstance(over, dict):
                        continue
                    deliveries = over.get("deliveries", []) if isinstance(over.get("deliveries"), list) else []
                    by_season_deliveries[season] += len(deliveries)
    return by_season_matches, by_season_deliveries


def _local_metrics(conn: sqlite3.Connection, season: int) -> dict[str, float]:
    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT match_id) AS matches,
            COUNT(*) AS deliveries,
            SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END) AS sixes,
            SUM(CASE WHEN is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 ELSE 0 END) AS wickets,
            SUM(CASE WHEN legal_ball = 1 AND total_runs = 0 THEN 1 ELSE 0 END) AS dot_balls,
            SUM(CASE WHEN legal_ball = 1 AND batter_runs = 0 THEN 1 ELSE 0 END) AS dot_balls_batter_zero,
            SUM(CASE WHEN is_super_over = 1 AND batter_runs = 4 THEN 1 ELSE 0 END) AS super_over_fours,
            SUM(CASE WHEN is_super_over = 1 AND is_wicket = 1 AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 ELSE 0 END) AS super_over_wickets
        FROM deliveries
        WHERE season_id = ?
        """,
        (season,),
    ).fetchone()
    return {
        "matches": float(row["matches"] or 0),
        "deliveries": float(row["deliveries"] or 0),
        "fours": float(row["fours"] or 0),
        "sixes": float(row["sixes"] or 0),
        "wickets": float(row["wickets"] or 0),
        "dot_balls": float(row["dot_balls"] or 0),
        "dot_balls_batter_zero": float(row["dot_balls_batter_zero"] or 0),
        "super_over_fours": float(row["super_over_fours"] or 0),
        "super_over_wickets": float(row["super_over_wickets"] or 0),
    }


def _official_2026_reference() -> dict[str, float]:
    return {
        "vaibhav_runs": 776.0,
        "vaibhav_avg": 48.5,
        "vaibhav_sixes": 72.0,
        "rabada_wickets": 29.0,
        "season_fours": 2332.0,
        "season_sixes": 1426.0,
        "season_wickets": 835.0,
        "season_dot_balls": 5686.0,
    }


def build_report(conn: sqlite3.Connection, zip_path: Path) -> dict[str, Any]:
    source_matches, source_deliveries = _source_match_delivery_counts(zip_path)
    seasons_local = {int(r[0]) for r in conn.execute("SELECT DISTINCT season_id FROM deliveries")}
    seasons_source = set(source_matches.keys())
    seasons = sorted(seasons_local | seasons_source)

    coverage = {
        int(r["season_id"]): dict(r)
        for r in conn.execute(
            "SELECT season_id, expected_matches, local_matches, missing_matches, status, verification_status FROM season_source_coverage WHERE source_key='cricsheet_ipl_json'"
        ).fetchall()
    }
    trust = {
        int(r["season_id"]): dict(r)
        for r in conn.execute(
            "SELECT season_id, coverage_status, reconciliation_status, status, reason FROM season_trust_gate"
        ).fetchall()
    }

    malformed = {
        int(r["season_id"]): int(r["c"])
        for r in conn.execute(
            """
            SELECT season_id, COUNT(*) AS c
            FROM deliveries
            WHERE innings IS NULL OR over_number IS NULL OR ball_number IS NULL OR TRIM(COALESCE(timeline_key, '')) = ''
            GROUP BY season_id
            """
        ).fetchall()
    }
    duplicate_delivery_identities = {
        int(r["season_id"]): int(r["duplicate_rows"])
        for r in conn.execute(
            """
            SELECT season_id, COALESCE(SUM(c - 1), 0) AS duplicate_rows
            FROM (
                SELECT season_id, match_id, innings, over_number, ball_number, COUNT(*) AS c
                FROM deliveries
                GROUP BY season_id, match_id, innings, over_number, ball_number
                HAVING COUNT(*) > 1
            )
            GROUP BY season_id
            """
        ).fetchall()
    }

    matrix: list[dict[str, Any]] = []
    for season in seasons:
        local_match_row = conn.execute(
            "SELECT COUNT(DISTINCT match_id) AS matches, COUNT(*) AS deliveries FROM deliveries WHERE season_id = ?",
            (season,),
        ).fetchone()
        local_match_count = int(local_match_row["matches"] or 0)
        local_delivery_count = int(local_match_row["deliveries"] or 0)
        source_match_count = len(source_matches.get(season, set()))
        source_delivery_count = int(source_deliveries.get(season, 0))
        local_ids = {int(r[0]) for r in conn.execute("SELECT DISTINCT match_id FROM deliveries WHERE season_id = ?", (season,)).fetchall()}
        source_ids = source_matches.get(season, set())
        cov = coverage.get(season)
        gate = trust.get(season)

        matrix.append(
            {
                "season": season,
                "local_match_count": local_match_count,
                "authoritative_match_count": source_match_count,
                "missing_matches": max(source_match_count - local_match_count, 0),
                "unexpected_matches": max(local_match_count - source_match_count, 0),
                "local_delivery_count": local_delivery_count,
                "authoritative_delivery_count": source_delivery_count,
                "missing_match_ids_sample": sorted(list(source_ids - local_ids))[:20],
                "unexpected_match_ids_sample": sorted(list(local_ids - source_ids))[:20],
                "duplicate_delivery_identities": duplicate_delivery_identities.get(season, 0),
                "malformed_delivery_identities": malformed.get(season, 0),
                "ingestion_status": "ready",
                "coverage_status": cov["status"] if cov else "not_recorded",
                "verification_status": cov["verification_status"] if cov else "unavailable",
                "trust_gate_status": gate["status"] if gate else "UNKNOWN",
                "trust_gate_reason": gate["reason"] if gate else "not_computed",
            }
        )

    rec_rows = conn.execute(
        """
        SELECT season_id, metric_name, source_key, local_value, reference_value, delta_value, relative_delta,
               status, root_cause, definition_notes, source_url
        FROM season_metric_reconciliation
        ORDER BY season_id, source_key, metric_name
        """
    ).fetchall()
    reconciliation = [dict(r) for r in rec_rows]

    official = _official_2026_reference()
    local_2026 = _local_metrics(conn, 2026)
    vaibhav = conn.execute(
        """
        SELECT
            SUM(CASE WHEN batter = 'V Suryavanshi' THEN batter_runs ELSE 0 END) AS runs,
            SUM(CASE WHEN batter = 'V Suryavanshi' AND is_wicket = 1 AND player_out = batter
                     AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('retired hurt','retired out','obstructing the field') THEN 1 ELSE 0 END) AS outs,
            SUM(CASE WHEN batter = 'V Suryavanshi' AND batter_runs = 6 THEN 1 ELSE 0 END) AS sixes
        FROM deliveries
        WHERE season_id = 2026
        """
    ).fetchone()
    rabada = conn.execute(
        """
        SELECT SUM(CASE WHEN bowler = 'K Rabada' AND is_wicket = 1
                     AND LOWER(COALESCE(wicket_kind, '')) NOT IN ('run out','retired hurt','retired out','obstructing the field')
                    THEN 1 ELSE 0 END) AS wickets
        FROM deliveries
        WHERE season_id = 2026
        """
    ).fetchone()

    discrepancy_2026 = {
        "season_fours": {
            "local": local_2026["fours"],
            "reference": official["season_fours"],
            "delta": local_2026["fours"] - official["season_fours"],
            "explainers": {
                "exclude_super_over": local_2026["fours"] - local_2026["super_over_fours"],
            },
        },
        "season_wickets": {
            "local": local_2026["wickets"],
            "reference": official["season_wickets"],
            "delta": local_2026["wickets"] - official["season_wickets"],
            "explainers": {
                "exclude_super_over": local_2026["wickets"] - local_2026["super_over_wickets"],
            },
        },
        "season_dot_balls": {
            "local": local_2026["dot_balls"],
            "reference": official["season_dot_balls"],
            "delta": local_2026["dot_balls"] - official["season_dot_balls"],
            "explainers": {
                "batter_zero_legal": local_2026["dot_balls_batter_zero"],
                "definition_gap_vs_local_dot": local_2026["dot_balls_batter_zero"] - local_2026["dot_balls"],
            },
        },
        "vaibhav_runs": {"local": float(vaibhav["runs"] or 0), "reference": official["vaibhav_runs"], "delta": float(vaibhav["runs"] or 0) - official["vaibhav_runs"]},
        "vaibhav_avg": {
            "local": round((float(vaibhav["runs"] or 0) / float(vaibhav["outs"] or 1)), 2) if int(vaibhav["outs"] or 0) else None,
            "reference": official["vaibhav_avg"],
            "delta": (round((float(vaibhav["runs"] or 0) / float(vaibhav["outs"] or 1)), 2) - official["vaibhav_avg"]) if int(vaibhav["outs"] or 0) else None,
        },
        "vaibhav_sixes": {"local": float(vaibhav["sixes"] or 0), "reference": official["vaibhav_sixes"], "delta": float(vaibhav["sixes"] or 0) - official["vaibhav_sixes"]},
        "rabada_wickets": {"local": float(rabada["wickets"] or 0), "reference": official["rabada_wickets"], "delta": float(rabada["wickets"] or 0) - official["rabada_wickets"]},
        "season_sixes": {"local": local_2026["sixes"], "reference": official["season_sixes"], "delta": local_2026["sixes"] - official["season_sixes"]},
    }

    def _official_2026_forensics(conn: sqlite3.Connection, zip_path: Path) -> dict[str, Any]:
        four_non_boundary = 0
        four_super_over = 0
        flagged_four_rows: list[dict[str, Any]] = []

        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not (name.endswith('.json') and name[:-5].isdigit()):
                    continue
                match_id = int(name[:-5])
                payload = json.loads(zf.read(name))
                if _season_from_info(payload.get('info', {}).get('season')) != 2026:
                    continue
                innings_list = payload.get('innings', []) if isinstance(payload.get('innings'), list) else []
                for innings_index, innings in enumerate(innings_list, start=1):
                    if not isinstance(innings, dict):
                        continue
                    is_super_over = 1 if bool(innings.get('super_over')) else 0
                    overs = innings.get('overs', []) if isinstance(innings.get('overs'), list) else []
                    for over in overs:
                        if not isinstance(over, dict):
                            continue
                        over_number = int(over.get('over', 0) or 0)
                        deliveries = over.get('deliveries', []) if isinstance(over.get('deliveries'), list) else []
                        for ball_number, delivery in enumerate(deliveries):
                            if not isinstance(delivery, dict):
                                continue
                            runs = delivery.get('runs', {}) if isinstance(delivery.get('runs'), dict) else {}
                            if int(runs.get('batter', 0) or 0) != 4:
                                continue
                            is_non_boundary = bool(runs.get('non_boundary', False))
                            if is_non_boundary:
                                four_non_boundary += 1
                            if is_super_over:
                                four_super_over += 1
                            if is_non_boundary or is_super_over:
                                flagged_four_rows.append(
                                    {
                                        'match_id': match_id,
                                        'innings': innings_index,
                                        'over_number': over_number,
                                        'ball_number': ball_number,
                                        'batter': delivery.get('batter'),
                                        'bowler': delivery.get('bowler'),
                                        'is_super_over': is_super_over,
                                        'non_boundary': is_non_boundary,
                                    }
                                )

        dot_gap_rows = conn.execute(
            """
            SELECT
                match_id, innings, over_number, ball_number,
                batter, bowler, batter_runs, total_runs,
                bye_runs, leg_bye_runs, penalty_runs, is_super_over,
                LOWER(COALESCE(wicket_kind, '')) AS wicket_kind
            FROM deliveries
            WHERE season_id = 2026
              AND legal_ball = 1
              AND batter_runs = 0
              AND total_runs > 0
            ORDER BY match_id, innings, over_number, ball_number
            """
        ).fetchall()
        dot_gap = [dict(row) for row in dot_gap_rows]

        dot_runout_scoring = [
            row for row in dot_gap if row['wicket_kind'] == 'run out'
        ]

        by_extra_kind: dict[str, int] = defaultdict(int)
        by_total_runs: dict[str, int] = defaultdict(int)
        by_super_over: dict[str, int] = defaultdict(int)
        for row in dot_gap:
            kind = []
            if int(row['bye_runs'] or 0) > 0:
                kind.append('bye')
            if int(row['leg_bye_runs'] or 0) > 0:
                kind.append('leg_bye')
            if int(row['penalty_runs'] or 0) > 0:
                kind.append('penalty')
            by_extra_kind['+'.join(kind) if kind else 'other'] += 1
            by_total_runs[str(int(row['total_runs'] or 0))] += 1
            by_super_over[str(int(row['is_super_over'] or 0))] += 1

        local_2026 = _local_metrics(conn, 2026)
        return {
            'fours': {
                'local_canonical_batter_runs_eq_4': local_2026['fours'],
                'official_reference': 2332.0,
                'delta': local_2026['fours'] - 2332.0,
                'non_boundary_fours': float(four_non_boundary),
                'super_over_fours': float(four_super_over),
                'boundary_regular_variant': float(local_2026['fours']) - float(four_non_boundary) - float(four_super_over),
                'flagged_deliveries': flagged_four_rows,
            },
            'dot_balls': {
                'canonical_legal_total_zero': local_2026['dot_balls'],
                'batter_facing_legal_batter_zero': local_2026['dot_balls_batter_zero'],
                'official_reference': 5686.0,
                'canonical_to_batter_facing_gap': local_2026['dot_balls_batter_zero'] - local_2026['dot_balls'],
                'gap_rows_count': len(dot_gap),
                'gap_grouping': {
                    'by_extra_kind': dict(sorted(by_extra_kind.items())),
                    'by_total_runs': dict(sorted(by_total_runs.items(), key=lambda kv: int(kv[0]))),
                    'by_super_over': dict(sorted(by_super_over.items(), key=lambda kv: int(kv[0]))),
                },
                'runout_scoring_rows': dot_runout_scoring,
                'batter_facing_minus_scoring_runout': local_2026['dot_balls_batter_zero'] - float(len(dot_runout_scoring)),
                'sample_rows': dot_gap[:30],
            },
            'wickets': {
                'local_canonical': local_2026['wickets'],
                'official_reference': 835.0,
                'exclude_super_over': local_2026['wickets'] - local_2026['super_over_wickets'],
                'super_over_wickets': local_2026['super_over_wickets'],
            },
        }

    forensic_2026 = _official_2026_forensics(conn, zip_path)
    representative_e2e = _representative_end_to_end_validation(
        conn,
        zip_path,
        [2008, 2012, 2016, 2019, 2023, 2024, 2025, 2026],
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "coverage_source_key": "cricsheet_ipl_json",
            "coverage_source_url": "https://cricsheet.org/downloads/ipl_json.zip",
            "zip_path": str(zip_path),
        },
        "seasons_audited": seasons,
        "coverage_matrix": matrix,
        "metric_reconciliation": reconciliation,
        "discrepancy_2026": discrepancy_2026,
        "forensic_2026": forensic_2026,
        "representative_end_to_end": representative_e2e,
    }


def _representative_end_to_end_validation(conn: sqlite3.Connection, zip_path: Path, seasons: list[int]) -> dict[str, Any]:
    service = TimeMachineService(conn)
    api = TimeMachineAPI(service)
    ask = AskMatchGenomeEngine(conn)
    source_matches, source_deliveries = _source_match_delivery_counts(zip_path)

    season_rows: list[dict[str, Any]] = []
    for season in seasons:
        source_metrics = {
            'matches': len(source_matches.get(season, set())),
            'deliveries': int(source_deliveries.get(season, 0)),
        }
        local = _local_metrics(conn, season)
        knowledge = season_stats_overview(conn, season)
        api_overview = api.get_stats_overview(season)

        db_view = {
            'matches': int(local['matches']),
            'deliveries': int(local['deliveries']),
            'runs': int(conn.execute('SELECT COALESCE(SUM(batter_runs),0) FROM deliveries WHERE season_id=?', (season,)).fetchone()[0]),
            'fours': int(local['fours']),
            'sixes': int(local['sixes']),
            'wickets': int(local['wickets']),
            'dot_balls': int(local['dot_balls']),
        }
        knowledge_view = {
            'matches': int(knowledge['matches']),
            'deliveries': int(conn.execute('SELECT COUNT(*) FROM deliveries WHERE season_id=?', (season,)).fetchone()[0]),
            'runs': int(knowledge['runs']),
            'fours': int(knowledge['fours']),
            'sixes': int(knowledge['sixes']),
            'wickets': int(knowledge['wickets']),
            'dot_balls': int(knowledge['dot_balls']),
        }
        api_view = {
            'matches': int(api_overview['matches']),
            'deliveries': int(conn.execute('SELECT COUNT(*) FROM deliveries WHERE season_id=?', (season,)).fetchone()[0]),
            'runs': int(api_overview['runs']),
            'fours': int(api_overview['fours']),
            'sixes': int(api_overview['sixes']),
            'wickets': int(api_overview['wickets']),
            'dot_balls': int(api_overview['dot_balls']),
        }

        season_rows.append(
            {
                'season': season,
                'source_complete': source_metrics['matches'] == db_view['matches'] and source_metrics['deliveries'] == db_view['deliveries'],
                'source_counts': source_metrics,
                'db': db_view,
                'knowledge': knowledge_view,
                'api': api_view,
                'db_equals_knowledge': db_view == knowledge_view,
                'knowledge_equals_api': knowledge_view == api_view,
                'trust_gate': (knowledge.get('coverage') or {}).get('trust_gate'),
            }
        )

    ask_checks: dict[str, Any] = {}
    questions = [
        'Who scored the most runs in IPL 2024?',
        'Who scored the most runs in IPL 2026?',
        'Who is RCB captain?',
        'Who was RCB captain in 2016?',
    ]
    for question in questions:
        payload = ask.ask(question)
        result = payload['results'][0]
        ask_checks[question] = {
            'status': result.get('status'),
            'label': (result.get('result') or {}).get('label'),
            'value_present': (result.get('result') or {}).get('value') is not None,
        }

    return {
        'seasons': season_rows,
        'ask_checks': ask_checks,
    }


def main() -> None:
    db_path = ROOT / "data" / "ipl.sqlite3"
    zip_path = ROOT / "artifacts" / "ipl_json.zip"
    conn = connect_db(db_path)
    try:
        initialize_schema(conn)
        report = build_report(conn, zip_path)
    finally:
        conn.close()

    out_path = ROOT / "artifacts" / "data_reconciliation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved artifact: {out_path}")


if __name__ == "__main__":
    main()

