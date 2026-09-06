from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.http_transport import create_http_server


def main() -> None:
    db_path = ROOT / "data" / "ipl.sqlite3"
    server = create_http_server(db_path=db_path, host="127.0.0.1", port=8080)
    print("MatchGenome Time Machine running on http://127.0.0.1:8080")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.conn.close()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()

