from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_engine, get_session_maker
from app.models import SkillConfig
from app.skills.skill_models import SkillJson
from app.tools.registry import get_tool_registry


def _sanitize_module_name(s: str) -> str:
    return "".join([c if c.isalnum() else "_" for c in s])


def _load_skill_json(skill_dir: Path) -> SkillJson:
    # Some editors may inject UTF-8 BOM. Use utf-8-sig to auto-strip it.
    raw = (skill_dir / "skill.json").read_text(encoding="utf-8-sig")
    return SkillJson.model_validate_json(raw)


def _load_tool_fn(skills_dir: Path, skill_id: str, tool_name: str):
    tool_path = skills_dir / skill_id / "tools" / f"{tool_name}.py"
    if not tool_path.exists():
        return None

    module_name = _sanitize_module_name(f"_skill_{skill_id}_{tool_name}")
    spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    return getattr(module, tool_name, None)


class SkillRegistryService:
    def __init__(self) -> None:
        self._skills: Dict[str, SkillJson] = {}

    @property
    def skills(self) -> Dict[str, SkillJson]:
        return self._skills

    def _skills_dir(self) -> Path:
        # In the backend container, /app == backend/ directory.
        # We keep skills under backend/ for now so it's inside the image.
        base = Path(os.environ.get("SKILLS_DIR", "skills"))
        return base

    async def get_enabled(self, skill_id: str) -> bool:
        async with get_session_maker()() as session:
            stmt = select(SkillConfig).where(SkillConfig.skill_id == skill_id, SkillConfig.config_key == "is_enabled")
            row = (await session.execute(stmt)).scalars().first()
            if not row:
                return True
            return str(row.config_value).lower() in ("1", "true", "yes", "y")

    async def set_enabled(self, skill_id: str, enabled: bool, updated_by: Optional[str] = None) -> None:
        value = "true" if enabled else "false"
        async with get_session_maker()() as session:
            stmt = select(SkillConfig).where(
                SkillConfig.skill_id == skill_id, SkillConfig.config_key == "is_enabled"
            )
            row = (await session.execute(stmt)).scalars().first()
            if row:
                row.config_value = value
                row.updated_by = updated_by
            else:
                session.add(
                    SkillConfig(
                        skill_id=skill_id,
                        config_key="is_enabled",
                        config_value=value,
                        updated_by=updated_by,
                    )
                )
            await session.commit()

    async def load_all(self) -> None:
        skills_dir = self._skills_dir()
        tool_registry = get_tool_registry()

        if not skills_dir.exists():
            # No skills configured yet; keep platform runnable.
            return

        for entry in skills_dir.iterdir():
            if not entry.is_dir():
                continue
            skill_dir = entry
            skill_json_path = skill_dir / "skill.json"
            if not skill_json_path.exists():
                continue

            skill = _load_skill_json(skill_dir)
            self._skills[skill.id] = skill

            # Tool registration
            # Cleanup existing namespace entries on reload.
            tool_registry.delete_prefix(f"{skill.id}::")
            for t in skill.tools:
                fn = _load_tool_fn(skills_dir, skill.id, t.name)
                if fn:
                    tool_registry.upsert(f"{skill.id}::{t.name}", fn)

    async def reload_skill(self, skill_id: str) -> None:
        # Re-load skill.json and re-register its tools.
        skills_dir = self._skills_dir()
        tool_registry = get_tool_registry()

        skill_dir = skills_dir / skill_id
        skill_json_path = skill_dir / "skill.json"
        if not skill_json_path.exists():
            return

        skill = _load_skill_json(skill_dir)
        self._skills[skill.id] = skill

        # Remove old namespace entries first.
        tool_registry.delete_prefix(f"{skill.id}::")

        for t in skill.tools:
            fn = _load_tool_fn(skills_dir, skill.id, t.name)
            if fn:
                tool_registry.upsert(f"{skill.id}::{t.name}", fn)


@lru_cache(maxsize=1)
def get_skill_registry_service() -> SkillRegistryService:
    return SkillRegistryService()

