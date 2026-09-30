"""Quick light/dark appearance probe for the studio design layer."""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base = sys.argv[1]
opts = Options()
opts.add_argument("--headless=new")
driver = webdriver.Chrome(options=opts)
try:
    driver.set_window_size(1440, 900)
    driver.get(base)
    time.sleep(2)
    driver.save_screenshot("artifacts/ui_after/home_dark_1440x900.png")
    driver.execute_script("document.getElementById('themeToggleBtn').click();")
    time.sleep(1.2)
    print("theme:", driver.execute_script("return document.documentElement.getAttribute('data-theme');"))
    driver.save_screenshot("artifacts/ui_after/home_light_1440x900.png")
    print("overflow:", driver.execute_script("return document.documentElement.scrollWidth - window.innerWidth;"))
finally:
    driver.quit()

