from __future__ import annotations

from typing import AsyncIterator, List, Optional

from app.config import get_settings
from app.llm.base import LLMAdapter, LLMChunk, LLMResponse, Message, ToolDef


class MockAdapter(LLMAdapter):
    """
    M1 tool-chain dev helper.
    - Returns deterministic text for `complete`.
    - `stream` yields a few chunks to validate websocket/hydration later.
    """

    def __init__(self) -> None:
        self._prefix = "[mock-llm]"
        settings = get_settings()
        if settings.llm_fallback:
            # Used later for fallback behavior; for now just keep it deterministic.
            self._prefix = f"[mock-llm-fallback:{settings.llm_fallback}]"

    async def complete(
        self, messages: List[Message], tools: Optional[List[ToolDef]] = None
    ) -> LLMResponse:
        # Minimal deterministic behavior: echo last user text.
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                # Join all text blocks; ignore non-text blocks for now.
                last_user = "".join([b.text or "" for b in m.content if b.type == "text"]).strip()
                break

        return LLMResponse(
            content=f"{self._prefix} received: {last_user}",
            raw={"tools_provided": bool(tools), "tool_count": len(tools or [])},
        )

    async def stream(
        self, messages: List[Message], tools: Optional[List[ToolDef]] = None
    ) -> AsyncIterator[LLMChunk]:
        full = (await self.complete(messages, tools)).content
        # Emit in a few chunks to mimic streaming.
        step = max(5, len(full) // 3)
        for i in range(0, len(full), step):
            yield LLMChunk(delta=full[i : i + step], raw={})

