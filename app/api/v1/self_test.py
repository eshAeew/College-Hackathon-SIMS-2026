"""REST API endpoints for Platform Self-Testing and Subsystem Readiness Diagnostics."""
from typing import List, Optional
from fastapi import APIRouter, Query, status

from app.models.schemas.self_test import (
    SelfTestRunRequest,
    SelfTestRunResponse,
    SubsystemCategory,
    SubsystemHealthMatrixResponse,
    SuiteMetadata,
)
from app.services.self_test_service import SelfTestService

router = APIRouter(prefix="/self-test", tags=["Platform Self-Testing"])


@router.get("/suites", response_model=List[SuiteMetadata], summary="List Available Test Suites")
def list_test_suites():
    """Retrieve all available architectural subsystem test suites."""
    return SelfTestService.get_available_suites()


@router.post("/run", response_model=SelfTestRunResponse, summary="Execute Platform Self-Tests")
def run_self_tests(
    request: SelfTestRunRequest = SelfTestRunRequest(),
):
    """Trigger programmatic execution of self-test suites across subsystems."""
    return SelfTestService.run_self_tests(
        subsystem=request.subsystem,
        stop_on_first_error=request.stop_on_first_error,
        include_tracebacks=request.include_tracebacks,
    )


@router.get("/latest", response_model=SelfTestRunResponse, summary="Get Latest Self-Test Report")
def get_latest_self_test():
    """Retrieve the most recent self-testing execution results."""
    return SelfTestService.get_latest_run()


@router.get("/matrix", response_model=SubsystemHealthMatrixResponse, summary="Subsystem Health Matrix")
def get_health_matrix():
    """Retrieve the current health readiness matrix across all architectural subsystems."""
    return SelfTestService.get_health_matrix()
