"""Firebase Admin SDK initialization.

The backend uses firebase-admin to:
  1. Verify ID tokens passed by the frontend in Authorization headers.
  2. Read and write Firestore documents (user profile, scans).
  3. Upload scan images to Firebase Storage.

The service-account JSON file should sit outside source control and be
referenced from FIREBASE_CREDENTIALS_FILE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import auth as fb_auth
from firebase_admin import credentials, firestore, storage

from .config import FIREBASE_CREDENTIALS_FILE, FIREBASE_STORAGE_BUCKET


_app: Optional[firebase_admin.App] = None
_db = None
_bucket = None


def init() -> None:
    """Initialize the Admin SDK once, idempotent."""
    global _app, _db, _bucket
    if _app is not None:
        return

    cred_path = Path(FIREBASE_CREDENTIALS_FILE).expanduser()
    if not cred_path.exists():
        raise FileNotFoundError(
            f"Firebase service-account JSON not found at {cred_path}. "
            f"Set FIREBASE_CREDENTIALS_FILE in .env."
        )
    cred = credentials.Certificate(str(cred_path))

    options = {}
    if FIREBASE_STORAGE_BUCKET:
        options["storageBucket"] = FIREBASE_STORAGE_BUCKET

    _app = firebase_admin.initialize_app(cred, options or None)
    _db = firestore.client()
    _bucket = storage.bucket() if FIREBASE_STORAGE_BUCKET else None


def db():
    if _db is None:
        init()
    return _db


def bucket():
    if _bucket is None:
        init()
    if _bucket is None:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET is not configured.")
    return _bucket


def verify_id_token(id_token: str) -> dict:
    """Verify a Firebase ID token from the client. Returns the decoded claims dict.
    Raises ValueError on any verification failure."""
    if _app is None:
        init()
    try:
        return fb_auth.verify_id_token(id_token)
    except Exception as exc:
        raise ValueError(f"Invalid Firebase ID token: {exc}") from exc
