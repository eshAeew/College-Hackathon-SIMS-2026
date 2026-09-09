"""Pydantic schemas for Project CRUD operations."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class ProjectBase(BaseModel):
    """Base project schema with common fields."""
    name: str = Field(..., min_length=1, max_length=120, description="Project or microservice name")
    description: Optional[str] = Field(default=None, max_length=1000, description="Optional project description")
    base_url: str = Field(..., description="Target API base URL (e.g., http://localhost:8000)")
    environment: str = Field(default="development", description="Environment profile (development, staging, production)")
    global_headers: Dict[str, str] = Field(default_factory=dict, description="Global headers attached to all requests (e.g. Auth tokens)")

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Ensure base URL starts with http:// or https://."""
        clean = v.strip().rstrip("/")
        if not (clean.startswith("http://") or clean.startswith("https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return clean


class ProjectCreate(ProjectBase):
    """Schema for registering a new project."""
    pass


class ProjectUpdate(BaseModel):
    """Schema for modifying an existing project (all fields optional)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    base_url: Optional[str] = None
    environment: Optional[str] = None
    global_headers: Optional[Dict[str, str]] = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip().rstrip("/")
            if not (clean.startswith("http://") or clean.startswith("https://")):
                raise ValueError("Base URL must start with http:// or https://")
            return clean
        return v


class ProjectResponse(ProjectBase):
    """Schema returned for project query responses."""
    id: int = Field(..., description="Unique project ID")
    created_at: datetime = Field(..., description="Timestamp of creation")
    updated_at: datetime = Field(..., description="Timestamp of last update")

    class Config:
        from_attributes = True
