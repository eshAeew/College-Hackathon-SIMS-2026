"""Pydantic schemas and DTOs for the Final Demo Workflow and Presentation Story."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DemoStepResult(BaseModel):
    """Execution output for an individual step in the 14-step demonstration."""
    step_number: int
    title: str
    action: str
    status: str  # COMPLETED, SKIPPED, FAILED
    headline: str
    details: Dict[str, Any] = Field(default_factory=dict)
    key_findings: List[str] = Field(default_factory=list)


class DemoBootstrapResponse(BaseModel):
    """Response returned when initializing demo workspace and test cases."""
    project_id: int
    project_name: str
    base_url: str
    endpoints_imported: int
    test_cases_created: int
    status: str
    message: str


class DemoStoryResponse(BaseModel):
    """Full end-to-end execution record of the 14-step demonstration story."""
    story_id: str
    project_id: int
    project_name: str
    total_steps: int
    completed_steps: int
    phase_1_baseline_run_id: Optional[int] = None
    phase_1_failures_detected: int = 0
    phase_2_verification_run_id: Optional[int] = None
    phase_2_pass_rate: float = 0.0
    regression_verdict: str = "PENDING"  # ALL_BUGS_RESOLVED, PARTIAL, FAILED
    steps: List[DemoStepResult]
    executed_at: str


class PitchSection(BaseModel):
    """A distinct segment of the 3-minute hackathon presentation."""
    time_stamp: str  # e.g. "0:00 - 0:30"
    title: str
    presenter_dialogue: str
    ui_action: str
    key_takeaway: str


class DemoPitchPlaybookResponse(BaseModel):
    """Complete presentation playbook with 3-minute script, step-by-step guide, and QA cheatsheet."""
    title: str
    target_time_limit: str
    elevator_pitch: str
    the_problem: str
    the_solution: str
    pitch_timeline: List[PitchSection]
    judge_qa_cheatsheet: List[Dict[str, str]]
    generated_at: str
