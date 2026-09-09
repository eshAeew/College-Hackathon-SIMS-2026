"""Database connectivity, session management, and Base declarative model using SQLAlchemy."""
import logging
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
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


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):

    """Enable foreign key constraints and WAL journal mode on SQLite connections."""
    if "sqlite" in str(type(dbapi_connection)).lower():
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
        except Exception as e:
            logger.debug(f"SQLite PRAGMA setup skipped: {e}")


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
        import app.models.entities.test_case  # noqa: F401
        import app.models.entities.test_run  # noqa: F401
        import app.models.entities.test_result  # noqa: F401
        import app.models.entities.ai_recommendation  # noqa: F401
        import app.models.entities.audit_event  # noqa: F401

        Base.metadata.create_all(bind=engine)
        logger.info(f"Database schema initialized successfully [{settings.DATABASE_URL.split('@')[-1]}]")
    except Exception as exc:
        logger.error(f"Failed to initialize database: {str(exc)}", exc_info=True)
        raise exc

