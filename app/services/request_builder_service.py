"""Service for dynamically compiling, interpolating, and serializing executable HTTP requests."""
import json
import logging
import re
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List, Union
import httpx

from app.models.entities.project import Project
from app.models.entities.endpoint import Endpoint
from app.models.schemas.request_config import (
    BodyType,
    RequestCompileOverride,
    CompiledRequestResponse,
    DirectRequestBuilderRequest,
    PreflightValidationRequest,
    PreflightValidationReport,
)
from app.utils.preflight_validator import execute_preflight_check

logger = logging.getLogger("app.services.request_builder")


class RequestBuilderService:
    """Engine responsible for path variable resolution, header merging, body serialization, and httpx.Request compilation."""

    @staticmethod
    def resolve_path(path: str, path_params: Dict[str, Any]) -> str:
        """Replace URL path variable placeholders (e.g., {user_id}) with URL-encoded values.
        
        Raises:
            ValueError: If a declared path variable has no corresponding value in path_params.
        """
        if not path:
            return "/"

        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path

        # Find all {var_name} placeholders
        placeholders = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path)
        resolved_path = path

        for var_name in placeholders:
            if var_name not in path_params or path_params[var_name] is None or str(path_params[var_name]).strip() == "":
                raise ValueError(f"Missing required path parameter: '{var_name}' for path template '{path}'")
            
            raw_val = str(path_params[var_name])
            # URL-encode the path segment safely
            encoded_val = urllib.parse.quote(raw_val, safe="")
            resolved_path = resolved_path.replace(f"{{{var_name}}}", encoded_val)

        return resolved_path

    @staticmethod
    def encode_query_params(query_params: Dict[str, Any]) -> str:
        """Encode query parameters supporting primitives, booleans, and list/array sequences."""
        if not query_params:
            return ""

        processed_params: List[Tuple[str, str]] = []
        for key, val in query_params.items():
            if val is None:
                continue
            if isinstance(val, bool):
                processed_params.append((key, "true" if val else "false"))
            elif isinstance(val, (list, tuple, set)):
                for item in val:
                    processed_params.append((key, str(item)))
            else:
                processed_params.append((key, str(val)))

        return urllib.parse.urlencode(processed_params, doseq=True)

    @staticmethod
    def resolve_url(
        base_url: str,
        path: str,
        path_params: Dict[str, Any],
        query_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str]:
        """Combine base URL, resolved path, and query parameters into a full target URL.
        
        Returns:
            (full_url, resolved_path)
        """
        clean_base = base_url.strip().rstrip("/")
        resolved_path = RequestBuilderService.resolve_path(path, path_params)
        
        full_url = f"{clean_base}{resolved_path}"

        if query_params:
            query_str = RequestBuilderService.encode_query_params(query_params)
            if query_str:
                delimiter = "&" if "?" in full_url else "?"
                full_url = f"{full_url}{delimiter}{query_str}"

        return full_url, resolved_path

    @staticmethod
    def merge_headers(
        project_headers: Optional[Dict[str, str]] = None,
        endpoint_headers: Optional[Dict[str, str]] = None,
        override_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Case-insensitively merge project global headers, endpoint headers, and runtime overrides."""
        merged: Dict[str, str] = {
            "User-Agent": "API-Sentinel/1.0 (Automated Reliability Engine)"
        }
        
        # Track lowercase mapping to preserve canonical casing
        header_map: Dict[str, str] = {k.lower(): k for k in merged.keys()}

        def apply_layer(layer: Optional[Dict[str, str]]):
            if not layer:
                return
            for key, val in layer.items():
                if val is None:
                    continue
                lower_key = key.lower()
                # Remove prior casing if different
                if lower_key in header_map:
                    merged.pop(header_map[lower_key], None)
                merged[key] = str(val)
                header_map[lower_key] = key

        apply_layer(project_headers)
        apply_layer(endpoint_headers)
        apply_layer(override_headers)

        return merged

    @staticmethod
    def serialize_body(
        body: Optional[Any],
        body_type: BodyType,
        headers: Dict[str, str]
    ) -> Tuple[Optional[bytes], Optional[str], Optional[Any], Dict[str, str]]:
        """Serialize payload into bytes and preview string, setting appropriate Content-Type header."""
        updated_headers = dict(headers)
        has_content_type = any(k.lower() == "content-type" for k in updated_headers.keys())

        if body is None or body_type == BodyType.EMPTY:
            return None, None, None, updated_headers

        if body_type == BodyType.JSON:
            if not has_content_type:
                updated_headers["Content-Type"] = "application/json"
            
            if isinstance(body, (dict, list)):
                raw_str = json.dumps(body, indent=2)
                parsed_body = body
            elif isinstance(body, str):
                try:
                    parsed_body = json.loads(body)
                    raw_str = json.dumps(parsed_body, indent=2)
                except Exception:
                    parsed_body = body
                    raw_str = body
            else:
                parsed_body = str(body)
                raw_str = str(body)

            return raw_str.encode("utf-8"), raw_str, parsed_body, updated_headers

        elif body_type == BodyType.FORM_DATA:
            if not has_content_type:
                updated_headers["Content-Type"] = "application/x-www-form-urlencoded"

            if isinstance(body, dict):
                encoded_str = urllib.parse.urlencode(body)
                parsed_body = body
            else:
                encoded_str = str(body)
                parsed_body = body

            return encoded_str.encode("utf-8"), encoded_str, parsed_body, updated_headers

        elif body_type == BodyType.RAW_TEXT:
            if not has_content_type:
                updated_headers["Content-Type"] = "text/plain; charset=utf-8"

            raw_str = str(body)
            return raw_str.encode("utf-8"), raw_str, raw_str, updated_headers

        return None, None, None, updated_headers

    @staticmethod
    def generate_curl_command(
        method: str,
        url: str,
        headers: Dict[str, str],
        raw_body_preview: Optional[str]
    ) -> str:
        """Construct an executable cURL command equivalent to the compiled request."""
        parts = [f"curl -X {method.upper()} '{url}'"]
        for key, val in headers.items():
            parts.append(f"-H '{key}: {val}'")
        if raw_body_preview:
            # Escape single quotes for safe shell execution
            escaped_body = raw_body_preview.replace("'", "'\\''")
            parts.append(f"-d '{escaped_body}'")
        return " \\\n  ".join(parts)

    @classmethod
    def compile_direct_request(cls, req: DirectRequestBuilderRequest) -> Tuple[httpx.Request, CompiledRequestResponse]:
        """Compile a request directly from arbitrary specifications without database lookup."""
        method_str = req.method.value if hasattr(req.method, "value") else str(req.method).upper()
        
        full_url, resolved_path = cls.resolve_url(
            base_url=req.base_url,
            path=req.path,
            path_params=req.path_params,
            query_params=req.query_params
        )

        merged_headers = cls.merge_headers(
            project_headers=None,
            endpoint_headers=req.headers,
            override_headers=None
        )

        raw_bytes, raw_preview, parsed_body, final_headers = cls.serialize_body(
            body=req.body,
            body_type=req.body_type,
            headers=merged_headers
        )

        curl_cmd = cls.generate_curl_command(
            method=method_str,
            url=full_url,
            headers=final_headers,
            raw_body_preview=raw_preview
        )

        httpx_req = httpx.Request(
            method=method_str,
            url=full_url,
            headers=final_headers,
            content=raw_bytes
        )

        response_dto = CompiledRequestResponse(
            method=method_str,
            url=full_url,
            base_url=req.base_url.strip().rstrip("/"),
            resolved_path=resolved_path,
            headers=final_headers,
            query_params=req.query_params,
            path_params=req.path_params,
            body_type=req.body_type,
            body=parsed_body,
            raw_body_preview=raw_preview,
            curl_command=curl_cmd
        )

        return httpx_req, response_dto

    @classmethod
    def compile_endpoint_request(
        cls,
        project: Project,
        endpoint: Endpoint,
        overrides: Optional[RequestCompileOverride] = None
    ) -> Tuple[httpx.Request, CompiledRequestResponse]:
        """Compile an executable HTTP request combining Project workspace, Endpoint spec, and runtime overrides."""
        overrides = overrides or RequestCompileOverride()

        method_str = endpoint.method.upper()
        base_url = (overrides.base_url or project.base_url).strip().rstrip("/")

        # Merge path parameters
        merged_path_params = dict(endpoint.path_params)
        if overrides.path_params:
            merged_path_params.update(overrides.path_params)

        # Merge query parameters
        merged_query_params = dict(endpoint.query_params)
        if overrides.query_params:
            merged_query_params.update(overrides.query_params)

        # Resolve URL
        full_url, resolved_path = cls.resolve_url(
            base_url=base_url,
            path=endpoint.path,
            path_params=merged_path_params,
            query_params=merged_query_params
        )

        # Merge headers (Project -> Endpoint -> Override)
        final_headers = cls.merge_headers(
            project_headers=project.global_headers,
            endpoint_headers=endpoint.headers,
            override_headers=overrides.headers
        )

        # Determine effective body and body_type
        effective_body = overrides.body if overrides.body is not None else endpoint.body_schema
        effective_body_type = overrides.body_type or (BodyType.JSON if effective_body and effective_body != {} else BodyType.EMPTY)

        raw_bytes, raw_preview, parsed_body, final_headers = cls.serialize_body(
            body=effective_body,
            body_type=effective_body_type,
            headers=final_headers
        )

        curl_cmd = cls.generate_curl_command(
            method=method_str,
            url=full_url,
            headers=final_headers,
            raw_body_preview=raw_preview
        )

        httpx_req = httpx.Request(
            method=method_str,
            url=full_url,
            headers=final_headers,
            content=raw_bytes
        )

        response_dto = CompiledRequestResponse(
            method=method_str,
            url=full_url,
            base_url=base_url,
            resolved_path=resolved_path,
            headers=final_headers,
            query_params=merged_query_params,
            path_params=merged_path_params,
            body_type=effective_body_type,
            body=parsed_body,
            raw_body_preview=raw_preview,
            curl_command=curl_cmd
        )

        return httpx_req, response_dto

    @classmethod
    def validate_preflight(cls, req: PreflightValidationRequest) -> PreflightValidationReport:
        """Run pre-flight validation audit on an arbitrary direct request."""
        method_str = req.method.value if hasattr(req.method, "value") else str(req.method)
        return execute_preflight_check(
            base_url=req.base_url,
            method=method_str,
            path=req.path,
            path_params=req.path_params,
            query_params=req.query_params,
            headers=req.headers,
            body=req.body,
            body_type=req.body_type
        )

    @classmethod
    def validate_endpoint_preflight(
        cls,
        project: Project,
        endpoint: Endpoint,
        overrides: Optional[RequestCompileOverride] = None
    ) -> PreflightValidationReport:
        """Run pre-flight validation audit on a stored Endpoint + Project workspace with overrides."""
        overrides = overrides or RequestCompileOverride()

        method_str = endpoint.method
        base_url = overrides.base_url or project.base_url

        # Merge path parameters
        merged_path_params = dict(endpoint.path_params)
        if overrides.path_params:
            merged_path_params.update(overrides.path_params)

        # Merge query parameters
        merged_query_params = dict(endpoint.query_params)
        if overrides.query_params:
            merged_query_params.update(overrides.query_params)

        # Merge headers
        merged_headers = cls.merge_headers(
            project_headers=project.global_headers,
            endpoint_headers=endpoint.headers,
            override_headers=overrides.headers
        )

        # Effective body
        effective_body = overrides.body if overrides.body is not None else endpoint.body_schema
        effective_body_type = overrides.body_type or (BodyType.JSON if effective_body and effective_body != {} else BodyType.EMPTY)

        return execute_preflight_check(
            base_url=base_url,
            method=method_str,
            path=endpoint.path,
            path_params=merged_path_params,
            query_params=merged_query_params,
            headers=merged_headers,
            body=effective_body,
            body_type=effective_body_type
        )
