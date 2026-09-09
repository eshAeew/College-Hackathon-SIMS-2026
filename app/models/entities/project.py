"""Project entity model for workspace isolation."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base


class Project(Base):
    """Database entity representing an API Testing Project / Workspace."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=False)
    environment = Column(String(50), default="development", nullable=False)
    global_headers_json = Column(Text, default="{}", nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    endpoints = relationship("Endpoint", back_populates="project", cascade="all, delete-orphan")
    test_runs = relationship("TestRun", back_populates="project", cascade="all, delete-orphan")

    @property
    def global_headers(self) -> dict:
        """Parse global headers JSON string into dictionary."""
        try:
            return json.loads(self.global_headers_json) if self.global_headers_json else {}
        except Exception:
            return {}

    @global_headers.setter
    def global_headers(self, value: dict) -> None:
        """Serialize global headers dictionary into JSON string."""
        self.global_headers_json = json.dumps(value or {})
