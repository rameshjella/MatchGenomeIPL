"""Theme consistency audit.

Walks every primary view in both appearances and reports elements whose own
painted colors contradict the active theme (dark surfaces in light mode,
light surfaces in dark mode) plus low-contrast text. Read-only: it never
mutates application state beyond normal navigation clicks.

Usage:
    python scripts/theme_contrast_audit.py [base_url]
"""

from __future__ import annotations

import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091/"

VIEWS = [
    ("goHomeBtn", "homeView"),
    ("goMatchesBtn", "fixturesView"),
    ("goTeamsBtn", "teamsView"),
    ("goPlayerIntelligenceBtn", "playerView"),
    ("goStatsBtn", "statsView"),
    ("goPredictBtn", "predictView"),
    ("goReplayBtn", "timeMachineView"),
    ("goAskBtn", "askView"),
]

AUDIT_JS = r"""
const mode = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
function parse(c) {
  const m = /rgba?\(([^)]+)\)/.exec(c || '');
  if (!m) return null;
  const p = m[1].split(',').map(function (v) { return parseFloat(v); });
  return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
}
function lum(c) {
  const f = [c.r, c.g, c.b].map(function (v) {
    v = v / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2];
}
function ratio(a, b) {
  const l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
function label(el) {
  return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
}
const surfaceIssues = {}, textIssues = {};
const nodes = document.querySelectorAll('main *');
for (const el of nodes) {
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) continue;
  const cs = getComputedStyle(el);
  if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < 0.05) continue;
  const bg = parse(cs.backgroundColor);
  if (bg && bg.a > 0.5) {
    const l = lum(bg);
    const fgOwn = parse(cs.color);
    const legible = fgOwn ? ratio(fgOwn, bg) >= 4.5 : false;
    if (!legible && mode === 'light' && l < 0.35) surfaceIssues[label(el)] = cs.backgroundColor;
    if (!legible && mode === 'dark' && l > 0.72) surfaceIssues[label(el)] = cs.backgroundColor;
  }
  // text contrast against nearest painted ancestor background
  if (el.childElementCount === 0 && el.textContent.trim().length > 1) {
    let p = el, abg = null;
    while (p && p !== document.documentElement) {
      const c = parse(getComputedStyle(p).backgroundColor);
      if (c && c.a > 0.85) { abg = c; break; }
      p = p.parentElement;
    }
    if (!abg || abg.a < 0.85) abg = (mode === 'light' ? { r: 247, g: 245, b: 240, a: 1 } : { r: 10, g: 12, b: 17, a: 1 });
    const fg = parse(cs.color);
    if (fg && fg.a > 0.3 && ratio(fg, abg) < 3.2) {
      textIssues[label(el)] = cs.color + ' on rgb(' + Math.round(abg.r) + ',' + Math.round(abg.g) + ',' + Math.round(abg.b) + ') ratio=' + ratio(fg, abg).toFixed(2);
    }
  }
}
return {
  mode: mode,
  overflow: document.documentElement.scrollWidth - window.innerWidth,
  surfaces: surfaceIssues,
  text: textIssues
};
"""


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-gpu")
    options.add_argument("--force-color-profile=srgb")
    return webdriver.Chrome(options=options)


def main() -> int:
    driver = build_driver()
    wait = WebDriverWait(driver, 20)
    report: dict[str, dict] = {}
    try:
        for theme in ("light", "dark"):
            driver.get(BASE_URL)
            driver.execute_script("localStorage.setItem('mg-theme', arguments[0]);", theme)
            driver.get(BASE_URL)
            wait.until(EC.presence_of_element_located((By.ID, "homeView")))
            for nav_id, view_id in VIEWS:
                try:
                    btn = driver.find_element(By.ID, nav_id)
                    driver.execute_script("arguments[0].click();", btn)
                    wait.until(lambda d, t=view_id: not d.find_element(By.ID, t).get_attribute("hidden"))
                except Exception as exc:  # noqa: BLE001
                    report[f"{theme}:{view_id}"] = {"error": str(exc)[:160]}
                    continue
                time.sleep(0.6)
                report[f"{theme}:{view_id}"] = driver.execute_script(AUDIT_JS)
    finally:
        driver.quit()

    issues = 0
    for key, data in report.items():
        surfaces = data.get("surfaces") or {}
        text = data.get("text") or {}
        overflow = data.get("overflow", 0)
        if surfaces or text or (isinstance(overflow, (int, float)) and overflow > 1) or data.get("error"):
            issues += 1
            print(f"\n== {key} overflow={overflow}")
            if data.get("error"):
                print("   error:", data["error"])
            for name, detail in sorted(surfaces.items())[:12]:
                print(f"   surface: {name} -> {detail}")
            for name, detail in sorted(text.items())[:12]:
                print(f"   text   : {name} -> {detail}")
    print("\nSUMMARY", json.dumps({"views_audited": len(report), "views_with_issues": issues}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






