"""Pydantic schemas and DTOs for Database health, telemetry, maintenance, backup, and seeding."""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class DatabaseDialect(str, Enum):
    """Supported database dialects."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    OTHER = "other"


class TableRecordCounts(BaseModel):
    """Record counts across all entity tables."""
    projects: int = Field(0, description="Total registered projects / workspaces")
    endpoints: int = Field(0, description="Total registered API endpoints")
    test_cases: int = Field(0, description="Total registered test cases")
    test_runs: int = Field(0, description="Total executed test runs")
    test_results: int = Field(0, description="Total individual test execution results")
    ai_recommendations: int = Field(0, description="Total persisted AI/heuristic recommendations")
    total_records: int = Field(0, description="Grand total of all records across all tables")


class DatabaseHealthResponse(BaseModel):
    """Comprehensive database health probe and telemetry."""
    status: str = Field(..., description="Overall database status: HEALTHY, DEGRADED, UNHEALTHY")
    dialect: str = Field(..., description="Active database engine dialect (e.g., sqlite, postgresql)")
    database_url_masked: str = Field(..., description="Sanitized database connection URL without secrets")
    ping_latency_ms: float = Field(..., description="Database connection ping roundtrip latency in milliseconds")
    foreign_keys_enabled: bool = Field(True, description="Whether foreign key integrity constraints are actively enforced")
    journal_mode: Optional[str] = Field(None, description="Active SQLite journal mode (e.g. WAL, DELETE)")
    file_size_bytes: Optional[int] = Field(None, description="Database file size on disk in bytes (if SQLite)")
    file_size_mb: Optional[float] = Field(None, description="Database file size on disk in Megabytes")
    tables: TableRecordCounts = Field(..., description="Breakdown of table record counts")
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DatabaseBackupResponse(BaseModel):
    """Outcome metadata for database backup operation."""
    success: bool = Field(..., description="Whether the backup succeeded")
    backup_path: str = Field(..., description="Absolute path to generated backup archive file")
    backup_size_bytes: int = Field(..., description="Size of backup file in bytes")
    backup_size_mb: float = Field(..., description="Size of backup file in Megabytes")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DatabaseMaintenanceResult(BaseModel):
    """Outcome metadata for database maintenance operations (vacuum, optimize)."""
    operation: str = Field(..., description="Executed maintenance operation (e.g. VACUUM, REINDEX)")
    status: str = Field(..., description="Operation execution status: SUCCESS, FAILED")
    duration_ms: float = Field(..., description="Duration taken to complete maintenance in milliseconds")
    details: str = Field(..., description="Descriptive summary of maintenance actions taken")
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DatabasePurgeRequest(BaseModel):
    """Parameters for pruning historical test runs and results."""
    days_threshold: int = Field(30, ge=1, le=365, description="Age threshold in days. Runs older than this will be purged.")


class DatabasePurgeResponse(BaseModel):
    """Summary of data pruned during retention policy execution."""
    days_threshold: int = Field(..., description="The applied age threshold in days")
    runs_purged: int = Field(..., description="Number of historical test runs purged")
    results_purged: int = Field(..., description="Number of individual test result records removed")
    recommendations_purged: int = Field(..., description="Number of orphaned recommendations removed")
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DatabaseSeedResponse(BaseModel):
    """Summary of demo / sample data seeding execution."""
    success: bool = Field(..., description="Whether seeding completed successfully")
    project_id: int = Field(..., description="ID of created or updated sample project")
    project_name: str = Field(..., description="Name of seeded sample project")
    endpoints_created: int = Field(..., description="Number of sample endpoints created")
    test_cases_created: int = Field(..., description="Number of sample test cases created")
    test_runs_created: int = Field(..., description="Number of sample test runs generated")
    seeded_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
