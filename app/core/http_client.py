"""Asynchronous HTTP Client Manager with Connection Pooling and Lifecycle Management."""
import logging
from typing import Optional
import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.core.http_client")

# Global singleton async client instance
_async_client: Optional[httpx.AsyncClient] = None


def get_async_client() -> httpx.AsyncClient:
    """Return the global shared httpx.AsyncClient instance.
    
    If not yet initialized (e.g. in test fixtures or CLI scripts), lazily instantiates a fallback client.
    """
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = create_async_client()
    return _async_client


def create_async_client(
    timeout_seconds: Optional[float] = None,
    max_connections: Optional[int] = None,
    max_keepalive: Optional[int] = None
) -> httpx.AsyncClient:
    """Instantiate a new httpx.AsyncClient configured with connection pooling limits."""
    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else settings.DEFAULT_TIMEOUT_SECONDS
    max_conn = max_connections if max_connections is not None else (settings.MAX_CONCURRENCY * 5)
    max_keep = max_keepalive if max_keepalive is not None else 20

    limits = httpx.Limits(
        max_connections=max_conn,
        max_keepalive_connections=max_keep,
        keepalive_expiry=30.0
    )

    client_timeout = httpx.Timeout(
        timeout=timeout,
        connect=5.0,
        read=timeout,
        write=timeout,
        pool=10.0
    )

    logger.debug(f"Created httpx.AsyncClient [max_conn={max_conn}, keepalive={max_keep}, timeout={timeout}s]")
    return httpx.AsyncClient(
        limits=limits,
        timeout=client_timeout,
        follow_redirects=True,
        http2=False
    )


async def init_async_client() -> httpx.AsyncClient:
    """Initialize the global shared AsyncClient during application startup."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = create_async_client()
        logger.info("Initialized shared httpx.AsyncClient connection pool")
    return _async_client


async def close_async_client() -> None:
    """Cleanly close the global shared AsyncClient and release connections during shutdown."""
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
        logger.info("Closed shared httpx.AsyncClient connection pool")
    _async_client = None
