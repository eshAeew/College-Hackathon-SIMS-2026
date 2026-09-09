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
        _ensure_columns()
        logger.info(f"Database schema initialized successfully [{settings.DATABASE_URL.split('@')[-1]}]")
    except Exception as exc:
        logger.error(f"Failed to initialize database: {str(exc)}", exc_info=True)
        raise exc



# Columns added after a table first shipped. create_all() only creates missing
# tables, so an existing database needs the ALTER itself. Each entry is applied
# only when absent, which makes this safe to run on every startup.
_ADDED_COLUMNS = {
    "ai_recommendations": {"dismissed_at": "DATETIME"},
}


def _ensure_columns() -> None:
    """Add post-release columns to tables that predate them."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name in present:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                logger.info(f"Schema: added {table}.{name}")
