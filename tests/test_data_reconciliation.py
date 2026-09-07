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
        season_2026 = by_season[2026]
        self.assertEqual(season_2015["missing_matches"], 0)
        self.assertEqual(season_2015["unexpected_matches"], 0)
        self.assertEqual(season_2015["coverage_status"], "complete")
        self.assertEqual(season_2015["trust_gate_status"], "PASS")
        self.assertEqual(season_2026["trust_gate_status"], "PASS_WITH_DEFINITION_NOTE")

    def test_2026_forensic_root_cause_details(self) -> None:
        forensic = self.report["forensic_2026"]
        fours = forensic["fours"]
        dots = forensic["dot_balls"]
        wickets = forensic["wickets"]

        self.assertEqual(fours["local_canonical_batter_runs_eq_4"], 2334.0)
        self.assertEqual(fours["non_boundary_fours"], 1.0)
        self.assertEqual(fours["super_over_fours"], 1.0)
        self.assertEqual(fours["boundary_regular_variant"], 2332.0)

        self.assertEqual(dots["canonical_legal_total_zero"], 5452.0)
        self.assertEqual(dots["batter_facing_legal_batter_zero"], 5687.0)
        self.assertEqual(dots["gap_rows_count"], 235)
        self.assertEqual(dots["gap_grouping"]["by_extra_kind"].get("bye"), 44)
        self.assertEqual(dots["gap_grouping"]["by_extra_kind"].get("leg_bye"), 191)
        self.assertEqual(dots["batter_facing_minus_scoring_runout"], 5686.0)
        self.assertEqual(len(dots["runout_scoring_rows"]), 1)

        self.assertEqual(wickets["local_canonical"], 837.0)
        self.assertEqual(wickets["exclude_super_over"], 835.0)

    def test_representative_end_to_end_validation(self) -> None:
        e2e = self.report["representative_end_to_end"]
        seasons = e2e["seasons"]
        self.assertEqual([row["season"] for row in seasons], [2008, 2012, 2016, 2019, 2023, 2024, 2025, 2026])
        for row in seasons:
            self.assertTrue(row["source_complete"])
            self.assertTrue(row["db_equals_knowledge"])
            self.assertTrue(row["knowledge_equals_api"])

        ask_checks = e2e["ask_checks"]
        self.assertEqual(ask_checks["Who scored the most runs in IPL 2024?"]["status"], "ok")
        self.assertTrue(ask_checks["Who scored the most runs in IPL 2024?"]["value_present"])
        self.assertEqual(ask_checks["Who scored the most runs in IPL 2026?"]["status"], "ok")
        self.assertTrue(ask_checks["Who scored the most runs in IPL 2026?"]["value_present"])


if __name__ == "__main__":
    unittest.main()
