"""Probe UI-facing API endpoints for user-visible error leakage."""
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")

paths = [
    "/api/seasons",
    "/api/fixtures?season_id=2026",
    "/api/results?season_id=2026",
    "/api/seasons/2026/matches",
    "/api/stats/overview?season_id=2026",
    "/api/stats/leaderboards?season_id=2026&limit=8",
    "/api/stats/top-performers?season_id=2026&limit=5",
    "/api/stats/points-table?season_id=2026",
    "/api/teams/Chennai%20Super%20Kings?season_id=2026",
    "/api/teams/Royal%20Challengers%20Bengaluru?season_id=2026",
    "/api/players?query=dhoni&limit=20",
]

for path in paths:
    try:
        with urllib.request.urlopen(base + path, timeout=15) as resp:
            body = resp.read(400).decode("utf-8", "replace")
        print(f"{resp.status} {path} :: {body[:160]}")
    except urllib.error.HTTPError as exc:
        detail = exc.read(400).decode("utf-8", "replace")
        print(f"{exc.code} {path} :: {detail[:220]}")
    except Exception as exc:
        print(f"ERR {path} :: {exc}")
