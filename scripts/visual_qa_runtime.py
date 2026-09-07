from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
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
        self.wait.until(EC.visibility_of_element_located((By.ID, "homeView")))

        self.results["checks"]["five_second_branding"] = {
            "h1": self._text(".brand-block h1"),
            "descriptor": self._text(".brand-block .eyebrow"),
        }
        self.results["checks"]["intro_paths_present"] = {
            "explore_match": self.driver.find_element(By.ID, "exploreMatchBtn").is_displayed(),
            "players": self.driver.find_element(By.ID, "goPlayersIntroBtn").is_displayed(),
            "ask": self.driver.find_element(By.ID, "homeAskBtn").is_displayed(),
        }

        self._save("01_home")
        self._check_overflow("home")

        self.driver.find_element(By.ID, "homeAskBtn").click()
        self.wait.until(lambda d: not d.find_element(By.ID, "askView").get_attribute("hidden"))
        self._save("02_ask")
        self._check_overflow("ask")

        for nav_id, view_id, shot in [
            ("goMatchesBtn", "fixturesView", "02a_matches"),
            ("goTeamsBtn", "teamsView", "02c_teams"),
            ("goStatsBtn", "statsView", "02d_stats"),
            ("goPredictBtn", "predictView", "02e_predict"),
        ]:
            btn = self.driver.find_element(By.ID, nav_id)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            self.driver.execute_script("arguments[0].click();", btn)
            self.wait.until(lambda d, target=view_id: not d.find_element(By.ID, target).get_attribute("hidden"))
            self._save(shot)
            self._check_overflow(shot)

        self.driver.find_element(By.ID, "goMatchesBtn").click()
        self.wait.until(lambda d: not d.find_element(By.ID, "fixturesView").get_attribute("hidden"))
        self.driver.find_element(By.ID, "matchTabResultsBtn").click()
        self._save("02b_results")
        self._check_overflow("02b_results")

        self.driver.find_element(By.ID, "goAskBtn").click()
        self.wait.until(lambda d: not d.find_element(By.ID, "askView").get_attribute("hidden"))

        ask_input = self.driver.find_element(By.ID, "askInput")
        ask_input.clear()
        ask_input.send_keys("How many sixes did MS Dhoni hit in 2014?")
        self.driver.find_element(By.ID, "askSubmitBtn").click()
        self.wait.until(
            lambda d: len(d.find_element(By.ID, "askResults").text.strip()) > 10
            and "Answers appear here" not in d.find_element(By.ID, "askResults").text
        )
        self._save("03_ask_result")

        ask_input.clear()
        ask_input.send_keys("What was the humidity in that match?")
        self.driver.find_element(By.ID, "askSubmitBtn").click()
        self.wait.until(
            lambda d: any(
                token in d.find_element(By.ID, "askResults").text
                for token in (
                    "Unsupported",
                    "could not map",
                    "does not currently have verified information",
                    "does not currently have a verified knowledge path",
                    "Need clarification",
                )
            )
        )
        self._save("04_ask_empty_or_error")

        tm_btn = self.driver.find_element(By.ID, "goReplayBtn")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tm_btn)
        self.driver.execute_script("arguments[0].click();", tm_btn)
        self.wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")) > 0)
        self._save("05_time_machine_initial")

        cards = self.driver.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")
        first_teams_text = cards[0].find_element(By.CSS_SELECTOR, ".match-teams").text.strip()
        self.results["checks"]["first_match_identity"] = {
            "text": first_teams_text,
            "raw_numeric_vs_numeric": bool(re.fullmatch(r"\d+\s+vs\s+\d+", first_teams_text)),
            "has_team_prefix": "Team " in first_teams_text,
        }
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cards[0])
        self.driver.execute_script("arguments[0].click();", cards[0])
        self.wait.until(lambda d: d.find_element(By.ID, "inningsSelect").get_attribute("value") is not None)
        self.wait.until(lambda d: d.find_element(By.ID, "startReplayBtn").is_enabled())
        self._save("06_match_selected")
        self._check_overflow("discovery")

        start_btn = self.driver.find_element(By.ID, "startReplayBtn")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", start_btn)
        self.driver.execute_script("arguments[0].click();", start_btn)
        self.wait.until(EC.visibility_of_element_located((By.ID, "replayPanel")))
        self._save("07_match_workspace")

        predict_btn = self.driver.find_element(By.ID, "predictBtn")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", predict_btn)
        prediction_ready = False
        for _ in range(3):
            self.driver.execute_script("arguments[0].click();", predict_btn)
            try:
                self.wait.until(lambda d: d.find_element(By.ID, "predictedTop").text.strip() not in {"", "-"})
                prediction_ready = True
                break
            except TimeoutException:
                continue
        if not prediction_ready:
            raise TimeoutException("Predict action did not produce a visible prediction.")
        self._save("08_before_ball_prediction")
        self._check_overflow("prediction")

        actual_before = self._text("#actualBlock")
        self.results["checks"]["actual_hidden_before_reveal"] = "Reveal the ball" in actual_before

        self.driver.find_element(By.ID, "tabEvidenceBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "panelEvidence")))
        self._save("10_evidence")
        self._check_overflow("evidence")

        self.driver.find_element(By.ID, "tabPredictionBtn").click()
        reveal_btn = self.driver.find_element(By.ID, "revealBtn")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", reveal_btn)
        self.driver.execute_script("arguments[0].click();", reveal_btn)
        self.wait.until(lambda d: "The Ball Happened" in d.find_element(By.ID, "actualBlock").text)
        self.results["checks"]["replay_accuracy_semantics"] = self._text("#accuracyValue")
        self._save("09_after_reveal")
        self._check_overflow("reveal")

        self.driver.find_element(By.ID, "tabBallByBallBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "panelBallByBall")))
        self._save("11_ball_by_ball")
        self._check_overflow("ball_by_ball")

        # Build a long-content state for scroll and panel containment checks.
        self.driver.find_element(By.ID, "tabPredictionBtn").click()
        for _ in range(20):
            self.driver.find_element(By.ID, "predictBtn").click()
            self.wait.until(lambda d: d.find_element(By.ID, "revealBtn").is_enabled())
            self.driver.find_element(By.ID, "revealBtn").click()
            self.wait.until(lambda d: "The Ball Happened" in d.find_element(By.ID, "actualBlock").text)
            if "Replay completed" in self.driver.find_element(By.ID, "statusBanner").text:
                break
        self.driver.find_element(By.ID, "tabBallByBallBtn").click()
        self._save("12_long_content_state")

        self.driver.find_element(By.ID, "goPlayerIntelligenceBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "playerView")))
        self.driver.find_element(By.ID, "playerSearchInput").clear()
        self.driver.find_element(By.ID, "playerSearchInput").send_keys("gang")
        search_btn = self.driver.find_element(By.ID, "playerSearchBtn")
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_btn)
        self.driver.execute_script("arguments[0].click();", search_btn)
        self.wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")) > 0)
        self._save("13_player_search")

        first_result = self.driver.find_elements(By.CSS_SELECTOR, "#playerSearchResults .search-result")[0]
        first_result.click()
        self.wait.until(lambda d: d.find_element(By.ID, "playerPanel").is_displayed())
        self._save("14_player_overview")
        self._check_overflow("player_overview")

        for tab_id, shot in [
            ("playerTabBattingBtn", "15_player_batting"),
            ("playerTabBowlingBtn", "16_player_bowling"),
            ("playerTabMatchupsBtn", "17_player_matchups"),
            ("playerTabSeasonsBtn", "18_player_seasons"),
            ("playerTabPhasesBtn", "19_player_phases"),
        ]:
            nodes = self.driver.find_elements(By.ID, tab_id)
            if nodes and nodes[0].is_displayed():
                nodes[0].click()
                time.sleep(0.25)
                self._save(shot)

        self.results["checks"]["player_name_from_replay"] = {
            "profile_name": self._text("#playerName"),
        }
        self.results["checks"]["player_photo_meta"] = self._text("#playerPhotoMeta")

        self.driver.find_element(By.ID, "goReplayBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "timeMachineView")))
        self.driver.find_element(By.ID, "tabPredictionBtn").click()
        batter_btn = self.driver.find_element(By.ID, "batterValue")
        batter_btn.click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "playerView")))
        self.wait.until(lambda d: d.find_element(By.ID, "playerPanel").is_displayed())
        self._save("20_match_to_player_navigation")

        self.driver.find_element(By.ID, "backToReplayBtn").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "timeMachineView")))
        self._save("21_player_to_match_navigation")

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
        (1440, 900, "desktop_1440x900"),
        (1280, 800, "desktop_1280x800"),
        (1024, 768, "tablet_1024x768"),
        (768, 1024, "tablet_768x1024"),
        (390, 844, "mobile_390x844"),
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


