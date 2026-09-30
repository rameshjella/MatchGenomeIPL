"""Check whether the light-appearance CSS rules are parsed by the browser."""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base = sys.argv[1].rstrip("/") + "/"
opts = Options()
opts.add_argument("--headless=new")
d = webdriver.Chrome(options=opts)
try:
    d.get(base)
    time.sleep(1.2)
    info = d.execute_script(
        """
        const out = {sheets: [], light: 0, total: 0, samples: []};
        for (const s of document.styleSheets) {
          let rules;
          try { rules = s.cssRules; } catch (e) { out.sheets.push(['blocked', String(e)]); continue; }
          out.sheets.push([s.href, rules.length]);
          out.total += rules.length;
          for (const r of rules) {
            const sel = r.selectorText || '';
            if (sel.includes('data-theme="light"')) out.light++;
          }
          out.samples = Array.from(rules).slice(-6).map(r => (r.selectorText || r.cssText).slice(0,80));
        }
        out.theme = document.documentElement.getAttribute('data-theme');
        out.bodyClass = document.body.className;
        return out;
        """
    )
    print(info)
finally:
    d.quit()

