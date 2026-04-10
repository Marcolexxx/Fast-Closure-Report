from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI

from app.config import get_settings
from app.db import test_db_connection
from app.db_init import init_task_schema
from app.logging_setup import configure_logging
from app.middleware_trace_id import trace_id_middleware
from app.routes.tasks import router as tasks_router
from app.routes.tasks_create import router as tasks_create_router
from app.routes.ws_task import router as ws_task_router
from app.routes.admin_skills import router as admin_skills_router
from app.routes.admin_tools import router as admin_tools_router
from app.routes.admin_permissions import router as admin_permissions_router
from app.routes.hil import router as hil_router
from app.routes.auth import router as auth_router
from app.routes.projects import router as projects_router
from app.routes.experience import router as experience_router
from app.routes.admin_config import router as admin_config_router
from app.routes.admin_users import router as admin_users_router
from app.routes.ppt_templates import router as ppt_templates_router
from app.skills.registry import get_skill_registry_service


configure_logging()
logger = logging.getLogger(__name__)


@dataclass
class HealthState:
    redis_ok: bool = False
    mysql_ok: bool = False
    redis_error: Optional[str] = None
    mysql_error: Optional[str] = None


def _parse_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port
    if not host or port is None:
        raise ValueError(f"Invalid url: {url}")
    return host, int(port)


async def _check_tcp(host: str, port: int, timeout_s: float = 1.5) -> bool:
    try:
        conn = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(conn, timeout=timeout_s)
        writer.close()
        return True
    except Exception:
        return False


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI-Copilot Platform", version="3.0.0")
app.middleware("http")(trace_id_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(tasks_create_router)
app.include_router(ws_task_router)
app.include_router(admin_skills_router)
app.include_router(admin_tools_router)
app.include_router(admin_permissions_router)
app.include_router(admin_config_router)
app.include_router(admin_users_router)
app.include_router(ppt_templates_router)
app.include_router(hil_router)
app.include_router(experience_router)
_health_state = HealthState()


@app.on_event("startup")
async def _startup_checks() -> None:
    settings = get_settings()

    # Ensure task tables exist (M1: still using `create_all`; later will switch to Alembic).
    await init_task_schema()

    # Self-healing Admin Seed
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from app.db import get_engine
        from app.models import User, UserRole
        from app.security.auth import hash_password
        from sqlalchemy import select

        async with async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)() as session:
            result = await session.execute(select(User).where(User.username == "admin"))
            admin = result.scalars().first()
            if not admin:
                logger.info("seed_admin_creating")
                admin = User(username="admin", role=UserRole.ADMIN.value)
                admin.hashed_password = hash_password("admin123")
                session.add(admin)
                await session.commit()
                logger.info("seed_admin_created")
            else:
                logger.info("seed_admin_already_exists")
    except Exception as e:
        logger.error(f"seed_admin_fatal_error: {e}")

    # Scan skills and register tools (M1: in-memory registry + ToolRegistry).
    await get_skill_registry_service().load_all()

    # Register built-in tools used for M1 dev/testing.
    # Real Skill tools will be loaded by Skill Registry in later phases.
    import app.tools.builtin_mock  # noqa: F401

    # Redis (TCP-level check)
    try:
        redis_host, redis_port = _parse_host_port(settings.redis_url)
        _health_state.redis_ok = await _check_tcp(redis_host, redis_port)
    except Exception as e:
        _health_state.redis_ok = False
        _health_state.redis_error = str(e)

    # MySQL (real query check)
    try:
        ok, err = await test_db_connection(timeout_s=2.0)
        _health_state.mysql_ok = ok
        _health_state.mysql_error = err
    except Exception as e:
        _health_state.mysql_ok = False
        _health_state.mysql_error = str(e)

    logger.info(
        "startup_checks_complete",
        extra={
            "redis_ok": _health_state.redis_ok,
            "mysql_ok": _health_state.mysql_ok,
        },
    )


def _health_payload() -> dict:
    # Keep M0 requirement: always return 200 while surfacing warnings.
    return {
        "status": "ok",
        "redis_ok": _health_state.redis_ok,
        "mysql_ok": _health_state.mysql_ok,
        "redis_error": _health_state.redis_error,
        "mysql_error": _health_state.mysql_error,
    }


@app.get("/health")
async def health() -> dict:
    return _health_payload()


@app.get("/api/health")
async def api_health() -> dict:
    return _health_payload()


@app.get("/")
async def root() -> dict:
    return {"service": "ai-copilot-platform", "status": "ok"}


