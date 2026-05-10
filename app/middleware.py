"""FastAPI middleware for automatic UTC → local-time conversion.

All timestamps are stored as UTC in the database.  This middleware
converts timestamp fields in JSON API responses to the user's configured
display timezone so that every consumer receives local times without
needing per-endpoint or per-callback conversion logic.
"""

import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import database as db

logger = logging.getLogger(__name__)

# Field names that hold ISO-8601 UTC timestamps and should be localised.
_TIMESTAMP_FIELDS = frozenset({
    "timestamp",
    "last_action_time",
})

# Paths where timestamps should NOT be converted (e.g. diagnostic endpoints).
_SKIP_PATHS = frozenset({
    "/api/timezone",
    "/health",
})


def _convert_value(value: str, tz: ZoneInfo) -> str:
    """Convert a single UTC ISO timestamp string to a naive local-time string."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return value


def _walk(obj, tz: ZoneInfo):
    """Recursively walk a JSON-compatible structure and convert timestamp fields."""
    if isinstance(obj, dict):
        for key in obj:
            if key in _TIMESTAMP_FIELDS and isinstance(obj[key], str) and obj[key]:
                obj[key] = _convert_value(obj[key], tz)
            else:
                _walk(obj[key], tz)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, tz)


class TimezoneMiddleware(BaseHTTPMiddleware):
    """Intercept JSON responses on ``/api/*`` routes and convert UTC
    timestamp fields to the user-configured display timezone."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path

        # Only process /api/ JSON responses; skip excluded paths.
        if not path.startswith("/api/") or path in _SKIP_PATHS:
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Read the full response body.
        body_parts: list[bytes] = []
        async for chunk in response.body_iterator:  # type: ignore[union-attr]
            body_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        body = b"".join(body_parts)

        try:
            data = json.loads(body)
            tz = db.get_display_tz()
            _walk(data, tz)
            body = json.dumps(data, ensure_ascii=False).encode()
        except Exception:
            # If anything goes wrong, return the original body untouched.
            pass

        # Drop the stale Content-Length; Response will recalculate it.
        headers = {k: v for k, v in response.headers.items()
                   if k.lower() != "content-length"}
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
