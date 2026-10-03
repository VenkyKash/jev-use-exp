import sys
content = sys.stdin.read()
new_content = content.replace(
    '    if len(titled) == 1 and all(w is titled[0] or w.get("is_on_screen") is False for w in eligible):\n        return titled[0]["window_id"]\n    if len(eligible) == 1 and eligible[0].get("is_on_screen", True):\n        return eligible[0]["window_id"]',
    '    if len(titled) == 1:\n        return titled[0]["window_id"]\n    on_screen = [w for w in eligible if w.get("is_on_screen", True)]\n    if len(on_screen) == 1:\n        return on_screen[0]["window_id"]'
)
with open("python/native_driver.py", "w") as f:
    f.write(new_content)
