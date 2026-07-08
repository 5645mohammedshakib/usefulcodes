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
    
    literals = re.findall(r"'([^']*)'", b64_expr)
    if not literals:
        literals = re.findall(r'"([^"]*)"', b64_expr)
        
    cleaned = "".join(literals)
    cleaned = cleaned.replace("\n", "").replace("\r", "").replace(" ", "")
    
    missing_padding = len(cleaned) % 4
    if missing_padding:
        cleaned += '=' * (4 - missing_padding)
        
    try:
        decoded = base64.b64decode(cleaned).decode("utf-8")
        return deobfuscate_code_recursive(decoded, level + 1)
    except Exception as e:
        return code

with open("student.html", "r", encoding="utf-8") as f:
    html = f.read()

pattern = r"<script([^>]*)>([\s\S]*?)</script>"

def replacer(match):
    attrs = match.group(1)
    content = match.group(2).strip()
    if "atob" not in content:
        return match.group(0)
    decoded = deobfuscate_code_recursive(content)
    return "<script" + attrs + ">\n" + decoded + "\n</script>"

decompiled = re.sub(pattern, replacer, html, flags=re.IGNORECASE)
with open("student.src.html", "w", encoding="utf-8") as f:
    f.write(decompiled)
print("Student Deobfuscation Done!")
