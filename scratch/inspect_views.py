import re

with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

print("Views:")
for m in re.finditer(r'id="view-([^"]*)"', html):
    print(" -", m.group(1))

print("Navs:")
for m in re.finditer(r'id="nav-([^"]*)"', html):
    print(" -", m.group(1))
