"""FastAPI REST router for OpenAPI 3.0 / Swagger 2.0 Specification Ingestion (Stage 14)."""
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.openapi import (
    OpenApiImportReport,
    OpenApiImportRequest,
    OpenApiParseRequest,
    ParsedOpenApiSummary,
)
from app.models.schemas.response import StandardResponse
from app.services.openapi_service import OpenApiService

logger = logging.getLogger("app.api.v1.openapi")
router = APIRouter(tags=["OpenAPI Specification Support"])


@router.post(
    "/openapi/validate",
    response_model=StandardResponse[ParsedOpenApiSummary],
    summary="Validate and Parse OpenAPI Document",
    description="Validates raw YAML or JSON OpenAPI/Swagger content without requiring a project."
)
def validate_openapi_document(
    req: OpenApiParseRequest
):
    """Validate and parse raw OpenAPI/Swagger document."""
    try:
        summary = OpenApiService.validate_and_parse_spec(req.spec_content)
        return StandardResponse(
            success=True,
            data=summary,
            message=f"Specification '{summary.title}' v{summary.version} ({summary.spec_version.value}) parsed successfully with {summary.total_operations} operation(s)"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"OpenAPI validation error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to parse specification: {e}")


@router.post(
    "/projects/{project_id}/openapi/parse",
    response_model=StandardResponse[ParsedOpenApiSummary],
    summary="Dry-Run Preview OpenAPI Import for Project",
    description="Previews all operations, parameters, and contracts discovered in the OpenAPI document before importing."
)
def preview_project_openapi_spec(
    project_id: int,
    req: OpenApiParseRequest,
    db: Session = Depends(get_db)
):
    """Preview OpenAPI spec operations for a project."""
    try:
        summary = OpenApiService.validate_and_parse_spec(req.spec_content)
        return StandardResponse(
            success=True,
            data=summary,
            message=f"Discovered {summary.total_operations} endpoint(s) ready for import into Project #{project_id}"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/projects/{project_id}/openapi/import",
    response_model=StandardResponse[OpenApiImportReport],
    status_code=status.HTTP_201_CREATED,
    summary="Import OpenAPI Specification into Project",
    description="Parses the OpenAPI document and creates or updates Endpoint database entities with full contracts."
)
def import_openapi_spec_into_project(
    project_id: int,
    req: OpenApiImportRequest,
    db: Session = Depends(get_db)
):
    """Import OpenAPI operations into project database."""
    try:
        report = OpenApiService.import_spec_into_project(project_id, req, db)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Import completed: {report.created_count} created, {report.updated_count} updated, {report.skipped_count} skipped"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"OpenAPI import error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Import failed: {e}")


@router.post(
    "/projects/{project_id}/openapi/import-file",
    response_model=StandardResponse[OpenApiImportReport],
    status_code=status.HTTP_201_CREATED,
    summary="Upload and Import OpenAPI File",
    description="Uploads a .yaml, .yml, or .json file to automatically populate project endpoints."
)
async def upload_and_import_openapi_file(
    project_id: int,
    file: UploadFile = File(...),
    overwrite_existing: bool = Form(True),
    create_smoke_tests: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Handle multipart file upload for OpenAPI YAML/JSON importing."""
    try:
        content_bytes = await file.read()
        spec_content = content_bytes.decode("utf-8")
        req = OpenApiImportRequest(
            spec_content=spec_content,
            overwrite_existing=overwrite_existing,
            create_smoke_tests=create_smoke_tests
        )
        report = OpenApiService.import_spec_into_project(project_id, req, db)
        return StandardResponse(
            success=True,
            data=report,
            message=f"Uploaded '{file.filename}' imported: {report.created_count} created, {report.updated_count} updated"
        )
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must be valid UTF-8 encoded text (YAML or JSON).")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"File import failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"File import failed: {e}")
