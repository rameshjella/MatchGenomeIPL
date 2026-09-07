import json
from urllib.request import Request, urlopen

queries = [
    "What is the full name of Dhoni?",
    "How many kids does Virat Kohli have?",
    "Who is RCB captain?",
    "Who coached CSK in 2018?",
    "Who owns KKR in 2026?",
    "Who scored most runs in IPL 2026?",
    "Show IPL 2026 fixtures.",
    "What happened in the 2026 final?",
    "V Suryavanshi",
    "Vaibhav Sooryavanshi",
]

for q in queries:
    body = json.dumps({"question": q}).encode("utf-8")
    req = Request("http://127.0.0.1:8080/api/ask", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    first = payload["results"][0]
    result = first.get("result") or {}
    value = result.get("value")
    if isinstance(value, list):
        value = f"list({len(value)})"
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=True)
    print(f"Q: {q}")
    print(f"status={first.get('status')} | label={result.get('label')} | value={value}")
    print("---")

