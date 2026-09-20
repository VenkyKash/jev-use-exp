"""In-memory UI fixtures for mechanics and Jev evaluation, not desktop evidence."""
from native_driver import normalize


class FixtureDriver:
    def __init__(self, kind="form", reverse=False):
        self.kind, self.reverse = kind, reverse
        self.calls = []
        self.version = 0
        self.fields = ["", ""]
        self.submitted = None
        self.display, self.left, self.pending = "0", None, False

    def accepts(self, tool, arguments):
        return tool in {"launch_app", "click", "type_text", "list_windows"}

    async def observe(self, pid, window_id):
        self.version += 1
        sid = f"fixture-{self.version}"
        if self.kind == "calculator":
            labels = list("0123456789") + ["×", "=", "Clear"]
            rows = [dict(role="AXButton", label=label, actions=["AXPress"]) for label in labels]
            rows.append(dict(role="AXStaticText", label="Display", value=self.display))
        else:
            rows = [dict(role="AXTextField", label="Name", value=self.fields[0]),
                    dict(role="AXTextField", label="City", value=self.fields[1]),
                    dict(role="AXButton", label="Submit", actions=["AXPress"]),
                    dict(role="AXButton", label="Reset", actions=["AXPress"]),
                    dict(role="AXStaticText", label="Receipt", value=" | ".join(self.submitted) if self.submitted else "")]
        if self.reverse:
            rows.reverse()
        for index, row in enumerate(rows):
            row.update(element_index=index, element_token=f"{sid}:{index}")
        self.rows = rows
        return normalize(dict(snapshot_id=sid, elements=rows), pid, window_id)

    async def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == "launch_app":
            return dict(pid=1, windows=[dict(window_id=2)])
        token = arguments["element_token"]
        sid, index = token.rsplit(":", 1)
        if sid != f"fixture-{self.version}":
            raise RuntimeError("stale_element_token")
        row = self.rows[int(index)]
        label = row["label"]
        if self.kind == "form":
            if tool == "type_text":
                self.fields[0 if label == "Name" else 1] += arguments["text"]
            elif label == "Submit":
                self.submitted = tuple(self.fields)
            elif label == "Reset":
                self.fields, self.submitted = ["", ""], None
        elif label.isdigit():
            self.display = label if self.pending or self.display == "0" else self.display+label
            self.pending = False
        elif label == "×":
            self.left, self.pending = int(self.display), True
        elif label == "=" and self.left is not None:
            self.display = str(self.left * int(self.display))
            self.left, self.pending = None, True
        elif label == "Clear":
            self.display, self.left, self.pending = "0", None, False
        return {"status": "ok"}
