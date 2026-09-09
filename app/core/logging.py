"""Structured JSON and console logging configuration with contextual Request-ID tracing."""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict

# Context variable to store active Request/Correlation ID per async task
request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


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
    """Initialize root and application loggers."""
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

    # Set third-party logger levels
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
