from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional

from app.llm.adapters.mock import MockAdapter
from app.llm.adapters.openai_compat import OpenAICompatibleAdapter
from app.llm.base import LLMAdapter, LLMChunk, LLMResponse, Message, ToolDef
from app.llm.data_classifier import DataClassifier
from app.services.system_config import get_namespace_map

logger = logging.getLogger(__name__)

_data_classifier = DataClassifier()


def _as_float(val: str, default: float) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _as_int(val: str, default: int) -> int:
    try:
        return int(float(val))
    except Exception:
        return default


class SystemConfiguredAdapter(LLMAdapter):
    """
    Runtime-configured adapter using SystemConfig namespace 'llm'.

    Keys expected (frontend already writes these today):
    - llm_provider: openai | deepseek | ollama | mock
    - llm_model
    - llm_api_key
    - llm_api_base
    - llm_temperature
    - llm_max_tokens
    """

    async def _resolve(self) -> tuple[LLMAdapter, str]:
        """Returns (adapter_instance, provider_name)."""
        cfg = await get_namespace_map("llm")
        provider = (cfg.get("llm_provider") or "mock").lower()
        if provider == "mock":
            return MockAdapter(), "mock"

        model = cfg.get("llm_model") or "gpt-4o"
        api_key = cfg.get("llm_api_key") or ""
        base_url = cfg.get("llm_api_base") or "https://api.openai.com/v1"
        temperature = _as_float(cfg.get("llm_temperature") or "0.2", 0.2)
        max_tokens = _as_int(cfg.get("llm_max_tokens") or "4096", 4096)

        # deepseek/ollama: treat as openai-compatible endpoints in V1
        adapter = OpenAICompatibleAdapter(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return adapter, provider

    async def complete(self, messages: List[Message], tools: Optional[List[ToolDef]] = None) -> LLMResponse:
        adapter, provider = await self._resolve()
        # PRD §5.1: DataClassifier blocks image_data from external APIs
        _data_classifier.check_payload(messages, provider)
        return await adapter.complete(messages, tools)

    async def stream(self, messages: List[Message], tools: Optional[List[ToolDef]] = None) -> AsyncIterator[LLMChunk]:
        adapter, provider = await self._resolve()
        # PRD §5.1: DataClassifier blocks image_data from external APIs
        _data_classifier.check_payload(messages, provider)
        async for chunk in adapter.stream(messages, tools):
            yield chunk


