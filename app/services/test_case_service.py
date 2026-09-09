import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.schemas.request_config import RequestCompileOverride
from app.models.schemas.test_case import (
    TestCaseAssertions,
    TestCaseCreate,
    TestCaseExecutionEvaluationResponse,
    TestCaseUpdate
)
from app.services.http_dispatcher import HttpDispatcherService
from app.services.request_builder_service import RequestBuilderService
from app.utils.assertion_engine import evaluate_assertions

logger = logging.getLogger("app.services.test_case")


class TestCaseService:
    """Service providing business logic and persistence operations for test cases."""

    @classmethod
    def create_test_case(
        cls,
        db: Session,
        endpoint_id: int,
        dto: TestCaseCreate
    ) -> TestCase:
        """Create a new test scenario associated with a registered endpoint."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Endpoint #{endpoint_id} does not exist.")

        test_case = TestCase(
            endpoint_id=endpoint_id,
            name=dto.name.strip(),
            description=dto.description.strip() if dto.description else None,
            is_active=dto.is_active,
            severity=dto.severity.value if hasattr(dto.severity, "value") else str(dto.severity),
            tags_json=json.dumps(dto.tags),
            path_params_json=json.dumps(dto.path_params),
            query_params_json=json.dumps(dto.query_params),
            headers_json=json.dumps(dto.headers),
            body_type=dto.body_type.value if hasattr(dto.body_type, "value") else str(dto.body_type),
            body_json=json.dumps(dto.body) if isinstance(dto.body, (dict, list)) else (str(dto.body) if dto.body is not None else None),
            assertions_json=json.dumps(dto.assertions)
        )

        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        logger.info(f"Created TestCase #{test_case.id}: '{test_case.name}' under Endpoint #{endpoint_id}")
        return test_case

    @classmethod
    def get_test_cases(
        cls,
        db: Session,
        endpoint_id: int,
        tag: Optional[str] = None,
        severity: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[TestCase]:
        """List test scenarios for an endpoint with optional filtering by tag, severity, and active status."""
        query = db.query(TestCase).filter(TestCase.endpoint_id == endpoint_id)

        if is_active is not None:
            query = query.filter(TestCase.is_active == is_active)

        if severity:
            query = query.filter(TestCase.severity == severity.lower())

        if tag:
            # Match tag in JSON array string: ["smoke", "regression"]
            tag_pattern = f'%"{tag.strip().lower()}"%'
            query = query.filter(TestCase.tags_json.ilike(tag_pattern))

        return query.order_by(TestCase.id.asc()).offset(skip).limit(limit).all()

    @classmethod
    def get_test_case_by_id(cls, db: Session, test_case_id: int) -> Optional[TestCase]:
        """Fetch a specific TestCase by ID."""
        return db.query(TestCase).filter(TestCase.id == test_case_id).first()

    @classmethod
    def update_test_case(
        cls,
        db: Session,
        test_case_id: int,
        dto: TestCaseUpdate
    ) -> Optional[TestCase]:
        """Update an existing test scenario with partial field updates."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            return None

        update_data = dto.model_dump(exclude_unset=True)

        if "name" in update_data and update_data["name"] is not None:
            test_case.name = update_data["name"].strip()
        if "description" in update_data:
            test_case.description = update_data["description"].strip() if update_data["description"] else None
        if "is_active" in update_data and update_data["is_active"] is not None:
            test_case.is_active = update_data["is_active"]
        if "severity" in update_data and update_data["severity"] is not None:
            sev = update_data["severity"]
            test_case.severity = sev.value if hasattr(sev, "value") else str(sev)
        if "tags" in update_data and update_data["tags"] is not None:
            test_case.tags_json = json.dumps(update_data["tags"])
        if "path_params" in update_data and update_data["path_params"] is not None:
            test_case.path_params_json = json.dumps(update_data["path_params"])
        if "query_params" in update_data and update_data["query_params"] is not None:
            test_case.query_params_json = json.dumps(update_data["query_params"])
        if "headers" in update_data and update_data["headers"] is not None:
            test_case.headers_json = json.dumps(update_data["headers"])
        if "body_type" in update_data and update_data["body_type"] is not None:
            bt = update_data["body_type"]
            test_case.body_type = bt.value if hasattr(bt, "value") else str(bt)
        if "body" in update_data:
            body_val = update_data["body"]
            test_case.body_json = json.dumps(body_val) if isinstance(body_val, (dict, list)) else (str(body_val) if body_val is not None else None)
        if "assertions" in update_data and update_data["assertions"] is not None:
            test_case.assertions_json = json.dumps(update_data["assertions"])

        test_case.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(test_case)
        logger.info(f"Updated TestCase #{test_case.id}: '{test_case.name}'")
        return test_case

    @classmethod
    def delete_test_case(cls, db: Session, test_case_id: int) -> bool:
        """Delete a test scenario by ID."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            return False

        db.delete(test_case)
        db.commit()
        logger.info(f"Deleted TestCase #{test_case_id}")
        return True

    @classmethod
    def toggle_test_case_active(cls, db: Session, test_case_id: int) -> Optional[TestCase]:
        """Toggle the active state of a test case."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            return None

        test_case.is_active = not test_case.is_active
        test_case.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(test_case)
        logger.info(f"Toggled TestCase #{test_case.id} active state to: {test_case.is_active}")
        return test_case

    @classmethod
    def duplicate_test_case(
        cls,
        db: Session,
        test_case_id: int,
        new_name: Optional[str] = None
    ) -> Optional[TestCase]:
        """Clone an existing test scenario."""
        original = cls.get_test_case_by_id(db, test_case_id)
        if not original:
            return None

        cloned_name = new_name.strip() if new_name else f"{original.name} (Copy)"

        cloned = TestCase(
            endpoint_id=original.endpoint_id,
            name=cloned_name,
            description=original.description,
            is_active=original.is_active,
            severity=original.severity,
            tags_json=original.tags_json,
            path_params_json=original.path_params_json,
            query_params_json=original.query_params_json,
            headers_json=original.headers_json,
            body_type=original.body_type,
            body_json=original.body_json,
            assertions_json=original.assertions_json
        )

        db.add(cloned)
        db.commit()
        db.refresh(cloned)
        logger.info(f"Duplicated TestCase #{test_case_id} -> New TestCase #{cloned.id}: '{cloned.name}'")
        return cloned

    @classmethod
    def get_test_case_assertions(cls, db: Session, test_case_id: int) -> Optional[TestCaseAssertions]:
        """Fetch parsed TestCaseAssertions for a specific test case."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            return None
        return TestCaseAssertions(**test_case.assertions)

    @classmethod
    def update_test_case_assertions(
        cls,
        db: Session,
        test_case_id: int,
        dto: TestCaseAssertions
    ) -> Optional[TestCase]:
        """Update structured assertion rules for a test scenario."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            return None

        test_case.assertions_json = json.dumps(dto.model_dump(exclude_unset=True))
        test_case.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(test_case)
        logger.info(f"Updated assertions for TestCase #{test_case_id}")
        return test_case

    @classmethod
    async def evaluate_test_case(
        cls,
        db: Session,
        test_case_id: int,
        client: Optional[httpx.AsyncClient] = None
    ) -> TestCaseExecutionEvaluationResponse:
        """Execute a test case scenario and evaluate all assertion rules against the live response telemetry."""
        test_case = cls.get_test_case_by_id(db, test_case_id)
        if not test_case:
            raise ValueError(f"TestCase #{test_case_id} not found.")

        endpoint = db.query(Endpoint).filter(Endpoint.id == test_case.endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Parent Endpoint #{test_case.endpoint_id} not found.")

        project = db.query(Project).filter(Project.id == endpoint.project_id).first()
        if not project:
            raise ValueError(f"Parent Project #{endpoint.project_id} not found.")

        # Build runtime request override using test case configurations
        override = RequestCompileOverride(
            path_params=test_case.path_params,
            query_params=test_case.query_params,
            headers=test_case.headers,
            body_type=test_case.body_type,
            body=test_case.body
        )

        httpx_req, compiled_req = RequestBuilderService.compile_endpoint_request(
            project=project,
            endpoint=endpoint,
            overrides=override
        )

        # Dispatch execution
        exec_res = await HttpDispatcherService.dispatch_httpx_request(
            request=httpx_req,
            options=None,
            client=client
        )

        # Run assertion evaluation
        assertion_report = evaluate_assertions(
            assertions=test_case.assertions,
            status_code=exec_res.status_code,
            latency_ms=exec_res.elapsed_ms,
            headers=exec_res.headers,
            body=exec_res.body,
            content_type=exec_res.content_type or exec_res.headers.get("content-type") or exec_res.headers.get("Content-Type"),
            test_case_id=test_case.id,
            test_case_name=test_case.name
        )

        return TestCaseExecutionEvaluationResponse(
            test_case_id=test_case.id,
            test_case_name=test_case.name,
            endpoint_id=endpoint.id,
            http_method=compiled_req.method,
            target_url=compiled_req.url,
            status_code=exec_res.status_code,
            latency_ms=exec_res.elapsed_ms,
            response_headers=exec_res.headers,
            response_body=exec_res.body,
            assertion_report=assertion_report
        )

