"""In-process, short-lived queue for administrator scan classification."""

import asyncio
import threading
import time
import uuid
import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


INTERCEPT_WINDOW_SECONDS = 30


@dataclass(frozen=True)
class ScanDecision:
    category: str | None = None
    provider: str = "gemini"


class PendingScan:
    def __init__(
        self,
        *,
        user_id: str,
        username: str,
        email: str,
        filename: str,
        document_type: str | None,
        width: int,
        height: int,
        image_data: bytes,
    ):
        self.id = uuid.uuid4().hex
        self.user_id = user_id
        self.username = username
        self.email = email
        self.filename = filename
        self.document_type = document_type
        self.width = width
        self.height = height
        self.image_data = image_data
        self.deadline = time.monotonic() + INTERCEPT_WINDOW_SECONDS
        self.expires_at = (
            datetime.utcnow() + timedelta(seconds=INTERCEPT_WINDOW_SECONDS)
        ).isoformat()
        self.category: str | None = None
        self.provider = "gemini"
        self.event: asyncio.Event | None = None
        self.event_loop: asyncio.AbstractEventLoop | None = None

    def public_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "filename": self.filename,
            "document_type": self.document_type,
            "width": self.width,
            "height": self.height,
            "expires_at": self.expires_at,
            "remaining_seconds": max(0, self.deadline - time.monotonic()),
        }


class InterceptQueue:
    def __init__(self, settings_path: Path | None = None):
        self._lock = threading.RLock()
        self._settings_path = settings_path
        self._openai_all_scans = False
        if settings_path and settings_path.exists():
            self._openai_all_scans = json.loads(settings_path.read_text(encoding="utf-8")).get("openai_all_scans") is True
        self._pending: dict[str, PendingScan] = {}
        self._subscribers: set[
            tuple[asyncio.AbstractEventLoop, asyncio.Queue]
        ] = set()

    def provider_settings(self) -> dict[str, bool]:
        with self._lock:
            return {"openai_all_scans": self._openai_all_scans}

    def set_openai_all_scans(self, enabled: bool) -> dict[str, bool]:
        with self._lock:
            settings = {"openai_all_scans": enabled}
            if self._settings_path:
                temporary = self._settings_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(settings), encoding="utf-8")
                temporary.replace(self._settings_path)
            self._openai_all_scans = enabled
            self._publish_locked("provider_settings", settings)
            return settings

    async def wait_for_decision(
        self,
        *,
        user_id: str,
        username: str,
        email: str,
        filename: str,
        document_type: str | None,
        width: int,
        height: int,
        image_data: bytes,
    ) -> ScanDecision:
        loop = asyncio.get_running_loop()
        scan = PendingScan(
            user_id=user_id,
            username=username,
            email=email,
            filename=filename,
            document_type=document_type,
            width=width,
            height=height,
            image_data=image_data,
        )
        scan.event = asyncio.Event()
        scan.event_loop = loop

        with self._lock:
            self._pending[scan.id] = scan
            self._publish_locked("scan_added", scan.public_data())

        try:
            await asyncio.wait_for(
                scan.event.wait(), timeout=INTERCEPT_WINDOW_SECONDS
            )
        except asyncio.TimeoutError:
            pass
        finally:
            with self._lock:
                if self._openai_all_scans:
                    scan.provider = "openai"
                if self._pending.get(scan.id) is scan:
                    del self._pending[scan.id]
                    self._publish_locked("scan_removed", {"id": scan.id})
        return ScanDecision(category=scan.category, provider=scan.provider)

    def get_pending(self, scan_id: str) -> PendingScan | None:
        with self._lock:
            return self._pending.get(scan_id)

    def choose_category(self, scan_id: str, category: str, *, provider: str = "gemini") -> dict[str, Any]:
        if provider not in {"gemini", "openai"}:
            raise ValueError("Unknown analysis provider")
        with self._lock:
            scan = self._pending.get(scan_id)
            if scan is None:
                raise LookupError("Scan is no longer waiting for an admin decision")
            if time.monotonic() >= scan.deadline:
                del self._pending[scan_id]
                self._publish_locked("scan_removed", {"id": scan_id})
                if scan.event_loop and scan.event:
                    scan.event_loop.call_soon_threadsafe(scan.event.set)
                raise TimeoutError("The 30-second decision window has expired")

            scan.category = category
            scan.provider = provider
            del self._pending[scan_id]
            self._publish_locked(
                "scan_decided", {"id": scan_id, "category": category, "provider": provider}
            )
            if scan.event_loop and scan.event:
                scan.event_loop.call_soon_threadsafe(scan.event.set)
            return {"user_id": scan.user_id, **scan.public_data()}

    def skip_scan(self, scan_id: str, *, provider: str = "gemini") -> dict[str, Any]:
        if provider not in {"gemini", "openai"}:
            raise ValueError("Unknown analysis provider")
        with self._lock:
            scan = self._pending.get(scan_id)
            if scan is None:
                raise LookupError("Scan is no longer waiting for an admin decision")
            if time.monotonic() >= scan.deadline:
                del self._pending[scan_id]
                self._publish_locked("scan_removed", {"id": scan_id})
                if scan.event_loop and scan.event:
                    scan.event_loop.call_soon_threadsafe(scan.event.set)
                raise TimeoutError("The 30-second decision window has expired")

            del self._pending[scan_id]
            scan.provider = provider
            self._publish_locked("scan_skipped", {"id": scan_id, "provider": provider})
            if scan.event_loop and scan.event:
                scan.event_loop.call_soon_threadsafe(scan.event.set)
            return {"user_id": scan.user_id, **scan.public_data()}

    def subscribe(
        self,
    ) -> tuple[asyncio.Queue, list[dict[str, Any]], asyncio.AbstractEventLoop]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        subscriber = (loop, queue)
        with self._lock:
            self._subscribers.add(subscriber)
            snapshot = [scan.public_data() for scan in self._pending.values()]
        return queue, snapshot, loop

    def unsubscribe(
        self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop
    ) -> None:
        with self._lock:
            self._subscribers.discard((loop, queue))

    def _publish_locked(self, event: str, data: dict[str, Any]) -> None:
        message = {"event": event, "data": data}
        for loop, queue in tuple(self._subscribers):
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._enqueue, queue, message)

    @staticmethod
    def _enqueue(queue: asyncio.Queue, message: dict[str, Any]) -> None:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(
                    {"event": "refresh", "data": {"reason": "queue_overflow"}}
                )
            except asyncio.QueueFull:
                pass


from .config import DATA_DIR

intercept_queue = InterceptQueue(DATA_DIR / "intercept-provider-settings.json")
