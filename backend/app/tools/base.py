from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)

    error_type: Optional[str] = None  # "BUSINESS" | "SYSTEM"
    error_code: Optional[str] = None
    message: Optional[str] = None
    summary: str = ""  # <= 200 chars, shown to Agent


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    user_id: Optional[str]
    trace_id: str
    storage: Optional[str] = None
    # `logger` is kept generic to avoid importing logging types.
    logger: Any = None

