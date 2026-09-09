"""Asynchronous HTTP Dispatcher and Execution Service with High-Precision Telemetry."""
import logging
import time
from typing import Any, Dict, Optional
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.http_client import get_async_client
from app.models.schemas.execution import (
    DirectExecutionRequest,
    EndpointExecutionRequest,
    ExecutionOptions,
    ExecutionResultResponse
)
from app.models.schemas.request_config import (
    DirectRequestBuilderRequest,
    RequestCompileOverride
)
from app.services.project_service import ProjectService
from app.services.endpoint_service import EndpointService
from app.services.request_builder_service import RequestBuilderService
from app.utils.preflight_validator import execute_preflight_check
from app.utils.telemetry_extractor import (
    extract_cookies,
    extract_redirect_history,
    parse_response_payload,
    classify_network_exception
)

logger = logging.getLogger("app.services.http_dispatcher")
settings = get_settings()


class HttpDispatcherService:
    """Service responsible for executing HTTP requests asynchronously with connection pooling and telemetry."""

    @classmethod
    async def dispatch_httpx_request(
        cls,
        request: httpx.Request,
        options: ExecutionOptions
    ) -> ExecutionResultResponse:
        """Dispatch a prepared httpx.Request and return a detailed ExecutionResultResponse with high-precision telemetry."""
        start_time = time.perf_counter()
        url_str = str(request.url)
        method_str = request.method

        logger.info(f"Dispatching [{method_str}] {url_str} (timeout={options.timeout_seconds}s, redirects={options.follow_redirects})")

        # Configure request-level timeout via httpx request extensions
        timeout = httpx.Timeout(options.timeout_seconds, connect=min(5.0, options.timeout_seconds))
        request.extensions["timeout"] = timeout.as_dict()

        # Select client based on SSL verification requirement
        client: httpx.AsyncClient
        is_transient_client = False

        if not options.verify_ssl:
            # Create a dedicated non-verifying client if SSL verification is disabled
            client = httpx.AsyncClient(
                verify=False,
                timeout=timeout,
                follow_redirects=options.follow_redirects
            )
            is_transient_client = True
        else:
            client = get_async_client()

        try:
            # Send request asynchronously
            response = await client.send(
                request,
                follow_redirects=options.follow_redirects
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract telemetry components
            cookies = extract_cookies(response)
            redirect_history = extract_redirect_history(response)
            redirect_count = len(response.history)
            parsed_body, is_binary, raw_b64, content_type = parse_response_payload(response)

            logger.info(
                f"Completed [{method_str}] {url_str} -> HTTP {response.status_code} "
                f"in {elapsed_ms:.3f}ms (redirects: {redirect_count})"
            )
            return ExecutionResultResponse.from_httpx_response(
                response=response,
                elapsed_ms=elapsed_ms,
                redirect_count=redirect_count,
                redirect_history=redirect_history,
                cookies=cookies,
                body=parsed_body,
                is_binary=is_binary,
                raw_body_base64=raw_b64,
                content_type=content_type
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            error_detail = classify_network_exception(exc, url_str, options.timeout_seconds)
            logger.warning(f"{error_detail.error_type} on [{method_str}] {url_str}: {error_detail.message}")

            return ExecutionResultResponse(
                url=url_str,
                method=method_str,
                status_code=None,
                status_text=None,
                headers={},
                cookies={},
                body=None,
                is_binary=False,
                raw_body_base64=None,
                is_success=False,
                is_redirect=False,
                is_client_error=False,
                is_server_error=False,
                http_version="HTTP/1.1",
                elapsed_ms=round(elapsed_ms, 3),
                redirect_count=0,
                redirect_history=[],
                content_length=0,
                content_type=None,
                error=error_detail.message,
                error_type=error_detail.error_type,
                error_detail=error_detail
            )

        finally:
            if is_transient_client:
                await client.aclose()

    @classmethod
    async def dispatch_direct(cls, req: DirectExecutionRequest) -> ExecutionResultResponse:
        """Compile and asynchronously dispatch an ad-hoc HTTP request."""
        # 1. Pre-flight validation
        preflight = execute_preflight_check(
            base_url=req.base_url,
            path=req.path,
            method=req.method.value,
            headers=req.headers,
            path_params=req.path_params,
            body=req.body,
            body_type=req.body_type.value
        )
        if not preflight.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Pre-flight validation failed. Request blocked from network dispatch.",
                    "errors": preflight.errors,
                    "warnings": preflight.warnings
                }
            )

        # 2. Compile request
        build_dto = DirectRequestBuilderRequest(
            base_url=req.base_url,
            method=req.method,
            path=req.path,
            path_params=req.path_params,
            query_params=req.query_params,
            headers=req.headers,
            body_type=req.body_type,
            body=req.body
        )
        httpx_req, _ = RequestBuilderService.compile_direct_request(build_dto)

        # 3. Dispatch
        return await cls.dispatch_httpx_request(httpx_req, req.options)

    @classmethod
    async def dispatch_endpoint(
        cls,
        project_id: int,
        endpoint_id: int,
        execution_req: EndpointExecutionRequest,
        db: Session
    ) -> ExecutionResultResponse:
        """Compile and asynchronously dispatch a stored endpoint configuration with runtime overrides."""
        project = ProjectService.get_project_by_id(db, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project #{project_id} not found"
            )

        endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint #{endpoint_id} not found"
            )

        if endpoint.project_id != project.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Endpoint #{endpoint_id} does not belong to Project #{project_id}"
            )

        # 1. Compile endpoint request
        override_dto = RequestCompileOverride(
            path_params=execution_req.path_params,
            query_params=execution_req.query_params,
            headers=execution_req.headers,
            body_type=execution_req.body_type,
            body=execution_req.body
        )
        httpx_req, compiled = RequestBuilderService.compile_endpoint_request(
            project=project,
            endpoint=endpoint,
            overrides=override_dto
        )

        # 2. Pre-flight audit on compiled request
        preflight = execute_preflight_check(
            base_url=compiled.url.split("?")[0],
            path="",
            method=compiled.method,
            headers=compiled.headers,
            path_params={},
            body=compiled.body,
            body_type=compiled.body_type.value if compiled.body_type else "empty"
        )
        if not preflight.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Pre-flight validation failed for endpoint configuration.",
                    "errors": preflight.errors,
                    "warnings": preflight.warnings
                }
            )

        # 3. Dispatch
        return await cls.dispatch_httpx_request(httpx_req, execution_req.options)
