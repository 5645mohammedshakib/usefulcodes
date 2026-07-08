with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

start = html.find('id="nav-categories"')
if start != -1:
    print(html[start:start+500])
else:
    print("nav-categories not found")
