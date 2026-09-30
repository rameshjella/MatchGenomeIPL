"""Find large empty rendered regions on a route."""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

base = sys.argv[1].rstrip("/") + "/"
btn = sys.argv[2]
opts = Options()
opts.add_argument("--headless=new")
d = webdriver.Chrome(options=opts)
try:
    d.set_window_size(1440, 900)
    d.get(base)
    time.sleep(1.5)
    d.execute_script("document.getElementById(arguments[0]).click();", btn)
    time.sleep(2.0)
    rows = d.execute_script(
        """
        const out = [];
        document.querySelectorAll('div,li,section,article,tr').forEach(el=>{
          if (el.offsetParent === null) return;
          const r = el.getBoundingClientRect();
          if (r.height < 28 || r.width < 120) return;
          const txt = (el.innerText||'').trim();
          if (txt.length > 6) return;
          if (el.querySelector('img,svg,canvas,input,select,button')) return;
          out.push([el.className.toString().slice(0,60), Math.round(r.width)+'x'+Math.round(r.height), txt]);
        });
        return out.slice(0, 15);
        """
    )
    for row in rows:
        print(row)
    print("total-empty-regions:", len(rows))
finally:
    d.quit()

