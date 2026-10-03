import re
with open("python/native_run.py", "r") as f:
    text = f.read()

replacement = """        elif target:
            if driver.accepts("list_windows", {"pid": target[0]}):
                windows = (await driver.call("list_windows", {"pid": target[0]})).get("windows", [])
                new_id = select_window(windows, target[0])
                if new_id is not None and new_id != target[1]:
                    target = (target[0], new_id)
                    emit(dict(event="target_rebound", pid=target[0], window_id=new_id))
            observation = await driver.observe(*target)"""

text = text.replace("        elif target:\n            observation = await driver.observe(*target)", replacement)
with open("python/native_run.py", "w") as f:
    f.write(text)
