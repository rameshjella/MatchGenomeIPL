"""Find controls that stretch to full width unintentionally on every route."""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base = sys.argv[1].rstrip("/") + "/"
ROUTES = [
    ("home", "goHomeBtn"),
    ("explore", "goMatchesBtn"),
    ("teams", "goTeamsBtn"),
    ("players", "goPlayerIntelligenceBtn"),
    ("stats", "goStatsBtn"),
    ("predict", "goPredictBtn"),
    ("replay", "goReplayBtn"),
    ("ask", "goAskBtn"),
]

JS = """
const out = [];
document.querySelectorAll('button').forEach(el=>{
  if (el.offsetParent === null) return;
  const r = el.getBoundingClientRect();
  if (r.width < 600) return;
  out.push((el.className||'(no class)') + ' | ' + Math.round(r.width) + 'px | ' + (el.innerText||'').trim().slice(0,28));
});
return out.slice(0,10);
"""

opts = Options()
opts.add_argument("--headless=new")
d = webdriver.Chrome(options=opts)
try:
    d.set_window_size(1440, 900)
    d.get(base)
    time.sleep(1.5)
    for name, btn in ROUTES:
        d.execute_script("document.getElementById(arguments[0]).click();", btn)
        time.sleep(1.5)
        for item in d.execute_script(JS):
            print(f"{name}: {item}")
finally:
    d.quit()
print("done")

