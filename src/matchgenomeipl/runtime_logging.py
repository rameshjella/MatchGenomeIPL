from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log_level_value() -> int:
    name = os.getenv("MATCHGENOME_LOG_LEVEL", "INFO").upper()
    return _LEVELS.get(name, 20)


def is_sql_logging_enabled() -> bool:
    return os.getenv("MATCHGENOME_SQL_LOG", "0").strip() == "1"


def _sanitize(value: Any) -> str:
    text = str(value)
    if len(text) > 160:
        return text[:157] + "..."
    return text


def log_event(tag: str, message: str, level: str = "INFO", **fields: Any) -> None:
    level_name = level.upper()
    if _LEVELS.get(level_name, 20) < _log_level_value():
        return

    details = ""
    if fields:
        pairs = [f"{key}={_sanitize(value)}" for key, value in fields.items()]
        details = " | " + " ".join(pairs)
    print(f"[{_now_utc()}] [{tag}] {message}{details}")


def log_http(method: str, path: str, status: int, started_at: float) -> None:
    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    log_event("HTTP", f"{method} {path} -> {status}", duration_ms=elapsed_ms)


def log_sql(operation: str, sql: str, params: tuple[Any, ...], started_at: float, row_count: int | None = None) -> None:
    if not is_sql_logging_enabled():
        return
    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    clean_sql = " ".join(sql.strip().split())
    details: dict[str, Any] = {
        "operation": operation,
        "params": tuple(_sanitize(p) for p in params),
        "duration_ms": elapsed_ms,
    }
    if row_count is not None:
        details["rows"] = row_count
    log_event("SQL", clean_sql, level="INFO", **details)

