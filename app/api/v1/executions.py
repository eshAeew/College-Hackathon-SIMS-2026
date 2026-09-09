"""API Router for Asynchronous Request Execution and Telemetry."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.http_client import get_async_client
from app.models.schemas.execution import (
    DirectExecutionRequest,
    EndpointExecutionRequest,
    ExecutionResultResponse,
    ClientInfoResponse
)
from app.models.schemas.response import StandardResponse
from app.services.http_dispatcher import HttpDispatcherService

router = APIRouter(tags=["Execution Engine"])
settings = get_settings()


@router.post(
    "/executions/dispatch",
    response_model=StandardResponse[ExecutionResultResponse],
    status_code=status.HTTP_200_OK,
    summary="Dispatch Ad-hoc HTTP Request",
    description="Asynchronously dispatches an ad-hoc HTTP request with connection pooling, configurable timeout, and redirects."
)
async def dispatch_direct_request(
    request: DirectExecutionRequest
):
    """Execute an arbitrary HTTP request asynchronously and return network telemetry and response data."""
    result = await HttpDispatcherService.dispatch_direct(request)
    return StandardResponse(
        success=True,
        data=result,
        message=f"Dispatched [{result.method}] {result.url} (Status: {result.status_code or 'Network Error'})"
    )


@router.post(
    "/projects/{project_id}/endpoints/{endpoint_id}/execute",
    response_model=StandardResponse[ExecutionResultResponse],
    status_code=status.HTTP_200_OK,
    summary="Execute Stored Endpoint",
    description="Compiles and executes a saved project endpoint with optional runtime overrides and execution options."
)
async def execute_project_endpoint(
    project_id: int,
    endpoint_id: int,
    execution_req: EndpointExecutionRequest = EndpointExecutionRequest(),
    db: Session = Depends(get_db)
):
    """Compile and dispatch a registered endpoint within its project workspace context."""
    result = await HttpDispatcherService.dispatch_endpoint(project_id, endpoint_id, execution_req, db)
    return StandardResponse(
        success=True,
        data=result,
        message=f"Executed Endpoint #{endpoint_id} [{result.method}] {result.url} (Status: {result.status_code or 'Network Error'})"
    )


@router.get(
    "/executions/client-info",
    response_model=StandardResponse[ClientInfoResponse],
    summary="HTTP Client & Connection Pool Diagnostics",
    description="Returns metadata about the active shared HTTP client connection pool and execution settings."
)
async def get_client_info():
    """Retrieve shared HTTP connection pool metrics and configuration."""
    client = get_async_client()
    info = ClientInfoResponse(
        is_active=not client.is_closed,
        default_timeout=settings.DEFAULT_TIMEOUT_SECONDS,
        max_concurrency=settings.MAX_CONCURRENCY,
        max_keepalive=20,
        environment=settings.ENVIRONMENT
    )
    return StandardResponse(
        success=True,
        data=info,
        message="HTTP client connection pool is active"
    )
