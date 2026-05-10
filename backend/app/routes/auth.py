"""
Authentication routes: register, login, refresh, me, Google OAuth.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, PromoCode
from ..auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from ..config import GOOGLE_CLIENT_ID

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


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name or "",
        "scans_this_month": user.scans_this_month,
        "role": user.role or "user",
        "is_active": bool(user.is_active),
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


# ── Endpoints ───────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    # Check duplicates
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        scans_this_month=0,
        scan_reset_date=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user),
    )


@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Sign in with Google using an ID token from Google Identity Services."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as grequests
    except ImportError:
        raise HTTPException(status_code=500, detail="Google auth library not installed")

    try:
        idinfo = id_token.verify_oauth2_token(body.id_token, grequests.Request(), GOOGLE_CLIENT_ID)
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
            # Create new user — generate unique username from email prefix
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

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user),
    )


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return user_to_dict(current_user)


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
    return user_to_dict(current_user)


class RedeemCodeRequest(BaseModel):
    code: str


@router.post("/redeem-code")
def redeem_code(
    body: RedeemCodeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    promo = db.query(PromoCode).filter(PromoCode.code == body.code.strip()).first()

    if not promo:
        raise HTTPException(status_code=404, detail="Invalid code")

    if not promo.is_active:
        raise HTTPException(status_code=400, detail="Code is inactive")

    if promo.expires_at and datetime.utcnow() > promo.expires_at:
        raise HTTPException(status_code=400, detail="Code has expired")

    if promo.max_uses and promo.uses_count >= promo.max_uses:
        raise HTTPException(status_code=400, detail="Code usage limit reached")

    current_user.plan = promo.plan
    promo.uses_count += 1
    db.commit()
    db.refresh(current_user)

    return {
        "success": True,
        "message": f"Plan upgraded to {promo.plan}",
        "user": user_to_dict(current_user),
    }


class ApiKeyRequest(BaseModel):
    api_key: str


@router.put("/api-key")
def set_api_key(
    body: ApiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save user's Gemini API key for quota management."""
    api_key = body.api_key.strip() if body.api_key else None

    # Validate format (should start with "AIza" for Gemini free tier keys)
    if api_key and not api_key.startswith("AIza"):
        raise HTTPException(status_code=400, detail="Invalid API key format. Gemini API keys start with 'AIza'.")

    current_user.gemini_api_key = api_key
    db.commit()
    db.refresh(current_user)

    return {
        "success": True,
        "message": "API key saved" if api_key else "API key removed",
        "has_api_key": bool(current_user.gemini_api_key),
    }
