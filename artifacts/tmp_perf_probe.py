import json
import time
from urllib.request import Request, urlopen


def get(url: str):
    t0 = time.perf_counter()
    with urlopen(url) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (time.perf_counter() - t0) * 1000.0, data


def post(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (time.perf_counter() - t0) * 1000.0, data

results = {}
results["seasons_ms"], _ = get("http://127.0.0.1:8080/api/seasons")
results["fixtures_ms"], _ = get("http://127.0.0.1:8080/api/fixtures?season_id=2026")
results["ask_fullname_ms"], _ = post("http://127.0.0.1:8080/api/ask", {"question": "What is the full name of Dhoni?"})
results["ask_runs_ms"], _ = post("http://127.0.0.1:8080/api/ask", {"question": "Who scored most runs in IPL 2026?"})
print(json.dumps({k: round(v, 2) for k, v in results.items()}, indent=2))

