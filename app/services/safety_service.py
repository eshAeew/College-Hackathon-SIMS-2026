"""Service layer for Safety, Target Authorization, and Destructive Safeguards (Stage 16)."""
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.entities.project import Project
from app.models.schemas.safety import (
    AuditTestRunRequest,
    AuditTestRunResponse,
    EnvironmentTier,
    EvaluateOperationRequest,
    EvaluateOperationResponse,
    SafetyPolicy,
    ValidateTargetRequest,
    ValidateTargetResponse,
)
from app.utils.safety_guard import (
    audit_test_suite_safety,
    evaluate_execution_safety,
    validate_target_host,
)

logger = logging.getLogger("app.services.safety")


class SafetyService:
    """Service providing target authorization and destructive operation safety gating."""

    @classmethod
    def validate_target(
        cls,
        req: ValidateTargetRequest,
        db: Optional[Session] = None
    ) -> ValidateTargetResponse:
        """Validate target host against safety policies."""
        policy = req.policy or SafetyPolicy()
        return validate_target_host(target_url=req.url, policy=policy)

    @classmethod
    def evaluate_operation(cls, req: EvaluateOperationRequest) -> EvaluateOperationResponse:
        """Evaluate whether a specific HTTP request is safe or requires destructive confirmation."""
        return evaluate_execution_safety(
            method=req.method,
            url=req.url,
            tags=req.tags,
            allow_destructive=req.allow_destructive,
            confirmation_token=req.confirmation_token
        )

    @classmethod
    def audit_test_run(cls, req: AuditTestRunRequest) -> AuditTestRunResponse:
        """Audit a collection of operations prior to test run dispatch."""
        return audit_test_suite_safety(
            operations=req.test_operations,
            allow_destructive=req.allow_destructive
        )

    @classmethod
    def get_project_safety_policy(cls, project_id: int, db: Session) -> SafetyPolicy:
        """Retrieve safety policy configured for a specific Project."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        # Default policy constructed from project properties
        allowed = ["localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"]
        if project.base_url:
            from urllib.parse import urlparse
            p_host = urlparse(project.base_url).netloc.split(":")[0]
            if p_host and p_host not in allowed:
                allowed.append(p_host)

        env_tier = EnvironmentTier.DEVELOPMENT
        if project.environment.lower() == "production":
            env_tier = EnvironmentTier.PRODUCTION
        elif project.environment.lower() == "staging":
            env_tier = EnvironmentTier.STAGING

        return SafetyPolicy(
            project_id=project.id,
            allowed_hosts=allowed,
            environment=env_tier,
            allow_private_networks=True,
            allow_localhost=True,
            allow_destructive_operations=False
        )

    @classmethod
    def update_project_safety_policy(
        cls,
        project_id: int,
        policy: SafetyPolicy,
        db: Session
    ) -> SafetyPolicy:
        """Update and return project safety policy."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        policy.project_id = project.id
        logger.info(f"Updated SafetyPolicy for Project #{project_id} (Env: {policy.environment.value})")
        return policy
