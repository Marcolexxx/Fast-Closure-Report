from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    DECIMAL,
    JSON,
    Float,
)
from sqlalchemy.dialects.postgresql import JSONB
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class UserRole(str, enum.Enum):
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    FINANCE = "finance"
    ADMIN = "admin"


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    APPROVED = "approved"


class ReviewAction(str, enum.Enum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# User & Auth
# ---------------------------------------------------------------------------

class User(AsyncAttrs, Base):
    __tablename__ = "User"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(256), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), default=UserRole.EXECUTOR.value)
    department_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="creator")
    review_logs: Mapped[list["ReviewLog"]] = relationship(back_populates="reviewer")


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(AsyncAttrs, Base):
    __tablename__ = "Project"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DRAFT.value, index=True)
    creator_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("User.id"), nullable=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # Linked task (the active Agent task for this project)
    task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Output artifacts
    pptx_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pptx_version: Mapped[int] = mapped_column(Integer, default=0)

    # Review tracking
    reject_count: Mapped[int] = mapped_column(Integer, default=0)

    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator: Mapped[Optional["User"]] = relationship(back_populates="projects")
    review_logs: Mapped[list["ReviewLog"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    files: Mapped[list["ProjectFile"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_Project_department_id_status", "department_id", "status"),
        Index("ix_Project_creator_id_created_at", "creator_id", "created_at"),
    )


class ProjectFile(AsyncAttrs, Base):
    """Uploaded file record — content-addressed by SHA256."""

    __tablename__ = "ProjectFile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)

    original_name: Mapped[str] = mapped_column(String(256))
    file_type: Mapped[str] = mapped_column(String(32))   # excel | image | pdf | zip
    mime_type: Mapped[str] = mapped_column(String(128), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    # Soft delete for recycle-bin feature (7-day recovery)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    uploaded_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="files")


class ReviewLog(AsyncAttrs, Base):
    __tablename__ = "ReviewLog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("User.id"), nullable=True)

    action: Mapped[str] = mapped_column(String(32))   # submit | approve | reject
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="review_logs")
    reviewer: Mapped[Optional["User"]] = relationship(back_populates="review_logs")


# ---------------------------------------------------------------------------
# PPT Templates
# ---------------------------------------------------------------------------

class PPTTemplate(AsyncAttrs, Base):
    __tablename__ = "PPTTemplate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(512))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Experience Layer — FeedbackEvent
# ---------------------------------------------------------------------------

class FeedbackEvent(AsyncAttrs, Base):
    """Captures HIL corrections for the Experience Layer (PatternMiner input)."""

    __tablename__ = "FeedbackEvent"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # FIX B3: Added idempotency_key column (was referenced in code but missing from model)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(256), unique=True, nullable=True, index=True)
    # FIX B6: Added ondelete=SET NULL so task deletion doesn't cascade-fail
    task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("AgentTask.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    skill_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Event types per PRD §8.3:
    # annotation_added | annotation_corrected | annotation_rejected |
    # receipt_matched_manually | excel_column_remapped |
    # quantity_override | classification_corrected
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # FIX B2: payload_json is bytes in MySQL — routes must encode strings before assignment
    payload_json: Mapped[bytes] = mapped_column(LargeBinary, default=b"{}")

    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_FeedbackEvent_skill_id_event_type", "skill_id", "event_type"),
    )


# ---------------------------------------------------------------------------
# Agent Core (unchanged from original)
# ---------------------------------------------------------------------------

class AgentTask(AsyncAttrs, Base):
    __tablename__ = "AgentTask"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)

    status: Mapped[TaskStatus] = mapped_column(String(32), default=TaskStatus.CREATED.value)
    current_step: Mapped[int] = mapped_column(default=0)
    max_steps: Mapped[int] = mapped_column(default=50)
    total_tokens_used: Mapped[int] = mapped_column(default=0)
    trace_id: Mapped[str] = mapped_column(String(128), default="-")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    context: Mapped[Optional["TaskContext"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", uselist=False
    )
    checkpoints: Mapped[list["TaskCheckpoint"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list["ToolCallLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_AgentTask_user_id_status_created_at", "user_id", "status", "created_at"),
    )


class TaskContext(AsyncAttrs, Base):
    __tablename__ = "TaskContext"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("AgentTask.id"), unique=True)

    context_json: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    schema_version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task: Mapped["AgentTask"] = relationship(back_populates="context")


class TaskCheckpoint(AsyncAttrs, Base):
    __tablename__ = "TaskCheckpoint"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("AgentTask.id"))

    step_index: Mapped[int] = mapped_column(default=0)
    step_name: Mapped[str] = mapped_column(String(128), default="")
    tool_name: Mapped[str] = mapped_column(String(128), default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(String(128), default="")
    schema_version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["AgentTask"] = relationship(back_populates="checkpoints")

    __table_args__ = (
        Index("ix_TaskCheckpoint_task_id_step_index", "task_id", "step_index"),
    )


class ToolCallLogStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ToolCallLog(AsyncAttrs, Base):
    __tablename__ = "ToolCallLog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("AgentTask.id"), index=True)

    tool_name: Mapped[str] = mapped_column(String(128), default="")
    input_digest: Mapped[str] = mapped_column(String(64), default="")
    input_summary: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")

    duration_ms: Mapped[int] = mapped_column(default=0)
    error_type: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(32), default=ToolCallLogStatus.SUCCESS.value)
    trace_id: Mapped[str] = mapped_column(String(128), default="-")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["AgentTask"] = relationship(back_populates="tool_calls")


class SkillConfig(AsyncAttrs, Base):
    __tablename__ = "SkillConfig"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    config_key: Mapped[str] = mapped_column(String(128))
    config_value: Mapped[str] = mapped_column(Text, default="true")
    updated_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("skill_id", "config_key", name="uq_SkillConfig_skill_id_config_key"),
    )


class TaskHilState(AsyncAttrs, Base):
    __tablename__ = "TaskHilState"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("AgentTask.id"), unique=True)

    ui_component: Mapped[str] = mapped_column(String(128), default="")
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    prefill_json: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    submit_json: Mapped[bytes] = mapped_column(LargeBinary, default=b"")

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task: Mapped["AgentTask"] = relationship()


# ---------------------------------------------------------------------------
# System Configuration (Admin Panel)
# ---------------------------------------------------------------------------

class SystemConfig(AsyncAttrs, Base):
    __tablename__ = "SystemConfig"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    namespace: Mapped[str] = mapped_column(String(64), index=True)
    config_key: Mapped[str] = mapped_column(String(128))
    config_value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("namespace", "config_key", name="uq_SystemConfig_ns_key"),
    )


# ---------------------------------------------------------------------------
# Audit Log (Admin Actions)
# ---------------------------------------------------------------------------

class AuditLog(AsyncAttrs, Base):
    __tablename__ = "AuditLog"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    detail_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Skill A Domain Models
# ---------------------------------------------------------------------------

class Item(AsyncAttrs, Base):
    __tablename__ = "Item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[Optional[str]] = mapped_column(String(128))
    target_qty: Mapped[int] = mapped_column(default=0)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    
    design_image_path: Mapped[Optional[str]] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssetImage(AsyncAttrs, Base):
    __tablename__ = "AssetImage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    
    asset_type: Mapped[str] = mapped_column(String(32), default="unknown")
    original_path: Mapped[str] = mapped_column(String(512))
    thumbnail_path: Mapped[str] = mapped_column(String(512))
    
    thumb_scale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_offset_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumb_offset_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    file_size: Mapped[int] = mapped_column(default=0)
    mime_type: Mapped[str] = mapped_column(String(128))
    sha256_hash: Mapped[str] = mapped_column(String(64), unique=True)
    
    exif_normalized: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    source: Mapped[str] = mapped_column(String(32), default="upload")
    upload_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    is_ai_failed: Mapped[bool] = mapped_column(Boolean, default=False)


class Annotation(AsyncAttrs, Base):
    __tablename__ = "Annotation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    image_id: Mapped[str] = mapped_column(String(36), ForeignKey("AssetImage.id"), index=True)
    item_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("Item.id"), nullable=True, index=True)
    
    type: Mapped[str] = mapped_column(String(32), default="rect")
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    w: Mapped[float] = mapped_column(Float, default=0.0)
    h: Mapped[float] = mapped_column(Float, default=0.0)
    
    geometry_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    source: Mapped[str] = mapped_column(String(32), default="ai")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Receipt(AsyncAttrs, Base):
    __tablename__ = "Receipt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    asset_image_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("AssetImage.id"))
    
    receipt_type: Mapped[str] = mapped_column(String(32), default="payment", index=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    txn_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    merchant_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    invoice_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    ocr_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    low_confidence_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReceiptMatch(AsyncAttrs, Base):
    __tablename__ = "ReceiptMatch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("Receipt.id"), nullable=True)
    invoice_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("Receipt.id"), nullable=True)
    
    match_type: Mapped[str] = mapped_column(String(32), default="auto_exact")
    amount_diff: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=Decimal("0.00"))
    date_diff_days: Mapped[int] = mapped_column(default=0)
    
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuantityCheckResult(AsyncAttrs, Base):
    __tablename__ = "QuantityCheckResult"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("Item.id"))
    
    target_qty: Mapped[int] = mapped_column(default=0)
    actual_qty: Mapped[int] = mapped_column(default=0)
    delta_pct: Mapped[float] = mapped_column(Float, default=0.0)
    
    status: Mapped[str] = mapped_column(String(32), default="pass")
    override_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CloudAlbumFetch(AsyncAttrs, Base):
    __tablename__ = "CloudAlbumFetch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    
    source_url: Mapped[str] = mapped_column(String(512))
    platform: Mapped[str] = mapped_column(String(64), default="")
    
    total_count: Mapped[int] = mapped_column(default=0)
    downloaded_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)
    
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ProjectSnapshot(AsyncAttrs, Base):
    __tablename__ = "ProjectSnapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("Project.id"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    
    pptx_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    triggered_by_step: Mapped[Optional[str]] = mapped_column(String(128))


class PatternReport(AsyncAttrs, Base):
    __tablename__ = "PatternReport"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    analysis_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    sample_count: Mapped[int] = mapped_column(default=0)
    suggestions_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LibrarianKnowledge(AsyncAttrs, Base):
    __tablename__ = "LibrarianKnowledge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("LibrarianKnowledge.id"), nullable=True, index=True)
    
    summary: Mapped[str] = mapped_column(Text)
    keywords: Mapped[str] = mapped_column(Text)
    intent_tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    knowledge_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    parent: Mapped[Optional["LibrarianKnowledge"]] = relationship("LibrarianKnowledge", backref="children", remote_side=[id])


class PromptTuningHistory(AsyncAttrs, Base):
    __tablename__ = "PromptTuningHistory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    suggestion_summary: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(32), default="accepted")
    applied_diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentBranch(AsyncAttrs, Base):
    __tablename__ = "AgentBranch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    base_prompt_version: Mapped[str] = mapped_column(String(64))
    
    prompt_overrides: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_param_overrides: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    usage_count: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
