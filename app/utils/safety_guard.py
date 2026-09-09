"""Safety and execution control utilities for host allowlisting and destructive gating (Stage 16)."""
import fnmatch
import hashlib
import ipaddress
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.models.schemas.safety import (
    AuditTestRunResponse,
    EnvironmentTier,
    EvaluateOperationResponse,
    OperationRiskLevel,
    SafetyPolicy,
    TargetHostAuthorizationStatus,
    ValidateTargetResponse,
)

logger = logging.getLogger("app.utils.safety_guard")

# Common keywords in paths or tags that indicate critical data purges
DESTRUCTIVE_PATH_KEYWORDS = {"truncate", "drop", "purge", "reset", "cleanup", "destroy", "wipe", "flush"}
DESTRUCTIVE_TAGS = {"destructive", "data-purge", "state-mutating", "cleanup"}


def is_localhost_host(host: str) -> bool:
    """Determine if a hostname represents localhost or loopback."""
    if not host:
        return False
    h = host.lower().split(":")[0]
    return h in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver")


def is_ip_address(host: str) -> bool:
    """Check if host string is a valid IPv4 or IPv6 address."""
    h = host.split(":")[0]
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def is_private_ip(host: str) -> bool:
    """Check if host is an RFC-1918 private IPv4 or private IPv6 address."""
    h = host.split(":")[0]
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def match_host_pattern(host: str, pattern: str) -> bool:
    """
    Match a hostname against an allowlist/blocklist pattern.
    Supports wildcards (*.example.com) and port-agnostic matching.
    """
    clean_host = host.lower().split(":")[0]
    clean_pattern = pattern.lower().split(":")[0]

    if clean_pattern.startswith("*."):
        suffix = clean_pattern[2:]
        return clean_host.endswith(suffix) or clean_host == suffix
    return fnmatch.fnmatch(clean_host, clean_pattern) or clean_host == clean_pattern


def validate_target_host(target_url: str, policy: Optional[SafetyPolicy] = None) -> ValidateTargetResponse:
    """
    Validate target URL against allowed hosts, private networks, and environment boundaries.
    """
    pol = policy or SafetyPolicy()
    try:
        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return ValidateTargetResponse(
                url=target_url,
                normalized_host="",
                is_authorized=False,
                authorization_status=TargetHostAuthorizationStatus.BLOCKED_MALFORMED_URL,
                is_localhost=False,
                is_private_network=False,
                is_https=False,
                message="Target URL is malformed or missing scheme/host."
            )

        host = parsed.netloc.split(":")[0].lower()
        is_https = parsed.scheme.lower() == "https"
        is_local = is_localhost_host(host)
        is_priv = is_private_ip(host)

        # 1. Check explicit blocked hosts
        for blocked in pol.blocked_hosts:
            if match_host_pattern(host, blocked):
                return ValidateTargetResponse(
                    url=target_url,
                    normalized_host=host,
                    is_authorized=False,
                    authorization_status=TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST,
                    is_localhost=is_local,
                    is_private_network=is_priv,
                    is_https=is_https,
                    message=f"Host '{host}' is explicitly blocked by safety policy."
                )

        # 2. Check Localhost
        if is_local:
            if not pol.allow_localhost:
                return ValidateTargetResponse(
                    url=target_url,
                    normalized_host=host,
                    is_authorized=False,
                    authorization_status=TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST,
                    is_localhost=True,
                    is_private_network=is_priv,
                    is_https=is_https,
                    message="Localhost testing is disabled in the current safety policy."
                )
            return ValidateTargetResponse(
                url=target_url,
                normalized_host=host,
                is_authorized=True,
                authorization_status=TargetHostAuthorizationStatus.AUTHORIZED,
                is_localhost=True,
                is_private_network=True,
                is_https=is_https,
                message=f"Host '{host}' is authorized as a local development target."
            )

        # 3. Check Private Network
        if is_priv:
            if not pol.allow_private_networks:
                return ValidateTargetResponse(
                    url=target_url,
                    normalized_host=host,
                    is_authorized=False,
                    authorization_status=TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST,
                    is_localhost=False,
                    is_private_network=True,
                    is_https=is_https,
                    message=f"Private network IP '{host}' is not permitted by safety policy."
                )
            return ValidateTargetResponse(
                url=target_url,
                normalized_host=host,
                is_authorized=True,
                authorization_status=TargetHostAuthorizationStatus.AUTHORIZED,
                is_localhost=False,
                is_private_network=True,
                is_https=is_https,
                message=f"Private network host '{host}' is authorized."
            )

        # 4. Check Allowed Hosts Allowlist
        is_in_allowlist = any(match_host_pattern(host, pattern) for pattern in pol.allowed_hosts)

        if pol.strict_host_allowlist and not is_in_allowlist:
            return ValidateTargetResponse(
                url=target_url,
                normalized_host=host,
                is_authorized=False,
                authorization_status=TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST,
                is_localhost=False,
                is_private_network=False,
                is_https=is_https,
                message=f"Host '{host}' is not present in the strict allowlist."
            )

        # 5. Check Production Safeguards
        if pol.environment == EnvironmentTier.PRODUCTION and not is_in_allowlist:
            return ValidateTargetResponse(
                url=target_url,
                normalized_host=host,
                is_authorized=False,
                authorization_status=TargetHostAuthorizationStatus.BLOCKED_PRODUCTION_SAFEGUARD,
                is_localhost=False,
                is_private_network=False,
                is_https=is_https,
                message=f"Production safeguard: Host '{host}' must be explicitly whitelisted before testing."
            )

        # 6. Check HTTPS requirement
        if pol.require_https_for_external and not is_https:
            return ValidateTargetResponse(
                url=target_url,
                normalized_host=host,
                is_authorized=False,
                authorization_status=TargetHostAuthorizationStatus.BLOCKED_DISALLOWED_HOST,
                is_localhost=False,
                is_private_network=False,
                is_https=False,
                message=f"External host '{host}' requires secure HTTPS connection."
            )

        return ValidateTargetResponse(
            url=target_url,
            normalized_host=host,
            is_authorized=True,
            authorization_status=TargetHostAuthorizationStatus.AUTHORIZED,
            is_localhost=False,
            is_private_network=False,
            is_https=is_https,
            message=f"Target host '{host}' is authorized for testing."
        )

    except Exception as e:
        logger.error(f"Error validating target URL '{target_url}': {e}", exc_info=True)
        return ValidateTargetResponse(
            url=target_url,
            normalized_host="",
            is_authorized=False,
            authorization_status=TargetHostAuthorizationStatus.BLOCKED_MALFORMED_URL,
            is_localhost=False,
            is_private_network=False,
            is_https=False,
            message=f"Validation failed: {str(e)}"
        )


def classify_operation_risk(
    method: str,
    path_or_url: str,
    tags: Optional[List[str]] = None
) -> OperationRiskLevel:
    """Classify the risk level of an HTTP operation."""
    m = method.upper()
    p = path_or_url.lower()
    tag_set = {t.lower() for t in (tags or [])}

    # Check for critical data purge indicators in path or tags
    path_tokens = set(p.replace("/", " ").replace("-", " ").replace("_", " ").split())
    has_purge_keyword = bool(path_tokens & DESTRUCTIVE_PATH_KEYWORDS)
    has_purge_tag = bool(tag_set & DESTRUCTIVE_TAGS)

    if (m in ("DELETE", "POST", "PUT", "PATCH")) and (has_purge_keyword or has_purge_tag):
        return OperationRiskLevel.CRITICAL_DATA_PURGE

    if m == "DELETE":
        return OperationRiskLevel.POTENTIALLY_DESTRUCTIVE

    if m in ("POST", "PUT", "PATCH"):
        return OperationRiskLevel.SAFE_IDEMPOTENT_WRITE

    return OperationRiskLevel.SAFE_READ_ONLY


def generate_confirmation_token(method: str, url: str) -> str:
    """Generate a deterministic confirmation token required to execute critical purges."""
    digest = hashlib.sha256(f"SENTINEL-CONFIRM-{method.upper()}-{url}".encode("utf-8")).hexdigest()[:12]
    return f"CONFIRM-{digest.upper()}"


def evaluate_execution_safety(
    method: str,
    url: str,
    tags: Optional[List[str]] = None,
    allow_destructive: bool = False,
    confirmation_token: Optional[str] = None
) -> EvaluateOperationResponse:
    """Evaluate whether an operation is permitted to execute given safety policies."""
    risk = classify_operation_risk(method, url, tags)
    is_dest = risk in (OperationRiskLevel.POTENTIALLY_DESTRUCTIVE, OperationRiskLevel.CRITICAL_DATA_PURGE)
    expected_token = generate_confirmation_token(method, url)

    if risk == OperationRiskLevel.SAFE_READ_ONLY or risk == OperationRiskLevel.SAFE_IDEMPOTENT_WRITE:
        return EvaluateOperationResponse(
            method=method.upper(),
            url=url,
            risk_level=risk,
            is_destructive=False,
            is_permitted=True,
            requires_confirmation=False,
            generated_confirmation_token=None,
            reason="Operation is safe and non-destructive."
        )

    if risk == OperationRiskLevel.POTENTIALLY_DESTRUCTIVE:
        if not allow_destructive:
            return EvaluateOperationResponse(
                method=method.upper(),
                url=url,
                risk_level=risk,
                is_destructive=True,
                is_permitted=False,
                requires_confirmation=True,
                generated_confirmation_token=expected_token,
                reason=f"Destructive operation {method.upper()} is blocked because allow_destructive_operations is disabled."
            )
        return EvaluateOperationResponse(
            method=method.upper(),
            url=url,
            risk_level=risk,
            is_destructive=True,
            is_permitted=True,
            requires_confirmation=False,
            generated_confirmation_token=None,
            reason=f"Destructive operation {method.upper()} is explicitly authorized."
        )

    # CRITICAL_DATA_PURGE
    if not allow_destructive:
        return EvaluateOperationResponse(
            method=method.upper(),
            url=url,
            risk_level=risk,
            is_destructive=True,
            is_permitted=False,
            requires_confirmation=True,
            generated_confirmation_token=expected_token,
            reason="Critical data purge operation is blocked because allow_destructive_operations is disabled."
        )

    if confirmation_token != expected_token:
        return EvaluateOperationResponse(
            method=method.upper(),
            url=url,
            risk_level=risk,
            is_destructive=True,
            is_permitted=False,
            requires_confirmation=True,
            generated_confirmation_token=expected_token,
            reason=f"Critical data purge requires explicit confirmation token '{expected_token}'."
        )

    return EvaluateOperationResponse(
        method=method.upper(),
        url=url,
        risk_level=risk,
        is_destructive=True,
        is_permitted=True,
        requires_confirmation=False,
        generated_confirmation_token=None,
        reason="Critical data purge is explicitly authorized with valid confirmation token."
    )


def audit_test_suite_safety(
    operations: List[Dict[str, Any]],
    allow_destructive: bool = False
) -> AuditTestRunResponse:
    """Perform pre-flight safety audit over a list of test operations."""
    total = len(operations)
    safe = 0
    destructive = 0
    critical = 0
    blocked = 0
    warnings: List[str] = []

    for op in operations:
        method = op.get("method", "GET")
        url = op.get("url", "/")
        tags = op.get("tags", [])
        token = op.get("confirmation_token")

        eval_resp = evaluate_execution_safety(
            method=method,
            url=url,
            tags=tags,
            allow_destructive=allow_destructive,
            confirmation_token=token
        )

        if eval_resp.risk_level in (OperationRiskLevel.SAFE_READ_ONLY, OperationRiskLevel.SAFE_IDEMPOTENT_WRITE):
            safe += 1
        elif eval_resp.risk_level == OperationRiskLevel.POTENTIALLY_DESTRUCTIVE:
            destructive += 1
        elif eval_resp.risk_level == OperationRiskLevel.CRITICAL_DATA_PURGE:
            critical += 1

        if not eval_resp.is_permitted:
            blocked += 1
            warnings.append(f"[{method.upper()} {url}] {eval_resp.reason}")

    is_permitted = (blocked == 0)

    return AuditTestRunResponse(
        total_operations=total,
        safe_operations=safe,
        destructive_operations=destructive,
        critical_purge_operations=critical,
        blocked_operations=blocked,
        is_run_permitted=is_permitted,
        warnings=warnings
    )
