"""Hidden administrator-only live scan intercept endpoints."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_admin
from ..database import get_db
from ..forgery.gemini_vision import CATEGORY_CODES
from ..intercept_queue import intercept_queue
from ..models import AdminAuditLog, User

router = APIRouter(prefix="/api/intercept", tags=["admin-intercept"])


class InterceptDecision(BaseModel):
    category: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/events")
async def intercept_events(current_admin: User = Depends(get_current_admin)):
    queue, snapshot, loop = intercept_queue.subscribe()

    async def event_stream():
        try:
            yield _sse("snapshot", {"scans": snapshot})
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(message["event"], message["data"])
        finally:
            intercept_queue.unsubscribe(queue, loop)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/scans/{scan_id}/image")
def intercept_scan_image(
    scan_id: str,
    current_admin: User = Depends(get_current_admin),
):
    scan = intercept_queue.get_pending(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Pending scan not found")
    return Response(
        content=scan.image_data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/scans/{scan_id}/decision")
def decide_intercept_scan(
    scan_id: str,
    body: InterceptDecision,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if body.category not in CATEGORY_CODES:
        raise HTTPException(status_code=422, detail="Unknown classification category")

    try:
        scan = intercept_queue.choose_category(scan_id, body.category)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc

    db.add(
        AdminAuditLog(
            admin_id=current_admin.id,
            action="intercept_scan_classification",
            target_user_id=scan["user_id"],
            details=json.dumps(
                {
                    "scan_id": scan_id,
                    "filename": scan["filename"],
                    "category": body.category,
                    "selected_at": datetime.utcnow().isoformat(),
                }
            ),
        )
    )
    db.commit()
    return {"success": True, "id": scan_id, "category": body.category}


@router.post("/scans/{scan_id}/skip")
def skip_intercept_scan(
    scan_id: str,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    try:
        scan = intercept_queue.skip_scan(scan_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc

    db.add(
        AdminAuditLog(
            admin_id=current_admin.id,
            action="intercept_scan_skipped",
            target_user_id=scan["user_id"],
            details=json.dumps(
                {
                    "scan_id": scan_id,
                    "filename": scan["filename"],
                    "skipped_at": datetime.utcnow().isoformat(),
                }
            ),
        )
    )
    db.commit()
    return {"success": True, "id": scan_id, "skipped": True}
