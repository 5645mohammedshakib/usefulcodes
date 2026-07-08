with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

start = html.find("function loadDashboardStats")
if start != -1:
    print(html[start:start+1500])
else:
    print("loadDashboardStats not found!")
