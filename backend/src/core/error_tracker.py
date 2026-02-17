"""Centralized error tracking for ARIA services.

Provides an in-memory error tracker that counts errors by service and type,
stores the last 1000 errors, and produces summaries for health check endpoints.
"""

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

MAX_ERRORS = 1000


class ErrorTracker:
    """Singleton that records and summarizes errors by service/type.

    Stores up to MAX_ERRORS in memory (oldest evicted). Thread-safe.
    """

    _instance: "ErrorTracker | None" = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ErrorTracker":
        """Return the singleton ErrorTracker instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._errors: deque[dict[str, Any]] = deque(maxlen=MAX_ERRORS)
        self._write_lock = threading.Lock()

    def record_error(self, service: str, error_type: str, message: str) -> None:
        """Record an error occurrence.

        Args:
            service: Service that produced the error (e.g. "tavus", "exa").
            error_type: Exception class name or error category.
            message: Human-readable error description.
        """
        entry = {
            "service": service,
            "error_type": error_type,
            "message": message,
            "timestamp": time.time(),
        }
        with self._write_lock:
            self._errors.append(entry)

    def get_recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent errors, newest first.

        Args:
            limit: Maximum number of errors to return.
        """
        with self._write_lock:
            items = list(self._errors)
        items.reverse()
        return items[:limit]

    def get_error_summary(self, period_seconds: int = 3600) -> dict[str, Any]:
        """Summarize errors within the given time window.

        Args:
            period_seconds: How far back to look (default 1 hour).

        Returns:
            Dict with total, by_service, by_type counts and period_seconds.
        """
        cutoff = time.time() - period_seconds
        with self._write_lock:
            items = list(self._errors)

        by_service: dict[str, int] = {}
        by_type: dict[str, int] = {}
        total = 0

        for entry in items:
            if entry["timestamp"] >= cutoff:
                total += 1
                svc = entry["service"]
                etype = entry["error_type"]
                by_service[svc] = by_service.get(svc, 0) + 1
                by_type[etype] = by_type.get(etype, 0) + 1

        return {
            "total": total,
            "by_service": by_service,
            "by_type": by_type,
            "period_seconds": period_seconds,
        }

    def reset(self) -> None:
        """Clear all tracked errors."""
        with self._write_lock:
            self._errors.clear()
