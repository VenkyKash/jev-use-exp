import sys
content = sys.stdin.read()
new_content = content.replace(
    '                                   and details.get("driver_code") in {"element_outside_target_window", "off_space_or_ax_unresolved"})',
    '                                   and details.get("driver_code") in {"element_outside_target_window", "off_space_or_ax_unresolved", "type_text_incomplete"})'
)
with open("python/native_run.py", "w") as f:
    f.write(new_content)
