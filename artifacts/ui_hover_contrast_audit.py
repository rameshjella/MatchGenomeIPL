"""Audit hover-state readability of interactive widgets across tabs and themes."""
from __future__ import annotations

import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099").rstrip("/") + "/"
THEMES = (sys.argv[2],) if len(sys.argv) > 2 else ("light", "dark")

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

SELECTORS = (
    ".entity-chip, .inline-player, .quick-link, .link-btn, .season-trail-step, "
    ".tab-btn, .mode-nav button, .ask-examples button, .ask-domain-strip button, "
    ".genome-node, .season-node, .home-season-node, .fixture-open-chip, .replay-chip"
)

RATIO_JS = r"""
function parse(c){
  const m = String(c).match(/rgba?\(([^)]+)\)/);
  if(!m) return null;
  const p = m[1].split(',').map(parseFloat);
  return {r:p[0], g:p[1], b:p[2], a:(p.length>3? p[3] : 1)};
}
function over(fg,bg){
  const a = fg.a + bg.a*(1-fg.a);
  if(!a) return {r:0,g:0,b:0,a:0};
  return {r:(fg.r*fg.a+bg.r*bg.a*(1-fg.a))/a, g:(fg.g*fg.a+bg.g*bg.a*(1-fg.a))/a,
          b:(fg.b*fg.a+bg.b*bg.a*(1-fg.a))/a, a:a};
}
function lum(c){
  const f=[c.r,c.g,c.b].map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
  return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2];
}
const isLight = document.documentElement.getAttribute('data-theme')==='light';
const base = isLight ? {r:244,g:241,b:236,a:1} : {r:9,g:11,b:15,a:1};
function bg(el){
  const stack=[]; let n=el;
  while(n && n!==document.documentElement){
    const s=getComputedStyle(n); const c=parse(s.backgroundColor);
    if(c && c.a>0) stack.push(c);
    if(c && c.a>=0.999) break;
    n=n.parentElement;
  }
  let acc=base;
  for(let i=stack.length-1;i>=0;i--) acc=over(stack[i],acc);
  return acc;
}
const el = arguments[0];
const s = getComputedStyle(el);
const fgRaw = parse(s.webkitTextFillColor && s.webkitTextFillColor!=='currentcolor' ? s.webkitTextFillColor : s.color);
if(!fgRaw) return [0, s.color];
const b = bg(el);
const fg = over(fgRaw, b);
const fl = lum(fg), bl = lum(b);
return [Math.round(((Math.max(fl,bl)+0.05)/(Math.min(fl,bl)+0.05))*100)/100, s.color, s.backgroundColor];
"""


def hover(driver, el):
    box = driver.execute_script(
        "const r = arguments[0].getBoundingClientRect();"
        "return [r.left + r.width/2, r.top + r.height/2, (arguments[0].innerText||'').trim().slice(0,36)];",
        el,
    )
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": float(box[0]), "y": float(box[1]), "buttons": 0},
    )
    return box[2]


def audit(driver, theme):
    driver.get(BASE)
    time.sleep(1.0)
    driver.execute_script(
        "localStorage.setItem('mg-theme', arguments[0]);"
        "document.documentElement.setAttribute('data-theme', arguments[0]);"
        "const s = document.createElement('style');"
        "s.textContent = '*{transition:none !important;animation:none !important;}';"
        "document.head.appendChild(s);",
        theme,
    )
    time.sleep(0.4)
    failures = []
    checked = []
    for name, btn in ROUTES:
        driver.execute_script("document.getElementById(arguments[0]).click();", btn)
        time.sleep(0.45)
        if name == "teams":
            try:
                driver.execute_script("document.getElementById('teamLoadBtn').click();")
                time.sleep(1.1)
            except Exception:  # noqa: BLE001
                pass
        elements = [e for e in driver.find_elements(By.CSS_SELECTOR, SELECTORS) if e.is_displayed()][:6]
        if name == "teams":
            squad = [
                e
                for e in driver.find_elements(By.CSS_SELECTOR, "#teamDetails .entity-chip, #teamDetails .inline-player")
                if e.is_displayed()
            ][:4]
            elements = squad + elements
        for el in elements:
            try:
                text = hover(driver, el)
                if not text:
                    continue
                ratio, color, back = driver.execute_script(RATIO_JS, el)
            except Exception:  # noqa: BLE001
                continue
            checked.append({"theme": theme, "route": name, "text": text, "hover_ratio": ratio})
            if ratio < 4.0:
                failures.append(
                    {"theme": theme, "route": name, "text": text,
                     "class": el.get_attribute("class"), "hover_ratio": ratio,
                     "color": color, "bg": back}
                )
            if name == "teams" and el is elements[0]:
                driver.save_screenshot(f"artifacts/hover_squad_signal_{theme}.png")
    return failures, checked


def main() -> int:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1600,1000")
    driver = webdriver.Chrome(options=opts)
    out = []
    seen = []
    try:
        for theme in THEMES:
            failures, checked = audit(driver, theme)
            out.extend(failures)
            seen.extend(checked)
    finally:
        driver.quit()
    worst = sorted(seen, key=lambda r: r["hover_ratio"])[:8]
    print(json.dumps({
        "hover_failures": out,
        "failure_count": len(out),
        "checked": len(seen),
        "weakest_hover_states": worst,
    }, indent=1))
    return 0 if not out else 1


if __name__ == "__main__":
    raise SystemExit(main())

