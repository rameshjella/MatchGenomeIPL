from __future__ import annotations

import io
import os
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.runtime_logging import log_event, log_sql


class RuntimeLoggingTests(unittest.TestCase):
    def test_log_event_prints_at_info(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            log_event("TEST", "hello", level="INFO", value=1)
        output = buf.getvalue()
        self.assertIn("[TEST]", output)
        self.assertIn("hello", output)

    def test_sql_logging_respects_toggle(self) -> None:
        original = os.environ.get("MATCHGENOME_SQL_LOG")
        os.environ["MATCHGENOME_SQL_LOG"] = "0"
        off = io.StringIO()
        with redirect_stdout(off):
            log_sql("op", "SELECT 1", tuple(), time.perf_counter(), row_count=1)
        self.assertEqual(off.getvalue(), "")

        os.environ["MATCHGENOME_SQL_LOG"] = "1"
        on = io.StringIO()
        with redirect_stdout(on):
            log_sql("op", "SELECT 1", tuple(), time.perf_counter(), row_count=1)
        self.assertIn("[SQL]", on.getvalue())

        if original is None:
            os.environ.pop("MATCHGENOME_SQL_LOG", None)
        else:
            os.environ["MATCHGENOME_SQL_LOG"] = original


if __name__ == "__main__":
    unittest.main()

