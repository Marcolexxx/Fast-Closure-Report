from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response

from app.config import get_settings
from app.logging_setup import trace_id_var


async def trace_id_middleware(request: Request, call_next: Callable[[Request], Response]) -> Response:
    settings = get_settings()
    incoming = request.headers.get(settings.trace_header_name)
    trace_id = incoming or str(uuid.uuid4())

    token = trace_id_var.set(trace_id)
    try:
        response = await call_next(request)
        # Ensure frontend/backends can correlate logs & tasks.
        response.headers[settings.trace_header_name] = trace_id
        return response
    finally:
        trace_id_var.reset(token)

