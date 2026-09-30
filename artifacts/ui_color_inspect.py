"""Inspect computed colors of section headings in light appearance."""
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
    d.execute_script("document.getElementById('themeToggleBtn').click();")
    time.sleep(0.6)
    d.execute_script("document.getElementById('goMatchesBtn').click();")
    time.sleep(1.6)
    out = d.execute_script(
        """
        const res = [];
        document.querySelectorAll('h2,h3').forEach(el=>{
          if (el.offsetParent === null) return;
          const s = getComputedStyle(el);
          let n = el, bgc = 'none', tag='';
          while(n && n !== document.documentElement){
            const c = getComputedStyle(n).backgroundColor;
            if (c && !/rgba\\(0, 0, 0, 0\\)/.test(c)) { bgc = c; tag = n.className; break; }
            n = n.parentElement;
          }
          res.push([el.textContent.trim().slice(0,32), s.color, s.webkitTextFillColor, bgc, String(tag).slice(0,40)]);
        });
        return res.slice(0,10);
        """
    )
    for row in out:
        print(row)
finally:
    d.quit()

