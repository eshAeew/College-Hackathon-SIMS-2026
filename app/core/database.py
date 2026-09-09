"""Database connectivity, session management, and Base declarative model using SQLAlchemy."""
import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import get_settings

logger = logging.getLogger("app.database")
settings = get_settings()

# Configure SQLite or PostgreSQL engine
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Set True for raw SQL debugging
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding isolated database sessions."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables on application startup."""
    try:
        # Import all entity models so metadata discovers them
        import app.models.entities.project  # noqa: F401
        import app.models.entities.endpoint  # noqa: F401
        import app.models.entities.ai_recommendation  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info(f"Database schema initialized successfully [{settings.DATABASE_URL.split('@')[-1]}]")
    except Exception as exc:
        logger.error(f"Failed to initialize database: {str(exc)}", exc_info=True)
        raise exc
