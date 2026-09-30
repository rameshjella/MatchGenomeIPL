"""Stress the shared SQLite connection with concurrent requests."""
import sys
import threading
import urllib.error
import urllib.request

base = sys.argv[1].rstrip("/")
paths = [
    "/api/seasons",
    "/api/fixtures?season_id=2026",
    "/api/results?season_id=2026",
    "/api/stats/overview?season_id=2026",
    "/api/stats/leaderboards?season_id=2026&limit=8",
    "/api/teams/Chennai%20Super%20Kings?season_id=2026",
    "/api/matches/1527674/scorecard",
    "/api/players?query=sharma&limit=20",
]

failures: list[str] = []
lock = threading.Lock()


def worker(path: str) -> None:
    for _ in range(6):
        try:
            with urllib.request.urlopen(base + path, timeout=30) as resp:
                resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(200).decode("utf-8", "replace")
            with lock:
                failures.append(f"{exc.code} {path} :: {detail}")
        except Exception as exc:
            with lock:
                failures.append(f"ERR {path} :: {exc}")


threads = [threading.Thread(target=worker, args=(p,)) for p in paths for _ in range(3)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(f"requests={len(threads) * 6} failures={len(failures)}")
for item in failures[:10]:
    print(" -", item)

