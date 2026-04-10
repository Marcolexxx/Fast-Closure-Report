from __future__ import annotations

import hashlib
import logging
import os
import shutil
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_engine
from app.models import Project, ProjectFile, ProjectStatus, ReviewAction, ReviewLog, User, UserRole
from app.security.deps import get_current_user
from app.security.file_validation import validate_upload

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)

ALLOWED_TYPES: dict[str, str] = {
    "xlsx": "excel", "xls": "excel", "csv": "excel",
    "jpg": "image", "jpeg": "image", "png": "image",
    "heic": "image", "webp": "image",
    "pdf": "pdf",
    "zip": "zip",
}


@lru_cache(maxsize=1)
def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ReviewAction_(BaseModel):
    action: str      # approve | reject
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_dept(project: Project, user: User) -> None:
    """Row-level isolation: non-admin users can only access their dept."""
    if user.role == UserRole.ADMIN.value:
        return
    if project.department_id and project.department_id != user.department_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _project_dict(p: Project) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "creator_id": p.creator_id,
        "department_id": p.department_id,
        "task_id": p.task_id,
        "pptx_path": p.pptx_path,
        "reject_count": p.reject_count,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_projects(
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with _sm()() as session:
        q = select(Project).where(Project.is_deleted == False)  # noqa: E712
        if current_user.role != UserRole.ADMIN.value:
            q = q.where(Project.department_id == current_user.department_id)
        if status_filter:
            q = q.where(Project.status == status_filter)
        q = q.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(q)).scalars().all()
    return {"items": [_project_dict(p) for p in rows], "total": len(rows)}


@router.post("", status_code=201)
async def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with _sm()() as session:
        project = Project(
            name=body.name,
            description=body.description,
            status=ProjectStatus.DRAFT.value,
            creator_id=current_user.id,
            department_id=current_user.department_id,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return _project_dict(project)


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with _sm()() as session:
        project = await session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    _check_dept(project, current_user)
    return _project_dict(project)


@router.patch("/{project_id}/review")
async def review_project(
    project_id: str,
    body: ReviewAction_,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.role not in (UserRole.REVIEWER.value, UserRole.ADMIN.value):
        raise HTTPException(status_code=403, detail="Only Reviewer/Admin can review")

    if body.action == "reject" and (not body.comment or len(body.comment.strip()) < 10):
        raise HTTPException(status_code=422, detail="Reject reason must be ≥10 characters")

    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        _check_dept(project, current_user)

        if project.status != ProjectStatus.PENDING_REVIEW.value:
            raise HTTPException(status_code=409, detail=f"Cannot review project in '{project.status}' status")

        if body.action == "approve":
            project.status = ProjectStatus.APPROVED.value
        elif body.action == "reject":
            project.status = ProjectStatus.REJECTED.value
            project.reject_count = Project.reject_count + 1
        else:
            raise HTTPException(status_code=422, detail="action must be 'approve' or 'reject'")

        log = ReviewLog(
            project_id=project_id,
            reviewer_id=current_user.id,
            action=body.action,
            comment=body.comment,
        )
        session.add(log)
        await session.commit()
        await session.refresh(project)
    return _project_dict(project)


@router.post("/{project_id}/submit-review")
async def submit_for_review(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.creator_id != current_user.id and current_user.role != UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail="Only project creator can submit")
        if project.status not in (ProjectStatus.DRAFT.value, ProjectStatus.REJECTED.value):
            raise HTTPException(status_code=409, detail="Project is not in a submittable state")

        project.status = ProjectStatus.PENDING_REVIEW.value
        log = ReviewLog(
            project_id=project_id,
            reviewer_id=current_user.id,
            action=ReviewAction.SUBMIT.value,
        )
        session.add(log)
        await session.commit()
        await session.refresh(project)
    return _project_dict(project)


@router.get("/{project_id}/files")
async def list_files(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        _check_dept(project, current_user)
        files = (
            await session.execute(
                select(ProjectFile)
                .where(ProjectFile.project_id == project_id, ProjectFile.is_deleted == False)  # noqa
            )
        ).scalars().all()
    return {
        "items": [
            {
                "id": f.id,
                "original_name": f.original_name,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "sha256": f.sha256,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ]
    }


from fastapi.responses import FileResponse

@router.get("/{project_id}/download-result")
async def download_result(
    project_id: str,
    current_user: User = Depends(get_current_user),
):
    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        _check_dept(project, current_user)
        
        if not project.pptx_path or not os.path.exists(project.pptx_path):
            raise HTTPException(status_code=404, detail="Result PPTX not found")
            
        filename = f"Report_{project.name}.pptx".replace(" ", "_")
        return FileResponse(
            path=project.pptx_path, 
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

@router.post("/{project_id}/files")
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()

    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        _check_dept(project, current_user)

    # --- Validate extension + MIME ---
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail=f"File type '{ext}' not allowed")

    content = await file.read()
    file_type = ALLOWED_TYPES[ext]

    # validate_upload checks magic bytes for images/pdf/zip
    try:
        validate_upload(content, ext)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))

    # --- Content addressing ---
    sha256 = hashlib.sha256(content).hexdigest()
    storage_root = settings.file_storage_root
    dest_dir = os.path.join(storage_root, "projects", project_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{sha256[:8]}_{file.filename}")

    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as fp:
            fp.write(content)

    async with _sm()() as session:
        record = ProjectFile(
            project_id=project_id,
            original_name=file.filename or "",
            file_type=file_type,
            mime_type=file.content_type or "",
            sha256=sha256,
            storage_path=dest_path,
            file_size=len(content),
            uploaded_by=current_user.id,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

    return {
        "id": record.id,
        "sha256": sha256,
        "file_type": file_type,
        "file_size": record.file_size,
        "original_name": record.original_name,
        "storage_path": dest_path,
    }

class UploadInit(BaseModel):
    filename: str
    file_size: int
    total_chunks: int
    file_hash: str

@router.post("/{project_id}/files/init")
async def init_upload(
    project_id: str,
    body: UploadInit,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    upload_id = body.file_hash
    temp_dir = os.path.join(settings.file_storage_root, "temp_uploads", upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    uploaded_chunks = []
    for i in range(body.total_chunks):
        if os.path.exists(os.path.join(temp_dir, str(i))):
            uploaded_chunks.append(i)
            
    return {
        "upload_id": upload_id,
        "uploaded_chunks": uploaded_chunks
    }

from fastapi import Form

@router.post("/{project_id}/files/chunk")
async def upload_chunk(
    project_id: str,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    temp_dir = os.path.join(settings.file_storage_root, "temp_uploads", upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    chunk_path = os.path.join(temp_dir, str(chunk_index))
    content = await file.read()
    with open(chunk_path, "wb") as f:
        f.write(content)
        
    return {"success": True}

class UploadComplete(BaseModel):
    upload_id: str
    filename: str
    file_size: int
    total_chunks: int

@router.post("/{project_id}/files/complete")
async def complete_upload(
    project_id: str,
    body: UploadComplete,
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    async with _sm()() as session:
        project = await session.get(Project, project_id)
        if not project or project.is_deleted:
            raise HTTPException(status_code=404, detail="Project not found")
        _check_dept(project, current_user)
        
    temp_dir = os.path.join(settings.file_storage_root, "temp_uploads", body.upload_id)
    merged_path = os.path.join(temp_dir, "merged")
    
    try:
        with open(merged_path, "wb") as outfile:
            for i in range(body.total_chunks):
                chunk_file = os.path.join(temp_dir, str(i))
                if not os.path.exists(chunk_file):
                    raise HTTPException(status_code=400, detail=f"Missing chunk {i}")
                with open(chunk_file, "rb") as infile:
                    outfile.write(infile.read())
                    
        with open(merged_path, "rb") as f:
            content = f.read()
            
        ext = (body.filename or "").rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_TYPES:
            raise HTTPException(status_code=415, detail=f"File type '{ext}' not allowed")
            
        try:
            validate_upload(content, ext)
        except ValueError as exc:
            raise HTTPException(status_code=415, detail=str(exc))
            
        file_type = ALLOWED_TYPES[ext]
        sha256 = hashlib.sha256(content).hexdigest()
        
        dest_dir = os.path.join(settings.file_storage_root, "projects", project_id)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, f"{sha256[:8]}_{body.filename}")
        
        if not os.path.exists(dest_path):
            shutil.copyfile(merged_path, dest_path)
            
        async with _sm()() as session:
            record = ProjectFile(
                project_id=project_id,
                original_name=body.filename,
                file_type=file_type,
                mime_type="",
                sha256=sha256,
                storage_path=dest_path,
                file_size=len(content),
                uploaded_by=current_user.id,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            
        return {
            "id": record.id,
            "sha256": sha256,
            "file_type": file_type,
            "file_size": record.file_size,
            "original_name": record.original_name,
            "storage_path": dest_path,
        }
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
