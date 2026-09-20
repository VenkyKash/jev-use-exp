"""MCP transport and strict normalization for the experimental native runner."""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from native_core import Element, Observation
from native_errors import DiagnosticError


class DriverFailure(DiagnosticError):
    pass


def select_window(windows: list[dict], pid: int) -> int | None:
    """Bind an unambiguous named window, never choose between named documents."""
    if not isinstance(windows, list):
        raise DiagnosticError("malformed_windows", "windows must be a list")
    eligible = [w for w in windows if isinstance(w, dict)
                and type(w.get("window_id")) is int and w["window_id"] > 0
                and type(w.get("pid", pid)) is int and w.get("pid", pid) == pid]
    ids = [w["window_id"] for w in eligible]
    if len(ids) != len(set(ids)):
        return None
    titled = [w for w in eligible if isinstance(w.get("title"), str) and w["title"].strip()]
    if len(titled) == 1 and all(w is titled[0] or w.get("is_on_screen") is False for w in eligible):
        return titled[0]["window_id"]
    if len(eligible) == 1 and eligible[0].get("is_on_screen", True):
        return eligible[0]["window_id"]
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
            if current.role in MENU_ROLES:
                excluded.add(element.index)
                break
            current = by_id.get(current.parent)
    return [e for e in elements if e.index not in excluded], len(excluded)


def normalize(raw: dict[str, Any], pid: int, window_id: int) -> Observation:
    snapshot = raw.get("snapshot_id")
    rows = raw.get("elements")
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
        elements.append(Element(index, role, label, value, token, tuple(actions),
                                row.get("enabled", True), parent,
                                row.get("in_web_content", False)))
    scoped, excluded = window_content(elements)
    if len(scoped) > 200:
        raise DiagnosticError("window_content_limit", "window content exceeds 200 elements",
                              element_count=len(scoped), excluded_menu_elements=excluded)
    complete = raw.get("elements_complete", True)
    if type(complete) is not bool:
        raise DiagnosticError("invalid_completeness", "elements_complete must be boolean")
    return Observation(snapshot, pid, window_id, tuple(scoped), excluded, complete)


class NativeDriver:
    def __init__(self, session: Any, label: str, schemas: dict[str, dict]) -> None:
        self.session, self.label, self.schemas = session, label, schemas

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
        return cls(session, label, schemas)

    def accepts(self, tool: str, arguments: dict) -> bool:
        schema = self.schemas.get(tool)
        if schema is None:
            return False
        args = dict(arguments)
        if not set(args).issubset(schema.get("properties", {})):
            return False
        if "session" in schema.get("properties", {}):
            args["session"] = self.label
        return Draft202012Validator(schema).is_valid(args)

    async def call(self, tool: str, arguments: dict) -> dict:
        if not self.accepts(tool, arguments):
            raise DriverFailure("unsupported_tool_arguments", f"unsupported tool or arguments: {tool}", tool=tool)
        args = dict(arguments)
        if "session" in self.schemas[tool].get("properties", {}):
            args["session"] = self.label
        try:
            result = await self.session.call_tool(tool, args)
        except Exception as error:
            raise DriverFailure("driver_transport_error", "Driver request failed",
                                tool=tool, cause_type=type(error).__name__) from error
        data = result.structuredContent
        if result.isError or not isinstance(data, dict):
            raise DriverFailure("driver_tool_error" if result.isError else "missing_structured_result",
                                f"{tool}: error or missing structured result", tool=tool)
        if data.get("refusal") or data.get("status") in {"refused", "error", "failed"}:
            raise DriverFailure("driver_refused", f"{tool}: refused or failed", tool=tool)
        return data

    async def observe(self, pid: int, window_id: int) -> Observation:
        raw = await self.call("get_window_state", {
            "pid": pid, "window_id": window_id, "include_screenshot": False,
        })
        try:
            return normalize(raw, pid, window_id)
        except DiagnosticError:
            raise
        except ValueError as error:
            # normalize's validation messages contain field names, never field values.
            raise DiagnosticError("invalid_observation", "Driver observation failed validation",
                                  reason=str(error)) from error
