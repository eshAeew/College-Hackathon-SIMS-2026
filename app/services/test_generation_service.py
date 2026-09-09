"""Service layer for Automated Test Generation and Staging Acceptance (Stage 15)."""
import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.schemas.test_generation import (
    AcceptStagedTestsRequest,
    AcceptStagedTestsResponse,
    AdHocTestGenerationRequest,
    BulkProjectTestGenerationRequest,
    BulkProjectTestGenerationResponse,
    GeneratedTestCategory,
    StagedTestCase,
    TestGenerationOptions,
    TestGenerationStagingResponse,
)
from app.utils.test_synthesizer import generate_test_suite_for_endpoint

logger = logging.getLogger("app.services.test_generation")


class TestGenerationService:
    """Service providing combinatorial test case synthesis and staging management."""

    @classmethod
    def generate_adhoc_tests(cls, req: AdHocTestGenerationRequest) -> TestGenerationStagingResponse:
        """Synthesize test cases from raw route, parameter, and schema specifications."""
        staged = generate_test_suite_for_endpoint(
            method=req.method,
            path=req.path,
            headers=req.headers,
            query_params=req.query_params,
            path_params=req.path_params,
            body_schema=req.body_schema,
            expected_status=req.expected_status,
            options=req.options
        )

        pos_count = sum(1 for t in staged if t.category == GeneratedTestCategory.POSITIVE)
        neg_count = len(staged) - pos_count

        return TestGenerationStagingResponse(
            endpoint_id=None,
            endpoint_name=f"{req.method.upper()} {req.path}",
            method=req.method.upper(),
            path=req.path,
            total_generated=len(staged),
            positive_count=pos_count,
            negative_count=neg_count,
            staged_tests=staged
        )

    @classmethod
    def generate_endpoint_tests(
        cls,
        endpoint_id: int,
        options: TestGenerationOptions,
        db: Session
    ) -> TestGenerationStagingResponse:
        """Synthesize staged test cases for a registered database Endpoint entity."""
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Endpoint #{endpoint_id} not found.")

        staged = generate_test_suite_for_endpoint(
            method=endpoint.method,
            path=endpoint.path,
            headers=endpoint.headers,
            query_params=endpoint.query_params,
            path_params=endpoint.path_params,
            body_schema=endpoint.body_schema,
            expected_status=endpoint.expected_status,
            options=options
        )

        pos_count = sum(1 for t in staged if t.category == GeneratedTestCategory.POSITIVE)
        neg_count = len(staged) - pos_count

        return TestGenerationStagingResponse(
            endpoint_id=endpoint.id,
            endpoint_name=endpoint.name,
            method=endpoint.method.upper(),
            path=endpoint.path,
            total_generated=len(staged),
            positive_count=pos_count,
            negative_count=neg_count,
            staged_tests=staged
        )

    @classmethod
    def accept_staged_tests(
        cls,
        endpoint_id: int,
        req: AcceptStagedTestsRequest,
        db: Session
    ) -> AcceptStagedTestsResponse:
        """
        Persist approved and selected staged test cases into the database as TestCase records.
        """
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise ValueError(f"Endpoint #{endpoint_id} not found.")

        created_ids: List[int] = []
        for staged in req.staged_tests:
            if not staged.is_selected:
                continue

            tc = TestCase(
                endpoint_id=endpoint.id,
                name=staged.name,
                description=staged.description,
                is_active=req.activate_immediately,
                severity=staged.severity.value,
                tags_json=json.dumps(staged.tags),
                path_params_json=json.dumps(staged.path_params),
                query_params_json=json.dumps(staged.query_params),
                headers_json=json.dumps(staged.headers),
                body_type=staged.body_type.value,
                body_json=json.dumps(staged.body) if staged.body is not None else None,
                assertions_json=json.dumps(staged.assertions)
            )
            db.add(tc)
            db.flush()
            created_ids.append(tc.id)

        db.commit()
        logger.info(
            f"Accepted {len(created_ids)} staged test cases under Endpoint #{endpoint_id} ('{endpoint.name}')"
        )

        return AcceptStagedTestsResponse(
            endpoint_id=endpoint.id,
            total_accepted=len(created_ids),
            created_test_case_ids=created_ids,
            message=f"Successfully persisted {len(created_ids)} generated test cases."
        )

    @classmethod
    def generate_project_bulk_tests(
        cls,
        project_id: int,
        req: BulkProjectTestGenerationRequest,
        db: Session
    ) -> BulkProjectTestGenerationResponse:
        """Synthesize test suites across multiple or all endpoints in a project."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        query = db.query(Endpoint).filter(Endpoint.project_id == project.id, Endpoint.is_active == True)
        if req.endpoint_ids:
            query = query.filter(Endpoint.id.in_(req.endpoint_ids))

        endpoints = query.all()
        endpoint_results: List[TestGenerationStagingResponse] = []
        total_tests_generated = 0
        total_tests_accepted = 0

        for ep in endpoints:
            staged_resp = cls.generate_endpoint_tests(endpoint_id=ep.id, options=req.options, db=db)
            endpoint_results.append(staged_resp)
            total_tests_generated += staged_resp.total_generated

            if req.auto_accept and staged_resp.staged_tests:
                accept_resp = cls.accept_staged_tests(
                    endpoint_id=ep.id,
                    req=AcceptStagedTestsRequest(
                        staged_tests=staged_resp.staged_tests,
                        activate_immediately=True
                    ),
                    db=db
                )
                total_tests_accepted += accept_resp.total_accepted

        return BulkProjectTestGenerationResponse(
            project_id=project.id,
            total_endpoints_processed=len(endpoints),
            total_tests_generated=total_tests_generated,
            total_tests_accepted=total_tests_accepted,
            endpoint_results=endpoint_results
        )
