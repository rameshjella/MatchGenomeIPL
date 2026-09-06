from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "http://127.0.0.1:8080/"
OUT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "visual_qa"
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class VisualQaRunner:
    def __init__(self, width: int, height: int, label: str) -> None:
        self.width = width
        self.height = height
        self.label = label
        self.driver = self._new_driver(width, height)
        self.wait = WebDriverWait(self.driver, 20)
        self.results: dict[str, object] = {"viewport": {"width": width, "height": height, "label": label}, "checks": {}}

    def _new_driver(self, width: int, height: int) -> webdriver.Chrome:
        options = Options()
        options.binary_location = CHROME_BIN
        options.add_argument("--headless=new")
        options.add_argument(f"--window-size={width},{height}")
        options.add_argument("--disable-gpu")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--force-device-scale-factor=1")
        if self.label == "mobile":
            options.add_experimental_option(
                "mobileEmulation",
                {
                    "deviceMetrics": {"width": width, "height": height, "pixelRatio": 3},
                    "userAgent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
                },
            )
        options.add_argument("--force-color-profile=srgb")
        return webdriver.Chrome(options=options)

    def _save(self, name: str) -> None:
        target = OUT_DIR / f"{self.label}_{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.driver.save_screenshot(str(target))

    def _check_overflow(self, key: str) -> None:
        data = self.driver.execute_script(
            "return {scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, overflow: document.documentElement.scrollWidth > window.innerWidth};"
        )
        self.results["checks"][f"{key}_overflow"] = data

    def _text(self, selector: str) -> str:
        return self.driver.find_element(By.CSS_SELECTOR, selector).text.strip()

    def run(self) -> dict[str, object]:
        self.driver.get(BASE_URL)
        self.wait.until(EC.visibility_of_element_located((By.ID, "matchCards")))
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")) > 0)

        self.results["checks"]["five_second_branding"] = {
            "h1": self._text(".brand h1"),
            "descriptor": self._text(".brand .eyebrow"),
        }
        self.results["checks"]["intro_paths_present"] = {
            "explore_match": self.driver.find_element(By.ID, "exploreMatchBtn").is_displayed(),
            "players": self.driver.find_element(By.ID, "goPlayersIntroBtn").is_displayed(),
        }

        self._save("01_landing")
        self._check_overflow("landing")

        cards = self.driver.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")
        first_teams_text = cards[0].find_element(By.CSS_SELECTOR, ".match-teams").text.strip()
        self.results["checks"]["first_match_identity"] = {
            "text": first_teams_text,
            "raw_numeric_vs_numeric": bool(re.fullmatch(r"\d+\s+vs\s+\d+", first_teams_text)),
            "has_team_prefix": "Team " in first_teams_text,
        }
        cards[0].click()
        self.wait.until(lambda d: d.find_element(By.ID, "inningsSelect").get_attribute("value") is not None)
        self._save("02_match_discovery")
        self._check_overflow("discovery")

        self.driver.find_element(By.ID, "startReplayBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "replayPanel")))

        self.driver.find_element(By.ID, "predictBtn").click()
        self.wait.until(lambda d: d.find_element(By.ID, "predictedTop").text.strip() not in {"", "-"})
        self._save("03_prediction")
        self._check_overflow("prediction")

        actual_before = self._text("#actualBlock")
        self.results["checks"]["actual_hidden_before_reveal"] = "Reveal the ball" in actual_before

        self.driver.find_element(By.ID, "tabEvidenceBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "panelEvidence")))
        self._save("04_evidence")
        self._check_overflow("evidence")

        self.driver.find_element(By.ID, "tabPredictionBtn").click()
        self.driver.find_element(By.ID, "revealBtn").click()
        self.wait.until(lambda d: "Actual Outcome" in d.find_element(By.ID, "actualBlock").text)
        self.results["checks"]["replay_accuracy_semantics"] = self._text("#accuracyValue")
        self._save("05_reveal")
        self._check_overflow("reveal")

        self.driver.find_element(By.ID, "tabBallByBallBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "panelBallByBall")))
        self._save("06_ball_by_ball")
        self._check_overflow("ball_by_ball")

        self.driver.find_element(By.ID, "tabPredictionBtn").click()
        batter_btn = self.driver.find_element(By.ID, "batterValue")
        batter_name = batter_btn.text.strip()
        batter_btn.click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "playerView")))
        self.wait.until(lambda d: d.find_element(By.ID, "playerPanel").is_displayed())
        self._save("07_player_overview")
        self._check_overflow("player_overview")

        self.results["checks"]["player_name_from_replay"] = {
            "batter_button": batter_name,
            "profile_name": self._text("#playerName"),
        }
        self.results["checks"]["player_photo_meta"] = self._text("#playerPhotoMeta")

        tab_ids = ["playerTabBattingBtn", "playerTabMatchupsBtn", "playerTabSeasonsBtn", "playerTabPhasesBtn"]
        for tab_id in tab_ids:
            matches = self.driver.find_elements(By.ID, tab_id)
            if not matches or not matches[0].is_displayed():
                continue
            matches[0].click()
            time.sleep(0.35)

        self._save("08_player_analytics")
        self._check_overflow("player_analytics")

        self.driver.find_element(By.ID, "backToReplayBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "timeMachineView")))
        self._save("09_back_to_replay")
        self._check_overflow("back_to_replay")

        # Journey B: open Players from nav, search, open profile, traverse tabs.
        self.driver.get(f"{BASE_URL}#view=player")
        self.wait.until(EC.visibility_of_element_located((By.ID, "playerView")))
        q = self.driver.find_element(By.ID, "playerSearchInput")
        q.clear()
        q.send_keys("gang")
        q.send_keys(Keys.ENTER)
        try:
            self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")) > 0)
        except TimeoutException:
            self.driver.find_element(By.ID, "playerSearchBtn").click()
            self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")) > 0)
        first_result = self.driver.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")[0]
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", first_result)
        self.driver.execute_script("arguments[0].click();", first_result)
        self.wait.until(lambda d: d.find_element(By.ID, "playerPanel").is_displayed())
        for tab_id in ["playerTabOverviewBtn", "playerTabBattingBtn", "playerTabBowlingBtn", "playerTabMatchupsBtn", "playerTabSeasonsBtn", "playerTabPhasesBtn"]:
            nodes = self.driver.find_elements(By.ID, tab_id)
            if nodes and nodes[0].is_displayed():
                nodes[0].click()
                time.sleep(0.2)
        self._save("10_players_search_journey")
        self._check_overflow("players_search_journey")

        # Keyboard focus progression sanity check.
        body = self.driver.find_element(By.TAG_NAME, "body")
        ActionChains(self.driver).move_to_element(body).click(body).perform()
        body.send_keys(Keys.TAB)
        body.send_keys(Keys.TAB)
        focused = self.driver.execute_script("return document.activeElement ? (document.activeElement.id || document.activeElement.tagName) : null;")
        self.results["checks"]["keyboard_focus_target_after_tabs"] = focused

        return self.results

    def close(self) -> None:
        self.driver.quit()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    viewports = [
        (1600, 1000, "desktop"),
        (1024, 768, "tablet"),
        (390, 844, "mobile"),
    ]

    report: dict[str, object] = {"runs": []}

    for width, height, label in viewports:
        runner = VisualQaRunner(width, height, label)
        try:
            report["runs"].append(runner.run())
        except Exception as exc:
            report["runs"].append(
                {
                    "viewport": {"width": width, "height": height, "label": label},
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        finally:
            runner.close()

    report_path = OUT_DIR / "visual_qa_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved screenshots and report to: {OUT_DIR}")


if __name__ == "__main__":
    main()


