"""
Admin: Permission Matrix (read-only)

The PRD defines a role-feature matrix. The frontend renders this matrix in Admin UI.
To avoid frontend hard-coding drifting from backend reality, we serve a canonical
matrix JSON here (display only).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.models import User
from app.security.deps import require_admin

router = APIRouter(prefix="/admin/permissions", tags=["admin-permissions"])


@router.get("")
async def get_permission_matrix(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    """
    Returns a display-only permission matrix aligned to PRD §3.2 (V3.0).

    This endpoint does not enforce permissions itself; real authorization is enforced
    at each API route. The goal is to provide a single source of truth for UI display.
    """
    roles = [
        {"id": "executor", "label": "执行员"},
        {"id": "reviewer", "label": "审核员"},
        {"id": "finance", "label": "财务员"},
        {"id": "admin", "label": "系统管理员"},
    ]

    # Keep this list consistent with PRD §3.2; it can be extended as platform evolves.
    features = [
        {"id": "project_create", "label": "创建项目"},
        {"id": "project_delete", "label": "删除项目"},
        {"id": "asset_upload", "label": "上传素材（Excel/图片/云相册）"},
        {"id": "design_bind", "label": "设计图拖拽绑定"},
        {"id": "annotation_canvas", "label": "标注画板操作"},
        {"id": "trash_soft_delete", "label": "废片清空（软删除）"},
        {"id": "submit_review", "label": "提交审核"},
        {"id": "review_approve_reject", "label": "审核通过/驳回"},
        {"id": "ppt_view", "label": "查看结案PPT"},
        {"id": "ppt_download", "label": "下载PPT"},
        {"id": "receipt_match_view", "label": "查看凭据配对详情"},
        {"id": "ppt_template_admin", "label": "管理PPT模板"},
        {"id": "ai_threshold_admin", "label": "配置AI阈值"},
        {"id": "user_admin", "label": "用户管理"},
        {"id": "experience_admin", "label": "经验层管理台"},
        {"id": "skill_toggle_admin", "label": "Skill启用/禁用"},
        {"id": "audit_log_view", "label": "查看审计日志（脱敏版）"},
        {"id": "monitoring_view", "label": "查看系统监控指标"},
    ]

    # Display-only matrix derived from PRD (not from runtime checks)
    allow = {
        "project_create": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "project_delete": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "asset_upload": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "design_bind": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "annotation_canvas": {"executor": True, "reviewer": True, "finance": False, "admin": True},
        "trash_soft_delete": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "submit_review": {"executor": True, "reviewer": False, "finance": False, "admin": True},
        "review_approve_reject": {"executor": False, "reviewer": True, "finance": False, "admin": True},
        "ppt_view": {"executor": True, "reviewer": True, "finance": True, "admin": True},
        "ppt_download": {"executor": True, "reviewer": True, "finance": True, "admin": True},
        "receipt_match_view": {"executor": True, "reviewer": True, "finance": True, "admin": True},
        "ppt_template_admin": {"executor": False, "reviewer": False, "finance": False, "admin": True},
        "ai_threshold_admin": {"executor": False, "reviewer": False, "finance": False, "admin": True},
        "user_admin": {"executor": False, "reviewer": False, "finance": False, "admin": True},
        "experience_admin": {"executor": False, "reviewer": False, "finance": False, "admin": True},
        "skill_toggle_admin": {"executor": False, "reviewer": False, "finance": False, "admin": True},
        "audit_log_view": {"executor": True, "reviewer": True, "finance": False, "admin": True},
        "monitoring_view": {"executor": False, "reviewer": False, "finance": False, "admin": True},
    }

    return {"roles": roles, "features": features, "allow": allow, "version": "PRD-V3.0"}

