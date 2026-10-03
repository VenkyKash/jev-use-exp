content = """def select_window(windows: list[dict], pid: int) -> int | None:
    \"\"\"Bind an unambiguous named window, never choose between named documents.\"\"\"
    if not isinstance(windows, list):
        from native_errors import DiagnosticError
        raise DiagnosticError("malformed_windows", "windows must be a list")
    eligible = [w for w in windows if isinstance(w, dict)
                and type(w.get("window_id")) is int and w["window_id"] > 0
                and type(w.get("pid", pid)) is int and w.get("pid", pid) == pid]
    ids = [w["window_id"] for w in eligible]
    if len(ids) != len(set(ids)):
        return None
    titled = [w for w in eligible if isinstance(w.get("title"), str) and w["title"].strip()]
    if len(titled) == 1:
        return titled[0]["window_id"]
    if len(titled) > 1:
        return None
    on_screen = [w for w in eligible if w.get("is_on_screen", True)]
    if len(on_screen) == 1:
        return on_screen[0]["window_id"]
    return None
"""

import re
with open("python/native_driver.py", "r") as f:
    text = f.read()

# Replace the select_window function
text = re.sub(r'def select_window.*?return None\n', content, text, flags=re.DOTALL)
with open("python/native_driver.py", "w") as f:
    f.write(text)
