from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "http://127.0.0.1:8080/"
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "visual_qa" / "p1_browser_validation"


def new_driver() -> webdriver.Chrome:
    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-gpu")
    options.add_argument("--force-device-scale-factor=1")
    return webdriver.Chrome(options=options)


def save(driver: webdriver.Chrome, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(OUT_DIR / f"{name}.png"))


def ask_question(driver: webdriver.Chrome, wait: WebDriverWait, question: str, screenshot_name: str) -> dict[str, str]:
    ask_input = driver.find_element(By.ID, "askInput")
    ask_input.clear()
    ask_input.send_keys(question)
    driver.find_element(By.ID, "askSubmitBtn").click()
    wait.until(
        lambda d: "No answer generated yet" not in d.find_element(By.ID, "askResults").text
        and len(d.find_element(By.ID, "askResults").text.strip()) > 8
    )
    time.sleep(0.6)
    text = driver.find_element(By.ID, "askResults").text.strip()
    save(driver, screenshot_name)
    return {"question": question, "result_excerpt": text[:420]}


def main() -> None:
    driver = new_driver()
    wait = WebDriverWait(driver, 25)
    checks: dict[str, Any] = {"route_checks": {}, "ask_checks": []}
    try:
        driver.get(BASE_URL)
        wait.until(lambda d: not d.find_element(By.ID, "homeView").get_attribute("hidden"))
        checks["route_checks"]["home_loaded"] = True
        save(driver, "01_home")

        driver.find_element(By.ID, "goMatchesBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "fixturesView").get_attribute("hidden"))
        checks["route_checks"]["matches_loaded"] = True
        save(driver, "02_matches")

        driver.find_element(By.ID, "goTeamsBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "teamsView").get_attribute("hidden"))
        driver.find_element(By.ID, "teamLoadBtn").click()
        wait.until(lambda d: "Select a team" not in d.find_element(By.ID, "teamDetails").text)
        checks["route_checks"]["teams_loaded"] = True
        save(driver, "03_teams")

        driver.find_element(By.ID, "goPlayerIntelligenceBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "playerView").get_attribute("hidden"))
        search = driver.find_element(By.ID, "playerSearchInput")
        search.clear()
        search.send_keys("dhoni")
        driver.find_element(By.ID, "playerSearchBtn").click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")) > 0)
        driver.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")[0].click()
        wait.until(lambda d: d.find_element(By.ID, "playerPanel").is_displayed())
        checks["route_checks"]["player_loaded"] = driver.find_element(By.ID, "playerName").text
        save(driver, "04_player")

        driver.find_element(By.ID, "goStatsBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "statsView").get_attribute("hidden"))
        wait.until(lambda d: len(d.find_element(By.ID, "statsOverviewBlock").text.strip()) > 12)
        checks["route_checks"]["stats_loaded"] = True
        save(driver, "05_stats")

        driver.find_element(By.ID, "goPredictBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "predictView").get_attribute("hidden"))
        checks["route_checks"]["predict_loaded"] = True
        save(driver, "06_predict")

        driver.find_element(By.ID, "goReplayBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")) > 0)
        checks["route_checks"]["replay_loaded"] = True
        save(driver, "07_replay")

        driver.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")[0].click()
        wait.until(lambda d: d.find_element(By.ID, "startReplayBtn").is_enabled())
        driver.find_element(By.ID, "startReplayBtn").click()
        wait.until(lambda d: d.find_element(By.ID, "replayPanel").is_displayed())
        checks["route_checks"]["replay_session_started"] = True
        save(driver, "08_replay_session")

        driver.find_element(By.ID, "goAskBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "askView").get_attribute("hidden"))
        checks["route_checks"]["ask_loaded"] = True
        save(driver, "09_ask")

        questions = [
            "What is the full name of Dhoni?",
            "Who is RCB captain?",
            "What was the winner of the IPL 2024 final?",
            "Who scored the most runs in IPL 2015?",
            "What is likely to happen next?",
        ]
        for idx, question in enumerate(questions, start=10):
            checks["ask_checks"].append(ask_question(driver, wait, question, f"{idx:02d}_ask_{idx}"))

        report_path = OUT_DIR / "report.json"
        report_path.write_text(json.dumps(checks, indent=2), encoding="utf-8")
        print(json.dumps(checks, indent=2))
        print(f"Saved browser validation artifacts to: {OUT_DIR}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

