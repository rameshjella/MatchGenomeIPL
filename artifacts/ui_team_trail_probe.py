"""Describe the rendered structure of the team season trail."""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base = sys.argv[1].rstrip("/") + "/"
opts = Options()
opts.add_argument("--headless=new")
d = webdriver.Chrome(options=opts)
try:
    d.set_window_size(1440, 900)
    d.get(base)
    time.sleep(1.5)
    d.execute_script("document.getElementById('goTeamsBtn').click();")
    time.sleep(2.2)
    rows = d.execute_script(
        """
        const out = [];
        document.querySelectorAll('*').forEach(el=>{
          if (el.offsetParent === null) return;
          const t = (el.innerText||'').trim();
          if (!/^(20\\d\\d)$/.test(t)) return;
          const r = el.getBoundingClientRect();
          const p = el.parentElement;
          out.push([t, el.tagName+'.'+el.className, Math.round(r.width)+'x'+Math.round(r.height),
                    p ? p.tagName+'.'+p.className : '', getComputedStyle(p||el).display]);
        });
        return out.slice(0,8);
        """
    )
    for row in rows:
        print(row)
finally:
    d.quit()

