"""
Authentication routes: register, login, refresh, me, Google OAuth.
"""

import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..device_details import browser_identity, device_label, request_ip
from ..database import get_db
from ..models import (
    User, UserApiKey, LoginCode, TrustedDevice, UserSession, RegistrationCode, RecoveryCode, AuthChallenge,
    PasswordResetToken, OperationalEvent, Scan, AdminAuditLog,
)
from ..auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, create_verification_token,
    create_signup_token, create_reset_token, decode_token, get_current_user,
    generate_otp_code, generate_device_token, hash_token,
)
from ..config import (
    APP_ENV, GOOGLE_CLIENT_ID, FRONTEND_URL,
    TWO_FACTOR_ENABLED, TWO_FACTOR_CODE_TTL_MINUTES, TWO_FACTOR_MAX_ATTEMPTS,
    TRUSTED_DEVICE_DAYS, REFRESH_TOKEN_EXPIRE_DAYS, UPLOAD_DIR, DATA_DIR,
)
from ..account_security import begin_auth, finish_auth, consume_recovery, archive_account, release_archived_identity
from ..operations import enforce_rate_limit
from ..key_storage import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ──────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str
    device_token: str | None = None  # remembered-device token, skips 2FA when valid


class Verify2FARequest(BaseModel):
    email: str
    code: str
    remember_device: bool = False


class Toggle2FARequest(BaseModel):
    enabled: bool

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    scans_this_month: int
    created_at: str

class GoogleAuthRequest(BaseModel):
    id_token: str

class RegisterResponse(BaseModel):
    message: str
    email: str
    verification_required: bool = True

class ResendRequest(BaseModel):
    email: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class DeleteAccountRequest(BaseModel):
    email: EmailStr
    password: str | None = None
    confirmation: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def user_to_dict(user: User, db: Session = None) -> dict:
    role_name = user.role or "user"
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name or "",
        "scans_this_month": user.scans_this_month,
        "role": role_name,
        "is_active": bool(user.is_active),
        "two_factor_enabled": True,
        "authenticator_enrolled": bool(user.totp_secret),
        "has_password": bool(user.hashed_password),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


# ── Two-factor helpers ──────────────────────────────────

def _issue_login(
    user: User,
    db: Session,
    device_token: str | None = None,
    request: Request | None = None,
    previous: UserSession | None = None,
) -> dict:
    """Build the standard authenticated response (tokens + user)."""
    now = datetime.utcnow()
    browser_id = previous.browser_id if previous else browser_identity(request)
    if browser_id:
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.browser_id == browser_id,
            UserSession.revoked_at.is_(None),
        ).update({UserSession.revoked_at: now})
    session = UserSession(
        browser_id=browser_id,
        ip_address=request_ip(request) or (previous.ip_address if previous else None),
        location=previous.location if previous else None,
        user_id=user.id,
        label=(request.headers.get("user-agent", "")[:200] if request else "") or (previous.label if previous else "Unknown device"),
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        last_used_at=now,
    )
    db.add(session)
    db.flush()
    db.commit()
    resp = {
        "requires_2fa": False,
        "access_token": create_access_token(user.id, session.id, user.auth_version),
        "refresh_token": create_refresh_token(user.id, session.id, user.auth_version),
        "token_type": "bearer",
        "user": user_to_dict(user, db),
        "session_id": session.id,
    }
    if device_token:
        resp["device_token"] = device_token
    return resp


@router.post("/register")
@router.post("/verify-registration")
def register():
    raise HTTPException(400, "New accounts must use Google sign-in with an @lspu.edu.ph address.")


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", body.email, 10, 900)
    user = db.query(User).filter(func.lower(User.email) == body.email.strip().lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return begin_auth(user, db)


class AuthenticatorRequest(BaseModel):
    challenge_token: str = Field(max_length=200)
    code: str = Field(min_length=6, max_length=64)


@router.post("/verify-2fa")
def verify_2fa(body: AuthenticatorRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "authenticator", "all", 30, 900)
    user, recovery = finish_auth(body.challenge_token, body.code, db)
    result = _issue_login(user, db, request=request)
    if recovery:
        result["recovery_codes"] = recovery
    return result


@router.post("/resend-2fa")
@router.post("/resend-verification")
def no_email_verification():
    raise HTTPException(400, "Use your Google Authenticator app. Codes are not sent by email.")


@router.put("/2fa")
def set_two_factor(current_user: User = Depends(get_current_user)):
    raise HTTPException(400, "Authenticator verification is required for all accounts.")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active or user.archived_at or not user.totp_secret:
        raise HTTPException(status_code=401, detail="User not found")
    if payload.get("ver", 0) != user.auth_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")

    previous = None
    previous_session_id = payload.get("sid")
    if previous_session_id:
        previous = (
            db.query(UserSession)
            .filter(
                UserSession.id == previous_session_id,
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if not previous:
            raise HTTPException(status_code=401, detail="Session has been revoked or expired")
        previous.revoked_at = datetime.utcnow()
        db.commit()

    tokens = _issue_login(user, db, request=request, previous=previous)
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user=user_to_dict(user, db),
    )


@router.post("/logout")
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_id = _request_session_id(request, current_user)
    if session_id:
        db.query(UserSession).filter(
            UserSession.id == session_id,
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        ).update({UserSession.revoked_at: datetime.utcnow()})
        db.commit()
    return {"success": True}


@router.get("/verify-email")
@router.post("/reset-password")
def retired_email_links():
    raise HTTPException(410, "Email verification links are no longer supported. Use Google sign-in or a recovery code.")


class RecoverAccountRequest(BaseModel):
    email: EmailStr
    recovery_code: str = Field(min_length=6, max_length=64)
    password: str = Field(max_length=72)


@router.post("/forgot-password")
def recover_account(body: RecoverAccountRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "account_recovery", "all", 5, 900)
    if not _password_meets_policy(body.password):
        raise HTTPException(400, "Password must be at least 12 characters with a letter and number (maximum 72 bytes).")
    user = db.query(User).filter(func.lower(User.email) == str(body.email).lower()).first()
    if not user or not user.is_active or user.archived_at or not consume_recovery(user, body.recovery_code, db):
        db.rollback()
        raise HTTPException(400, "Invalid account or recovery code. If all codes are lost, contact an administrator.")
    user.hashed_password = hash_password(body.password)
    user.totp_secret = None
    user.totp_last_step = -1
    user.auth_version += 1
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
    db.query(AuthChallenge).filter(AuthChallenge.user_id == user.id).delete()
    db.query(UserSession).filter(UserSession.user_id == user.id).update({UserSession.revoked_at: datetime.utcnow()})
    db.commit()
    return begin_auth(user, db)


def _password_meets_policy(password: str) -> bool:
    return (
        len(password) >= 12
        and len(password.encode("utf-8")) <= 72
        and re.search(r"[A-Za-z]", password) is not None
        and re.search(r"\d", password) is not None
    )


@router.put("/password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="This account uses Google sign-in and has no password to change.")
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if not _password_meets_policy(body.new_password):
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters and contain a letter and a number; maximum encoded length is 72 bytes.")

    current_user.hashed_password = hash_password(body.new_password)
    current_user.auth_version += 1
    db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None),
    ).update({UserSession.revoked_at: datetime.utcnow()})
    db.query(TrustedDevice).filter(TrustedDevice.user_id == current_user.id).delete()
    db.query(LoginCode).filter(LoginCode.user_id == current_user.id).delete()
    db.commit()
    return _issue_login(current_user, db, request=request)


@router.post("/google")
def google_login(body: GoogleAuthRequest, request: Request, db: Session = Depends(get_db)):
    """Sign in with Google using an ID token from Google Identity Services."""
    enforce_rate_limit(request, "google_login", request.client.host if request.client else "unknown", 20, 60)
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as grequests
    except ImportError:
        raise HTTPException(status_code=500, detail="Google auth library not installed")

    try:
        idinfo = id_token.verify_oauth2_token(
            body.id_token,
            grequests.Request(),
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {str(e)}")

    google_id = idinfo.get("sub")
    email = (idinfo.get("email") or "").strip().lower()
    full_name = idinfo.get("name", "")

    if not google_id or not email or idinfo.get("email_verified") is not True:
        raise HTTPException(status_code=400, detail="Invalid token: missing google_id or email")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = db.query(User).filter(func.lower(User.email) == email).first()
    if user and not user.is_active and not user.archived_at:
        raise HTTPException(403, "Account banned. Contact an administrator.")
    if not user or user.archived_at:
        if email.rsplit("@", 1)[-1] != "lspu.edu.ph" or idinfo.get("hd") != "lspu.edu.ph":
            raise HTTPException(403, "New accounts require an institutional @lspu.edu.ph Google account.")
        if user:
            release_archived_identity(user, db)
        base = email.split("@")[0]
        username, n = base, 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base}{n}"
            n += 1
        user = User(email=email, username=username, full_name=full_name, google_id=google_id,
                    is_active=True, is_verified=True, scan_reset_date=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.google_id and user.google_id != google_id:
        raise HTTPException(403, "Google identity does not match this account")
    else:
        user.google_id = google_id
        db.commit()

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return begin_auth(user, db)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_to_dict(current_user, db)


@router.get("/me/export")
def export_my_data(
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download account data and retained scan images as a ZIP archive."""
    enforce_rate_limit(request, "account_export", current_user.id, 3, 3600)
    scans = db.query(Scan).filter(Scan.user_id == current_user.id).order_by(Scan.created_at).all()
    scan_data = []
    for scan in scans:
        record = {}
        for column in Scan.__table__.columns:
            value = getattr(scan, column.name)
            record[column.name] = value.isoformat() if isinstance(value, datetime) else value
        scan_data.append(record)

    export = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "account": {
            "email": current_user.email,
            "username": current_user.username,
            "full_name": current_user.full_name or "",
            "role": current_user.role,
            "plan": current_user.plan,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "api_keys": [
            {"label": key.label, "is_active": bool(key.is_active), "created_at": key.created_at.isoformat() if key.created_at else None}
            for key in db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).all()
        ],
        "scans": scan_data,
    }

    with tempfile.NamedTemporaryFile(prefix="revelator-export-", suffix=".zip", dir=DATA_DIR, delete=False) as temp:
        archive_path = Path(temp.name)
    upload_root = UPLOAD_DIR.resolve()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("account.json", json.dumps(export, ensure_ascii=False, indent=2))
            for scan in scans:
                if not scan.image_path:
                    continue
                image_path = (UPLOAD_DIR / scan.image_path).resolve()
                if upload_root in image_path.parents and image_path.is_file():
                    archive.write(image_path, f"images/{scan.scan_id}.jpg")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    background_tasks.add_task(os.remove, archive_path)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="revelator-account-export.zip",
        background=background_tasks,
    )


@router.delete("/me")
def delete_my_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the signed-in account, its scans, and uploaded images."""
    if body.confirmation != "ARCHIVE":
        raise HTTPException(status_code=400, detail='Type "ARCHIVE" exactly to confirm account archival.')
    if body.email.strip().casefold() != current_user.email.casefold():
        raise HTTPException(status_code=400, detail="Email confirmation does not match this account.")
    if current_user.hashed_password and (
        not body.password or not verify_password(body.password, current_user.hashed_password)
    ):
        raise HTTPException(status_code=400, detail="Current password is required to archive this account.")

    archive_account(current_user, db, current_user.id)
    return {"success": True, "archived": True}


def _request_session_id(request: Request, user: User) -> str | None:
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token) if token else None
    return payload.get("sid") if payload and payload.get("sub") == user.id else None


class SessionLocationRequest(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


@router.put("/me/session-location")
def update_session_location(
    body: SessionLocationRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(UserSession).filter(
        UserSession.id == _request_session_id(request, current_user),
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > datetime.utcnow(),
    ).first()
    if not session:
        raise HTTPException(status_code=401, detail="Session unavailable")
    if (body.latitude is None) != (body.longitude is None):
        raise HTTPException(status_code=422, detail="Both coordinates are required")
    # Round to roughly kilometre precision; do not retain exact coordinates.
    session.location = (f"{body.latitude:.2f}, {body.longitude:.2f}"
                        if body.latitude is not None else None)
    db.commit()
    return {"success": True}


@router.get("/me/sessions")
def list_my_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_session_id = _request_session_id(request, current_user)
    sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.utcnow(),
        )
        .order_by(UserSession.created_at.desc())
        .all()
    )
    return {"sessions": [{
        "id": session.id,
        "label": device_label(session.label),
        "ip_address": session.ip_address,
        "location": session.location,
        "created_at": session.created_at.isoformat(),
        "last_used_at": session.last_used_at.isoformat() + "Z" if session.last_used_at else None,
        "expires_at": session.expires_at.isoformat(),
        "current": session.id == current_session_id,
    } for session in sessions]}


@router.delete("/me/sessions/{session_id}")
def revoke_my_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None),
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    session.revoked_at = datetime.utcnow()
    db.commit()
    return {"success": True}


@router.delete("/me/sessions")
def revoke_all_my_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_session_id = _request_session_id(request, current_user)
    db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None),
        UserSession.id != current_session_id if current_session_id else True,
    ).update({UserSession.revoked_at: datetime.utcnow()})
    db.commit()
    return {"success": True}


@router.get("/me/trusted-devices")
def list_my_trusted_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = db.query(TrustedDevice).filter(
        TrustedDevice.user_id == current_user.id,
        TrustedDevice.expires_at > datetime.utcnow(),
    ).order_by(TrustedDevice.created_at.desc()).all()
    return {"devices": [{
        "id": device.id,
        "label": device_label(device.label),
        "created_at": device.created_at.isoformat(),
        "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None,
        "expires_at": device.expires_at.isoformat() + "Z",
    } for device in devices]}


@router.delete("/me/trusted-devices/{device_id}")
def revoke_my_trusted_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.query(TrustedDevice).filter(
        TrustedDevice.id == device_id,
        TrustedDevice.user_id == current_user.id,
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail="Remembered device not found.")
    db.delete(device)
    db.commit()
    return {"success": True}


@router.put("/me")
def update_me(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if "full_name" in body:
        current_user.full_name = body["full_name"]
    if "username" in body:
        existing = db.query(User).filter(User.username == body["username"]).first()
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.username = body["username"]
    db.commit()
    db.refresh(current_user)
    return user_to_dict(current_user, db)




class ApiKeyRequest(BaseModel):
    api_key: str


@router.put("/api-key")
def set_api_key(
    body: ApiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy single-key endpoint - kept for backward compatibility."""
    api_key = body.api_key.strip() if body.api_key else None
    current_user.gemini_api_key = encrypt_api_key(api_key)
    db.commit()
    return {"success": True, "message": "API key saved" if api_key else "API key removed"}


# ── Multi-key endpoints ──────────────────────────────────────────────────────

def _key_to_dict(k: UserApiKey) -> dict:
    hours_until_reset = None
    if k.quota_exhausted_at:
        from datetime import timezone
        elapsed = (datetime.utcnow() - k.quota_exhausted_at).total_seconds()
        remaining = max(0, 86400 - elapsed)  # 24h window
        hours_until_reset = round(remaining / 3600, 1)

    return {
        "id": k.id,
        "label": k.label,
        "key_preview": f"...{(decrypt_api_key(k.api_key) or '')[-4:]}",
        "api_key": decrypt_api_key(k.api_key),
        "is_active": bool(k.is_active),
        # Kept for API compatibility. Quota failures are never persisted locally.
        "quota_exhausted": False,
        "hours_until_reset": None,
        "created_at": k.created_at.isoformat() if k.created_at else "",
    }


@router.get("/api-keys")
def list_api_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).order_by(UserApiKey.created_at).all()
    return {"keys": [_key_to_dict(k) for k in keys]}


class AddKeyRequest(BaseModel):
    api_key: str
    label: str = "My Key"


class UpdateKeyRequest(BaseModel):
    label: str = None
    api_key: str = None


@router.post("/api-keys")
def add_api_key(body: AddKeyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")

    count = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).count()
    if count >= 20:
        raise HTTPException(status_code=400, detail="Maximum of 20 API keys allowed.")

    key = UserApiKey(
        user_id=current_user.id,
        label=body.label.strip() or "My Key",
        api_key=encrypt_api_key(api_key),
        is_active=count == 0,  # Auto-activate if first key
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return _key_to_dict(key)


@router.delete("/api-keys/{key_id}")
def delete_api_key(key_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(UserApiKey).filter(UserApiKey.id == key_id, UserApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    db.delete(key)
    db.commit()
    return {"success": True}


@router.put("/api-keys/{key_id}/activate")
def activate_api_key(key_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keys = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).all()
    target = next((k for k in keys if k.id == key_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Key not found")
    for k in keys:
        k.is_active = (k.id == key_id)
    db.commit()
    return {"success": True}


@router.put("/api-keys/{key_id}")
def update_api_key(
    key_id: str,
    body: UpdateKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = db.query(UserApiKey).filter(UserApiKey.id == key_id, UserApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    if body.label is not None:
        key.label = body.label.strip()

    if body.api_key is not None:
        api_key = body.api_key.strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required.")
        key.api_key = encrypt_api_key(api_key)

    db.commit()
    return _key_to_dict(key)
