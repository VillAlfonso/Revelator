"""Small operational event and rate-limit helpers."""

import hashlib
import logging
import threading
import time
from collections import defaultdict, deque

from .database import SessionLocal
from .models import OperationalEvent

logger = logging.getLogger("revelator.operations")
_rate_lock = threading.Lock()
_rate_windows = defaultdict(deque)
_rate_logged_bucket = {}


def record_event(
    event_type: str,
    message: str,
    *,
    severity: str = "info",
    request_id: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    user_id: str | None = None,
    scan_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(OperationalEvent(
            event_type=event_type,
            request_id=request_id,
            severity=severity,
            path=(path or "")[:300] or None,
            status_code=status_code,
            message=message[:2000],
            user_id=user_id,
            scan_id=scan_id,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Could not persist operational event")
    finally:
        db.close()


def enforce_rate_limit(request, scope: str, subject: str, limit: int, window_seconds: int) -> None:
    """Apply a process-local sliding-window limit keyed by endpoint and subject."""
    from fastapi import HTTPException

    normalized = (subject or "").strip().lower()
    subject_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    client_host = request.client.host if request.client else "unknown"
    key = (scope, client_host, subject_hash)
    now = time.monotonic()
    with _rate_lock:
        events = _rate_windows[key]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(_rate_windows) > 5000:
            expired_before = now - window_seconds
            for old_key in list(_rate_windows):
                old_events = _rate_windows[old_key]
                while old_events and old_events[0] <= expired_before:
                    old_events.popleft()
                if not old_events:
                    del _rate_windows[old_key]
                    _rate_logged_bucket.pop(old_key, None)
        if len(events) >= limit:
            retry_after = max(1, int(window_seconds - (now - events[0])))
            bucket = int(now // window_seconds)
            should_log = _rate_logged_bucket.get(key) != bucket
            _rate_logged_bucket[key] = bucket
            if should_log:
                record_event(
                    "rate_limit",
                    f"Rate limit exceeded for {scope}",
                    severity="warning",
                    request_id=getattr(request.state, "request_id", None),
                    path=request.url.path,
                    status_code=429,
                )
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        events.append(now)
