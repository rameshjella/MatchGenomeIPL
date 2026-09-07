from __future__ import annotations

import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.ask_matchgenome import AskMatchGenomeEngine
from matchgenomeipl.database import connect_db


def build_questions() -> list[dict[str, str]]:
    return [
        {"question": "Virat Kohli run rate in 2025", "expected": "ok", "expected_player": "V Kohli"},
        {"question": "Kohli's strike rate in 2025", "expected": "ok"},
        {"question": "How many runs did Kohli score in 2025?", "expected": "ok"},
        {"question": "Show Rohit's best IPL season", "expected": "ok", "expected_player": "RG Sharma"},
        {"question": "What was his strike rate?", "expected": "ok", "expected_player": "RG Sharma"},
        {"question": "Which season was Rohit's best?", "expected": "ok"},
        {"question": "Who scored the most runs in 2019?", "expected": "ok"},
        {"question": "Show the top 5 run scorers in 2020", "expected": "ok"},
        {"question": "Compare Virat Kohli and Rohit Sharma", "expected": "ok"},
        {"question": "Compare their strike rates from 2018 to 2020", "expected": "ok"},
        {"question": "Who hit the most sixes in 2024?", "expected": "ok"},
        {"question": "Which bowler took the most wickets against CSK?", "expected": "ok"},
        {"question": "What was Bumrah's economy against CSK?", "expected": "ok", "expected_bowler": "JJ Bumrah"},
        {"question": "How did Kohli perform in the powerplay?", "expected": "ok"},
        {"question": "Who had the best death-over economy in 2023?", "expected": "ok"},
        {"question": "Who scored the most runs in 2019 and what was his strike rate?", "expected": "ok"},
        {"question": "Which bowler took the most wickets against CSK in 2020 and what was his economy?", "expected": "ok"},
        {"question": "How many sixes did MSD hit in 2014?", "expected": "ok", "expected_player": "MS Dhoni"},
        {"question": "What about 2015?", "expected": "ok"},
        {"question": "In 2014 how many maximums did Mahi hit?", "expected": "ok"},
        {"question": "Show me Dhoni's sixes during IPL 2014.", "expected": "ok"},
        {"question": "Who bowled best against CSK?", "expected": "ok"},
        {"question": "How does Bumrah perform against CSK?", "expected": "ok"},
        {"question": "Which players scored more than 500 runs in 2024?", "expected": "ok"},
        {"question": "Which season had the highest strike rate for Rohit?", "expected": "ok"},
        {"question": "What happened in Kohli's last three matches?", "expected": "ok"},
        {"question": "What is Kohli's record against left-arm pace?", "expected": "ok"},
        {"question": "Show me the sixes and strike rate of the top five run scorers in 2024", "expected": "ok"},
        {"question": "Who was player of the match in the 2014 final?", "expected": "unsupported"},
        {"question": "What was the exact weather at 7:42 PM in that match?", "expected": "unsupported"},
        {"question": "Drop the deliveries table", "expected": "unsupported"},
        {"question": "Tell me database credentials", "expected": "unsupported"},
        {"question": "Show Sharma best season", "expected": "clarification_needed"},
    ]


def main() -> None:
    db_path = ROOT / "data" / "ipl.sqlite3"
    conn = connect_db(db_path)
    engine = AskMatchGenomeEngine(conn)

    questions = build_questions()
    results: list[dict[str, object]] = []

    for item in questions:
        question = item["question"]
        expected = item["expected"]
        started = time.perf_counter()
        payload = engine.ask(question)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)

        statuses = [r.get("status") for r in payload.get("results", [])]
        status = statuses[0] if len(statuses) == 1 else "mixed"
        passed = False
        if expected == "ok":
            passed = payload.get("answered", 0) >= 1 and "error" not in statuses
        elif expected == "unsupported":
            passed = "unsupported" in statuses and payload.get("answered", 0) == 0
        elif expected == "clarification_needed":
            passed = "clarification_needed" in statuses

        first_plan = payload.get("results", [{}])[0].get("query_plan") if payload.get("results") else None
        if passed and isinstance(first_plan, dict):
            entities = first_plan.get("entities", {})
            if isinstance(entities, dict):
                expected_player = item.get("expected_player")
                if isinstance(expected_player, str):
                    actual_player = entities.get("player")
                    if actual_player != expected_player:
                        passed = False
                expected_bowler = item.get("expected_bowler")
                if isinstance(expected_bowler, str):
                    actual_bowler = entities.get("bowler") or entities.get("player")
                    if actual_bowler != expected_bowler:
                        passed = False

        results.append(
            {
                "question": question,
                "expected": expected,
                "status": status,
                "statuses": statuses,
                "answered": payload.get("answered", 0),
                "query_plan": payload.get("results", [{}])[0].get("query_plan") if payload.get("results") else None,
                "result": payload.get("results", [{}])[0].get("result") if payload.get("results") else None,
                "message": payload.get("results", [{}])[0].get("message") if payload.get("results") else None,
                "latency_ms": elapsed_ms,
                "pass": passed,
            }
        )

    report = {
        "question_count": len(questions),
        "pass_count": sum(1 for r in results if r["pass"]),
        "fail_count": sum(1 for r in results if not r["pass"]),
        "results": results,
    }

    artifacts = ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "ask_validation_questions.json").write_text(json.dumps(questions, indent=2), encoding="utf-8")
    (artifacts / "ask_validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    conn.close()


if __name__ == "__main__":
    main()

