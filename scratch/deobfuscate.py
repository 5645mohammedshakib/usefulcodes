import re, base64

def deobfuscate_code(b64_str):
    cleaned = b64_str.replace("'", "").replace("+", "").replace(" ", "").replace("\n", "").replace("\r", "").replace('"', "")
    decoded = base64.b64decode(cleaned).decode("utf-8")
    if "eval(atob(" in decoded:
        m = re.search(r"eval\(atob\(([\s\S]*?)\)\)", decoded)
        if m:
            return deobfuscate_code(m.group(1))
    return decoded

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's find script blocks containing eval(atob(...))
pattern = r"<script([^>]*)>([\s\S]*?)eval\(atob\(([\s\S]*?)\)\)([\s\S]*?)</script>"

def replacer(match):
    attrs = match.group(1)
    b64_str = match.group(3)
    try:
        decoded = deobfuscate_code(b64_str)
        return "<script" + attrs + ">\n" + decoded + "\n</script>"
    except Exception as e:
        print("Error decoding script:", e)
        return match.group(0)

decompiled = re.sub(pattern, replacer, html, flags=re.IGNORECASE)
with open("index.src.html", "w", encoding="utf-8") as f:
    f.write(decompiled)
print("Deobfuscation done!")
