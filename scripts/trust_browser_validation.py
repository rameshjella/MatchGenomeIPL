from __future__ import annotations

import json
import threading
from pathlib import Path
import sys
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from matchgenomeipl.database import connect_db
from matchgenomeipl.http_transport import create_http_server

OUT_DIR = ROOT / "artifacts" / "trust_browser_validation"
BASE_URL = "http://127.0.0.1:8091/"
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _new_driver() -> webdriver.Chrome:
    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-gpu")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--force-color-profile=srgb")
    return webdriver.Chrome(options=options)


def _save(driver: webdriver.Chrome, name: str) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    driver.save_screenshot(str(path))
    return str(path)


def _ask(wait: WebDriverWait, driver: webdriver.Chrome, question: str, shot_name: str) -> dict[str, str]:
    driver.find_element(By.ID, "goAskBtn").click()
    wait.until(lambda d: not d.find_element(By.ID, "askView").get_attribute("hidden"))
    ask_input = driver.find_element(By.ID, "askInput")
    ask_input.clear()
    ask_input.send_keys(question)
    driver.find_element(By.ID, "askSubmitBtn").click()
    wait.until(
        lambda d: "ask-result-card" in d.find_element(By.ID, "askResults").get_attribute("innerHTML")
        and "Answers appear here" not in d.find_element(By.ID, "askResults").text
    )
    answer_text = driver.find_element(By.ID, "askResults").text
    screenshot = _save(driver, shot_name)
    return {"question": question, "answer_text": answer_text, "screenshot": screenshot}


def main() -> None:
    db_path = ROOT / "data" / "ipl.sqlite3"
    static_dir = ROOT / "web"
    conn = connect_db(db_path)
    server = create_http_server(db_path=db_path, host="127.0.0.1", port=8091, static_dir=static_dir)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    driver = _new_driver()
    wait = WebDriverWait(driver, 20)
    report: dict[str, Any] = {"asks": [], "screenshots": []}

    try:
        driver.get(BASE_URL)
        wait.until(EC.visibility_of_element_located((By.ID, "homeView")))

        asks = [
            ("Who won the IPL 2024 final?", "ask_2024_final"),
            ("Who is RCB captain?", "ask_rcb_current"),
            ("Who was RCB captain in 2016?", "ask_rcb_2016"),
            ("How many runs did Vaibhav Sooryavanshi score in IPL 2026?", "ask_vaibhav_runs_2026"),
        ]
        for question, shot in asks:
            result = _ask(wait, driver, question, shot)
            report["asks"].append(result)
            report["screenshots"].append(result["screenshot"])

        driver.find_element(By.ID, "goStatsBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "statsView").get_attribute("hidden"))
        Select(driver.find_element(By.ID, "statsSeasonSelect")).select_by_value("2026")
        driver.find_element(By.ID, "statsRefreshBtn").click()
        wait.until(lambda d: "2026" in d.find_element(By.ID, "statsOverviewBlock").text)
        stats_text = driver.find_element(By.ID, "statsOverviewBlock").text
        stats_shot = _save(driver, "stats_2026")
        report["stats"] = {"text": stats_text, "screenshot": stats_shot}
        report["screenshots"].append(stats_shot)

        driver.find_element(By.ID, "goTeamsBtn").click()
        wait.until(lambda d: not d.find_element(By.ID, "teamsView").get_attribute("hidden"))
        Select(driver.find_element(By.ID, "teamsSelect")).select_by_visible_text("Royal Challengers Bengaluru")
        Select(driver.find_element(By.ID, "teamSeasonSelect")).select_by_value("2026")
        driver.find_element(By.ID, "teamLoadBtn").click()
        wait.until(lambda d: "Rajat Patidar" in d.find_element(By.ID, "teamDetails").text)
        team_text = driver.find_element(By.ID, "teamDetails").text
        team_shot = _save(driver, "teams_rcb_2026")
        report["team"] = {"text": team_text, "screenshot": team_shot}
        report["screenshots"].append(team_shot)
    finally:
        driver.quit()
        server.shutdown()
        server.server_close()
        conn.close()

    out_path = OUT_DIR / "report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()


