"""
Admin: Skills Management API (Enhanced)
- Enable/disable via unified endpoint
- Skill detail (full skill.json with tools)
- Git install / Upload install
- Auth protected
"""
from __future__ import annotations

import json
import logging
import os
import zipfile
import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import AuditLog, SkillConfig, User
from app.security.deps import get_current_user, require_admin
from app.skills.registry import get_skill_registry_service

router = APIRouter(prefix="/admin/skills", tags=["admin-skills"])
logger = logging.getLogger(__name__)


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def _write_audit(actor: User, action: str, skill_id: str, detail: dict) -> None:
    async with _sm()() as s:
        s.add(AuditLog(
            user_id=actor.id, username=actor.username,
            action=action, resource_type="skill", resource_id=skill_id,
            detail_json=json.dumps(detail, ensure_ascii=False)
        ))
        await s.commit()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SkillToggle(BaseModel):
    enabled: bool


class GitInstallRequest(BaseModel):
    git_url: str
    branch: str = "main"
    skill_id: Optional[str] = None   # Override skill id from skill.json


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_skills(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List all registered skills with their enabled status."""
    service = get_skill_registry_service()
    skills = list(service.skills.values())
    result: list[dict] = []
    for s in skills:
        enabled = await service.get_enabled(s.id)
        result.append({
            "id": s.id,
            "name": s.name,
            "version": s.version,
            "description": getattr(s, 'description', ''),
            "icon": getattr(s, 'icon', ''),
            "required_roles": getattr(s, 'required_roles', []),
            "tools_count": len(s.tools),
            "is_enabled": enabled,
        })
    return result


@router.get("/{skill_id}")
async def get_skill_detail(
    skill_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return full skill details including all tool definitions."""
    service = get_skill_registry_service()
    skill = service.skills.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    enabled = await service.get_enabled(skill_id)

    # Read raw skill.json for full details
    skills_dir = service._skills_dir()
    skill_json_path = skills_dir / skill_id / "skill.json"
    raw_json = {}
    if skill_json_path.exists():
        try:
            raw_json = json.loads(skill_json_path.read_text(encoding="utf-8-sig"))
        except Exception:
            pass

    # Read agent prompt if exists
    prompt_path = skills_dir / skill_id / "agent_prompt.md"
    agent_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else None

    tools_detail = []
    for t in skill.tools:
        tool_info = {
            "name": t.name,
            "type": t.type,
            "timeout": t.timeout,
        }
        if hasattr(t, 'ui'):
            tool_info["ui"] = t.ui
        if hasattr(t, 'async_'):
            tool_info["async"] = t.async_
        # Check if tool file exists
        tool_path = skills_dir / skill_id / "tools" / f"{t.name}.py"
        tool_info["has_implementation"] = tool_path.exists()
        tools_detail.append(tool_info)

    return {
        "id": skill.id,
        "name": skill.name,
        "version": skill.version,
        "description": getattr(skill, 'description', ''),
        "icon": getattr(skill, 'icon', ''),
        "required_roles": getattr(skill, 'required_roles', []),
        "trigger_examples": getattr(skill, 'trigger_examples', []),
        "is_enabled": enabled,
        "tools": tools_detail,
        "agent_prompt": agent_prompt,
        "raw_skill_json": raw_json,
    }


@router.post("/{skill_id}/enabled")
async def set_skill_enabled(
    skill_id: str,
    body: SkillToggle,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Unified enable/disable endpoint. Accepts {enabled: bool}."""
    service = get_skill_registry_service()
    if skill_id not in service.skills:
        raise HTTPException(status_code=404, detail="Skill not found")

    await service.set_enabled(skill_id, body.enabled, updated_by=current_user.id)
    await _write_audit(current_user, "toggle_skill", skill_id, {"enabled": body.enabled})
    return {"ok": True, "skill_id": skill_id, "is_enabled": body.enabled}


@router.post("/{skill_id}/reload")
async def reload_skill(
    skill_id: str,
    current_user: User = Depends(require_admin),
) -> dict:
    service = get_skill_registry_service()
    await service.reload_skill(skill_id)
    await _write_audit(current_user, "reload_skill", skill_id, {})
    return {"ok": True, "skill_id": skill_id}


@router.post("/reload_all")
async def reload_all_skills(
    current_user: User = Depends(require_admin),
) -> dict:
    service = get_skill_registry_service()
    await service.load_all()
    await _write_audit(current_user, "reload_all_skills", "all", {"count": len(service.skills)})
    return {"ok": True, "reloaded": len(service.skills)}


@router.post("/install-from-git")
async def install_skill_from_git(
    body: GitInstallRequest,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Install a skill from a Git repository URL.
    Clones the repo and copies the skill directory into the skills folder.
    Requires 'git' to be available in the container.
    """
    import subprocess
    import tempfile

    service = get_skill_registry_service()
    skills_dir = service._skills_dir()

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                ["git", "clone", "--depth=1", f"--branch={body.branch}", body.git_url, tmpdir + "/repo"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                raise HTTPException(status_code=400, detail=f"Git clone failed: {result.stderr[:500]}")

            repo_path = Path(tmpdir) / "repo"

            # Find skill.json in the repo
            skill_json_candidates = list(repo_path.glob("**/skill.json"))
            if not skill_json_candidates:
                raise HTTPException(status_code=400, detail="No skill.json found in repository")

            skill_json_path = skill_json_candidates[0]
            skill_dir = skill_json_path.parent

            raw = json.loads(skill_json_path.read_text(encoding="utf-8-sig"))
            skill_id = body.skill_id or raw.get("id")
            if not skill_id:
                raise HTTPException(status_code=400, detail="Could not determine skill_id")

            dest = skills_dir / skill_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Git clone timed out (60s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Install failed: {str(e)}")

    # Reload registry
    await service.load_all()
    await _write_audit(current_user, "install_skill_git", skill_id, {"git_url": body.git_url, "branch": body.branch})
    return {"ok": True, "skill_id": skill_id, "message": "Skill installed and registry reloaded"}


@router.post("/install-from-zip")
async def install_skill_from_zip(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Install a skill by uploading a zip archive containing the skill directory.
    The archive should contain a root folder with skill.json inside.
    """
    import tempfile

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=415, detail="Only .zip archives are supported")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty archive")

    service = get_skill_registry_service()
    skills_dir = service._skills_dir()
    skill_id = None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "skill.zip"
            archive.write_bytes(content)

            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(tmpdir)

            # Find skill.json
            candidates = list(Path(tmpdir).glob("**/skill.json"))
            if not candidates:
                raise HTTPException(status_code=400, detail="No skill.json found in archive")

            skill_json_path = candidates[0]
            skill_dir = skill_json_path.parent
            raw = json.loads(skill_json_path.read_text(encoding="utf-8-sig"))
            skill_id = raw.get("id")
            if not skill_id:
                raise HTTPException(status_code=400, detail="skill.json missing 'id' field")

            dest = skills_dir / skill_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Install failed: {str(e)}")

    await service.load_all()
    await _write_audit(current_user, "install_skill_zip", skill_id, {"filename": file.filename})
    return {"ok": True, "skill_id": skill_id, "message": "Skill installed and registry reloaded"}
