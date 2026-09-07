from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db, initialize_schema
from matchgenomeipl.enrichment import run_cricsheet_enrichment, run_reference_knowledge_enrichment


def main() -> None:
    db_path = ROOT / "data" / "ipl.sqlite3"
    conn = connect_db(db_path)
    try:
        initialize_schema(conn)
        cricsheet_stats = run_cricsheet_enrichment(conn, ROOT, force_refresh=False)
        knowledge_stats = run_reference_knowledge_enrichment(conn)
    finally:
        conn.close()
    print({"cricsheet": cricsheet_stats, "knowledge": knowledge_stats})


if __name__ == "__main__":
    main()

