import re, base64

def deobfuscate_code_recursive(code):
    # Try to find eval(atob('...')) inside code
    # We clean up the code inside atob
    start = code.find("atob(")
    if start == -1:
        return code
        
    inside = code[start + 5:]
    depth = 1
    idx = 0
    for char in inside:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                break
        idx += 1
    
    b64_expr = inside[:idx]
    cleaned = b64_expr.replace("'", "").replace("+", "").replace(" ", "").replace("\n", "").replace("\r", "").replace('"', "")
    
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
        
    try:
        decoded = base64.b64decode(cleaned).decode("utf-8")
        # Keep deobfuscating recursively
        return deobfuscate_code_recursive(decoded)
    except Exception as e:
        print("Error decoding:", e)
        return code

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Replace each script content with its fully deobfuscated version
pattern = r"<script([^>]*)>([\s\S]*?)</script>"

def replacer(match):
    attrs = match.group(1)
    content = match.group(2).strip()
    if "atob" not in content:
        return match.group(0)
    try:
        decoded = deobfuscate_code_recursive(content)
        # If it still has eval(atob in it, resolve it one more time just in case
        if "eval(atob(" in decoded:
            decoded = deobfuscate_code_recursive(decoded)
        return "<script" + attrs + ">\n" + decoded + "\n</script>"
    except Exception as e:
        print("Error in script replacer:", e)
        return match.group(0)

decompiled = re.sub(pattern, replacer, html, flags=re.IGNORECASE)

# Clean up any leftover comments or empty lines
decompiled = re.sub(r"\n\s*\n", "\n", decompiled)

with open("index.src.html", "w", encoding="utf-8") as f:
    f.write(decompiled)
print("De-obfuscated to index.src.html successfully!")
