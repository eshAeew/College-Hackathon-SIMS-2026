"""TestCase entity model for storing functional test scenarios per endpoint."""
import json
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class TestCase(Base):
    """Database entity representing a functional test scenario mapped to an Endpoint."""
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    severity = Column(String(30), default="medium", nullable=False, index=True)
    
    # Tags (JSON array of strings, e.g. ["smoke", "regression", "security", "negative"])
    tags_json = Column(Text, default="[]", nullable=False)

    # Request parameter configurations for this scenario
    path_params_json = Column(Text, default="{}", nullable=False)
    query_params_json = Column(Text, default="{}", nullable=False)
    headers_json = Column(Text, default="{}", nullable=False)
    body_type = Column(String(30), default="json", nullable=False)
    body_json = Column(Text, nullable=True)

    # Assertion & expectation rules configuration
    assertions_json = Column(Text, default="{}", nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Database Relationships
    endpoint = relationship("Endpoint", back_populates="test_cases")

    @property
    def tags(self) -> list:
        """Parse tags JSON string into list."""
        try:
            return json.loads(self.tags_json) if self.tags_json else []
        except Exception:
            return []

    @tags.setter
    def tags(self, value: list) -> None:
        """Serialize tags list into JSON string."""
        self.tags_json = json.dumps(value or [])

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
    def body(self) -> any:
        """Parse body JSON string into dictionary, list, or raw string."""
        if not self.body_json:
            return None
        try:
            return json.loads(self.body_json)
        except Exception:
            return self.body_json

    @body.setter
    def body(self, value: any) -> None:
        """Serialize body value into JSON string or plain string."""
        if value is None:
            self.body_json = None
        elif isinstance(value, (dict, list)):
            self.body_json = json.dumps(value)
        else:
            self.body_json = str(value)

    @property
    def assertions(self) -> dict:
        """Parse assertions JSON string into dictionary."""
        try:
            return json.loads(self.assertions_json) if self.assertions_json else {}
        except Exception:
            return {}

    @assertions.setter
    def assertions(self, value: dict) -> None:
        """Serialize assertions dictionary into JSON string."""
        self.assertions_json = json.dumps(value or {})
