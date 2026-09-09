"""Generic Base Repository providing type-safe CRUD, pagination, and transaction operations."""
import logging
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar
from sqlalchemy.orm import Session
from app.core.database import Base

logger = logging.getLogger("app.repositories")
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository providing standardized data access methods."""

    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get_by_id(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by primary key."""
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Fetch all records with optional offset and limit pagination."""
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def count(self) -> int:
        """Count total rows in the table."""
        return self.db.query(self.model).count()

    def create(self, **kwargs) -> ModelType:
        """Instantiate and persist a new model instance."""
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def create_batch(self, instances: List[ModelType]) -> List[ModelType]:
        """Bulk persist a list of model instances."""
        self.db.add_all(instances)
        self.db.commit()
        for inst in instances:
            self.db.refresh(inst)
        return instances

    def update(self, id: Any, **kwargs) -> Optional[ModelType]:
        """Update fields on an existing record."""
        instance = self.get_by_id(id)
        if not instance:
            return None
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        self.db.commit()
        self.db.refresh(instance)
        return instance

    def delete(self, id: Any) -> bool:
        """Delete a record by primary key."""
        instance = self.get_by_id(id)
        if not instance:
            return False
        self.db.delete(instance)
        self.db.commit()
        return True

    def exists(self, id: Any) -> bool:
        """Check whether a record with given primary key exists."""
        return self.db.query(self.model.id).filter(self.model.id == id).first() is not None
