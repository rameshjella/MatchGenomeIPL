"""Audit resting-state text/control visibility on every tab in both appearances."""
from __future__ import annotations

import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099").rstrip("/") + "/"
MIN_RATIO = 4.5
SHOOT = "--shots" in sys.argv

SCAN_JS = r"""
function parse(c){
  const m = String(c).match(/rgba?\(([^)]+)\)/);
  if(!m) return null;
  const p = m[1].split(',').map(parseFloat);
  return {r:p[0], g:p[1], b:p[2], a:(p.length>3? p[3] : 1)};
}
function over(fg,bg){
  const a = fg.a + bg.a*(1-fg.a);
  if(!a) return {r:0,g:0,b:0,a:0};
  return {r:(fg.r*fg.a+bg.r*bg.a*(1-fg.a))/a,
          g:(fg.g*fg.a+bg.g*bg.a*(1-fg.a))/a,
          b:(fg.b*fg.a+bg.b*bg.a*(1-fg.a))/a, a:a};
}
function lum(c){
  const f=[c.r,c.g,c.b].map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
  return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2];
}
const isLight = document.documentElement.getAttribute('data-theme')==='light';
const base = isLight ? {r:244,g:241,b:236,a:1} : {r:9,g:11,b:15,a:1};
function bgOf(el){
  const stack=[]; let n=el;
  while(n && n!==document.documentElement){
    const s=getComputedStyle(n);
    const c=parse(s.backgroundColor);
    if(c && c.a>0) stack.push(c);
    if(c && c.a>=0.999) break;
    n=n.parentElement;
  }
  let acc=base;
  for(let i=stack.length-1;i>=0;i--) acc=over(stack[i],acc);
  return acc;
}
function visible(el){
  const r = el.getBoundingClientRect();
  if(r.width < 2 || r.height < 2) return false;
  const s = getComputedStyle(el);
  if(s.visibility==='hidden' || s.display==='none' || parseFloat(s.opacity)===0) return false;
  return true;
}
const root = document.querySelector(arguments[0]);
if(!root) return [];
const out = [];
const nodes = root.querySelectorAll('h1,h2,h3,h4,h5,p,span,strong,small,li,td,th,button,a,label,summary,dt,dd,em,b,div');
for(const el of nodes){
  let own = '';
  for(const n of el.childNodes){ if(n.nodeType===3) own += n.nodeValue; }
  own = own.trim();
  if(own.length < 2) continue;
  if(!visible(el)) continue;
  const s = getComputedStyle(el);
  let fgSrc = s.color;
  if(s.webkitTextFillColor && s.webkitTextFillColor !== 'currentcolor') fgSrc = s.webkitTextFillColor;
  const fgRaw = parse(fgSrc);
  if(!fgRaw) continue;
  if(fgRaw.a === 0){
    if(String(s.backgroundImage).indexOf('gradient') >= 0) continue;
  }
  const b = bgOf(el);
  const fg = over(fgRaw, b);
  const fl = lum(fg), bl = lum(b);
  const ratio = (Math.max(fl,bl)+0.05)/(Math.min(fl,bl)+0.05);
  out.push({
    text: own.slice(0,48),
    tag: el.tagName.toLowerCase(),
    cls: (el.className && el.className.baseVal !== undefined ? el.className.baseVal : String(el.className||'')).slice(0,70),
    ratio: Math.round(ratio*100)/100,
    color: fgSrc,
    bg: 'rgb('+Math.round(b.r)+','+Math.round(b.g)+','+Math.round(b.b)+')'
  });
}
return out;
"""


def click(driver, element_id):
    driver.execute_script(
        "const e=document.getElementById(arguments[0]); if(e) e.click();", element_id
    )


def scan(driver, root_selector):
    try:
        return driver.execute_script(SCAN_JS, root_selector) or []
    except Exception:  # noqa: BLE001
        return []


def audit_theme(driver, theme):
    driver.get(BASE)
    time.sleep(0.9)
    driver.execute_script(
        "localStorage.setItem('mg-theme', arguments[0]);"
        "document.documentElement.setAttribute('data-theme', arguments[0]);"
        "const s=document.createElement('style');"
        "s.textContent='*{transition:none !important;animation:none !important;}';"
        "document.head.appendChild(s);",
        theme,
    )
    time.sleep(0.4)

    rows = []
    layouts = []

    def record(route, root_selector):
        for item in scan(driver, root_selector):
            item["theme"] = theme
            item["route"] = route
            rows.append(item)
        layout = driver.execute_script(
            "const r=document.querySelector(arguments[0]);"
            "const t=(r?(r.innerText||''):'').trim();"
            "return {overflow: document.documentElement.scrollWidth - window.innerWidth,"
            " textLen: t.length,"
            " clipped: r ? Math.max(0, r.scrollWidth - r.clientWidth) : 0};",
            root_selector,
        )
        layout.update({"theme": theme, "route": route})
        layouts.append(layout)
        if SHOOT:
            safe = route.replace(":", "_")
            driver.save_screenshot(f"artifacts/ui_theme_shots/{theme}_{safe}.png")

    click(driver, "goHomeBtn")
    time.sleep(0.5)
    record("home", "#homeView")

    click(driver, "goMatchesBtn")
    time.sleep(0.9)
    record("matches:fixtures", "#fixturesView")
    click(driver, "matchTabResultsBtn")
    time.sleep(0.5)
    record("matches:results", "#fixturesView")

    click(driver, "goTeamsBtn")
    time.sleep(0.4)
    click(driver, "teamLoadBtn")
    time.sleep(1.1)
    record("teams", "#teamsView")

    click(driver, "goStatsBtn")
    time.sleep(1.0)
    for tab, key in [
        ("statsTabOverviewBtn", "overview"),
        ("statsTabBattingBtn", "batting"),
        ("statsTabBowlingBtn", "bowling"),
        ("statsTabRecordsBtn", "records"),
        ("statsTabGraphsBtn", "signals"),
        ("statsTabPointsBtn", "points"),
    ]:
        click(driver, tab)
        time.sleep(0.35)
        record(f"stats:{key}", "#statsView")

    click(driver, "goPredictBtn")
    time.sleep(0.4)
    record("predict", "#predictView")

    click(driver, "goAskBtn")
    time.sleep(0.4)
    record("ask", "#askView")

    click(driver, "goPlayerIntelligenceBtn")
    time.sleep(0.9)
    driver.execute_script(
        "const p=document.getElementById('playerPanel'); if(p) p.hidden=false;"
    )
    time.sleep(0.3)
    record("players", "#playerView")

    click(driver, "goReplayBtn")
    time.sleep(0.9)
    driver.execute_script(
        "const p=document.getElementById('replayPanel'); if(p) p.hidden=false;"
    )
    time.sleep(0.3)
    for tab, key in [
        ("tabPredictionBtn", "prediction"),
        ("tabBallByBallBtn", "ball_by_ball"),
        ("tabEvidenceBtn", "evidence"),
    ]:
        click(driver, tab)
        time.sleep(0.3)
        record(f"replay:{key}", "#timeMachineView")

    driver.save_screenshot(f"artifacts/ui_theme_shots/audit_{theme}_replay.png")
    return rows, layouts


def main() -> int:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--hide-scrollbars")
    driver = webdriver.Chrome(options=opts)
    rows = []
    layouts = []
    try:
        for theme in ("light", "dark"):
            r, l = audit_theme(driver, theme)
            rows.extend(r)
            layouts.extend(l)
    finally:
        driver.quit()

    fails = [r for r in rows if r["ratio"] < MIN_RATIO]
    seen, unique = set(), []
    for r in sorted(fails, key=lambda x: x["ratio"]):
        key = (r["theme"], r["cls"], r["color"], r["bg"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    overflow = [l for l in layouts if l["overflow"] > 2 or l["clipped"] > 2]
    empty = [l for l in layouts if l["textLen"] < 40]

    print(json.dumps({
        "scanned": len(rows),
        "fail_count": len(fails),
        "unique_failures": unique[:40],
        "overflow_issues": overflow,
        "empty_panels": empty,
    }, indent=1))
    return 0 if not (fails or overflow or empty) else 1


if __name__ == "__main__":
    raise SystemExit(main())

