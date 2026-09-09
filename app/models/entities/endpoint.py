"""Endpoint entity model for API route registration and contract management."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Endpoint(Base):
    """Database entity representing an API Endpoint under a specific Project."""
    __tablename__ = "endpoints"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True)
    method = Column(String(10), nullable=False, default="GET", index=True)
    path = Column(String(500), nullable=False, index=True)
    expected_status = Column(Integer, default=200, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # JSON Serialized Contract Specifications
    headers_json = Column(Text, default="{}", nullable=False)
    query_params_json = Column(Text, default="{}", nullable=False)
    path_params_json = Column(Text, default="{}", nullable=False)
    body_schema_json = Column(Text, default="{}", nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Database Relationships
    project = relationship("Project", back_populates="endpoints")

    @property
    def headers(self) -> dict:
        """Parse headers JSON string into dictionary."""
        try:
            return json.loads(self.headers_json) if self.headers_json else {}
        except Exception:
            return {}

    @headers.setter
    def headers(self, value: dict) -> None:
        """Serialize headers dictionary into JSON string."""
        self.headers_json = json.dumps(value or {})

    @property
    def query_params(self) -> dict:
        """Parse query parameters JSON string into dictionary."""
        try:
            return json.loads(self.query_params_json) if self.query_params_json else {}
        except Exception:
            return {}

    @query_params.setter
    def query_params(self, value: dict) -> None:
        """Serialize query parameters dictionary into JSON string."""
        self.query_params_json = json.dumps(value or {})

    @property
    def path_params(self) -> dict:
        """Parse path parameters JSON string into dictionary."""
        try:
            return json.loads(self.path_params_json) if self.path_params_json else {}
        except Exception:
            return {}

    @path_params.setter
    def path_params(self, value: dict) -> None:
        """Serialize path parameters dictionary into JSON string."""
        self.path_params_json = json.dumps(value or {})

    @property
    def body_schema(self) -> dict:
        """Parse body schema JSON string into dictionary."""
        try:
            return json.loads(self.body_schema_json) if self.body_schema_json else {}
        except Exception:
            return {}

    @body_schema.setter
    def body_schema(self, value: dict) -> None:
        """Serialize body schema dictionary into JSON string."""
        self.body_schema_json = json.dumps(value or {})
