"""Lightweight in-memory distributed tracing and execution span manager."""
import time
import uuid
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from collections import OrderedDict


class TraceSpan:
    """Represents an execution span within a trace."""

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.span_id = span_id or str(uuid.uuid4())[:8]
        self.trace_id = trace_id
        self.name = name
        self.parent_span_id = parent_span_id
        self.start_time = time.perf_counter()
        self.end_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.status = "OK"
        self.metadata: Dict[str, Any] = metadata or {}
        self.children: List[TraceSpan] = []

    def finish(self, status: str = "OK", error: Optional[str] = None) -> None:
        """Complete the span and record elapsed duration."""
        self.end_time = time.perf_counter()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 3)
        self.status = status
        if error:
            self.metadata["error"] = str(error)

    def to_dict(self) -> Dict[str, Any]:
        """Convert span tree to recursive dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "metadata": self.metadata,
            "children": [c.to_dict() for c in self.children],
        }


class Tracer:
    """Thread-safe tracer storing active and completed execution traces."""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Tracer, cls).__new__(cls)
                cls._instance._traces: OrderedDict[str, TraceSpan] = OrderedDict()
                cls._instance._max_traces = 1000
                cls._instance._local = threading.local()
            return cls._instance

    @property
    def current_span(self) -> Optional[TraceSpan]:
        """Get the current active span for the executing thread."""
        return getattr(self._local, "current_span", None)

    @current_span.setter
    def current_span(self, span: Optional[TraceSpan]) -> None:
        self._local.current_span = span

    @contextmanager
    def span(self, name: str, trace_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """Context manager to record a traced execution step."""
        parent = self.current_span
        actual_trace_id = trace_id or (parent.trace_id if parent else str(uuid.uuid4()))
        parent_span_id = parent.span_id if parent else None

        new_span = TraceSpan(
            name=name,
            trace_id=actual_trace_id,
            parent_span_id=parent_span_id,
            metadata=metadata,
        )

        if parent:
            parent.children.append(new_span)
        else:
            with self._lock:
                if len(self._traces) >= self._max_traces:
                    self._traces.popitem(last=False)
                self._traces[actual_trace_id] = new_span

        prev_span = self.current_span
        self.current_span = new_span
        try:
            yield new_span
            if new_span.end_time is None:
                new_span.finish("OK")
        except Exception as exc:
            new_span.finish("ERROR", error=str(exc))
            raise exc
        finally:
            self.current_span = prev_span

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve completed trace by trace_id."""
        with self._lock:
            span = self._traces.get(trace_id)
            if not span:
                return None

            def count_spans(s: TraceSpan) -> int:
                return 1 + sum(count_spans(c) for c in s.children)

            return {
                "trace_id": trace_id,
                "root_span_name": span.name,
                "total_duration_ms": span.duration_ms or 0.0,
                "span_count": count_spans(span),
                "status": span.status,
                "root_span": span.to_dict(),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def clear(self) -> None:
        """Clear trace cache (used in testing)."""
        with self._lock:
            self._traces.clear()
