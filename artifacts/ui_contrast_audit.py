"""Audit every route for unreadable text, overflow and leaked technical errors."""
from __future__ import annotations

import pathlib
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE = sys.argv[1].rstrip("/") + "/"
OUT = pathlib.Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

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

CONTRAST_JS = r"""
function parse(c){
  const m = String(c).match(/rgba?\(([^)]+)\)/);
  if(!m) return null;
  const p = m[1].split(',').map(x=>parseFloat(x));
  return {r:p[0], g:p[1], b:p[2], a:(p.length>3? p[3] : 1)};
}
function over(fg, bg){
  const a = fg.a + bg.a*(1-fg.a);
  if (a === 0) return {r:0,g:0,b:0,a:0};
  return {
    r:(fg.r*fg.a + bg.r*bg.a*(1-fg.a))/a,
    g:(fg.g*fg.a + bg.g*bg.a*(1-fg.a))/a,
    b:(fg.b*fg.a + bg.b*bg.a*(1-fg.a))/a,
    a:a
  };
}
function lum(c){
  const f = [c.r,c.g,c.b].map(v=>{v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4);});
  return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2];
}
const isLight = document.documentElement.getAttribute('data-theme') === 'light';
const base = isLight ? {r:244,g:241,b:236,a:1} : {r:9,g:11,b:15,a:1};
function bg(el){
  const stack = [];
  let n = el;
  while(n && n !== document.documentElement){
    const s = getComputedStyle(n);
    const c = parse(s.backgroundColor);
    if (c && c.a > 0) stack.push(c);
    if (c && c.a >= 0.999) break;
    if (s.backgroundImage && s.backgroundImage !== 'none') return null; // gradient: skip element
    n = n.parentElement;
  }
  let acc = base;
  for (let i = stack.length - 1; i >= 0; i--) acc = over(stack[i], acc);
  return acc;
}
const bad = [];
document.querySelectorAll('h1,h2,h3,h4,p,span,strong,td,th,li,button,label,a').forEach(el=>{
  if (el.offsetParent === null) return;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return;
  const txt = (el.textContent||'').trim();
  if (!txt || txt.length > 200) return;
  if (el.querySelector('h1,h2,h3,h4,p,span,strong,td,th,li,button,label,a')) return;
  const s = getComputedStyle(el);
  const fgRaw = parse(s.webkitTextFillColor && s.webkitTextFillColor !== 'currentcolor' ? s.webkitTextFillColor : s.color);
  if (!fgRaw) return;
  const b = bg(el);
  if (!b) return;
  const fg = over(fgRaw, b);
  const fl = lum(fg), bl = lum(b);
  const ratio = (Math.max(fl,bl)+0.05)/(Math.min(fl,bl)+0.05);
  if (ratio < 3) bad.push(txt.slice(0,60) + ' :: ' + ratio.toFixed(2));
});
return bad.slice(0, 12);
"""

LEAK_TOKENS = (
    "NoneType",
    "Traceback",
    "API misuse",
    "bad parameter",
    "sqlite",
    "internal_error",
    "Request failed",
    "undefined",
)

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--force-device-scale-factor=1")
driver = webdriver.Chrome(options=opts)
problems: list[str] = []
try:
    for theme in ("dark", "light"):
        driver.set_window_size(1440, 900)
        driver.get(BASE)
        time.sleep(1.5)
        driver.execute_script(
            "localStorage.setItem('mg-theme', arguments[0]);"
            "document.documentElement.setAttribute('data-theme', arguments[0]);",
            theme,
        )
        time.sleep(0.5)
        for name, btn in ROUTES:
            try:
                driver.execute_script("document.getElementById(arguments[0]).click();", btn)
            except Exception as exc:
                problems.append(f"{theme}/{name} click: {exc}")
                continue
            time.sleep(1.6)
            driver.save_screenshot(str(OUT / f"{theme}_{name}_1440x900.png"))
            for item in driver.execute_script(CONTRAST_JS):
                problems.append(f"LOWCONTRAST {theme}/{name}: {item}")
            body = driver.execute_script("return document.body.innerText;")
            for token in LEAK_TOKENS:
                if token.lower() in body.lower():
                    problems.append(f"LEAK {theme}/{name}: {token}")
            over = driver.execute_script(
                "return document.documentElement.scrollWidth - window.innerWidth;"
            )
            if over and over > 2:
                problems.append(f"OVERFLOW {theme}/{name}: {over}px")
finally:
    driver.quit()

print("CLEAN" if not problems else f"ISSUES ({len(problems)})")
for item in problems:
    print(" -", item)

