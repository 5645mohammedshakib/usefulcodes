with open("index.src.html", "r", encoding="utf-8") as f:
    html = f.read()

start = html.find("function navigateTo")
if start != -1:
    # Print 50 lines starting from navigateTo
    lines = html[start:].split("\n")
    for l in lines[:40]:
        print(l)
