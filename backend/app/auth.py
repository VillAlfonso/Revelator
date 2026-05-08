"""Authentication dependency.

The frontend obtains a Firebase ID token after sign-in and includes it as a
Bearer token in every backend call. We verify the token, then look up (or
create) the user's profile document in Firestore.

User profile shape (collection `users`, doc id = uid):
    {
        email, full_name, photo_url,
        plan: "free" | "pro" | "premium",
        scans_this_month: int,
        scan_reset_date: timestamp,
        stripe_customer_id, paymongo_customer_id,
        created_at, updated_at,
    }
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from .firebase_admin_init import db, verify_id_token


def _now():
    return datetime.now(timezone.utc)


def _ensure_user_doc(uid: str, claims: dict) -> dict:
    """Return the user's Firestore profile, creating it on first sign-in."""
    ref = db().collection("users").document(uid)
    snap = ref.get()
    if snap.exists:
        return snap.to_dict() | {"uid": uid}

    profile = {
        "email": claims.get("email", ""),
        "full_name": claims.get("name", ""),
        "photo_url": claims.get("picture", ""),
        "plan": "free",
        "scans_this_month": 0,
        "scan_reset_date": _now(),
        "stripe_customer_id": "",
        "stripe_subscription_id": "",
        "paymongo_customer_id": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    ref.set(profile)
    return profile | {"uid": uid}


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency that returns the current user's Firestore profile dict.

    Reads `Authorization: Bearer <firebase_id_token>`, verifies it with
    firebase-admin, and ensures a `users/{uid}` doc exists in Firestore.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Bearer token")

    token = authorization.split(None, 1)[1].strip()
    try:
        claims = verify_id_token(token)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    uid = claims["uid"]
    return _ensure_user_doc(uid, claims)
