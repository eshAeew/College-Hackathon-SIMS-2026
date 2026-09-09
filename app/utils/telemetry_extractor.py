"""Response & Network Telemetry Extraction, MIME-type classification, and Exception Diagnostics."""
import base64
import http
import json
import logging
import ssl
from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.models.schemas.execution import RedirectStep, NetworkErrorDetail

logger = logging.getLogger("app.utils.telemetry")

# Binary MIME patterns to avoid decoding as raw string
BINARY_MIME_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/x-tar",
    "application/wasm"
)


def extract_cookies(response: httpx.Response) -> Dict[str, str]:
    """Extract cookies from response cookies container."""
    try:
        return dict(response.cookies)
    except Exception:
        return {}


def extract_redirect_history(response: httpx.Response) -> List[RedirectStep]:
    """Extract structured redirect history from response history chain."""
    history_steps: List[RedirectStep] = []
    for resp in response.history:
        history_steps.append(
            RedirectStep(
                url=str(resp.url),
                status_code=resp.status_code,
                location=resp.headers.get("location")
            )
        )
    return history_steps


def parse_response_payload(
    response: httpx.Response
) -> Tuple[Optional[Any], bool, Optional[str], Optional[str]]:
    """Parse response content into structured data, detecting binary vs text format.
    
    Returns:
        (body, is_binary, raw_body_base64, content_type)
    """
    content_type = response.headers.get("content-type", "").lower()
    raw_bytes = response.content

    if not raw_bytes:
        return None, False, None, content_type or None

    # Check if content type is explicitly binary
    is_binary = any(content_type.startswith(prefix) for prefix in BINARY_MIME_PREFIXES)

    if is_binary:
        b64_encoded = base64.b64encode(raw_bytes).decode("ascii")
        return None, True, b64_encoded, content_type or None

    # Try JSON decoding if mime type is json
    if "application/json" in content_type or "+json" in content_type:
        try:
            parsed_json = json.loads(raw_bytes.decode("utf-8"))
            return parsed_json, False, None, content_type or None
        except Exception:
            pass

    # Attempt utf-8 decoding for text
    try:
        text_content = raw_bytes.decode("utf-8")
        return text_content, False, None, content_type or None
    except UnicodeDecodeError:
        # Fallback to binary Base64 if bytes cannot be decoded as utf-8
        b64_encoded = base64.b64encode(raw_bytes).decode("ascii")
        return None, True, b64_encoded, content_type or "application/octet-stream"


def classify_network_exception(
    exc: Exception,
    url: str,
    timeout_seconds: float
) -> NetworkErrorDetail:
    """Classify network and transport errors into standardized categories with troubleshooting hints."""
    exc_type = exc.__class__.__name__
    exc_str = str(exc)

    # 1. Timeout Errors
    if isinstance(exc, httpx.ConnectTimeout):
        return NetworkErrorDetail(
            error_type="ConnectTimeout",
            error_category="timeout",
            message=f"Connection establishment timed out after {timeout_seconds}s for {url}.",
            is_retryable=True,
            troubleshooting_hint="Target server took too long to accept TCP connection. Verify server is reachable and not dropping packets."
        )

    if isinstance(exc, httpx.ReadTimeout):
        return NetworkErrorDetail(
            error_type="ReadTimeout",
            error_category="timeout",
            message=f"Request timed out: Target server did not send response within {timeout_seconds}s for {url}.",
            is_retryable=True,
            troubleshooting_hint="Server accepted connection but response generation timed out. Increase timeout_seconds or check server load."
        )

    if isinstance(exc, httpx.TimeoutException):
        return NetworkErrorDetail(
            error_type="TimeoutException",
            error_category="timeout",
            message=f"Request timed out after {timeout_seconds}s for {url}.",
            is_retryable=True,
            troubleshooting_hint="Network operation exceeded configured timeout threshold."
        )

    # 2. SSL / TLS Verification Errors
    if isinstance(exc, ssl.SSLError) or "SSL" in exc_type or "CERTIFICATE" in exc_str.upper():
        return NetworkErrorDetail(
            error_type="SSLValidationError",
            error_category="security",
            message=f"SSL/TLS Certificate verification failed for {url}: {exc_str}",
            is_retryable=False,
            troubleshooting_hint="Target certificate is expired, self-signed, or untrusted. Set 'verify_ssl: false' in options if testing in local/staging environments."
        )

    # 3. DNS Lookup Errors
    if "getaddrinfo failed" in exc_str or "Name or service not known" in exc_str or "gaierror" in exc_type.lower():
        return NetworkErrorDetail(
            error_type="DNSLookupError",
            error_category="dns",
            message=f"DNS resolution failed for {url}: Host name could not be resolved.",
            is_retryable=True,
            troubleshooting_hint="Check for typographical errors in the target domain name or verify DNS server reachability."
        )

    # 4. Connection Refused
    if "Connection refused" in exc_str or "10061" in exc_str or "ECONNREFUSED" in exc_str:
        return NetworkErrorDetail(
            error_type="ConnectionRefused",
            error_category="network",
            message=f"Connection refused by target host for {url}.",
            is_retryable=True,
            troubleshooting_hint="Target host is reachable, but no process is listening on the specified port. Verify backend server is started."
        )

    # 5. Generic Connect / Network Error
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return NetworkErrorDetail(
            error_type="ConnectError",
            error_category="network",
            message=f"Failed to connect to {url}: {exc_str or 'Target unreachable'}",
            is_retryable=True,
            troubleshooting_hint="Ensure target host is online, firewall rules permit outbound traffic, and network routing is configured correctly."
        )

    # 6. Redirect Loop
    if isinstance(exc, httpx.TooManyRedirects):
        return NetworkErrorDetail(
            error_type="TooManyRedirects",
            error_category="redirect",
            message=f"Exceeded maximum redirect limit while requesting {url}.",
            is_retryable=False,
            troubleshooting_hint="Target URL is encountering a circular redirect loop (e.g., http -> https -> http). Check server redirect rules."
        )

    # 7. Protocol Decoding Error
    if isinstance(exc, httpx.DecodingError):
        return NetworkErrorDetail(
            error_type="DecodingError",
            error_category="protocol",
            message=f"Failed to decode response content from {url}: {exc_str}",
            is_retryable=False,
            troubleshooting_hint="Server returned malformed content-encoding (e.g. corrupted gzip/brotli stream)."
        )

    # Default / Unknown
    return NetworkErrorDetail(
        error_type=exc_type or "UnknownNetworkError",
        error_category="unknown",
        message=f"Unexpected execution error: {exc_str}",
        is_retryable=False,
        troubleshooting_hint="Inspect application logs for full stack trace."
    )
