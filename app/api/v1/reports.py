"""Reporting & Export REST API Router (Stage 22)."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.report import ComprehensiveTestReport
from app.models.schemas.response import StandardResponse
from app.services.report_service import ReportService

logger = logging.getLogger("app.api.v1.reports")

router = APIRouter(prefix="/reports", tags=["Reporting & Export"])


@router.get(
    "/runs/{run_id}",
    response_model=StandardResponse[ComprehensiveTestReport],
    status_code=status.HTTP_200_OK,
    summary="Get Comprehensive Test Run Report (JSON)",
    description="Returns a complete 6-section diagnostic test execution report including executive summary, functional results, performance stats, regressions, and AI recommendations."
)
def get_test_run_report(
    run_id: int,
    baseline_run_id: Optional[int] = Query(None, description="Optional baseline run ID for regression comparisons"),
    db: Session = Depends(get_db)
):
    """Retrieve structured diagnostic JSON report for a test run."""
    try:
        report = ReportService.generate_report(run_id, db, baseline_run_id=baseline_run_id)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Generated report for TestRun #{run_id} (Verdict: {report.summary.verdict.value})"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error generating report for TestRun #{run_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate report: {e}")


@router.get(
    "/runs/{run_id}/html",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Export Standalone HTML Report",
    description="Renders a self-contained, responsive, printable HTML diagnostic report in dark cyberpunk aesthetic."
)
def get_test_run_html_report(
    run_id: int,
    baseline_run_id: Optional[int] = Query(None, description="Optional baseline run ID for regression comparisons"),
    db: Session = Depends(get_db)
):
    """Retrieve printable standalone HTML report."""
    try:
        report = ReportService.generate_report(run_id, db, baseline_run_id=baseline_run_id)
        html_content = ReportService.generate_html_report(report)
        return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error rendering HTML report for TestRun #{run_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to render HTML report: {e}")


@router.get(
    "/runs/{run_id}/markdown",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Export Markdown Report",
    description="Renders a GitHub-flavored Markdown report suitable for CI/CD pipeline summaries and pull request comments."
)
def get_test_run_markdown_report(
    run_id: int,
    baseline_run_id: Optional[int] = Query(None, description="Optional baseline run ID for regression comparisons"),
    db: Session = Depends(get_db)
):
    """Retrieve markdown-formatted test report."""
    try:
        report = ReportService.generate_report(run_id, db, baseline_run_id=baseline_run_id)
        md_content = ReportService.generate_markdown_report(report)
        return PlainTextResponse(content=md_content, media_type="text/markdown", status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error rendering markdown report for TestRun #{run_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to render markdown report: {e}")


@router.get(
    "/runs/{run_id}/download",
    summary="Download Standalone Report File",
    description="Triggers file download of the report in HTML, Markdown, or JSON format."
)
def download_test_run_report(
    run_id: int,
    format: str = Query("html", regex="^(html|md|json)$", description="Target file format (html, md, json)"),
    baseline_run_id: Optional[int] = Query(None, description="Optional baseline run ID"),
    db: Session = Depends(get_db)
):
    """Download report as a file attachment."""
    try:
        report = ReportService.generate_report(run_id, db, baseline_run_id=baseline_run_id)
        fmt = format.lower()
        if fmt == "html":
            content = ReportService.generate_html_report(report)
            media_type = "text/html"
            filename = f"api_sentinel_report_run_{run_id}.html"
        elif fmt == "md":
            content = ReportService.generate_markdown_report(report)
            media_type = "text/markdown"
            filename = f"api_sentinel_report_run_{run_id}.md"
        else:
            content = report.model_dump_json(indent=2)
            media_type = "application/json"
            filename = f"api_sentinel_report_run_{run_id}.json"

        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error downloading report for TestRun #{run_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to download report: {e}")
