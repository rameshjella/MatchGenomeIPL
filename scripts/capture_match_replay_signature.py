from __future__ import annotations

import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = "http://127.0.0.1:8080/"
CHROME_BIN = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

VIEWPORTS = [
    (1440, 900, "desktop_1440x900"),
    (1280, 800, "desktop_1280x800"),
    (1024, 768, "tablet_1024x768"),
    (768, 1024, "tablet_768x1024"),
    (390, 844, "mobile_390x844"),
]


def new_driver(width: int, height: int, label: str) -> webdriver.Chrome:
    options = Options()
    options.binary_location = CHROME_BIN
    options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--disable-gpu")
    options.add_argument("--force-device-scale-factor=1")
    # Keep capture stable across environments by using viewport sizing only.
    return webdriver.Chrome(options=options)


def save(driver: webdriver.Chrome, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(out_dir / f"{name}.png"))


def click(driver: webdriver.Chrome, element) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    driver.execute_script("arguments[0].click();", element)


def capture_for_viewport(width: int, height: int, label: str, out_root: Path) -> None:
    driver = new_driver(width, height, label)
    wait = WebDriverWait(driver, 20)
    out_dir = out_root / label
    try:
        driver.get(BASE_URL)
        wait.until(lambda d: not d.find_element(By.ID, "homeView").get_attribute("hidden"))

        click(driver, driver.find_element(By.ID, "goMatchesBtn"))
        wait.until(lambda d: not d.find_element(By.ID, "fixturesView").get_attribute("hidden"))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#fixturesList .fixture-card")) > 0)

        # Open a concrete match detail to capture the unfolding match story surface.
        click(driver, driver.find_elements(By.CSS_SELECTOR, "#fixturesList .fixture-card")[0])
        wait.until(lambda d: "MATCH EVENT" in d.find_element(By.ID, "fixtureDetail").text or "MATCH" in d.find_element(By.ID, "fixtureDetail").text)
        save(driver, out_dir, "01_match_detail")

        open_replay = driver.find_elements(By.ID, "openFixtureInTimeMachineBtn")
        if open_replay:
            click(driver, open_replay[0])
        else:
            click(driver, driver.find_element(By.ID, "goReplayBtn"))

        wait.until(lambda d: not d.find_element(By.ID, "timeMachineView").get_attribute("hidden"))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")) > 0)
        quick_replay = driver.find_elements(By.CSS_SELECTOR, "#matchCards .replay-chip")
        if quick_replay:
            click(driver, quick_replay[0])
        else:
            click(driver, driver.find_elements(By.CSS_SELECTOR, "#matchCards .match-card")[0])
            wait.until(lambda d: d.find_element(By.ID, "startReplayBtn").is_enabled())
            click(driver, driver.find_element(By.ID, "startReplayBtn"))
        wait.until(lambda d: d.find_element(By.ID, "replayPanel").is_displayed())

        save(driver, out_dir, "02_replay_stage")

        click(driver, driver.find_element(By.ID, "predictBtn"))
        wait.until(lambda d: d.find_element(By.ID, "revealBtn").is_enabled())
        save(driver, out_dir, "03_replay_forecast")

        click(driver, driver.find_element(By.ID, "revealBtn"))
        wait.until(
            lambda d: any(
                token in d.find_element(By.ID, "actualBlock").text
                for token in ("WHAT ACTUALLY HAPPENED", "MATCHGENOME", "Reality")
            )
        )
        save(driver, out_dir, "04_replay_reveal")

        click(driver, driver.find_element(By.ID, "tabBallByBallBtn"))
        wait.until(lambda d: not d.find_element(By.ID, "panelBallByBall").get_attribute("hidden"))
        save(driver, out_dir, "05_replay_ledger")
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output directory for screenshots")
    args = parser.parse_args()
    out_root = Path(args.out).resolve()

    failures: list[str] = []
    completed: list[str] = []
    for width, height, label in VIEWPORTS:
        try:
            capture_for_viewport(width, height, label, out_root)
            completed.append(label)
        except Exception as exc:  # pragma: no cover - runtime guard for capture continuity
            failures.append(f"{label}: {exc}")

    report = {"output": str(out_root), "completed": completed, "failures": failures}
    (out_root / "capture_report.json").write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
    print(f"Saved captures to: {out_root}")
    if failures:
        print("Capture failures:")
        for failure in failures:
            print(f" - {failure}")


if __name__ == "__main__":
    main()



