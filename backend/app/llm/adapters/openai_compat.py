from __future__ import annotations

import json
from typing import AsyncIterator, List, Optional

import aiohttp

from app.llm.base import LLMAdapter, LLMChunk, LLMResponse, Message, ToolDef


def _messages_to_openai(messages: List[Message]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        # Current platform is text-first; if future blocks appear, we keep only text.
        text = "".join([(b.text or "") for b in (m.content or []) if b.type == "text"]).strip()
        out.append({"role": m.role, "content": text})
    return out


class OpenAICompatibleAdapter(LLMAdapter):
    """
    Minimal OpenAI-compatible chat-completions adapter over HTTP.

    Supported endpoints:
    - POST {base_url}/chat/completions

    Notes:
    - Text-only for now (keeps platform safe: no image payloads to external APIs).
    - Tools are ignored (tool calling not implemented in this adapter yet).
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = float(temperature)
        self._max_tokens = int(max_tokens)
        self._timeout_s = float(timeout_s)

    async def complete(self, messages: List[Message], tools: Optional[List[ToolDef]] = None) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": _messages_to_openai(messages),
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, data=json.dumps(payload)) as resp:
                raw_text = await resp.text()
                if resp.status >= 400:
                    return LLMResponse(content="", raw={"status": resp.status, "error": raw_text})
                data = json.loads(raw_text or "{}")
        content = (
            (data.get("choices") or [{}])[0].get("message", {}).get("content")
            or ""
        )
        return LLMResponse(content=content, raw=data)

    async def stream(self, messages: List[Message], tools: Optional[List[ToolDef]] = None) -> AsyncIterator[LLMChunk]:
        # For now, return a single chunk (keeps compatibility with streaming consumers).
        res = await self.complete(messages, tools)
        yield LLMChunk(delta=res.content, raw=res.raw or {})

