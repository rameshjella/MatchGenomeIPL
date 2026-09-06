from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import BOOLEAN_COLUMNS, INTEGER_COLUMNS, REQUIRED_COLUMNS


BOOL_TRUE = {"1", "true", "t", "yes", "y"}
BOOL_FALSE = {"0", "false", "f", "no", "n"}


@dataclass
class DatasetProfile:
    file_type: str
    row_count: int
    column_count: int
    columns: list[str]
    seasons: list[int]
    match_count: int
    innings_values: list[int]
    teams: list[str]
    players: int
    deliveries_per_match_min: int
    deliveries_per_match_max: int
    deliveries_per_match_avg: float
    innings_per_match_min: int
    innings_per_match_max: int
    null_counts: dict[str, int]
    duplicate_rows: int
    duplicate_delivery_identities: int
    invalid_numeric_counts: dict[str, int]
    invalid_boolean_counts: dict[str, int]
    impossible_run_records: int
    wicket_inconsistencies: int
    malformed_records: int
    super_over_records: int


@dataclass
class RowValidationResult:
    normalized: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def parse_int(value: str | None, column: str, required: bool = True) -> tuple[int | None, str | None]:
    raw = (value or "").strip()
    if raw == "":
        if required:
            return None, f"missing:{column}"
        return None, None
    try:
        num = int(raw)
    except ValueError:
        try:
            as_float = float(raw)
            if abs(as_float - round(as_float)) < 1e-9:
                num = int(round(as_float))
            else:
                return None, f"not_integer:{column}={raw}"
        except ValueError:
            return None, f"not_integer:{column}={raw}"
    return num, None


def parse_bool(value: str | None, column: str) -> tuple[int | None, str | None]:
    raw = (value or "").strip().lower()
    if raw in BOOL_TRUE:
        return 1, None
    if raw in BOOL_FALSE:
        return 0, None
    return None, f"invalid_boolean:{column}={value}"


def validate_columns(actual_columns: list[str]) -> tuple[bool, list[str]]:
    missing = [c for c in REQUIRED_COLUMNS if c not in actual_columns]
    extras = [c for c in actual_columns if c not in REQUIRED_COLUMNS]
    errors: list[str] = []
    if missing:
        errors.append(f"missing_columns:{','.join(missing)}")
    if extras:
        errors.append(f"unexpected_columns:{','.join(extras)}")
    return not missing, errors


def validate_and_normalize_row(row: dict[str, str]) -> RowValidationResult:
    result = RowValidationResult()

    # Parse integer-like columns first.
    for column in INTEGER_COLUMNS:
        value, error = parse_int(row.get(column), column, required=True)
        if error:
            result.errors.append(error)
        result.normalized[column] = value

    # Parse booleans from TRUE/FALSE-style source values.
    for column in BOOLEAN_COLUMNS:
        value, error = parse_bool(row.get(column), column)
        if error:
            result.errors.append(error)
        result.normalized[column] = value

    for column in [
        "batter",
        "bowler",
        "non_striker",
        "team_batting",
        "team_bowling",
        "batsman_type",
        "bowler_type",
        "player_out",
        "fielders_involved",
        "wicket_kind",
    ]:
        raw = (row.get(column) or "").strip()
        result.normalized[column] = raw or None

    required_text = ["batter", "bowler", "team_batting", "team_bowling"]
    for column in required_text:
        if not result.normalized.get(column):
            result.errors.append(f"missing:{column}")

    batter_runs = result.normalized.get("batter_runs") or 0
    extras = result.normalized.get("extras") or 0
    total_runs = result.normalized.get("total_runs")
    if total_runs is not None and batter_runs + extras != total_runs:
        result.errors.append("run_total_mismatch")

    extras_components = (
        (result.normalized.get("wide_ball_runs") or 0)
        + (result.normalized.get("no_ball_runs") or 0)
        + (result.normalized.get("leg_bye_runs") or 0)
        + (result.normalized.get("bye_runs") or 0)
        + (result.normalized.get("penalty_runs") or 0)
    )
    if result.normalized.get("extras") is not None and extras != extras_components:
        result.errors.append("extras_breakdown_mismatch")

    is_wicket = result.normalized.get("is_wicket")
    has_wicket_detail = bool(result.normalized.get("player_out") or result.normalized.get("wicket_kind"))
    if is_wicket == 1 and not has_wicket_detail:
        result.errors.append("wicket_flag_without_detail")
    if is_wicket == 0 and has_wicket_detail:
        result.errors.append("wicket_detail_without_flag")

    over_number = result.normalized.get("over_number")
    ball_number = result.normalized.get("ball_number")
    if over_number is not None and over_number < 0:
        result.errors.append("negative_over_number")
    if ball_number is not None and ball_number < 0:
        result.errors.append("negative_ball_number")

    result.normalized["legal_ball"] = 0 if (result.normalized.get("is_wide_ball") == 1 or result.normalized.get("is_no_ball") == 1) else 1
    return result


def build_timeline_key(normalized: dict[str, Any]) -> str:
    return (
        f"{normalized['season_id']:04d}-"
        f"{normalized['match_id']:08d}-"
        f"{normalized['innings']:02d}-"
        f"{normalized['over_number']:02d}-"
        f"{normalized['ball_number']:02d}"
    )


def profile_dataset(csv_path: Path | str) -> DatasetProfile:
    path = Path(csv_path)
    deliveries_per_match: Counter[int] = Counter()
    innings_per_match: defaultdict[int, set[int]] = defaultdict(set)
    null_counts: Counter[str] = Counter()
    invalid_numeric_counts: Counter[str] = Counter()
    invalid_boolean_counts: Counter[str] = Counter()

    duplicate_rows = 0
    duplicate_delivery_identities = 0
    malformed_records = 0
    impossible_run_records = 0
    wicket_inconsistencies = 0
    super_over_records = 0

    row_count = 0
    seasons: set[int] = set()
    matches: set[int] = set()
    innings_values: set[int] = set()
    teams: set[str] = set()
    players: set[str] = set()

    seen_rows: set[tuple[tuple[str, str], ...]] = set()
    seen_identity: set[tuple[int, int, int, int, int]] = set()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []

        for row in reader:
            row_count += 1
            row_tuple = tuple((k, row.get(k, "")) for k in columns)
            if row_tuple in seen_rows:
                duplicate_rows += 1
            else:
                seen_rows.add(row_tuple)

            for column in columns:
                value = (row.get(column) or "").strip().lower()
                if value in {"", "null"}:
                    null_counts[column] += 1

            validation = validate_and_normalize_row(row)
            if not validation.is_valid:
                malformed_records += 1
                for err in validation.errors:
                    if err.startswith("not_integer"):
                        invalid_numeric_counts[err.split(":", 1)[1].split("=")[0]] += 1
                    if err.startswith("invalid_boolean"):
                        invalid_boolean_counts[err.split(":", 1)[1].split("=")[0]] += 1
                    if err in {"run_total_mismatch", "extras_breakdown_mismatch"}:
                        impossible_run_records += 1
                    if err in {"wicket_flag_without_detail", "wicket_detail_without_flag"}:
                        wicket_inconsistencies += 1

            normalized = validation.normalized
            if all(normalized.get(k) is not None for k in ("season_id", "match_id", "innings", "over_number", "ball_number")):
                identity = (
                    normalized["season_id"],
                    normalized["match_id"],
                    normalized["innings"],
                    normalized["over_number"],
                    normalized["ball_number"],
                )
                if identity in seen_identity:
                    duplicate_delivery_identities += 1
                else:
                    seen_identity.add(identity)

            season = normalized.get("season_id")
            match = normalized.get("match_id")
            innings = normalized.get("innings")
            if season is not None:
                seasons.add(season)
            if match is not None:
                matches.add(match)
            if innings is not None:
                innings_values.add(innings)
            if match is not None:
                deliveries_per_match[match] += 1
                if innings is not None:
                    innings_per_match[match].add(innings)

            for team_field in ("team_batting", "team_bowling"):
                team_name = normalized.get(team_field)
                if team_name:
                    teams.add(team_name)

            for player_field in ("batter", "bowler", "non_striker", "player_out", "fielders_involved"):
                player_name = normalized.get(player_field)
                if player_name:
                    players.add(player_name)

            if normalized.get("is_super_over") == 1:
                super_over_records += 1

    if deliveries_per_match:
        min_deliveries = min(deliveries_per_match.values())
        max_deliveries = max(deliveries_per_match.values())
        avg_deliveries = sum(deliveries_per_match.values()) / len(deliveries_per_match)
    else:
        min_deliveries = max_deliveries = 0
        avg_deliveries = 0.0

    if innings_per_match:
        min_innings = min(len(x) for x in innings_per_match.values())
        max_innings = max(len(x) for x in innings_per_match.values())
    else:
        min_innings = max_innings = 0

    return DatasetProfile(
        file_type=path.suffix.lower().lstrip("."),
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        seasons=sorted(seasons),
        match_count=len(matches),
        innings_values=sorted(innings_values),
        teams=sorted(teams),
        players=len(players),
        deliveries_per_match_min=min_deliveries,
        deliveries_per_match_max=max_deliveries,
        deliveries_per_match_avg=round(avg_deliveries, 2),
        innings_per_match_min=min_innings,
        innings_per_match_max=max_innings,
        null_counts=dict(null_counts),
        duplicate_rows=duplicate_rows,
        duplicate_delivery_identities=duplicate_delivery_identities,
        invalid_numeric_counts=dict(invalid_numeric_counts),
        invalid_boolean_counts=dict(invalid_boolean_counts),
        impossible_run_records=impossible_run_records,
        wicket_inconsistencies=wicket_inconsistencies,
        malformed_records=malformed_records,
        super_over_records=super_over_records,
    )

