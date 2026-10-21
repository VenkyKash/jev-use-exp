"""MCP transport and strict normalization for the experimental native runner."""
from __future__ import annotations

from typing import Any
import re

from jsonschema import Draft202012Validator

from native_core import Element, Observation
from native_errors import DiagnosticError
from driver_candidates import thaw


class DriverFailure(DiagnosticError):
    pass


def select_window(windows: list[dict], pid: int) -> int | None:
    """Bind an unambiguous named window, never choose between named documents."""
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
    titled = [w for w in eligible if isinstance(w.get("title"), str) and w["title"].strip()]
    if len(titled) == 1:
        return titled[0]["window_id"]
    on_screen = [w for w in eligible if w.get("is_on_screen", True)]
    if len(on_screen) == 1:
        return on_screen[0]["window_id"]
    return None


MENU_ROLES = {"AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem"}


def window_content(elements: list[Element]) -> tuple[list[Element], int]:
    by_id = {element.index: element for element in elements}
    excluded = set()
    for element in elements:
        current = element
        chain = set()
        while current is not None:
            if current.index in chain:
                raise DiagnosticError("cyclic_element_tree", "cyclic element parent references")
            chain.add(current.index)
            if current.role == "AXMenuBar":
                excluded.add(element.index)
                break
            current = by_id.get(current.parent)
    return [e for e in elements if e.index not in excluded], len(excluded)


def normalize(raw: dict[str, Any], pid: int, window_id: int, *, query: str | None = None) -> Observation:
    snapshot = raw.get("snapshot_id")
    rows = raw.get("elements")
    if (not snapshot and rows == [] and raw.get("degraded") is True
            and raw.get("pid") == pid and raw.get("window_id") == window_id):
        # Local observation identity only; never an element-addressing token.
        import uuid
        snapshot = "unindexed-" + uuid.uuid4().hex
    if not isinstance(snapshot, str) or not snapshot or not isinstance(rows, list):
        raise DiagnosticError("missing_snapshot", "Driver must supply snapshot_id and structured elements",
                              has_snapshot=isinstance(snapshot, str), has_elements=isinstance(rows, list))
    if len(rows) > 2000 or raw.get("truncated") or raw.get("tree_truncated"):
        raise DiagnosticError("raw_observation_limit", "observation exceeds v0 context limit; no silent truncation",
                              element_count=len(rows))
    elements = []
    indices = set()
    tokens = set()
    for row in rows:
        if not isinstance(row, dict):
            raise DiagnosticError("malformed_element", "element must be an object")
        index = row.get("element_index")
        role = row.get("role")
        token = row.get("element_token")
        actions = row.get("actions", [])
        label, value = row.get("label"), row.get("value")
        if label is None:
            label = ""
        if type(index) is not int or index < 0 or index in indices:
            raise ValueError("invalid or duplicate element index")
        if not isinstance(role, str) or not role:
            raise ValueError("invalid element role")
        if token is not None and (not isinstance(token, str) or not token or token in tokens):
            raise ValueError("invalid or duplicate element token")
        if not isinstance(actions, list) or any(not isinstance(a, str) for a in actions):
            raise ValueError("invalid element actions")
        if not isinstance(label, str) or (value is not None and not isinstance(value, str)):
            raise ValueError("invalid element label or value")
        if max(len(label), len(value or "")) > 4000:
            raise ValueError("element text exceeds v0 context limit")
        for field in ("enabled", "in_web_content"):
            if field in row and type(row[field]) is not bool:
                raise ValueError(f"invalid {field}")
        parent = row.get("parent_index")
        if parent is not None and (type(parent) is not int or parent < 0):
            raise DiagnosticError("invalid_parent", "invalid parent reference")
        indices.add(index)
        if token:
            tokens.add(token)
        from native_geometry import element_frame
        elements.append(Element(index, role, label, value, token, tuple(actions),
                                row.get("enabled", True), parent,
                                row.get("in_web_content", False), element_frame(row.get("frame"))))
    scoped, excluded = window_content(elements)
    if len(scoped) > 2000:
        raise DiagnosticError("window_content_limit", "window content exceeds 2000 elements",
                              element_count=len(scoped), excluded_menu_elements=excluded)
    complete = False if snapshot.startswith("unindexed-") else raw.get("elements_complete", True)
    if type(complete) is not bool:
        raise DiagnosticError("invalid_completeness", "elements_complete must be boolean")
    text = raw.get("tree_markdown", "")
    if not isinstance(text, str):
        raise ValueError("invalid tree text")
    # Separate non-actionable evidence; never invent element refs from markdown.
    text = re.split(r"(?m)^- (?:\[\d+\] )?AXMenuBar\b", text, maxsplit=1)[0]
    by_id = {e.index: e for e in elements}
    paths = []
    for element in elements:
        if element.role != "AXMenuItem" or not element.enabled or not element.label:
            continue
        path, current, in_application_menu = [], element, False
        while current is not None:
            in_application_menu |= current.role == "AXMenuBar"
            if current.role in {"AXMenuBarItem", "AXMenuItem"} and current.label:
                path.append(current.label)
            current = by_id.get(current.parent)
        if in_application_menu and len(path) > 1:
            paths.append(tuple(reversed(path)))
    capability = raw.get("background_input")
    if capability is not None and not isinstance(capability, dict):
        raise DiagnosticError("invalid_capability_report", "background_input must be an object")
    metadata = {}
    for key in ("app_name", "window_title"):
        value = raw.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 4000):
            raise DiagnosticError("invalid_app_metadata", "invalid application metadata", field=key)
        metadata[key] = value
    inspection = None
    if query is not None:
        complete = False
        inspection = dict(query=query, matching="case-insensitive substring plus ancestors",
                          total_element_count=raw.get("total_element_count", raw.get("element_count")),
                          returned_element_count=len(rows),
                          absence="unknown outside this partial view; reobserve restores the full view")
    from native_geometry import capture_geometry
    cid = raw.get("capture_id")
    return Observation(snapshot, pid, window_id, tuple(scoped), excluded, complete, text, tuple(paths), capability,
                       geometry=capture_geometry(raw),
                       inspection=inspection, availability={
                           "degraded": raw.get("degraded", False),
                           "reason": raw.get("degraded_reason"),
                           **raw.get("window_visibility", {}),
                       }, capture_id=cid if isinstance(cid, str) else None, **metadata)


class NativeDriver:
    def __init__(self, session: Any, label: str, schemas: dict[str, dict]) -> None:
        self.session, self.label, self.schemas = session, label, schemas
        self.restore_target = None
        self.activation_attempted = False

    @classmethod
    async def connect(cls, session: Any, label: str) -> NativeDriver:
        await session.initialize()
        schemas = {}
        cursor = None
        while True:
            page = await session.list_tools(cursor=cursor)
            schemas.update({tool.name: tool.inputSchema for tool in page.tools})
            cursor = page.nextCursor
            if not cursor:
                break
        session_label = None
        if "start_session" in schemas:
            try:
                res = await session.call_tool("start_session", {"session": label})
                if not getattr(res, "isError", False):
                    session_label = label
            except Exception:
                pass
        return cls(session, session_label, schemas)

    def accepts(self, tool: str, arguments: dict) -> bool:
        schema = self.schemas.get(tool)
        if schema is None:
            return False
        args = thaw(arguments)
        if not set(args).issubset(schema.get("properties", {})):
            return False
        if self.label and "session" in schema.get("properties", {}):
            args["session"] = self.label
        return Draft202012Validator(schema).is_valid(args)

    async def call(self, tool: str, arguments: dict) -> dict:
        if not self.accepts(tool, arguments):
            raise DriverFailure("unsupported_tool_arguments", f"unsupported tool or arguments: {tool}", tool=tool)
        args = thaw(arguments)
        if tool == "bring_to_front" and not self.activation_attempted:
            apps = (await self.call("list_apps", {})).get("apps", [])
            active = next((a for a in apps if a.get("active")), None)
            if active:
                windows = (await self.call("list_windows", {"pid": active["pid"]})).get("windows", [])
                visible = [w for w in windows if w.get("is_on_screen") and w.get("title")]
                if visible:
                    prior = max(visible, key=lambda w: w.get("z_index") or 0)
                    self.restore_target = dict(pid=active["pid"], window_id=prior["window_id"])
            self.activation_attempted = True
        if self.label and "session" in self.schemas[tool].get("properties", {}):
            args["session"] = self.label
        try:
            result = await self.session.call_tool(tool, args)
        except Exception as error:
            raise DriverFailure("driver_transport_error", "Driver request failed",
                                tool=tool, cause_type=type(error).__name__) from error
        data = result.structuredContent
        def diagnostics():
            import json
            import os
            text = json.dumps({"structured": data, "messages": [getattr(block, "text", "")
                              for block in getattr(result, "content", [])]}, default=str)
            for name in ("TYPESAFE_API_KEY", "CUA_DRIVER_TOKEN"):
                secret = os.getenv(name)
                if secret:
                    text = text.replace(secret, "[REDACTED]")
            return dict(driver_response=text[:4000], omitted_characters=max(0, len(text)-4000),
                        driver_code=data.get("code") if isinstance(data, dict) else None,
                        driver_effect=data.get("effect") if isinstance(data, dict) else None)
        if result.isError or not isinstance(data, dict):
            raise DriverFailure("driver_tool_error" if result.isError else "missing_structured_result",
                                f"{tool}: error or missing structured result", tool=tool, **diagnostics())
        if data.get("refusal") or data.get("status") in {"refused", "error", "failed"}:
            raise DriverFailure("driver_refused", f"{tool}: refused or failed", tool=tool, **diagnostics())
        return data

    async def restore_focus(self):
        if self.restore_target is not None:
            target, self.restore_target = self.restore_target, None
            return await self.call("bring_to_front", target)

    async def observe(self, pid: int, window_id: int, include_screenshot: bool = True) -> Observation:
        obs_args = {
            "pid": pid, "window_id": window_id, "include_screenshot": include_screenshot,
        }
        if self.accepts("get_window_state", {**obs_args, "timeout_ms": 5000}):
            obs_args["timeout_ms"] = 5000
        try:
            raw = await self.call("get_window_state", obs_args)
        except DriverFailure as e:
            if include_screenshot and ("x11 screenshot failure" in str(e).lower() or "mit-shm" in str(e).lower()):
                obs_args["include_screenshot"] = False
                raw = await self.call("get_window_state", obs_args)
                import uuid
                if "snapshot_id" not in raw:
                    raw["snapshot_id"] = "unindexed-" + uuid.uuid4().hex
            else:
                raise
        if self.accepts("list_windows", {"pid": pid}):
            windows = (await self.call("list_windows", {"pid": pid})).get("windows", [])
            window = next((w for w in windows if w.get("window_id") == window_id), {})
            raw["window_visibility"] = {k: window.get(k) for k in
                                        ("is_on_screen", "on_current_space", "space_ids")}
        # Persist before normalization so rejected/partial responses remain auditable.
        if hasattr(self, "emit"):
            self.emit(dict(event="raw_observation", response=raw))
        try:
            return normalize(raw, pid, window_id)
        except DiagnosticError:
            raise
        except ValueError as error:
            # normalize's validation messages contain field names, never field values.
            raise DiagnosticError("invalid_observation", "Driver observation failed validation",
                                  reason=str(error)) from error
