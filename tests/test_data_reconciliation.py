from __future__ import annotations

from pathlib import Path
import sqlite3
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def _load_reconciliation_module():
    module_path = ROOT / "scripts" / "data_reconciliation.py"
    spec = importlib.util.spec_from_file_location("data_reconciliation", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DataReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_path = ROOT / "data" / "ipl.sqlite3"
        cls.zip_path = ROOT / "artifacts" / "ipl_json.zip"
        if not cls.db_path.exists() or not cls.zip_path.exists():
            raise unittest.SkipTest("Local DB or cached Cricsheet archive not available for reconciliation tests")
        module = _load_reconciliation_module()
        conn = sqlite3.connect(cls.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cls.report = module.build_report(conn, cls.zip_path)
        finally:
            conn.close()

    def test_all_seasons_have_coverage_rows(self) -> None:
        seasons = self.report["seasons_audited"]
        self.assertEqual(seasons[0], 2008)
        self.assertEqual(seasons[-1], 2026)
        self.assertEqual(len(seasons), 19)

    def test_2026_discrepancy_snapshot(self) -> None:
        discrepancy = self.report["discrepancy_2026"]
        self.assertEqual(discrepancy["season_fours"]["local"], 2334.0)
        self.assertEqual(discrepancy["season_fours"]["reference"], 2332.0)
        self.assertEqual(discrepancy["season_wickets"]["local"], 837.0)
        self.assertEqual(discrepancy["season_wickets"]["reference"], 835.0)
        self.assertEqual(discrepancy["season_dot_balls"]["local"], 5452.0)
        self.assertEqual(discrepancy["season_dot_balls"]["reference"], 5686.0)

    def test_representative_historical_season_complete(self) -> None:
        by_season = {row["season"]: row for row in self.report["coverage_matrix"]}
        season_2015 = by_season[2015]
        self.assertEqual(season_2015["missing_matches"], 0)
        self.assertEqual(season_2015["unexpected_matches"], 0)
        self.assertEqual(season_2015["coverage_status"], "complete")
        self.assertEqual(season_2015["trust_gate_status"], "PASS")


if __name__ == "__main__":
    unittest.main()

