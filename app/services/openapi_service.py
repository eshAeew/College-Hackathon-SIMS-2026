"""Service Layer for OpenAPI Parsing, Validation, and Endpoint Ingestion (Stage 14)."""
import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.entities.endpoint import Endpoint
from app.models.entities.project import Project
from app.models.entities.test_case import TestCase
from app.models.schemas.openapi import (
    ImportedEndpointDetail,
    OpenApiImportReport,
    OpenApiImportRequest,
    ParsedOpenApiSummary,
)
from app.utils.openapi_parser import (
    detect_spec_format_and_parse,
    parse_openapi_document,
)

logger = logging.getLogger("app.services.openapi")


class OpenApiService:
    """Service providing parsing, validation, and database import for OpenAPI/Swagger specifications."""

    @classmethod
    def validate_and_parse_spec(cls, spec_content: str) -> ParsedOpenApiSummary:
        """Parse raw YAML or JSON specification string into structured in-memory model."""
        raw_doc = detect_spec_format_and_parse(spec_content)
        return parse_openapi_document(raw_doc)

    @classmethod
    def import_spec_into_project(
        cls,
        project_id: int,
        req: OpenApiImportRequest,
        db: Session
    ) -> OpenApiImportReport:
        """
        Parse OpenAPI document and upsert/insert discovered Endpoint records into the SQLite database.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project #{project_id} not found.")

        parsed_summary = cls.validate_and_parse_spec(req.spec_content)
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        imported_details: List[ImportedEndpointDetail] = []

        # Update Project base_url if not set and spec has servers
        if (not project.base_url or project.base_url == "https://api.example.com") and parsed_summary.servers:
            project.base_url = parsed_summary.servers[0]
            db.commit()

        for op in parsed_summary.operations:
            # Query existing endpoint matching (project_id, method, path)
            existing = db.query(Endpoint).filter(
                Endpoint.project_id == project.id,
                Endpoint.method == op.method,
                Endpoint.path == op.path
            ).first()

            # Prepare response schema JSON
            resp_schema_json = "{}"
            if op.response_schemas:
                # Priority: 200 / 201 schema, or first available
                primary_schema = (
                    op.response_schemas.get(str(op.expected_status_code))
                    or op.response_schemas.get("200")
                    or op.response_schemas.get("201")
                    or next(iter(op.response_schemas.values()))
                )
                resp_schema_json = json.dumps(primary_schema)

            if existing:
                if req.overwrite_existing:
                    existing.name = op.summary or f"{op.method} {op.path}"
                    existing.description = op.description or existing.description
                    existing.headers_json = json.dumps(op.header_parameters)
                    existing.query_params_json = json.dumps(op.query_parameters)
                    existing.path_params_json = json.dumps(op.path_parameters)
                    existing.body_schema_json = json.dumps(op.request_body_schema) if op.request_body_schema else "{}"
                    existing.response_schema_json = resp_schema_json
                    existing.expected_status = op.expected_status_code
                    
                    db.commit()
                    db.refresh(existing)
                    updated_count += 1
                    imported_details.append(
                        ImportedEndpointDetail(
                            id=existing.id,
                            name=existing.name,
                            method=existing.method,
                            path=existing.path,
                            status="UPDATED"
                        )
                    )
                else:
                    skipped_count += 1
                    imported_details.append(
                        ImportedEndpointDetail(
                            id=existing.id,
                            name=existing.name,
                            method=existing.method,
                            path=existing.path,
                            status="SKIPPED"
                        )
                    )
            else:
                # Create brand new Endpoint entity
                new_ep = Endpoint(
                    project_id=project.id,
                    name=op.summary or f"{op.method} {op.path}",
                    description=op.description,
                    method=op.method,
                    path=op.path,
                    headers_json=json.dumps(op.header_parameters),
                    query_params_json=json.dumps(op.query_parameters),
                    path_params_json=json.dumps(op.path_parameters),
                    body_schema_json=json.dumps(op.request_body_schema) if op.request_body_schema else "{}",
                    response_schema_json=resp_schema_json,
                    expected_status=op.expected_status_code,
                    is_active=True
                )
                db.add(new_ep)
                db.commit()
                db.refresh(new_ep)

                # Optionally generate default smoke test case
                if req.create_smoke_tests:
                    smoke_tc = TestCase(
                        endpoint_id=new_ep.id,
                        name=f"Smoke - {new_ep.name}",
                        description=f"Auto-generated smoke test from OpenAPI specification",
                        severity="high",
                        tags_json=json.dumps(["smoke", "auto-generated"]),
                        path_params_json=json.dumps(op.path_parameters),
                        query_params_json=json.dumps(op.query_parameters),
                        headers_json=json.dumps(op.header_parameters),
                        body_type=op.request_body_type,
                        body_json=json.dumps({}) if op.request_body_schema else None,
                        assertions_json=json.dumps({"expected_status": op.expected_status_code})
                    )
                    db.add(smoke_tc)
                    db.commit()

                created_count += 1
                imported_details.append(
                    ImportedEndpointDetail(
                        id=new_ep.id,
                        name=new_ep.name,
                        method=new_ep.method,
                        path=new_ep.path,
                        status="CREATED"
                    )
                )

        logger.info(
            f"Imported OpenAPI spec '{parsed_summary.title}' into Project #{project_id}: "
            f"{created_count} created, {updated_count} updated, {skipped_count} skipped."
        )

        return OpenApiImportReport(
            project_id=project.id,
            spec_title=parsed_summary.title,
            spec_version=parsed_summary.version,
            total_discovered=parsed_summary.total_operations,
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            endpoints=imported_details
        )
