"""FastAPI REST router for Test Run Management and Lifecycle Orchestration."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.test_run import (
    TestResultResponse,
    TestRunCancelRequest,
    TestRunCreateRequest,
    TestRunDetailResponse,
    TestRunSummaryResponse,
)
from app.services.test_run_service import TestRunService
from app.utils.run_state_machine import InvalidStateTransitionError

logger = logging.getLogger("app.api.v1.test_runs")
router = APIRouter(tags=["Test Run Management"])


@router.post(
    "/projects/{project_id}/runs",
    response_model=StandardResponse[TestRunDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create and Launch a Test Run"
)
async def create_and_launch_test_run(
    project_id: int,
    req: TestRunCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Queue and optionally execute a full test suite run across project endpoints.
    """
    try:
        test_run = TestRunService.create_test_run(project_id, req, db)
        if req.execute_immediately:
            test_run = await TestRunService.execute_test_run(test_run.id, db)
        detail = TestRunService.format_detail(test_run)
        return StandardResponse(
            success=True,
            data=detail,
            message=f"Test Run #{test_run.id} initiated successfully with status '{test_run.status}'"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to launch test run: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Execution failed: {e}")


@router.get(
    "/projects/{project_id}/runs",
    response_model=StandardResponse[List[TestRunSummaryResponse]],
    summary="List Project Test Runs"
)
def list_project_test_runs(
    project_id: int,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by RunStatus"),
    db: Session = Depends(get_db)
):
    """List historical test runs for a project."""
    runs = TestRunService.list_project_runs(project_id, db, status=status_filter)
    summaries = [TestRunService.format_summary(r) for r in runs]
    return StandardResponse(
        success=True,
        data=summaries,
        message=f"Retrieved {len(summaries)} test runs for Project #{project_id}"
    )


@router.get(
    "/runs/{run_id}",
    response_model=StandardResponse[TestRunDetailResponse],
    summary="Get Test Run Details and Results"
)
def get_test_run_details(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve test run summary and detailed individual results."""
    try:
        run = TestRunService.get_test_run(run_id, db)
        detail = TestRunService.format_detail(run)
        return StandardResponse(
            success=True,
            data=detail,
            message=f"Retrieved details for Test Run #{run_id}"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/runs/{run_id}/execute",
    response_model=StandardResponse[TestRunDetailResponse],
    summary="Execute a Queued Test Run"
)
async def execute_queued_test_run(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Trigger execution for a previously queued test run."""
    try:
        run = await TestRunService.execute_test_run(run_id, db)
        detail = TestRunService.format_detail(run)
        return StandardResponse(
            success=True,
            data=detail,
            message=f"Test Run #{run_id} executed successfully"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/runs/{run_id}/cancel",
    response_model=StandardResponse[TestRunSummaryResponse],
    summary="Cancel a Test Run"
)
def cancel_test_run(
    run_id: int,
    req: TestRunCancelRequest,
    db: Session = Depends(get_db)
):
    """Cancel an active or queued test run."""
    try:
        run = TestRunService.cancel_test_run(run_id, req.reason or "Cancelled by user", db)
        summary = TestRunService.format_summary(run)
        return StandardResponse(
            success=True,
            data=summary,
            message=f"Test Run #{run_id} cancelled"
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/runs/{run_id}",
    response_model=StandardResponse[dict],
    summary="Delete a Test Run"
)
def delete_test_run(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Delete a test run and its associated execution records."""
    try:
        TestRunService.delete_test_run(run_id, db)
        return StandardResponse(
            success=True,
            data={"id": run_id, "deleted": True},
            message=f"Test Run #{run_id} deleted successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
