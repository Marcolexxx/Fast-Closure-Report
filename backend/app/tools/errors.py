from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BusinessError(Exception):
    message: str
    error_code: Optional[str] = None

    def __str__(self) -> str:
        return self.message

