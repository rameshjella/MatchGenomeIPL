"""Browser proof for time-travel seek, replay durability and theme stability.

Drives the real UI: picks a match, travels to a mid-innings ball, predicts and
reveals, then reloads the page and resumes the persisted session. Also asserts
the home view's first widget keeps an identical position across refreshes.

Usage:
    python scripts/replay_seek_browser_validation.py [base_url]
"""

from __future__ import annotations

import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091/"


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,960")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)


def main() -> int:
    driver = build_driver()
    wait = WebDriverWait(driver, 30)
    failures: list[str] = []
    try:
        driver.get(BASE_URL)
        wait.until(EC.presence_of_element_located((By.ID, "homeView")))

        # --- Home widget position must be identical after every refresh -----
        offsets = []
        for _ in range(3):
            driver.get(BASE_URL + "#view=home")
            wait.until(EC.visibility_of_element_located((By.ID, "homeView")))
            time.sleep(0.7)
            offsets.append(
                driver.execute_script(
                    "const el = document.querySelector('.top-shell');"
                    "return Math.round(el.getBoundingClientRect().top + window.scrollY);"
                )
            )
        if len(set(offsets)) != 1:
            failures.append(f"home widget position drifts across refreshes: {offsets}")
        print("home_widget_offsets", offsets)

        # --- Travel to a mid-innings delivery -------------------------------
        driver.execute_script("document.getElementById('goReplayBtn').click();")
        wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, "#matchCards [role='listitem'], #matchCards button"))
        driver.execute_script(
            "const c = document.querySelector(\"#matchCards [role='listitem'], #matchCards button\"); c.click();"
        )
        wait.until(lambda d: len(d.find_element(By.ID, "startPointSelect").find_elements(By.TAG_NAME, "option")) > 5)

        seek = Select(driver.find_element(By.ID, "startPointSelect"))
        options = seek.options
        target = options[len(options) // 2]
        target_label = target.text
        seek.select_by_value(target.get_attribute("value"))
        print("seek_target", target_label)

        driver.execute_script("document.getElementById('startReplayBtn').click();")
        wait.until(lambda d: not d.find_element(By.ID, "replayPanel").get_attribute("hidden"))

        driver.execute_script("document.getElementById('predictBtn').click();")
        wait.until(lambda d: d.find_element(By.ID, "overBallValue").text.strip() not in ("", "-"))
        shown = driver.find_element(By.ID, "overBallValue").text.strip()
        expected = target.get_attribute("value").replace(":", ".")
        if shown != expected:
            failures.append(f"replay did not start at the requested ball: shown={shown} expected={expected}")
        print("replay_started_at", shown)

        driver.execute_script("document.getElementById('revealBtn').click();")
        time.sleep(1.5)
        accuracy_before = driver.find_element(By.ID, "accuracyValue").text.strip()

        # --- Durability: reload and resume ----------------------------------
        driver.get(BASE_URL)
        wait.until(EC.presence_of_element_located((By.ID, "homeView")))
        time.sleep(2.5)
        driver.execute_script("document.getElementById('goReplayBtn').click();")
        wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        resume = driver.find_element(By.ID, "resumeReplayBtn")
        if resume.get_attribute("hidden"):
            failures.append("resume affordance was not offered after reload")
        else:
            driver.execute_script("arguments[0].click();", resume)
            wait.until(lambda d: not d.find_element(By.ID, "replayPanel").get_attribute("hidden"))
            time.sleep(1.0)
            accuracy_after = driver.find_element(By.ID, "accuracyValue").text.strip()
            if accuracy_after != accuracy_before:
                failures.append(f"resumed accuracy mismatch: {accuracy_before} -> {accuracy_after}")
            print("accuracy_before", accuracy_before, "accuracy_after", accuracy_after)

        # --- Theme stays applied to the dynamically rendered replay ---------
        for theme in ("light", "dark"):
            driver.execute_script("localStorage.setItem('mg-theme', arguments[0]);", theme)
            driver.get(BASE_URL)
            wait.until(EC.presence_of_element_located((By.ID, "homeView")))
            time.sleep(2.0)
            driver.execute_script("document.getElementById('goReplayBtn').click();")
            time.sleep(0.6)
            applied = driver.execute_script("return document.documentElement.getAttribute('data-theme');")
            bg = driver.execute_script(
                "const s = getComputedStyle(document.getElementById('startPointSelect'));"
                "return s.backgroundColor + '|' + s.color + '|' + getComputedStyle(document.documentElement).colorScheme;"
            )
            print(f"theme={theme} applied={applied} seek_select={bg}")
            if applied != theme:
                failures.append(f"theme {theme} not applied on replay view")
    finally:
        driver.quit()

    if failures:
        for item in failures:
            print("FAIL:", item)
        return 1
    print("PASS: seek, durability and theme checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



