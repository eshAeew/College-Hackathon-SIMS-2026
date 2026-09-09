"""REST API endpoints for Database Health, Diagnostics, Maintenance, Backups & Seeding."""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.schemas.database import (
    DatabaseBackupResponse,
    DatabaseHealthResponse,
    DatabaseMaintenanceResult,
    DatabasePurgeRequest,
    DatabasePurgeResponse,
    DatabaseSeedResponse,
)
from app.services.database_service import DatabaseService

logger = logging.getLogger("app.api.database")
router = APIRouter(prefix="/database", tags=["Database & Persistence"])


@router.get(
    "/health",
    response_model=DatabaseHealthResponse,
    summary="Probe database health, latency, PRAGMAs, and table metrics"
)
def get_database_health(db: Session = Depends(get_db)):
    """Return comprehensive database engine metrics, connection latency, WAL mode status, and table row counts."""
    try:
        return DatabaseService.get_health(db)
    except Exception as e:
        logger.error(f"Failed to query database health: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database health probe failure: {str(e)}"
        )


@router.post(
    "/maintenance/vacuum",
    response_model=DatabaseMaintenanceResult,
    summary="Reclaim disk space and rebuild query planner statistics"
)
def vacuum_database(db: Session = Depends(get_db)):
    """Execute SQLite VACUUM and ANALYZE to optimize disk storage and B-tree fragmentation."""
    try:
        return DatabaseService.vacuum(db)
    except Exception as e:
        logger.error(f"Failed to vacuum database: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database vacuum failure: {str(e)}"
        )


@router.post(
    "/maintenance/backup",
    response_model=DatabaseBackupResponse,
    summary="Create a point-in-time snapshot backup"
)
def backup_database(db: Session = Depends(get_db)):
    """Generate a timestamped snapshot backup file in the application backup directory."""
    try:
        return DatabaseService.backup(db)
    except Exception as e:
        logger.error(f"Failed to create database backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database backup failure: {str(e)}"
        )


@router.post(
    "/maintenance/purge-runs",
    response_model=DatabasePurgeResponse,
    summary="Purge historical test runs older than age threshold"
)
def purge_old_test_runs(
    req: DatabasePurgeRequest = DatabasePurgeRequest(days_threshold=30),
    db: Session = Depends(get_db)
):
    """Prune historical test runs and child test results older than the specified days threshold."""
    try:
        return DatabaseService.purge_old_runs(db, days_threshold=req.days_threshold)
    except Exception as e:
        logger.error(f"Failed to purge old test runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database purge failure: {str(e)}"
        )


@router.post(
    "/seed-sample",
    response_model=DatabaseSeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Seed sample e-commerce project, endpoints, and test suites"
)
def seed_sample_database(db: Session = Depends(get_db)):
    """Bootstrap a full sample workspace with catalog/checkout endpoints, test cases, and historical test runs."""
    try:
        return DatabaseService.seed_sample_data(db)
    except Exception as e:
        logger.error(f"Failed to seed sample database: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database seed failure: {str(e)}"
        )
