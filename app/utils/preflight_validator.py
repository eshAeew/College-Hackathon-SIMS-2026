"""Pre-flight validation engine checking URL structure, hostnames, path parameters, payload syntax, and header validity."""
import re
import json
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple

from app.models.schemas.request_config import BodyType, PreflightValidationReport


def validate_url_syntax(base_url: str, path: str) -> Tuple[bool, bool, bool, bool, Optional[str], List[str], List[str]]:
    """Validate URL scheme, hostname, port, and path formatting.
    
    Returns:
        (url_valid, scheme_valid, host_valid, port_valid, resolved_target_url, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not base_url or not base_url.strip():
        errors.append("Base URL cannot be empty")
        return False, False, False, False, None, errors, warnings

    cleaned_base = base_url.strip()
    
    # Check Scheme
    try:
        parsed = urllib.parse.urlparse(cleaned_base)
    except Exception as exc:
        errors.append(f"Failed to parse base URL: {str(exc)}")
        return False, False, False, False, None, errors, warnings

    scheme = parsed.scheme.lower()
    scheme_valid = scheme in ("http", "https")
    if not scheme_valid:
        errors.append(f"Invalid URL scheme '{parsed.scheme}'. Only 'http://' and 'https://' are supported.")

    # Check Hostname & Port
    netloc = parsed.netloc
    if not netloc and parsed.path and not parsed.path.startswith("/"):
        # Catch case where scheme was omitted e.g. "localhost:8000"
        netloc = parsed.path
        errors.append("Base URL is missing 'http://' or 'https://' scheme prefix")

    host_valid = False
    port_valid = True

    if not netloc:
        errors.append("Base URL is missing a valid hostname or domain")
    else:
        # Check port if present
        if ":" in netloc:
            host_part, port_str = netloc.rsplit(":", 1)
            # Check for trailing colon with no port (e.g. "http://localhost:")
            if not port_str.strip():
                port_valid = False
                errors.append("Base URL has a trailing colon ':' without a port number")
            else:
                try:
                    port_num = int(port_str)
                    if not (1 <= port_num <= 65535):
                        port_valid = False
                        errors.append(f"Port number '{port_num}' is out of valid range (1-65535)")
                except ValueError:
                    port_valid = False
                    errors.append(f"Invalid non-numeric port '{port_str}' in base URL")
        else:
            host_part = netloc

        # Hostname syntax validation
        host_clean = host_part.strip("[]")  # IPv6 support
        if not host_clean or " " in host_clean:
            errors.append(f"Invalid hostname '{host_part}' contains whitespace or is empty")
        else:
            host_valid = True

    # Security Warning
    if scheme == "http" and host_valid and not any(h in netloc.lower() for h in ("localhost", "127.0.0.1", "0.0.0.0", "test", "local")):
        warnings.append("Using unencrypted 'http://' for remote host. 'https://' is strongly recommended for production.")

    # Check Path formatting
    if path and not path.strip().startswith("/"):
        errors.append(f"Path '{path}' must start with a leading slash '/'")

    url_valid = scheme_valid and host_valid and port_valid and (len(errors) == 0)
    target_url = f"{cleaned_base.rstrip('/')}/{path.lstrip('/')}" if url_valid else None

    return url_valid, scheme_valid, host_valid, port_valid, target_url, errors, warnings


def validate_path_parameters(path: str, path_params: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """Check that every {variable} in path template has a non-null, non-blank concrete value.
    
    Returns:
        (is_complete, path_variables, missing_variables)
    """
    if not path:
        return True, [], []

    path_vars = list(dict.fromkeys(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path)))
    missing = [
        var for var in path_vars
        if var not in path_params or path_params[var] is None or str(path_params[var]).strip() == ""
    ]
    return (len(missing) == 0), path_vars, missing


def validate_body_syntax(body: Optional[Any], body_type: BodyType) -> Tuple[bool, Optional[str]]:
    """Verify syntactic correctness of request body according to its declared BodyType.
    
    Returns:
        (is_valid, error_message)
    """
    if body is None or body_type == BodyType.EMPTY:
        return True, None

    if body_type == BodyType.JSON:
        if isinstance(body, (dict, list)):
            try:
                json.dumps(body)
                return True, None
            except Exception as exc:
                return False, f"JSON payload is not serializable: {str(exc)}"
        elif isinstance(body, str):
            body_str = body.strip()
            if not body_str:
                return True, None
            try:
                json.loads(body_str)
                return True, None
            except json.JSONDecodeError as exc:
                return False, f"Malformed JSON string at line {exc.lineno}, col {exc.colno}: {exc.msg}"
        else:
            return False, f"JSON body must be a dictionary, list, or valid JSON string, got {type(body).__name__}"

    elif body_type == BodyType.FORM_DATA:
        if isinstance(body, dict):
            return True, None
        elif isinstance(body, str):
            return True, None
        else:
            return False, f"Form-data body must be a dictionary or urlencoded string, got {type(body).__name__}"

    elif body_type == BodyType.RAW_TEXT:
        return True, None

    return True, None


def validate_headers_syntax(headers: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """Validate header keys and values against RFC standards.
    
    Returns:
        (headers_valid, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not headers:
        return True, errors, warnings

    for key, val in headers.items():
        if not isinstance(key, str) or not key.strip():
            errors.append("Header name must be a non-empty string")
            continue
        
        # Check for invalid header name characters (spaces or control chars)
        if any(c in key for c in " \t\r\n:"):
            errors.append(f"Header name '{key}' contains invalid whitespace or colon character")

        if val is None:
            warnings.append(f"Header '{key}' has a null value and may be omitted or rejected by server")

    return (len(errors) == 0), errors, warnings


def execute_preflight_check(
    base_url: str,
    method: str,
    path: str,
    path_params: Optional[Dict[str, Any]] = None,
    query_params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Any] = None,
    body_type: BodyType = BodyType.JSON
) -> PreflightValidationReport:
    """Run full pre-flight audit covering URL, host, port, path parameters, payload syntax, and headers."""
    path_params = path_params or {}
    query_params = query_params or {}
    headers = headers or {}

    all_errors: List[str] = []
    all_warnings: List[str] = []

    # 1. URL & Host Syntax
    url_valid, scheme_valid, host_valid, port_valid, target_url, url_errors, url_warnings = validate_url_syntax(base_url, path)
    all_errors.extend(url_errors)
    all_warnings.extend(url_warnings)

    # 2. Path Parameter Completeness
    path_complete, path_vars, missing_path_vars = validate_path_parameters(path, path_params)
    if not path_complete:
        all_errors.append(f"Missing values for path parameter(s): {', '.join(missing_path_vars)}")

    # 3. Body Payload Syntax
    body_valid, body_err = validate_body_syntax(body, body_type)
    if not body_valid and body_err:
        all_errors.append(body_err)

    # 4. Headers Syntax
    headers_valid, header_errors, header_warnings = validate_headers_syntax(headers)
    all_errors.extend(header_errors)
    all_warnings.extend(header_warnings)

    # Auth check warning
    has_auth = any(k.lower() in ("authorization", "x-api-key", "apikey", "token") for k in headers.keys())
    if not has_auth and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
        all_warnings.append(f"No authentication header (Authorization / X-API-Key) configured for state-modifying {method.upper()} request")

    overall_valid = url_valid and path_complete and body_valid and headers_valid and (len(all_errors) == 0)

    # Compute fully resolved target URL preview if possible
    resolved_url_preview = None
    if url_valid and path_complete:
        from app.services.request_builder_service import RequestBuilderService
        try:
            full_u, _ = RequestBuilderService.resolve_url(base_url, path, path_params, query_params)
            resolved_url_preview = full_u
        except Exception:
            resolved_url_preview = target_url

    return PreflightValidationReport(
        is_valid=overall_valid,
        target_url=resolved_url_preview or target_url,
        url_valid=url_valid,
        scheme_valid=scheme_valid,
        host_valid=host_valid,
        port_valid=port_valid,
        path_params_complete=path_complete,
        missing_path_params=missing_path_vars,
        body_valid=body_valid,
        headers_valid=headers_valid,
        errors=all_errors,
        warnings=all_warnings
    )
