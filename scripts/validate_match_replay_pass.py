from __future__ import annotations

import json
from pathlib import Path
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

BASE_URL = "http://127.0.0.1:8080"
OUT_PATH = Path("artifacts/match_detail_replay_signature/validation_report.json")
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main() -> None:
    report: dict[str, object] = {}

    teams = json.loads(urllib.request.urlopen(f"{BASE_URL}/api/teams").read().decode())["teams"]
    seasons = [s["season_id"] for s in json.loads(urllib.request.urlopen(f"{BASE_URL}/api/seasons").read().decode())["seasons"]]
    bad = []
    for team in teams:
        name = team.get("team", "")
        for season in seasons:
            url = f"{BASE_URL}/api/teams/{urllib.parse.quote(name)}?season_id={season}"
            try:
                body = urllib.request.urlopen(url).read().decode()
            except Exception as exc:  # pragma: no cover - runtime guard
                body = str(exc)
            if "int() argument must be a string, a bytes-like object or a real number, not" in body:
                bad.append({"team": name, "season": season})
    report["int_none_regression_count"] = len(bad)

    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,900")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    def wait_for_home_ready(stage_key: str) -> tuple[str, str]:
        for attempt in range(2):
            try:
                wait.until(lambda d: d.find_element(By.ID, "homeSeasonTag").text.strip().isdigit())
                wait.until(lambda d: d.find_element(By.ID, "homeContextPill").text.strip() != "")
                return (
                    driver.find_element(By.ID, "homeContextPill").text.strip(),
                    driver.find_element(By.ID, "homeSeasonTag").text.strip(),
                )
            except TimeoutException:
                if attempt == 1:
                    report[f"{stage_key}_wait_timeout"] = True
                    return (
                        driver.find_element(By.ID, "homeContextPill").text.strip(),
                        driver.find_element(By.ID, "homeSeasonTag").text.strip(),
                    )
                driver.get(f"{BASE_URL}/")
    try:
        driver.get(f"{BASE_URL}/")
        fresh_context, fresh_season = wait_for_home_ready("home_initial")
        report["home_fresh_context"] = fresh_context
        report["home_fresh_season"] = fresh_season

        driver.get(f"{BASE_URL}/#view=replay")
        wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")) > 0)
        driver.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")[0].click()
        wait.until(lambda d: d.find_element(By.ID, "startReplayBtn").is_enabled())
        driver.find_element(By.ID, "startReplayBtn").click()
        wait.until(lambda d: d.find_element(By.ID, "replayPanel").is_displayed())
        driver.find_element(By.ID, "predictBtn").click()
        wait.until(lambda d: d.find_element(By.ID, "revealBtn").is_enabled())
        why_text = driver.find_element(By.ID, "whyBlock").text
        report["replay_signal_label_present"] = ("SIGNAL" in why_text or "EVIDENCE" in why_text)

        driver.find_element(By.ID, "revealBtn").click()
        wait.until(lambda d: "MATCHGENOME" in d.find_element(By.ID, "actualBlock").text)
        driver.find_element(By.ID, "tabBallByBallBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "panelBallByBall").get_attribute("hidden"))
        report["ledger_has_accuracy"] = "accuracy" in driver.find_element(By.ID, "predictionLedger").text.lower()

        driver.find_element(By.ID, "goHomeBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "homeView").get_attribute("hidden"))
        post_context, post_season = wait_for_home_ready("home_after_replay")
        report["home_after_replay_context"] = post_context
        report["home_after_replay_season"] = post_season

        body_text = driver.find_element(By.TAG_NAME, "body").text
        report["raw_runtime_error_visible"] = any(token in body_text for token in ("NoneType", "Traceback", "internal_error"))
    finally:
        driver.quit()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()



