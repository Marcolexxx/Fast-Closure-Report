from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMAdapter
from app.llm.adapters.configured import SystemConfiguredAdapter


def get_llm_adapter() -> LLMAdapter:
    """
    Select LLM adapter based on:
    1) SystemConfig namespace 'llm' (Admin-managed runtime config)
    2) Fallback to env Settings.llm_adapter (dev / container defaults)
    """
    settings = get_settings()

    # In V1 we treat env selection as "enable runtime-configured adapter".
    # When llm_adapter != mock, we still resolve provider/model/keys at runtime via SystemConfig.
    # This keeps existing dev behavior (mock by default) while letting Admin UI drive config.
    adapter = (settings.llm_adapter or "mock").lower()
    if adapter == "mock":
        # Still allow runtime config to override to non-mock if Admin changed it.
        return SystemConfiguredAdapter()
    return SystemConfiguredAdapter()

