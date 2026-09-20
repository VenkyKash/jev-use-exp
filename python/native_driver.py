"""MCP transport and strict normalization for the experimental native runner."""
from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from native_core import Element, Observation


class DriverFailure(RuntimeError):
    pass


def normalize(raw: dict[str, Any], pid: int, window_id: int) -> Observation:
    snapshot = raw.get("snapshot_id")
    rows = raw.get("elements")
    if not isinstance(snapshot, str) or not snapshot or not isinstance(rows, list):
        raise ValueError("Driver must supply snapshot_id and structured elements")
    if len(rows) > 200 or raw.get("truncated") or raw.get("tree_truncated"):
        raise ValueError("observation exceeds v0 context limit; no silent truncation")
    elements = []
    indices = set()
    tokens = set()
    for row in rows:
        index = row.get("element_index")
        role = row.get("role")
        token = row.get("element_token")
        actions = row.get("actions", [])
        label, value = row.get("label", ""), row.get("value")
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
        indices.add(index)
        if token:
            tokens.add(token)
        elements.append(Element(index, role, label, value, token, tuple(actions),
                                row.get("enabled", True), row.get("parent_index"),
                                row.get("in_web_content", False)))
    return Observation(snapshot, pid, window_id, tuple(elements))


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
            raise DriverFailure(f"unsupported tool or arguments: {tool}")
        args = dict(arguments)
        if "session" in self.schemas[tool].get("properties", {}):
            args["session"] = self.label
        result = await self.session.call_tool(tool, args)
        data = result.structuredContent
        if result.isError or not isinstance(data, dict):
            raise DriverFailure(f"{tool}: error or missing structured result")
        if data.get("refusal") or data.get("status") in {"refused", "error", "failed"}:
            raise DriverFailure(f"{tool}: refused or failed")
        return data

    async def observe(self, pid: int, window_id: int) -> Observation:
        raw = await self.call("get_window_state", {
            "pid": pid, "window_id": window_id, "include_screenshot": False,
        })
        return normalize(raw, pid, window_id)
