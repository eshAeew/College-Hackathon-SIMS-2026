"""API Router for TestCase Management, Tagging, Duplication, and Filtering."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.test_case import (
    AdHocAssertionEvaluationRequest,
    TestCaseAssertions,
    TestCaseAssertionReport,
    TestCaseCreate,
    TestCaseDuplicate,
    TestCaseExecutionEvaluationResponse,
    TestCaseResponse,
    TestCaseSeverity,
    TestCaseUpdate,
)
from app.services.endpoint_service import EndpointService
from app.services.test_case_service import TestCaseService
from app.utils.assertion_engine import evaluate_assertions

router = APIRouter(tags=["Test Case Management"])


def _format_test_case_response(test_case) -> TestCaseResponse:
    """Helper converting SQLAlchemy TestCase entity to Pydantic TestCaseResponse DTO."""
    return TestCaseResponse(
        id=test_case.id,
        endpoint_id=test_case.endpoint_id,
        name=test_case.name,
        description=test_case.description,
        is_active=test_case.is_active,
        severity=TestCaseSeverity(test_case.severity) if test_case.severity in [s.value for s in TestCaseSeverity] else TestCaseSeverity.MEDIUM,
        tags=test_case.tags,
        path_params=test_case.path_params,
        query_params=test_case.query_params,
        headers=test_case.headers,
        body_type=test_case.body_type,
        body=test_case.body,
        assertions=test_case.assertions,
        created_at=test_case.created_at,
        updated_at=test_case.updated_at
    )


@router.post(
    "/endpoints/{endpoint_id}/test-cases",
    response_model=StandardResponse[TestCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create Test Case Scenario",
    description="Registers a new functional test case scenario under a specific API endpoint."
)
async def create_test_case(
    endpoint_id: int,
    test_case_dto: TestCaseCreate,
    db: Session = Depends(get_db)
):
    """Create a new TestCase record."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    try:
        created = TestCaseService.create_test_case(db, endpoint_id, test_case_dto)
        return StandardResponse(
            success=True,
            data=_format_test_case_response(created),
            message=f"Test case '{created.name}' created successfully under Endpoint #{endpoint_id}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create test case: {str(exc)}"
        )


@router.get(
    "/endpoints/{endpoint_id}/test-cases",
    response_model=StandardResponse[List[TestCaseResponse]],
    summary="List Test Cases for Endpoint",
    description="Lists all test cases for an endpoint, with support for filtering by tag, severity, and active status."
)
async def list_test_cases(
    endpoint_id: int,
    tag: Optional[str] = Query(None, description="Filter by tag (e.g. 'smoke', 'regression')"),
    severity: Optional[str] = Query(None, description="Filter by severity ('critical', 'high', 'medium', 'low')"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Pagination limit"),
    db: Session = Depends(get_db)
):
    """List test cases under an endpoint."""
    endpoint = EndpointService.get_endpoint_by_id(db, endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint #{endpoint_id} not found"
        )

    test_cases = TestCaseService.get_test_cases(
        db=db,
        endpoint_id=endpoint_id,
        tag=tag,
        severity=severity,
        is_active=is_active,
        skip=skip,
        limit=limit
    )

    formatted = [_format_test_case_response(tc) for tc in test_cases]
    return StandardResponse(
        success=True,
        data=formatted,
        message=f"Retrieved {len(formatted)} test case(s) for Endpoint #{endpoint_id}"
    )


@router.get(
    "/test-cases/{test_case_id}",
    response_model=StandardResponse[TestCaseResponse],
    summary="Get Test Case Details",
    description="Fetches detailed configuration of a specific test scenario."
)
async def get_test_case(
    test_case_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve test case by ID."""
    test_case = TestCaseService.get_test_case_by_id(db, test_case_id)
    if not test_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data=_format_test_case_response(test_case),
        message=f"Retrieved test case #{test_case_id}"
    )


@router.put(
    "/test-cases/{test_case_id}",
    response_model=StandardResponse[TestCaseResponse],
    summary="Update Test Case",
    description="Updates existing test scenario parameters and assertions."
)
async def update_test_case(
    test_case_id: int,
    update_dto: TestCaseUpdate,
    db: Session = Depends(get_db)
):
    """Update test case by ID."""
    updated = TestCaseService.update_test_case(db, test_case_id, update_dto)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data=_format_test_case_response(updated),
        message=f"Updated test case #{test_case_id}"
    )


@router.delete(
    "/test-cases/{test_case_id}",
    response_model=StandardResponse[dict],
    summary="Delete Test Case",
    description="Permanently removes a test case scenario."
)
async def delete_test_case(
    test_case_id: int,
    db: Session = Depends(get_db)
):
    """Delete test case by ID."""
    deleted = TestCaseService.delete_test_case(db, test_case_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data={"deleted_id": test_case_id},
        message=f"Test case #{test_case_id} deleted successfully"
    )


@router.patch(
    "/test-cases/{test_case_id}/toggle-active",
    response_model=StandardResponse[TestCaseResponse],
    summary="Toggle Test Case Active State",
    description="Toggles the active state of a test scenario (enable/disable for test runs)."
)
async def toggle_test_case_active(
    test_case_id: int,
    db: Session = Depends(get_db)
):
    """Toggle active flag for a test case."""
    toggled = TestCaseService.toggle_test_case_active(db, test_case_id)
    if not toggled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    state_str = "enabled" if toggled.is_active else "disabled"
    return StandardResponse(
        success=True,
        data=_format_test_case_response(toggled),
        message=f"Test case #{test_case_id} is now {state_str}"
    )


@router.post(
    "/test-cases/{test_case_id}/duplicate",
    response_model=StandardResponse[TestCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate Test Case",
    description="Creates an exact clone of an existing test case with an optional custom name."
)
async def duplicate_test_case(
    test_case_id: int,
    duplicate_dto: TestCaseDuplicate = TestCaseDuplicate(),
    db: Session = Depends(get_db)
):
    """Duplicate an existing test case."""
    cloned = TestCaseService.duplicate_test_case(db, test_case_id, duplicate_dto.name)
    if not cloned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data=_format_test_case_response(cloned),
        message=f"Duplicated test case #{test_case_id} as new test case #{cloned.id} ('{cloned.name}')"
    )


@router.get(
    "/test-cases/{test_case_id}/assertions",
    response_model=StandardResponse[TestCaseAssertions],
    summary="Get Test Case Assertions",
    description="Retrieves the structured assertion rules and expectation configuration for a test scenario."
)
async def get_test_case_assertions(
    test_case_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve assertion rules for a test case."""
    assertions = TestCaseService.get_test_case_assertions(db, test_case_id)
    if assertions is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data=assertions,
        message=f"Retrieved assertions for test case #{test_case_id}"
    )


@router.put(
    "/test-cases/{test_case_id}/assertions",
    response_model=StandardResponse[TestCaseResponse],
    summary="Update Test Case Assertions",
    description="Configures or replaces the structured assertion rules and expectations for a test scenario."
)
async def update_test_case_assertions(
    test_case_id: int,
    assertions_dto: TestCaseAssertions,
    db: Session = Depends(get_db)
):
    """Update assertion rules for a test case."""
    updated = TestCaseService.update_test_case_assertions(db, test_case_id, assertions_dto)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case #{test_case_id} not found"
        )

    return StandardResponse(
        success=True,
        data=_format_test_case_response(updated),
        message=f"Updated assertions for test case #{test_case_id}"
    )


@router.post(
    "/test-cases/{test_case_id}/evaluate",
    response_model=StandardResponse[TestCaseExecutionEvaluationResponse],
    summary="Execute Test Case & Evaluate Assertions",
    description="Dispatches the test case HTTP request against the live endpoint and evaluates all configured assertions."
)
async def execute_and_evaluate_test_case(
    test_case_id: int,
    db: Session = Depends(get_db)
):
    """Execute test case and verify assertion rules against the response telemetry."""
    try:
        result = await TestCaseService.evaluate_test_case(db=db, test_case_id=test_case_id)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Executed TestCase #{test_case_id} - {'ALL ASSERTIONS PASSED' if result.assertion_report.all_passed else f'{result.assertion_report.failed_rules} ASSERTION(S) FAILED'}"
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test case execution/evaluation failed: {str(exc)}"
        )


@router.post(
    "/assertions/evaluate",
    response_model=StandardResponse[TestCaseAssertionReport],
    summary="Ad-Hoc Assertion Evaluation",
    description="Evaluates arbitrary assertion specifications against provided HTTP response telemetry."
)
async def evaluate_adhoc_assertions(
    request: AdHocAssertionEvaluationRequest
):
    """Evaluate assertions on provided response telemetry without needing a database entity."""
    report = evaluate_assertions(
        assertions=request.assertions,
        status_code=request.status_code,
        latency_ms=request.latency_ms,
        headers=request.headers,
        body=request.body,
        content_type=request.content_type
    )

    return StandardResponse(
        success=True,
        data=report,
        message=f"Evaluated {report.total_rules} assertion(s): {report.passed_rules} passed, {report.failed_rules} failed"
    )

