with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for the sidebar nav list
start = html.find('<aside')
if start != -1:
    print(html[start:start+1800])
else:
    print("sidebar not found")
