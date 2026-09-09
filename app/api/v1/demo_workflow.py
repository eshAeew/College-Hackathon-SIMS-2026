"""REST API endpoints for the 14-Step Demo Workflow and Presentation Playbook."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.demo_workflow import (
    DemoBootstrapResponse,
    DemoPitchPlaybookResponse,
    DemoStoryResponse,
)
from app.services.demo_workflow_service import DemoWorkflowService

router = APIRouter(prefix="/demo", tags=["Demo Workflow & Pitch Playbook"])


@router.post("/bootstrap", response_model=DemoBootstrapResponse, summary="1. Bootstrap Demo Workspace")
def bootstrap_demo_workspace(
    db: Session = Depends(get_db),
):
    """Initialize the Alpha Commerce Demo Store workspace with 6 endpoints and test cases."""
    return DemoWorkflowService.bootstrap_demo(db=db)


@router.post("/execute-phase-1", summary="2. Execute Phase 1 Baseline (Flawed Target)")
def execute_phase_1(
    db: Session = Depends(get_db),
):
    """Execute baseline test run against the intentionally flawed demo target and collect diagnostics."""
    return DemoWorkflowService.execute_phase_1_baseline(db=db)


@router.post("/apply-fixes", summary="3. Apply Remediations to Target API")
def apply_fixes():
    """Simulate applying developer code fixes to resolve all 6 demo API bugs."""
    return DemoWorkflowService.apply_demo_fixes()


@router.post("/execute-phase-2", summary="4. Execute Phase 2 Verification & Diff")
def execute_phase_2(
    baseline_run_id: Optional[int] = Query(None, description="Baseline run ID for regression diffing"),
    db: Session = Depends(get_db),
):
    """Execute verification test run against the fixed target and compute comparison diff."""
    return DemoWorkflowService.execute_phase_2_verification(db=db, baseline_run_id=baseline_run_id)


@router.post("/run-complete-story", response_model=DemoStoryResponse, summary="5. 1-Click Run Complete 14-Step Demo Story")
def run_complete_story(
    db: Session = Depends(get_db),
):
    """Autonomous 1-click execution of the entire 14-step before->detection->fix->verification story."""
    return DemoWorkflowService.run_complete_story(db=db)


@router.get("/playbook", response_model=DemoPitchPlaybookResponse, summary="6. Get 3-Minute Pitch Playbook")
def get_pitch_playbook():
    """Retrieve the structured 3-minute pitch timeline, cues, and judge Q&A cheatsheet."""
    return DemoWorkflowService.get_pitch_playbook()
