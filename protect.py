import re, base64, os

files = ["index.html", "student.html"]

def obf_script(match):
    attrs = match.group(1)
    code = match.group(2).strip()
    if not code or len(code) < 100:
        return match.group(0)
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    chunks = [encoded[i:i+100] for i in range(0, len(encoded), 100)]
    joined = "+".join(["'" + c + "'" for c in chunks])
    wrapper = "eval(atob(" + joined + "))"
    return "<script" + attrs + ">" + wrapper + "</script>"

for fname in files:
    if not os.path.exists(fname):
        print("NOT FOUND: " + fname)
        continue
    print("Processing " + fname)
    with open(fname, "r", encoding="utf-8") as f:
        html = f.read()
    html = re.sub(r"<script(?![^>]*src=)([^>]*)>([\s\S]*?)</script>", obf_script, html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)
    html = re.sub(r"\n\s*\n", "\n", html)
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print("  Saved " + fname)

print("All done!")
