# MatchGenomeIPL Vertical Slice

This repository contains a DB-first IPL analytics and prediction backend using the real dataset in `data/ipl_ball_by_ball_data.csv`.

## What it does

- Ingests deliveries into a local SQLite database with:
  - raw-record preservation (`raw_deliveries`),
  - validated core delivery rows (`deliveries`),
  - rejected row tracking (`rejected_deliveries`).
- Persists source manifest/fingerprint metadata (`data_sources`, `ingestion_state`) to skip re-ingestion when the source is unchanged.
- Materializes core entities (`seasons`, `teams`, `players`, `matches`, `innings_summary`) and reusable aggregates.
- Exposes deterministic analytics and match-state reconstruction immediately before a real delivery.
- Provides a deterministic baseline next-ball probability model with hierarchical evidence fallback.
- Adds strict temporal evaluation with knowledge cutoff and online delivery replay.
- Adds calibrated mixture tuning of global, phase, and hierarchical signals using inner temporal validation.
- Adds a chronology-based recency weighting experiment for the calibrated mixture.

## Project layout

- `src/matchgenomeipl/database.py` - SQLite schema and connection helpers.
- `src/matchgenomeipl/validation.py` - schema checks, row normalization, and dataset profiling.
- `src/matchgenomeipl/ingestion.py` - persistent ingestion lifecycle, source change detection, and derived materialization.
- `src/matchgenomeipl/analytics.py` - dataset, batter, bowler, and innings analytics.
- `src/matchgenomeipl/match_state.py` - pre-delivery state reconstruction.
- `src/matchgenomeipl/prediction.py` - baseline next-ball probability model.
- `src/matchgenomeipl/chronology.py` - chronology abstraction and diagnostics.
- `src/matchgenomeipl/evaluation.py` - temporal backtesting and model comparison metrics.
- `src/matchgenomeipl/time_machine.py` - in-memory replay session lifecycle and deterministic predict/reveal contract.
- `src/matchgenomeipl/time_machine_api.py` - framework-free API facade for Time Machine capabilities.
- `src/matchgenomeipl/http_transport.py` - thin HTTP transport exposing Time Machine API endpoints and static web assets.
- `scripts/run_vertical_slice.py` - real-data execution and proof report.
- `scripts/run_temporal_evaluation.py` - temporal experiments (e.g. 2024 -> 2025) across baselines.
- `scripts/prediction_runtime.py` - single-prediction and sequential replay runtime benchmark.
- `scripts/evaluation_runtime.py` - focused runtime benchmark for temporal evaluation splits.
- `scripts/run_time_machine_vertical_slice.py` - end-to-end replay flow proof (select, predict, reveal, update).
- `scripts/time_machine_runtime.py` - replay initialization/predict/reveal runtime benchmark.
- `scripts/run_time_machine_app.py` - launches the user-facing Time Machine web app on local HTTP.
- `scripts/time_machine_http_runtime.py` - end-to-end HTTP and UI-loading runtime benchmark.
- `tests/` - fast tests using local fixtures.

## Quick start

```powershell
python -m unittest discover -s tests -v
python scripts/run_vertical_slice.py
python scripts/run_temporal_evaluation.py
python scripts/prediction_runtime.py
python scripts/evaluation_runtime.py
python scripts/run_time_machine_vertical_slice.py
python scripts/time_machine_runtime.py
python scripts/run_time_machine_app.py
python scripts/time_machine_http_runtime.py
```

Open `http://127.0.0.1:8080` after starting `run_time_machine_app.py` to use the Time Machine replay UI.

The vertical slice script prints JSON with ingestion/runtime status, analytics examples, one reconstructed pre-delivery state, and one baseline prediction result.
The temporal evaluation script prints JSON with cutoff-aware evaluation metrics for global, phase, and hierarchical baselines.
It also includes calibrated-mixture weights, validation diagnostics, and improvement deltas versus phase/hierarchical baselines.
It now also reports time-decayed mixture tuning/results and deltas versus the existing calibrated mixture.

