import time
import uuid
from fastapi import Request
from app.core.ai_logging import log_event

async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    try:
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        log_event(
            "request_completed",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event(
            "request_failed",
            request_id=request_id,
            error=str(e),
            duration_ms=duration_ms,
        )
        raise
