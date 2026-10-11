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
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, UserApiKey, LoginCode, TrustedDevice, UserSession,
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
from ..email_utils import send_verification_email, send_reset_email, send_2fa_code_email, _smtp_configured
from ..operations import enforce_rate_limit
from ..key_storage import encrypt_api_key, decrypt_api_key

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ──────────────────────────

class RegisterRequest(BaseModel):
    email: str
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
        "two_factor_enabled": bool(user.two_factor_enabled) if user.two_factor_enabled is not None else True,
        "has_password": bool(user.hashed_password),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


# ── Two-factor helpers ──────────────────────────────────

def _issue_login(
    user: User,
    db: Session,
    device_token: str | None = None,
    request: Request | None = None,
) -> dict:
    """Build the standard authenticated response (tokens + user)."""
    now = datetime.utcnow()
    session = UserSession(
        user_id=user.id,
        label=(request.headers.get("user-agent", "Unknown device")[:200] if request else "Unknown device"),
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


def _device_is_trusted(user: User, device_token: str | None, db: Session) -> bool:
    """True if this remembered-device token is valid and unexpired for the user."""
    if not device_token:
        return False
    dev = (
        db.query(TrustedDevice)
        .filter(TrustedDevice.user_id == user.id,
                TrustedDevice.token_hash == hash_token(device_token))
        .first()
    )
    if not dev:
        return False
    if dev.expires_at and dev.expires_at < datetime.utcnow():
        db.delete(dev)
        db.commit()
        return False
    dev.last_used_at = datetime.utcnow()
    db.commit()
    return True


def _send_login_code(user: User, db: Session) -> bool:
    """Issue a fresh 6-digit code (replacing any prior one) and email it.

    Returns whether the email was actually sent."""
    db.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    code = generate_otp_code()
    db.add(LoginCode(
        user_id=user.id,
        code_hash=hash_token(code),
        expires_at=datetime.utcnow() + timedelta(minutes=TWO_FACTOR_CODE_TTL_MINUTES),
        attempts=0,
    ))
    db.commit()
    return send_2fa_code_email(user.email, code, TWO_FACTOR_CODE_TTL_MINUTES)


def _twofa_required_for(user: User) -> bool:
    """Whether this password account is configured to require the email-code step."""
    return bool(
        TWO_FACTOR_ENABLED
        and user.two_factor_enabled
        and user.hashed_password
    )


# ── Endpoints ───────────────────────────────────────────

@router.post("/register")
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "register", body.email, 5, 86400)
    from ..config import REQUIRE_EMAIL_VERIFICATION
    if not _password_meets_policy(body.password):
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters and contain a letter and a number.")

    # An identifier is only "taken" once it belongs to a *verified* account.
    # Any unverified row found here is a stale leftover (from the old flow, or
    # from this user themselves never finishing); reclaim it so they can re-register.
    existing_email = db.query(User).filter(User.email == body.email).first()
    if existing_email:
        if existing_email.is_verified:
            raise HTTPException(status_code=400, detail="Email already registered")
        db.delete(existing_email)
        db.commit()

    existing_username = db.query(User).filter(User.username == body.username).first()
    if existing_username:
        if existing_username.is_verified:
            raise HTTPException(status_code=400, detail="Username already taken")
        db.delete(existing_username)
        db.commit()

    # Free / laptop-hosted deployments: skip the email round-trip, create a
    # verified account now, and return tokens so the client auto-logs in.
    if not REQUIRE_EMAIL_VERIFICATION:
        user = User(
            email=body.email,
            username=body.username,
            hashed_password=hash_password(body.password),
            full_name=body.full_name or "",
            is_verified=True,
            scans_this_month=0,
            scan_reset_date=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        return _issue_login(user, db)

    # Verification required: stateless signup - no user row is created here. The
    # registration payload is encoded into the verification token; the row is
    # only inserted when the link in the email is clicked.
    token = create_signup_token(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    if not send_verification_email(body.email, token):
        raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable. Please try again later.")

    return {
        "message": "Check your email to confirm your address. Your account is created once you click the link.",
        "email": body.email,
    }


@router.post("/login")
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", body.email, 10, 900)
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before signing in. Check your inbox or request a new link.")

    # A remembered device skips the code entirely.
    if _device_is_trusted(user, body.device_token, db):
        return _issue_login(user, db, request=request)

    # Otherwise require an email code when configured. Local development may
    # fall back if SMTP is unavailable; production fails closed.
    if _twofa_required_for(user):
        if _smtp_configured() and _send_login_code(user, db):
            return {
                "requires_2fa": True,
                "email": user.email,
                "message": f"We emailed a 6-digit code to {user.email}. Enter it to finish signing in.",
            }
        if APP_ENV == "production":
            raise HTTPException(
                status_code=503,
                detail="Email security verification is temporarily unavailable. Please try again later.",
            )

    return _issue_login(user, db, request=request)


@router.post("/verify-2fa")
def verify_2fa(body: Verify2FARequest, request: Request, db: Session = Depends(get_db)):
    """Finish a 2FA login by confirming the emailed 6-digit code."""
    enforce_rate_limit(request, "verify_2fa", body.email, 10, 900)
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    rec = (
        db.query(LoginCode)
        .filter(LoginCode.user_id == user.id)
        .order_by(LoginCode.created_at.desc())
        .first()
    )
    if not rec:
        raise HTTPException(status_code=401, detail="No sign-in code is pending. Please sign in again.")

    if rec.expires_at < datetime.utcnow():
        db.delete(rec)
        db.commit()
        raise HTTPException(status_code=401, detail="That code has expired. Request a new one.")

    if rec.attempts >= TWO_FACTOR_MAX_ATTEMPTS:
        db.delete(rec)
        db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts. Please sign in again for a new code.")

    code = (body.code or "").strip().replace(" ", "")
    if hash_token(code) != rec.code_hash:
        rec.attempts += 1
        db.commit()
        remaining = max(0, TWO_FACTOR_MAX_ATTEMPTS - rec.attempts)
        raise HTTPException(status_code=401, detail=f"Incorrect code. {remaining} attempt(s) left.")

    # Correct: consume every pending code for this user.
    db.query(LoginCode).filter(LoginCode.user_id == user.id).delete()

    device_token = None
    if body.remember_device:
        device_token = generate_device_token()
        db.add(TrustedDevice(
            user_id=user.id,
            token_hash=hash_token(device_token),
            label=request.headers.get("user-agent", "Remembered device")[:200],
            expires_at=datetime.utcnow() + timedelta(days=TRUSTED_DEVICE_DAYS),
            last_used_at=datetime.utcnow(),
        ))
    db.commit()

    return _issue_login(user, db, device_token=device_token, request=request)


@router.post("/resend-2fa")
def resend_2fa(body: ResendRequest, request: Request, db: Session = Depends(get_db)):
    """Re-send the login code. Always 200 so accounts can't be enumerated."""
    enforce_rate_limit(request, "resend_2fa", body.email, 3, 3600)
    user = db.query(User).filter(User.email == body.email).first()
    if user and user.is_active and user.is_verified and _twofa_required_for(user):
        _send_login_code(user, db)
    return {"message": "If a sign-in is in progress, a new code has been sent."}


@router.put("/2fa")
def set_two_factor(
    body: Toggle2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Turn email 2FA on or off for the signed-in account."""
    current_user.two_factor_enabled = bool(body.enabled)
    if not body.enabled:
        db.query(LoginCode).filter(LoginCode.user_id == current_user.id).delete()
    db.commit()
    return {"success": True, "two_factor_enabled": bool(current_user.two_factor_enabled)}


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    if payload.get("ver", 0) != user.auth_version:
        raise HTTPException(status_code=401, detail="Session has been revoked")

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

    tokens = _issue_login(user, db)
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
def verify_email(token: str, db: Session = Depends(get_db)):
    """Confirm an email address from the link we sent.

    Two token shapes are accepted:
      - `signup`: stateless - the registration payload is in the token; create
        the user row now and mark it verified.
      - `verify`: legacy - token references an existing unverified row by id.
        Kept for any in-flight links from before the stateless flow shipped.
    """
    payload = decode_token(token)
    if not payload:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")

    token_type = payload.get("type")

    if token_type == "signup":
        email = payload.get("email")
        username = payload.get("username")
        hashed_password = payload.get("hashed_password")
        full_name = payload.get("full_name", "") or ""

        if not email or not username or not hashed_password:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")

        # Re-check uniqueness now that we're actually creating the row.
        # Reclaim any stale unverified row owning the same identifier.
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            if existing_email.is_verified:
                return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")
            db.delete(existing_email)
            db.commit()

        existing_username = db.query(User).filter(User.username == username).first()
        if existing_username:
            if existing_username.is_verified:
                return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")
            db.delete(existing_username)
            db.commit()

        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            full_name=full_name,
            is_verified=True,
            scans_this_month=0,
            scan_reset_date=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=1")

    if token_type == "verify":
        user = db.query(User).filter(User.id == payload["sub"]).first()
        if not user:
            return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")
        if not user.is_verified:
            user.is_verified = True
            db.commit()
        return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=1")

    return RedirectResponse(url=f"{FRONTEND_URL}/login?verified=0")


@router.post("/resend-verification")
def resend_verification(body: ResendRequest, request: Request, db: Session = Depends(get_db)):
    """Send a fresh verification link. Always returns success to avoid leaking which emails exist."""
    enforce_rate_limit(request, "resend_verification", body.email, 3, 3600)
    user = db.query(User).filter(User.email == body.email).first()
    if user and not user.is_verified and user.hashed_password:
        user.verification_sent_at = datetime.utcnow()
        db.commit()
        send_verification_email(user.email, create_verification_token(user.id))
    return {"message": "If that account needs verification, a new link has been sent."}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Email a password-reset link. Always returns success so emails can't be enumerated."""
    enforce_rate_limit(request, "forgot_password", body.email, 3, 3600)
    user = db.query(User).filter(User.email == body.email).first()
    # Only password accounts can reset; Google-only accounts have no password to change.
    if user and user.hashed_password:
        token = create_reset_token(user.id)
        payload = decode_token(token)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: datetime.utcnow()})
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(payload["jti"]),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        ))
        db.commit()
        send_reset_email(user.email, token)
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Set a new password using a valid reset token from the emailed link."""
    enforce_rate_limit(request, "reset_password", request.client.host if request.client else "unknown", 5, 3600)
    payload = decode_token(body.token)
    if not payload or payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    reset_id = payload.get("jti")
    reset_record = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == hash_token(reset_id or ""),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    ) if reset_id else None
    if not reset_record:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    if not _password_meets_policy(body.password):
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters and contain a letter and a number.")

    user.hashed_password = hash_password(body.password)
    # Completing a reset proves email ownership, so mark verified too.
    user.is_verified = True
    user.auth_version += 1
    reset_record.used_at = datetime.utcnow()
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).update({PasswordResetToken.used_at: datetime.utcnow()})
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update({UserSession.revoked_at: datetime.utcnow()})
    db.query(TrustedDevice).filter(TrustedDevice.user_id == user.id).delete()
    db.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    db.commit()
    return {"message": "Password updated. You can now sign in."}


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
    return _issue_login(current_user, db)


@router.post("/google", response_model=TokenResponse)
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
    email = idinfo.get("email")
    full_name = idinfo.get("name", "")

    if not google_id or not email:
        raise HTTPException(status_code=400, detail="Invalid token: missing google_id or email")

    # Find existing user by google_id
    user = db.query(User).filter(User.google_id == google_id).first()

    if not user:
        # Try to find by email to link existing accounts
        user = db.query(User).filter(User.email == email).first()
        if user:
            # Link existing email account to Google
            user.google_id = google_id
            db.commit()
        else:
            # Create new user - generate unique username from email prefix
            base = email.split("@")[0]
            username = base
            n = 1
            while db.query(User).filter(User.username == username).first():
                username = f"{base}{n}"
                n += 1

            user = User(
                email=email,
                username=username,
                hashed_password=None,  # Google users don't have passwords
                full_name=full_name,
                google_id=google_id,
                is_active=True,
                is_verified=True,  # Google already verified the email
                scans_this_month=0,
                scan_reset_date=datetime.utcnow(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    tokens = _issue_login(user, db, request=request)
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        user=user_to_dict(user, db),
    )


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
    if body.confirmation != "DELETE":
        raise HTTPException(status_code=400, detail='Type "DELETE" exactly to confirm account deletion.')
    if body.email.strip().casefold() != current_user.email.casefold():
        raise HTTPException(status_code=400, detail="Email confirmation does not match this account.")
    if current_user.hashed_password and (
        not body.password or not verify_password(body.password, current_user.hashed_password)
    ):
        raise HTTPException(status_code=400, detail="Current password is required to delete this account.")

    user_id = current_user.id
    user_dir = (UPLOAD_DIR / user_id).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if user_dir.parent == upload_root and user_dir.is_dir():
        try:
            shutil.rmtree(user_dir)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Uploaded scan files could not be removed, so the account was not deleted. Please retry or contact support.",
            ) from exc

    db.query(LoginCode).filter(LoginCode.user_id == user_id).delete()
    db.query(TrustedDevice).filter(TrustedDevice.user_id == user_id).delete()
    db.query(UserSession).filter(UserSession.user_id == user_id).delete()
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user_id).delete()
    db.query(OperationalEvent).filter(OperationalEvent.user_id == user_id).delete()
    db.query(AdminAuditLog).filter(
        (AdminAuditLog.admin_id == user_id) | (AdminAuditLog.target_user_id == user_id)
    ).delete(synchronize_session=False)
    db.delete(current_user)
    db.commit()
    return {"success": True}


def _request_session_id(request: Request, user: User) -> str | None:
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token) if token else None
    return payload.get("sid") if payload and payload.get("sub") == user.id else None


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
        "label": session.label,
        "created_at": session.created_at.isoformat(),
        "last_used_at": session.last_used_at.isoformat() if session.last_used_at else None,
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
        "label": device.label or "Remembered device",
        "created_at": device.created_at.isoformat(),
        "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None,
        "expires_at": device.expires_at.isoformat(),
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
