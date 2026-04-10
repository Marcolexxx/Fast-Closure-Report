from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ToolType = Literal["auto", "human_in_loop"]


class SkillToolSpec(BaseModel):
    name: str
    timeout: int = 30
    type: ToolType
    ui: Optional[str] = None
    async_: Optional[bool] = Field(default=None, alias="async")

    class Config:
        populate_by_name = True


class SkillJson(BaseModel):
    id: str
    name: str
    version: str

    min_platform_version: str
    min_context_version: str

    description: Optional[str] = None
    icon: Optional[str] = None
    trigger_examples: List[str] = Field(default_factory=list)
    required_roles: List[str] = Field(default_factory=list)
    tools: List[SkillToolSpec] = Field(default_factory=list)

