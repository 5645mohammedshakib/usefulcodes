import re, base64

with open("index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Let's find script blocks
scripts = list(re.finditer(r"<script([^>]*)>([\s\S]*?)</script>", html, flags=re.IGNORECASE))
for i, m in enumerate(scripts):
    content = m.group(2).strip()
    print(f"Script {i}: length={len(content)}")
    if "atob" in content:
        # Let's extract everything inside the outermost atob(...)
        # We can find the first 'atob(' and the last ')'
        start = content.find("atob(")
        if start != -1:
            # Outermost parenthesis matching
            inside = content[start + 5:]
            # We want to find the matching closing parenthesis
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
            print(f"  Found b64 expression: length={len(b64_expr)}, starts with: {b64_expr[:100]}")
            # Clean up
            cleaned = b64_expr.replace("'", "").replace("+", "").replace(" ", "").replace("\n", "").replace("\r", "").replace('"', "")
            print(f"  Cleaned base64 length: {len(cleaned)}")
            try:
                # Add padding if needed
                missing_padding = len(cleaned) % 4
                if missing_padding:
                    cleaned += '=' * (4 - missing_padding)
                decoded = base64.b64decode(cleaned).decode("utf-8")
                print(f"  Decoded successfully! Length={len(decoded)}")
                print(f"  Decoded starts with: {decoded[:100]}")
                
                # Check if there is another level
                if "eval(atob(" in decoded:
                    print("    Detected nested level 2!")
                    start2 = decoded.find("atob(")
                    inside2 = decoded[start2 + 5:]
                    depth2 = 1
                    idx2 = 0
                    for char in inside2:
                        if char == '(':
                            depth2 += 1
                        elif char == ')':
                            depth2 -= 1
                            if depth2 == 0:
                                break
                        idx2 += 1
                    b64_expr2 = inside2[:idx2]
                    cleaned2 = b64_expr2.replace("'", "").replace("+", "").replace(" ", "").replace("\n", "").replace("\r", "").replace('"', "")
                    missing_padding2 = len(cleaned2) % 4
                    if missing_padding2:
                        cleaned2 += '=' * (4 - missing_padding2)
                    decoded2 = base64.b64decode(cleaned2).decode("utf-8")
                    print(f"    Decoded level 2 successfully! Length={len(decoded2)}")
                    print(f"    Decoded 2 starts with: {decoded2[:200]}")
            except Exception as e:
                print("  Failed to decode:", e)
