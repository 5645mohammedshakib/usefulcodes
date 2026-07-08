with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

# Find view-dashboard element
start = html.find('id="view-dashboard"')
if start != -1:
    print(html[start:start+1800])
else:
    print("view-dashboard not found")
