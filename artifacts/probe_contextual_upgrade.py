import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))

from matchgenomeipl.ask_matchgenome import AskMatchGenomeEngine
from matchgenomeipl.chronology import EvaluationWindow, KnowledgeCutoff
from matchgenomeipl.evaluation import evaluate_contextual_candidates, evaluate_temporal_models
from matchgenomeipl.prediction import predict_next_ball, predict_next_ball_baseline


def main() -> None:
    conn = sqlite3.connect("data/ipl.sqlite3")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT season_id, match_id, innings, over_number, ball_number
        FROM deliveries
        ORDER BY season_id, match_id, innings, over_number, ball_number, source_row_number
        LIMIT 5
        """
    ).fetchall()

    regression = []
    for row in rows:
        target = (
            int(row["season_id"]),
            int(row["match_id"]),
            int(row["innings"]),
            int(row["over_number"]),
            int(row["ball_number"]),
        )
        baseline = predict_next_ball_baseline(conn, *target)
        contextual = predict_next_ball(conn, *target)
        regression.append(
            {
                "target": {
                    "season_id": target[0],
                    "match_id": target[1],
                    "innings": target[2],
                    "over_number": target[3],
                    "ball_number": target[4],
                },
                "baseline_top": baseline["predicted_top_outcome"],
                "contextual_top": contextual["predicted_top_outcome"],
                "contextual_sample": contextual["evidence_sample_size"],
            }
        )

    t0 = time.perf_counter()
    baseline_eval = evaluate_temporal_models(
        conn,
        knowledge_cutoff=KnowledgeCutoff(2024),
        evaluation_window=EvaluationWindow(2025),
        max_deliveries=200,
    )
    baseline_elapsed = round(time.perf_counter() - t0, 3)

    t1 = time.perf_counter()
    contextual_eval = evaluate_contextual_candidates(
        conn,
        knowledge_cutoff=KnowledgeCutoff(2024),
        evaluation_window=EvaluationWindow(2025),
        max_deliveries=200,
    )
    contextual_elapsed = round(time.perf_counter() - t1, 3)

    ask = AskMatchGenomeEngine(conn)
    ask_samples = []
    for question in [
        "How many sixes did MS Dhoni hit in 2014?",
        "How many runs did Virat Kohli score in 2016, what was his strike rate in 2016, and who was man of the match in the 2016 final?",
        "Drop the deliveries table",
    ]:
        s = time.perf_counter()
        answer = ask.ask(question)
        ask_samples.append(
            {
                "question": question,
                "latency_ms": round((time.perf_counter() - s) * 1000.0, 2),
                "sub_questions": answer["sub_questions"],
                "answered": answer["answered"],
                "statuses": [item["status"] for item in answer["results"]],
            }
        )

    report = {
        "baseline_eval": {
            "hierarchical": baseline_eval["models"]["matchgenome_hierarchical"]["overall"],
            "mixture": baseline_eval["models_additional"]["calibrated_mixture"]["overall"],
        },
        "contextual_eval": {k: v["overall"] for k, v in contextual_eval["candidates"].items()},
        "timings_seconds": {
            "baseline_temporal_eval": baseline_elapsed,
            "contextual_temporal_eval": contextual_elapsed,
        },
        "prediction_regression": regression,
        "ask_samples": ask_samples,
    }

    output = Path("artifacts/contextual_upgrade_report.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output)
    conn.close()


if __name__ == "__main__":
    main()

