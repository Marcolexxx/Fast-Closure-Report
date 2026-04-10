from __future__ import annotations

from functools import lru_cache
from typing import Awaitable, Callable, Dict

from app.tools.base import TaskContext, ToolResult


ToolFn = Callable[[dict, TaskContext], Awaitable[ToolResult]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolFn] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = fn

    def upsert(self, name: str, fn: ToolFn) -> None:
        # Used by Skill hot reload to update tool implementations in-place.
        self._tools[name] = fn

    def delete_prefix(self, prefix: str) -> None:
        # Used for Skill hot reload so old tool implementations don't linger.
        keys = [k for k in self._tools.keys() if k.startswith(prefix)]
        for k in keys:
            del self._tools[k]

    def get(self, name: str) -> ToolFn:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())


@lru_cache(maxsize=1)
def get_tool_registry() -> ToolRegistry:
    return ToolRegistry()


def tool(name: str) -> Callable[[ToolFn], ToolFn]:
    def _wrap(fn: ToolFn) -> ToolFn:
        get_tool_registry().register(name, fn)
        return fn

    return _wrap

