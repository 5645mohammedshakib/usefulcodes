with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for navigateTo and loadDataForView
import re
start_nav = html.find("function navigateTo")
if start_nav != -1:
    print(html[start_nav:start_nav+1000])

start_load = html.find("function loadDataForView")
if start_load != -1:
    print(html[start_load:start_load+1000])
