# MatchGenomeIPL Vertical Slice

This repository now contains a first working vertical slice for IPL delivery analytics using the real dataset in `data/ipl_ball_by_ball_data.csv`.

## What it does

- Profiles the real CSV dataset and reports data quality signals.
- Ingests deliveries into a local SQLite database with:
  - raw-record preservation (`raw_deliveries`),
  - validated core delivery rows (`deliveries`),
  - rejected row tracking (`rejected_deliveries`).
- Exposes deterministic analytics and match-state reconstruction immediately before a real delivery.
- Provides a deterministic baseline next-ball probability model with hierarchical evidence fallback.
- Adds strict temporal evaluation with knowledge cutoff and online delivery replay.

## Project layout

- `src/matchgenomeipl/database.py` - SQLite schema and connection helpers.
- `src/matchgenomeipl/validation.py` - schema checks, row normalization, and dataset profiling.
- `src/matchgenomeipl/ingestion.py` - repeatable CSV ingestion pipeline.
- `src/matchgenomeipl/analytics.py` - dataset, batter, bowler, and innings analytics.
- `src/matchgenomeipl/match_state.py` - pre-delivery state reconstruction.
- `src/matchgenomeipl/prediction.py` - baseline next-ball probability model.
- `src/matchgenomeipl/chronology.py` - chronology abstraction and diagnostics.
- `src/matchgenomeipl/evaluation.py` - temporal backtesting and model comparison metrics.
- `scripts/run_vertical_slice.py` - real-data execution and proof report.
- `scripts/run_temporal_evaluation.py` - temporal experiments (e.g. 2024 -> 2025) across baselines.
- `tests/` - fast tests using local fixtures.

## Quick start

```powershell
python -m unittest discover -s tests -v
python scripts/run_vertical_slice.py
python scripts/run_temporal_evaluation.py
```

The script prints a JSON report with profile findings, ingestion stats, analytics examples, one reconstructed pre-delivery state, and one baseline prediction result.
The temporal evaluation script prints JSON with cutoff-aware evaluation metrics for global, phase, and hierarchical baselines.

