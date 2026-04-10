"""
DataClassifier — PRD §5.1 Security Constraint

Inspects LLM payloads before dispatch. If any ContentBlock contains
`image_data` (base64 binary), the request MUST be routed to a local
InferenceAdapter only. Sending image binary to external APIs (Claude,
OpenAI, DeepSeek) is forbidden.

Usage:
    classifier = DataClassifier()
    classifier.check_payload(messages)  # raises DataLeakageError if violation
"""
from __future__ import annotations

import logging
from typing import List

from app.llm.base import Message

logger = logging.getLogger(__name__)


class DataLeakageError(Exception):
    """Raised when an attempt is made to send image binary to an external API."""
    pass


class DataClassifier:
    """
    Scans a list of Message objects for image_data fields.
    If found, raises DataLeakageError to prevent external API calls.
    """

    def contains_image_data(self, messages: List[Message]) -> bool:
        """Return True if any content block carries base64 image_data."""
        for msg in messages:
            for block in msg.content:
                if block.image_data:
                    return True
        return False

    def check_payload(self, messages: List[Message], adapter_name: str) -> None:
        """
        Validate that image binary is NOT being sent to an external adapter.
        Local adapters (inference, ollama with local images) are exempt.

        Args:
            messages: The message list about to be sent.
            adapter_name: The resolved adapter name (e.g. 'openai', 'claude', 'ollama', 'inference', 'mock').

        Raises:
            DataLeakageError if image_data is present and adapter is external.
        """
        EXTERNAL_ADAPTERS = {"openai", "claude", "deepseek"}
        if adapter_name.lower() not in EXTERNAL_ADAPTERS:
            return  # local adapter — safe

        if self.contains_image_data(messages):
            logger.error(
                "data_classifier_blocked",
                extra={
                    "adapter_name": adapter_name,
                    "reason": "image_data detected in payload destined for external API",
                },
            )
            raise DataLeakageError(
                f"Blocked: payload contains image_data but target adapter '{adapter_name}' "
                f"is external. Image binary must not leave the internal network. "
                f"Route this request to a local InferenceAdapter instead."
            )
