"""Headless capture of key MatchGenome routes for visual validation."""
from __future__ import annotations

import pathlib
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8097/"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "artifacts/ui_after")
OUT.mkdir(parents=True, exist_ok=True)

SIZES = [(1440, 900), (1280, 800), (1024, 768), (768, 1024), (390, 844)]
ROUTES = [
    ("home", "goHomeBtn"),
    ("matches", "goMatchesBtn"),
    ("players", "goPlayerIntelligenceBtn"),
    ("stats", "goStatsBtn"),
    ("replay", "goReplayBtn"),
    ("ask", "goAskBtn"),
]

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--force-device-scale-factor=1")
driver = webdriver.Chrome(options=opts)
errors: list[str] = []
try:
    for width, height in SIZES:
        driver.set_window_size(width, height)
        for name, btn_id in ROUTES:
            driver.get(BASE)
            time.sleep(1.4)
            try:
                driver.execute_script(
                    "document.getElementById(arguments[0]).click();", btn_id
                )
            except Exception as exc:  # pragma: no cover - diagnostic path
                errors.append(f"{name}@{width}: {exc}")
            time.sleep(1.4)
            driver.save_screenshot(str(OUT / f"{name}_{width}x{height}.png"))
        overflow = driver.execute_script(
            "return document.documentElement.scrollWidth - window.innerWidth;"
        )
        if overflow and overflow > 2:
            errors.append(f"horizontal-overflow {width}px: {overflow}")
    body_text = driver.find_element(By.TAG_NAME, "body").text
    for token in ("NoneType", "Traceback", "Internal Server Error"):
        if token in body_text:
            errors.append(f"raw-error-visible: {token}")
finally:
    driver.quit()

print("ERRORS:" if errors else "CLEAN")
for item in errors:
    print(" -", item)

