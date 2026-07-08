import re, base64

def deobfuscate_code_recursive(code, level=1):
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
    
    # Extract all single-quoted string literals and concatenate them
    # This preserves '+' characters inside the base64 data!
    literals = re.findall(r"'([^']*)'", b64_expr)
    if not literals:
        # Try double quotes just in case
        literals = re.findall(r'"([^"]*)"', b64_expr)
        
    cleaned = "".join(literals)
    # Remove any newlines or spaces if they somehow got in
    cleaned = cleaned.replace("\n", "").replace("\r", "").replace(" ", "")
    
    print(f"Level {level}: expr len={len(b64_expr)}, cleaned len={len(cleaned)}")
    
    # Pad to multiple of 4
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
        
    try:
        decoded = base64.b64decode(cleaned).decode("utf-8")
        return deobfuscate_code_recursive(decoded, level + 1)
    except Exception as e:
        print(f"Level {level} failed: {e}")
        return code

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Replace each script content
pattern = r"<script([^>]*)>([\s\S]*?)</script>"

def replacer(match):
    attrs = match.group(1)
    content = match.group(2).strip()
    if "atob" not in content:
        return match.group(0)
    print("Deobfuscating script tag...")
    decoded = deobfuscate_code_recursive(content)
    return "<script" + attrs + ">\n" + decoded + "\n</script>"

decompiled = re.sub(pattern, replacer, html, flags=re.IGNORECASE)
with open("index.src.html", "w", encoding="utf-8") as f:
    f.write(decompiled)
print("Done!")
