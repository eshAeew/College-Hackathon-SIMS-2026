"""Pydantic Schemas and DTOs for Safety & Execution Controls (Stage 16)."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TargetHostAuthorizationStatus(str, Enum):
    """Target host authorization evaluation status."""
    AUTHORIZED = "AUTHORIZED"
    BLOCKED_DISALLOWED_HOST = "BLOCKED_DISALLOWED_HOST"
    BLOCKED_PUBLIC_IP_IN_DEV_MODE = "BLOCKED_PUBLIC_IP_IN_DEV_MODE"
    BLOCKED_PRODUCTION_SAFEGUARD = "BLOCKED_PRODUCTION_SAFEGUARD"
    BLOCKED_MALFORMED_URL = "BLOCKED_MALFORMED_URL"


class OperationRiskLevel(str, Enum):
    """Risk classification for HTTP operations."""
    SAFE_READ_ONLY = "SAFE_READ_ONLY"
    SAFE_IDEMPOTENT_WRITE = "SAFE_IDEMPOTENT_WRITE"
    POTENTIALLY_DESTRUCTIVE = "POTENTIALLY_DESTRUCTIVE"
    CRITICAL_DATA_PURGE = "CRITICAL_DATA_PURGE"


class EnvironmentTier(str, Enum):
    """Execution environment tiers with differing security safeguards."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class SafetyPolicy(BaseModel):
    """Configurable safety and authorization policy for host and method execution."""
    project_id: Optional[int] = Field(default=None, description="Associated Project ID if stored")
    allowed_hosts: List[str] = Field(
        default=["localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver", "api.example.com"],
        description="Allowed host names, domain wildcards (*.example.com), or IP addresses"
    )
    blocked_hosts: List[str] = Field(
        default=["production.internal.bank", "aws.metadata.internal"],
        description="Explicitly forbidden target hosts"
    )
    allow_private_networks: bool = Field(
        default=True,
        description="Allow RFC-1918 private IPv4 addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)"
    )
    allow_localhost: bool = Field(
        default=True,
        description="Allow loopback and local development hosts"
    )
    require_https_for_external: bool = Field(
        default=False,
        description="Enforce HTTPS scheme for external non-localhost hosts"
    )
    environment: EnvironmentTier = Field(
        default=EnvironmentTier.DEVELOPMENT,
        description="Active environment tier"
    )
    strict_host_allowlist: bool = Field(
        default=False,
        description="If True, any host not explicitly matching allowed_hosts is blocked"
    )
    allow_destructive_operations: bool = Field(
        default=False,
        description="Master authorization toggle allowing execution of destructive operations"
    )


class ValidateTargetRequest(BaseModel):
    """Request payload to validate target URL authorization."""
    url: str = Field(..., description="Target URL to check", examples=["http://localhost:8000/api", "https://api.example.com"])
    policy: Optional[SafetyPolicy] = Field(default=None, description="Optional custom policy override")


class ValidateTargetResponse(BaseModel):
    """Report detailing target host authorization outcome."""
    url: str
    normalized_host: str
    is_authorized: bool
    authorization_status: TargetHostAuthorizationStatus
    is_localhost: bool
    is_private_network: bool
    is_https: bool
    message: str
    advisory_banner: Optional[str] = Field(
        default="⚠️ AUTHORIZED TESTING ONLY: Ensure you have explicit authorization before scanning or executing tests against target hosts.",
        description="Prominent security advisory text"
    )


class EvaluateOperationRequest(BaseModel):
    """Request payload to classify risk and check safety gating for an HTTP operation."""
    method: str = Field(..., description="HTTP Method (GET, POST, PUT, DELETE, PATCH)")
    url: str = Field(..., description="Target route or URL")
    tags: List[str] = Field(default_factory=list, description="Associated test tags")
    allow_destructive: bool = Field(default=False, description="Whether destructive operations are authorized")
    confirmation_token: Optional[str] = Field(default=None, description="Explicit confirmation token for critical purges")


class EvaluateOperationResponse(BaseModel):
    """Outcome of operation risk evaluation and safety gating."""
    method: str
    url: str
    risk_level: OperationRiskLevel
    is_destructive: bool
    is_permitted: bool
    requires_confirmation: bool
    generated_confirmation_token: Optional[str] = None
    reason: str


class AuditTestRunRequest(BaseModel):
    """Request payload to perform pre-flight safety audit over a collection of operations."""
    test_operations: List[Dict[str, Any]] = Field(
        ...,
        description="List of operation objects containing 'method', 'url', and optional 'tags'",
        examples=[[{"method": "GET", "url": "/users"}, {"method": "DELETE", "url": "/users/1"}]]
    )
    allow_destructive: bool = Field(default=False, description="Whether destructive operations are authorized")


class AuditTestRunResponse(BaseModel):
    """Summary of pre-flight safety audit over a batch of operations."""
    total_operations: int
    safe_operations: int
    destructive_operations: int
    critical_purge_operations: int
    blocked_operations: int
    is_run_permitted: bool
    warnings: List[str] = Field(default_factory=list)
