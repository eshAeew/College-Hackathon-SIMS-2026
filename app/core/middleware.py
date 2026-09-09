"""Request correlation ID and request/response logging middleware."""
import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx_var

logger = logging.getLogger("app.middleware")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware attaching unique correlation ID and logging execution latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate Request ID
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Set context variable for structured logging
        token = request_id_ctx_var.set(request_id)
        start_time = time.perf_counter()

        logger.info(f"Incoming Request: {request.method} {request.url.path}")

        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.2f}"

            logger.info(
                f"Completed Request: {request.method} {request.url.path} "
                f"Status: {response.status_code} in {elapsed_ms:.2f}ms"
            )
            return response
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                f"Unhandled Exception: {request.method} {request.url.path} "
                f"after {elapsed_ms:.2f}ms - {str(exc)}",
                exc_info=True
            )
            raise exc
        finally:
            request_id_ctx_var.reset(token)
