import collections
import json
import logging
import sys
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Context variable to store active Request/Correlation ID per async task
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


class InMemoryLogBuffer:
    """Thread-safe ring-buffer retaining the most recent log records for live querying."""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, capacity: int = 500):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InMemoryLogBuffer, cls).__new__(cls)
                cls._instance._buffer = collections.deque(maxlen=capacity)
            return cls._instance

    def append(self, log_entry: Dict[str, Any]) -> None:
        with self._lock:
            self._buffer.append(log_entry)

    def get_logs(
        self,
        limit: int = 100,
        level: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            records = list(self._buffer)

        if level:
            records = [r for r in records if r.get("level") == level.upper()]
        if search:
            s_lower = search.lower()
            records = [
                r for r in records
                if s_lower in r.get("message", "").lower() or s_lower in r.get("logger", "").lower()
            ]

        return list(reversed(records))[:limit]

    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> int:
        with self._lock:
            c = len(self._buffer)
            self._buffer.clear()
            return c


def get_log_buffer() -> InMemoryLogBuffer:
    """Singleton getter for the in-memory application log buffer."""
    return InMemoryLogBuffer()


class InMemoryLogHandler(logging.Handler):
    """Logging handler pushing structured records into the InMemoryLogBuffer."""

    def __init__(self, buffer: Optional[InMemoryLogBuffer] = None):
        super().__init__()
        self.buffer = buffer or get_log_buffer()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            req_id = request_id_ctx_var.get()
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "request_id": req_id,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info) if self.formatter else str(record.exc_info)
            self.buffer.append(log_entry)
        except Exception:
            self.handleError(record)


class JSONLogFormatter(logging.Formatter):
    """Formats log records as structured JSON strings."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


class ConsoleLogFormatter(logging.Formatter):
    """Human-readable colored/clean console log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx_var.get()
        req_part = f"[{req_id[:8]}]" if req_id != "-" else "[-]"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{timestamp} | {record.levelname:<8} | {req_part} | {record.name} - {record.getMessage()}"
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return msg


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Initialize root and application loggers with console and in-memory buffer handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        console_handler.setFormatter(JSONLogFormatter())
    else:
        console_handler.setFormatter(ConsoleLogFormatter())

    root_logger.addHandler(console_handler)
    root_logger.addHandler(InMemoryLogHandler())

    # Set third-party logger levels
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

