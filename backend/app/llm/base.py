from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ContentBlock(BaseModel):
    # Keep the same naming as PRD for easy later replacement.
    type: Literal["text", "image", "tool_result"]
    text: Optional[str] = None
    image_data: Optional[str] = None  # base64, local-only model calls
    image_url: Optional[str] = None  # allow only internal urls


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: List[ContentBlock]


class ToolDef(BaseModel):
    name: str
    description: str = ""
    # JSON schema-ish dict; tool router will map input dict at runtime.
    parameters: Dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    # For now we keep a simple string output. Later phases will extend this
    # to structured tool-call plans.
    content: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class LLMChunk(BaseModel):
    delta: str
    raw: Dict[str, Any] = Field(default_factory=dict)


class LLMAdapter(ABC):
    @abstractmethod
    async def complete(
        self, messages: List[Message], tools: Optional[List[ToolDef]] = None
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(
        self, messages: List[Message], tools: Optional[List[ToolDef]] = None
    ) -> AsyncIterator[LLMChunk]:
        ...

