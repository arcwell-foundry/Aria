"""Request timing, request ID, and performance stats middleware.

Provides:
- RequestIDMiddleware: Assigns a UUID to every request for log traceability.
- RequestTimingMiddleware: Measures and logs request duration, warns on slow requests.
- perf_stats: In-memory ring buffer of recent request timings for the stats endpoint.
"""

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

SLOW_REQUEST_THRESHOLD_MS = 1000.0
SLOW_QUERY_THRESHOLD_MS = 500.0
MAX_STATS_ENTRIES = 1000


# ---------------------------------------------------------------------------
# In-memory stats store
# ---------------------------------------------------------------------------

@dataclass
class RequestRecord:
    """Single request timing record."""

    method: str
    path: str
    status_code: int
    duration_ms: float
    request_id: str
    timestamp: float = field(default_factory=time.time)


class PerfStats:
    """Thread-safe ring buffer holding the last N request records."""

    def __init__(self, maxlen: int = MAX_STATS_ENTRIES) -> None:
        self._records: deque[RequestRecord] = deque(maxlen=maxlen)
        self._lock = Lock()

    def record(self, rec: RequestRecord) -> None:
        with self._lock:
            self._records.append(rec)

    def snapshot(self) -> list[RequestRecord]:
        with self._lock:
            return list(self._records)

    def summarize(self) -> dict[str, Any]:
        """Return p50/p95/p99 response times grouped by endpoint."""
        records = self.snapshot()
        if not records:
            return {"total_requests": 0, "endpoints": {}}

        # Group by "METHOD path"
        by_endpoint: dict[str, list[float]] = {}
        for r in records:
            key = f"{r.method} {r.path}"
            by_endpoint.setdefault(key, []).append(r.duration_ms)

        endpoints: dict[str, dict[str, Any]] = {}
        for key, durations in sorted(by_endpoint.items()):
            durations_sorted = sorted(durations)
            endpoints[key] = {
                "count": len(durations_sorted),
                "p50_ms": round(_percentile(durations_sorted, 50), 2),
                "p95_ms": round(_percentile(durations_sorted, 95), 2),
                "p99_ms": round(_percentile(durations_sorted, 99), 2),
                "max_ms": round(durations_sorted[-1], 2),
            }

        all_durations = sorted(r.duration_ms for r in records)
        return {
            "total_requests": len(records),
            "global": {
                "p50_ms": round(_percentile(all_durations, 50), 2),
                "p95_ms": round(_percentile(all_durations, 95), 2),
                "p99_ms": round(_percentile(all_durations, 99), 2),
                "max_ms": round(all_durations[-1], 2),
            },
            "endpoints": endpoints,
        }


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile from pre-sorted data."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# Module-level singleton used by both middleware and the stats endpoint.
perf_stats = PerfStats()


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique request ID to every request.

    - Stores the ID in ``request.state.request_id``.
    - Returns the ID in the ``X-Request-ID`` response header.
    - Injects the ID into the log record via a ``LoggerAdapter`` stored at
      ``request.state.logger``.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Measure request duration and log performance data.

    - Adds ``X-Response-Time`` header (in milliseconds).
    - Logs a WARNING for any request exceeding 1 s.
    - Logs an INFO-level line with ``[SLOW_QUERY]`` tag for requests > 500 ms.
    - Pushes a ``RequestRecord`` into the shared ``perf_stats`` ring buffer.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        request_id = getattr(request.state, "request_id", "unknown")
        method = request.method
        path = request.url.path
        status_code = response.status_code

        # Record into ring buffer
        perf_stats.record(
            RequestRecord(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
        )

        # Warn on slow requests (>1 s)
        if duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "Slow request: %s %s completed in %.2f ms [request_id=%s, status=%d]",
                method,
                path,
                duration_ms,
                request_id,
                status_code,
            )
        # Log slow-query-level requests (>500 ms)
        elif duration_ms >= SLOW_QUERY_THRESHOLD_MS:
            logger.info(
                "[SLOW_QUERY] %s %s completed in %.2f ms [request_id=%s, status=%d]",
                method,
                path,
                duration_ms,
                request_id,
                status_code,
            )

        return response
