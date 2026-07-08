with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for functions
import re
print("Functions:")
for m in re.finditer(r"function\s+(\w+)\s*\(", html):
    print(" -", m.group(1))

print("Let variables:")
for m in re.finditer(r"let\s+(\w+)\s*=", html):
    print(" -", m.group(1))
