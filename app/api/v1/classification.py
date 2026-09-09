"""REST API Router for Result Classification Engine (Stage 17)."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.response import StandardResponse
from app.models.schemas.result_classification import (
    BatchClassificationReport,
    BatchClassificationRequest,
    ClassifiedResultReport,
    ExecutionClassificationInput,
    TestRunClassificationReport,
)
from app.services.result_classification_service import ResultClassificationService

logger = logging.getLogger("app.api.v1.classification")

router = APIRouter(tags=["Result Classification Engine"])


@router.post(
    "/classification/classify",
    response_model=StandardResponse[ClassifiedResultReport],
    summary="Classify Single Execution Result",
    status_code=status.HTTP_200_OK
)
def classify_single_execution(
    item: ExecutionClassificationInput
):
    """
    Evaluates execution telemetry against the 4-tier decision matrix (PASS, FAIL, WARNING, ERROR) and assigns impact severity.
    """
    try:
        result = ResultClassificationService.classify_single(item)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Classified as {result.outcome.value} ({result.severity.value} Severity): {result.title}"
        )
    except Exception as e:
        logger.error(f"Failed to classify execution: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/classification/classify-batch",
    response_model=StandardResponse[BatchClassificationReport],
    summary="Classify Batch Execution Results",
    status_code=status.HTTP_200_OK
)
def classify_batch_executions(
    req: BatchClassificationRequest
):
    """
    Processes a batch of execution items, generating summary KPI cards, health index score, and prioritized failure queues.
    """
    try:
        result = ResultClassificationService.classify_batch(req)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Classified {result.summary.total_executions} executions (Health Index: {result.summary.health_score_index}%)."
        )
    except Exception as e:
        logger.error(f"Failed to classify batch: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/runs/{run_id}/classification",
    response_model=StandardResponse[TestRunClassificationReport],
    summary="Get Classification Breakdown for Test Run",
    status_code=status.HTTP_200_OK
)
def get_test_run_classification(
    run_id: int,
    db: Session = Depends(get_db)
):
    """
    Analyzes all executed test results in a specific TestRun through the classification matrix.
    """
    try:
        result = ResultClassificationService.classify_test_run(run_id=run_id, db=db)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Classification report for TestRun #{run_id} generated."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to classify TestRun #{run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/projects/{project_id}/classification/latest",
    response_model=StandardResponse[TestRunClassificationReport],
    summary="Get Latest Run Classification for Project",
    status_code=status.HTTP_200_OK
)
def get_project_latest_classification(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieves and classifies the most recent TestRun executed for a project.
    """
    try:
        result = ResultClassificationService.classify_project_latest(project_id=project_id, db=db)
        return StandardResponse(
            success=True,
            data=result,
            message=f"Latest classification report for Project #{project_id} generated."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to classify latest run for project #{project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
