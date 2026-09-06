from __future__ import annotations

import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.http_transport import create_http_server
from matchgenomeipl.ingestion import ensure_dataset_ready
from matchgenomeipl.database import connect_db, database_runtime_status
from matchgenomeipl.runtime_logging import log_event


def main() -> None:
    started = time.perf_counter()
    host = os.getenv("MATCHGENOME_HOST", "127.0.0.1")
    port = int(os.getenv("MATCHGENOME_PORT", "8080"))
    csv_path = ROOT / "data" / "ipl_ball_by_ball_data.csv"
    db_path = ROOT / "data" / "ipl.sqlite3"

    log_event("STARTUP", "MatchGenomeIPL Time Machine")
    log_event("ENV", "Python runtime", version=sys.version.split()[0], executable=sys.executable)
    log_event("ENV", "Repository root", root=ROOT)
    log_event("DB", "Opening SQLite", path=db_path)

    bootstrap_conn = connect_db(db_path)
    try:
        stats = ensure_dataset_ready(bootstrap_conn, csv_path)
        db_status = database_runtime_status(bootstrap_conn)
    finally:
        bootstrap_conn.close()

    if stats.skipped:
        log_event("DATA", "Source unchanged - ingestion skipped", source=stats.source_file)
    else:
        log_event(
            "DATA",
            "Dataset refresh completed",
            source=stats.source_file,
            loaded_rows=stats.loaded_rows,
            rejected_rows=stats.rejected_rows,
            status=stats.status,
        )

    log_event(
        "DB",
        "Runtime status",
        dataset_status=db_status.get("dataset_status"),
        deliveries=db_status.get("deliveries"),
    )

    server = create_http_server(db_path=db_path, host=host, port=port)
    url = f"http://{host}:{port}"
    log_event("SERVER", "HTTP transport ready", host=host, port=port, url=url)
    log_event("READY", "MatchGenomeIPL is ready", startup_seconds=round(time.perf_counter() - started, 3))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_event("SHUTDOWN", "Received interrupt - stopping server")
    finally:
        server.shutdown()
        server.server_close()
        server.conn.close()  # type: ignore[attr-defined]
        log_event("SHUTDOWN", "Server stopped")


if __name__ == "__main__":
    main()

