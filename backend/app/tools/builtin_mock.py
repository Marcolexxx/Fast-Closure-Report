from __future__ import annotations

from app.tools.base import ToolResult, TaskContext
from app.tools.registry import tool


@tool("mock.echo")
async def mock_echo(input: dict, context: TaskContext) -> ToolResult:
    # Useful for unit tests of ToolRouter/execute_tool.
    return ToolResult(
        success=True,
        data={"echo": input},
        summary="Echoed input (mock)",
    )

