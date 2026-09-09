"""Database Management, Health Probes, Maintenance, Backups & Seeding Engine."""
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import engine
from app.models.entities import Project, Endpoint, TestCase, TestRun, TestResult, AIRecommendation
from app.models.schemas.database import (
    DatabaseBackupResponse,
    DatabaseHealthResponse,
    DatabaseMaintenanceResult,
    DatabasePurgeResponse,
    DatabaseSeedResponse,
    TableRecordCounts,
)
from app.repositories import (
    ProjectRepository,
    EndpointRepository,
    TestCaseRepository,
    TestRunRepository,
    TestResultRepository,
    AIRecommendationRepository,
)

logger = logging.getLogger("app.services.database")
settings = get_settings()


class DatabaseService:
    """Service handling database diagnostics, PRAGMAs, vacuum, backups, retention, and seeding."""

    @classmethod
    def get_health(cls, db: Session) -> DatabaseHealthResponse:
        """Probe database connectivity, measure ping latency, inspect PRAGMAs and count records."""
        t0 = time.perf_counter()
        try:
            db.execute(text("SELECT 1"))
            ping_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            status = "HEALTHY"
        except Exception as e:
            logger.error(f"Database ping check failed: {e}")
            ping_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            status = "UNHEALTHY"

        dialect_name = str(db.bind.dialect.name) if db.bind else "sqlite"
        masked_url = settings.DATABASE_URL
        if "@" in masked_url:
            prefix, rest = masked_url.split("://", 1)
            creds, host = rest.split("@", 1)
            masked_url = f"{prefix}://***:***@{host}"

        # SQLite PRAGMA inspection
        foreign_keys_on = True
        journal_mode = None
        file_size_bytes = None
        file_size_mb = None

        if "sqlite" in dialect_name.lower():
            try:
                fk_res = db.execute(text("PRAGMA foreign_keys")).scalar()
                foreign_keys_on = bool(fk_res)
            except Exception:
                foreign_keys_on = True

            try:
                jm_res = db.execute(text("PRAGMA journal_mode")).scalar()
                journal_mode = str(jm_res).upper() if jm_res else None
            except Exception:
                journal_mode = "WAL"

            # Check database file size if file-based
            db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
            if db_path and os.path.exists(db_path):
                try:
                    file_size_bytes = os.path.getsize(db_path)
                    file_size_mb = round(file_size_bytes / (1024.0 * 1024.0), 3)
                except Exception:
                    file_size_bytes = 0
                    file_size_mb = 0.0

        # Table counts
        p_count = db.query(Project).count()
        e_count = db.query(Endpoint).count()
        tc_count = db.query(TestCase).count()
        tr_count = db.query(TestRun).count()
        res_count = db.query(TestResult).count()
        rec_count = db.query(AIRecommendation).count()
        total_rec = p_count + e_count + tc_count + tr_count + res_count + rec_count

        tables = TableRecordCounts(
            projects=p_count,
            endpoints=e_count,
            test_cases=tc_count,
            test_runs=tr_count,
            test_results=res_count,
            ai_recommendations=rec_count,
            total_records=total_rec,
        )

        return DatabaseHealthResponse(
            status=status,
            dialect=dialect_name,
            database_url_masked=masked_url,
            ping_latency_ms=ping_ms,
            foreign_keys_enabled=foreign_keys_on,
            journal_mode=journal_mode,
            file_size_bytes=file_size_bytes,
            file_size_mb=file_size_mb,
            tables=tables,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def vacuum(cls, db: Session) -> DatabaseMaintenanceResult:
        """Execute SQLite VACUUM and ANALYZE to reclaim disk space and rebuild query planner statistics."""
        t0 = time.perf_counter()
        dialect_name = str(db.bind.dialect.name) if db.bind else "sqlite"
        try:
            if "sqlite" in dialect_name.lower():
                # SQLite VACUUM cannot run within an open transaction block
                raw_conn = db.connection().connection
                raw_conn.isolation_level = None
                cursor = raw_conn.cursor()
                cursor.execute("VACUUM")
                cursor.execute("ANALYZE")
                cursor.close()
                raw_conn.isolation_level = "DEFERRED"
                details = "SQLite VACUUM and ANALYZE completed successfully. Unused disk pages reclaimed and index statistics refreshed."
            else:
                db.execute(text("VACUUM ANALYZE"))
                details = f"{dialect_name} VACUUM ANALYZE executed successfully."

            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.info(f"Database maintenance VACUUM completed in {duration_ms}ms")
            return DatabaseMaintenanceResult(
                operation="VACUUM & ANALYZE",
                status="SUCCESS",
                duration_ms=duration_ms,
                details=details,
                executed_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.error(f"Database vacuum failed: {e}", exc_info=True)
            return DatabaseMaintenanceResult(
                operation="VACUUM & ANALYZE",
                status="FAILED",
                duration_ms=duration_ms,
                details=f"Maintenance error: {str(e)}",
                executed_at=datetime.now(timezone.utc).isoformat(),
            )

    @classmethod
    def backup(cls, db: Session, backup_dir: Optional[str] = None) -> DatabaseBackupResponse:
        """Create a point-in-time timestamped backup snapshot of the database."""
        target_dir = backup_dir or os.path.join(os.getcwd(), "backups")
        os.makedirs(target_dir, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"sentinel_backup_{timestamp_str}.db"
        target_path = os.path.abspath(os.path.join(target_dir, backup_filename))

        dialect_name = str(db.bind.dialect.name) if db.bind else "sqlite"
        if "sqlite" in dialect_name.lower():
            try:
                # Use SQLite Online Backup API for hot, zero-downtime backup
                raw_conn = db.connection().connection
                backup_conn = sqlite3.connect(target_path)
                raw_conn.backup(backup_conn)
                backup_conn.close()

                size_bytes = os.path.getsize(target_path)
                size_mb = round(size_bytes / (1024.0 * 1024.0), 3)

                logger.info(f"Database snapshot backup created: {target_path} ({size_mb} MB)")
                return DatabaseBackupResponse(
                    success=True,
                    backup_path=target_path,
                    backup_size_bytes=size_bytes,
                    backup_size_mb=size_mb,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                logger.error(f"SQLite online backup failed: {e}", exc_info=True)
                raise RuntimeError(f"Database backup failed: {str(e)}")
        else:
            raise NotImplementedError(f"Automated snapshot backup not supported for dialect: {dialect_name}")

    @classmethod
    def purge_old_runs(cls, db: Session, days_threshold: int = 30) -> DatabasePurgeResponse:
        """Purge historical test runs and child test results older than the given age threshold."""
        run_repo = TestRunRepository(db)
        old_runs = run_repo.get_runs_older_than(days=days_threshold)

        runs_count = len(old_runs)
        results_count = 0
        recs_count = 0

        for r in old_runs:
            res_list = db.query(TestResult).filter(TestResult.run_id == r.id).all()
            results_count += len(res_list)
            for res in res_list:
                recs_count += db.query(AIRecommendation).filter(AIRecommendation.test_result_id == res.id).delete()
            db.query(TestResult).filter(TestResult.run_id == r.id).delete()
            db.delete(r)

        db.commit()
        logger.info(f"Purged {runs_count} test runs, {results_count} results, {recs_count} recommendations (Threshold: {days_threshold} days)")
        return DatabasePurgeResponse(
            days_threshold=days_threshold,
            runs_purged=runs_count,
            results_purged=results_count,
            recommendations_purged=recs_count,
            executed_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def seed_sample_data(cls, db: Session) -> DatabaseSeedResponse:
        """Seed a realistic e-commerce API project with endpoints, test cases, and a completed run."""
        proj_repo = ProjectRepository(db)
        endpoint_repo = EndpointRepository(db)
        tc_repo = TestCaseRepository(db)
        run_repo = TestRunRepository(db)
        res_repo = TestResultRepository(db)

        # 1. Project
        proj_name = "Alpha Commerce Demo Store"
        existing = proj_repo.get_by_name(proj_name)
        if existing:
            project = existing
        else:
            project = proj_repo.create(
                name=proj_name,
                description="Demo microservices e-commerce catalog and checkout API for automated quality profiling.",
                base_url="http://127.0.0.1:8000",
                environment="development"
            )

        # 2. Endpoints
        eps_data = [
            {"method": "GET", "path": "/api/v1/products", "name": "List Products Catalog", "description": "Fetches paginated products catalog."},
            {"method": "POST", "path": "/api/v1/products", "name": "Create Product", "description": "Creates a new catalog product."},
            {"method": "GET", "path": "/api/v1/products/{id}", "name": "Get Product by ID", "description": "Fetches single product details by integer ID."},
            {"method": "POST", "path": "/api/v1/checkout", "name": "Process Order Checkout", "description": "Processes payment and fulfills shopping cart order."}
        ]

        created_endpoints = []
        for ed in eps_data:
            ep = endpoint_repo.get_by_path_and_method(project.id, ed["method"], ed["path"])
            if not ep:
                ep = endpoint_repo.create(
                    project_id=project.id,
                    method=ed["method"],
                    path=ed["path"],
                    name=ed["name"],
                    description=ed["description"],
                    is_active=True
                )
            created_endpoints.append(ep)

        # 3. Test Cases
        created_tcs = []
        tc_specs = [
            (created_endpoints[0].id, "Smoke Check - Product List", "smoke", 200, 300.0, "LOW"),
            (created_endpoints[0].id, "SLA Benchmark - Product List", "performance", 200, 150.0, "MEDIUM"),
            (created_endpoints[1].id, "Nominal Product Creation", "smoke", 201, 400.0, "MEDIUM"),
            (created_endpoints[1].id, "Negative Missing Title", "negative", 422, 200.0, "HIGH"),
            (created_endpoints[2].id, "Get Product #1", "smoke", 200, 200.0, "LOW"),
            (created_endpoints[3].id, "Checkout Normal Order", "smoke", 200, 500.0, "CRITICAL"),
        ]

        for ep_id, tc_name, tag, exp_code, max_lat, sev in tc_specs:
            existing_tc = db.query(TestCase).filter(TestCase.endpoint_id == ep_id, TestCase.name == tc_name).first()
            if not existing_tc:
                tc = tc_repo.create(
                    endpoint_id=ep_id,
                    name=tc_name,
                    tags_json=f'["{tag}"]',
                    assertions_json=f'{{"expected_status": {exp_code}, "max_latency_ms": {max_lat}}}',
                    severity=sev,
                    is_active=True
                )
                created_tcs.append(tc)

        # 4. Sample Test Run
        run = run_repo.create(
            project_id=project.id,
            name="Automated Baseline Health Run",
            environment="development",
            status="COMPLETED",
            total_tests=len(created_tcs) or 4,
            passed_tests=len(created_tcs) or 4,
            failed_tests=0,
            duration_ms=142.5,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc)
        )

        for tc in (created_tcs or tc_repo.get_by_project(project.id)[:4]):
            res_repo.create(
                run_id=run.id,
                test_case_id=tc.id,
                endpoint_id=tc.endpoint_id,
                status="PASS",
                test_name=tc.name,
                http_method="GET",
                url="http://127.0.0.1:8000/sample",
                response_code=200,
                response_time_ms=42.0
            )


        logger.info(f"Sample data seeded under Project #{project.id}: '{project.name}'")
        return DatabaseSeedResponse(
            success=True,
            project_id=project.id,
            project_name=project.name,
            endpoints_created=len(created_endpoints),
            test_cases_created=len(created_tcs),
            test_runs_created=1,
            seeded_at=datetime.now(timezone.utc).isoformat(),
        )
