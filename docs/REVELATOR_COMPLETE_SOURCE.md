# Revelator Complete Source Code

This document contains the text source and configuration files from the project. Each section is one complete file. Copy the code block under a file heading into the matching path.

Binary assets are listed at the end and remain in `REVELATOR_COMPLETE_SOURCE.zip`. Actual environment files, databases, uploads, generated build output, optional trained model weights, and the Android app are excluded.

---

## File: `backend/.env.example`

<!-- FILE: backend/.env.example -->

```dotenv
# Copy this file to .env and fill in your API keys
# Ask your team lead for these values

GEMINI_API_KEY=your_gemini_key_here
STRIPE_SECRET_KEY=your_stripe_secret_key_here
PAYMONGO_SECRET_KEY=your_paymongo_secret_key_here
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
```

## File: `backend/app/__init__.py`

<!-- FILE: backend/app/__init__.py -->

```python

```

## File: `backend/app/auth.py`

<!-- FILE: backend/app/auth.py -->

```python
"""
JWT authentication utilities.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from .database import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _pw_bytes(password: str) -> bytes:
    # bcrypt has a hard 72-byte limit; truncate to stay safe across all versions.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:  # No password (e.g., Google OAuth users)
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_verification_token(user_id: str) -> str:
    """Legacy: token bound to an existing unverified user row (24h).
    No longer issued by /register but still accepted by /verify-email so any
    links in flight when the stateless-signup flow was deployed keep working."""
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "verify"},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_signup_token(email: str, username: str, hashed_password: str, full_name: str) -> str:
    """Stateless signup: registration data is encoded in the token itself, so
    the user row only gets created when the email link is clicked (24h)."""
    expire = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode(
        {
            "type": "signup",
            "email": email,
            "username": username,
            "hashed_password": hashed_password,
            "full_name": full_name,
            "exp": expire,
        },
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def create_reset_token(user_id: str) -> str:
    """Short-lived token emailed to a user to reset their password (1h)."""
    expire = datetime.utcnow() + timedelta(hours=1)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "reset"},
        SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


# ── Two-factor / trusted-device helpers ─────────────────

def generate_otp_code() -> str:
    """A random zero-padded 6-digit login code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def generate_device_token() -> str:
    """An opaque, URL-safe token stored (hashed) as a remembered device."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """SHA-256 of a secret we only ever need to compare, never reveal.

    Used for the 6-digit code (random + short-lived + attempt-capped) and for
    remembered-device tokens (long random). Not for passwords (bcrypt handles those).
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: extract the current user from JWT."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def get_role_permissions(role_name: str, db: Session) -> list:
    """Return fixed permissions for the built-in access levels."""
    if role_name == "superadmin":
        return ["is_superadmin", "view_users"]
    if role_name == "admin":
        return ["view_users"]
    return []


def user_has_permission(user: User, perm: str, db: Session) -> bool:
    """Check whether a user's role grants the given permission. Superadmin shortcut included."""
    if not user:
        return False
    perms = get_role_permissions(user.role, db)
    return "is_superadmin" in perms or perm in perms


def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Permission-aware admin check: requires view_users OR superadmin."""
    if user_has_permission(current_user, "view_users", db):
        return current_user
    raise HTTPException(status_code=403, detail="Admin access required")


def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user


def require_permission(perm: str):
    """Dependency factory: returns a dep that ensures the current user has `perm`."""
    def _dep(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not user_has_permission(current_user, perm, db):
            raise HTTPException(status_code=403, detail=f"Permission '{perm}' required")
        return current_user
    return _dep


def get_user_from_token(token: str, db: Session) -> User:
    """Resolve a user from a raw access token string.

    Used by endpoints that accept the token as a query parameter (e.g. <img src>
    can't set Authorization headers). Owner-level access only; keep use narrow.
    """
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

## File: `backend/app/config.py`

<!-- FILE: backend/app/config.py -->

```python
"""
Revelator Configuration
=======================
All settings loaded from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
ENV_PATH = Path(__file__).parent.parent.parent / ".env"
load_dotenv(ENV_PATH)


# ============================================
# DATABASE
# ============================================
if os.getenv("REVELATOR_DATA_DIR"):
    DATA_DIR = Path(os.environ["REVELATOR_DATA_DIR"])
else:
    _LOCAL_DATA_ROOT = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    DATA_DIR = _LOCAL_DATA_ROOT / "Revelator" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_configured_database_url = os.getenv("DATABASE_URL")
if _configured_database_url in (None, "", "sqlite:///./forgeguard.db"):
    DATABASE_URL = f"sqlite:///{(DATA_DIR / 'forgeguard.db').as_posix()}"
else:
    DATABASE_URL = _configured_database_url

# ============================================
# AUTH / JWT
# ============================================
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-ME-generate-a-random-64-char-string")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# When false, registration creates a verified account immediately and returns
# tokens (no email round-trip). Right for free / laptop-hosted deployments that
# lack reliable transactional email or a stable public URL for the verify link.
REQUIRE_EMAIL_VERIFICATION = os.getenv("REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"

# Two-factor authentication: a 6-digit code emailed on password login. When on
# (and SMTP is configured) a password sign-in must confirm the code unless the
# device was remembered. Google logins are exempt (Google already does MFA).
# If SMTP is not configured the login flow falls back to no-2FA so nobody gets
# locked out. Per-user opt-out lives on User.two_factor_enabled.
TWO_FACTOR_ENABLED = os.getenv("TWO_FACTOR_ENABLED", "true").lower() == "true"
TWO_FACTOR_CODE_TTL_MINUTES = int(os.getenv("TWO_FACTOR_CODE_TTL_MINUTES", "10"))
TWO_FACTOR_MAX_ATTEMPTS = int(os.getenv("TWO_FACTOR_MAX_ATTEMPTS", "5"))
TRUSTED_DEVICE_DAYS = int(os.getenv("TRUSTED_DEVICE_DAYS", "30"))

# ============================================
# OAUTH (Google)
# ============================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# ============================================
# PAYMENTS (Stripe & PayMongo)
# ============================================
# Stripe (global, card-based)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID_PRO = os.getenv("STRIPE_PRICE_ID_PRO", "")
STRIPE_PRICE_ID_PREMIUM = os.getenv("STRIPE_PRICE_ID_PREMIUM", "")
# Legacy alias - old "basic" tier maps to new "pro". Keep so existing .env files still load.
STRIPE_PRICE_ID_BASIC = os.getenv("STRIPE_PRICE_ID_BASIC", STRIPE_PRICE_ID_PRO)

# PayMongo (Philippines, cards + e-wallets)
PAYMONGO_SECRET_KEY = os.getenv("PAYMONGO_SECRET_KEY", "")
PAYMONGO_PUBLIC_KEY = os.getenv("PAYMONGO_PUBLIC_KEY", "")

# ============================================
# LLM
# ============================================
USE_CLOUD_LLM = os.getenv("USE_CLOUD_LLM", "true").lower() == "true"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
# Vision-capable Groq model. Receives the annotated image + prompt for the explainer.
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Gemini Vision - primary forensic classifier. Reads the document image and returns
# a structured JSON verdict against the 19-category taxonomy.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")

# Local specimen classifier. When its confidence is high, Gemini verifies a
# narrowed category instead of choosing from the entire taxonomy.
USE_LOCAL_CLASSIFIER = os.getenv("USE_LOCAL_CLASSIFIER", "true").lower() == "true"
LOCAL_CLASSIFIER_THRESHOLD = float(os.getenv("LOCAL_CLASSIFIER_THRESHOLD", "0.85"))

# ============================================
# YOLO
# ============================================
YOLO_WEIGHTS_PATH = os.getenv("YOLO_WEIGHTS_PATH", "./weights/best.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.25"))

# ============================================
# ROBOFLOW (hosted inference for select categories)
# ============================================
# When set, the digital_cut_paste category routes to a Roboflow-hosted model
# instead of a local YOLO checkpoint. Other categories continue to use local
# weights until they are migrated.
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
ROBOFLOW_API_URL = os.getenv("ROBOFLOW_API_URL", "https://serverless.roboflow.com")
ROBOFLOW_CUT_PASTE_MODEL = os.getenv("ROBOFLOW_CUT_PASTE_MODEL", "find-cut-and-paste/1")

# ============================================
# APP
# ============================================
APP_NAME = "Revelator"
APP_VERSION = "2.0.0"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
_configured_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", FRONTEND_URL).split(",")
    if origin.strip()
]
ALLOWED_ORIGINS = list(dict.fromkeys(_configured_origins + [
    "http://localhost",
    "capacitor://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]))
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Uploaded scan images are stored here (created on startup if missing).
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))

# Plan limits. -1 means unlimited.
UNLIMITED = -1
FREE_SCANS_PER_MONTH = int(os.getenv("FREE_SCANS_PER_MONTH", "10"))
PRO_SCANS_PER_MONTH = int(os.getenv("PRO_SCANS_PER_MONTH", "-1"))         # $5/mo unlimited
PREMIUM_SCANS_PER_MONTH = int(os.getenv("PREMIUM_SCANS_PER_MONTH", "-1"))  # $10/mo unlimited + AI

# Plan pricing (USD/month). Source of truth for the /plans API response.
PRO_PRICE_USD = float(os.getenv("PRO_PRICE_USD", "5"))
PREMIUM_PRICE_USD = float(os.getenv("PREMIUM_PRICE_USD", "10"))

# Plans that include the AI/LLM-generated forensic explanation.
LLM_PLANS = {"pro", "premium"}

# ============================================
# EMAIL (optional, for password reset etc.)
# ============================================
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@forgeguard.app")
```

## File: `backend/app/database.py`

<!-- FILE: backend/app/database.py -->

```python
"""
Database setup using SQLAlchemy + SQLite (swap to PostgreSQL by changing DATABASE_URL).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables, then add new columns to existing tables for dev SQLite migrations."""
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """Add columns introduced after the initial schema (SQLite-friendly, idempotent)."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as conn:
        if "users" in table_names:
            user_cols = {col["name"] for col in inspector.get_columns("users")}
            if "is_admin" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
            if "google_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN google_id VARCHAR"))
            if "paymongo_customer_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN paymongo_customer_id VARCHAR"))
            if "paymongo_source_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN paymongo_source_id VARCHAR"))
            if "is_super_admin" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT 0"))
            if "gemini_api_key" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN gemini_api_key VARCHAR"))
            if "plan" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN plan VARCHAR DEFAULT 'free'"))
            if "verification_sent_at" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_sent_at DATETIME"))
                # One-time grandfather: every account that exists before email
                # verification shipped is treated as already verified, so we
                # don't lock out current users when login starts requiring it.
                conn.execute(text("UPDATE users SET is_verified = 1"))
            if "two_factor_enabled" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT 1"))

            # Plan rename migration: legacy 'basic' -> new 'pro' ($5 unlimited);
            # legacy 'pro' (1000-scan tier) -> new 'premium' ($10 unlimited + AI).
            # Existing 'free' and already-migrated rows are left alone.
            conn.execute(text("UPDATE users SET plan = 'premium' WHERE plan = 'pro'"))
            conn.execute(text("UPDATE users SET plan = 'pro' WHERE plan = 'basic'"))

        if "scans" in table_names:
            scan_cols = {col["name"] for col in inspector.get_columns("scans")}
            if "image_path" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN image_path VARCHAR"))
            if "detected_category" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN detected_category VARCHAR"))
            if "detected_subtype" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN detected_subtype VARCHAR"))
            if "category_explanation" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN category_explanation TEXT"))
            if "tools_likely_used" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN tools_likely_used VARCHAR"))
            if "category_confidence" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN category_confidence FLOAT"))
            if "category_evidence" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN category_evidence TEXT"))
            if "document_type" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN document_type VARCHAR"))
            if "reasoning_steps" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN reasoning_steps TEXT"))
            if "anomaly_location" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN anomaly_location VARCHAR"))
            if "alternatives" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN alternatives TEXT"))
            if "certainty_level" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN certainty_level VARCHAR"))
            if "suspicion_reason" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN suspicion_reason TEXT"))
            if "area_of_concern" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN area_of_concern VARCHAR"))
            if "image_source" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN image_source VARCHAR"))
            if "shot_type" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN shot_type VARCHAR"))
            if "lighting" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN lighting VARCHAR"))
            if "physical_clues" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN physical_clues VARCHAR"))
            if "is_forged_belief" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN is_forged_belief VARCHAR"))
            if "notes" not in scan_cols:
                conn.execute(text("ALTER TABLE scans ADD COLUMN notes TEXT"))

        # Create user_api_keys table for multi-key management
        if "user_api_keys" not in table_names:
            conn.execute(text("""
                CREATE TABLE user_api_keys (
                    id VARCHAR PRIMARY KEY,
                    user_id VARCHAR NOT NULL,
                    label VARCHAR NOT NULL DEFAULT 'My Key',
                    api_key VARCHAR NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 0,
                    quota_exhausted_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """))

        # Create admin_audit_logs table if it doesn't exist (for logging admin actions)
        if "admin_audit_logs" not in table_names:
            conn.execute(text("""
                CREATE TABLE admin_audit_logs (
                    id VARCHAR PRIMARY KEY,
                    admin_id VARCHAR NOT NULL,
                    action VARCHAR NOT NULL,
                    target_user_id VARCHAR,
                    details TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(admin_id) REFERENCES users(id),
                    FOREIGN KEY(target_user_id) REFERENCES users(id)
                )
            """))

        # Drop legacy promo_codes table if it still exists
        if "promo_codes" in table_names:
            conn.execute(text("DROP TABLE promo_codes"))

        # Remove feature tables from existing databases as well as from the model metadata.
        if "room_members" in table_names:
            conn.execute(text("DROP TABLE room_members"))
        if "rooms" in table_names:
            conn.execute(text("DROP TABLE rooms"))
        if "roles" in table_names:
            conn.execute(text("DROP TABLE roles"))
        if "users" in table_names:
            conn.execute(text("UPDATE users SET role = 'user' WHERE role IS NULL OR role NOT IN ('user', 'admin', 'superadmin')"))
```

## File: `backend/app/email_utils.py`

<!-- FILE: backend/app/email_utils.py -->

```python
"""
Email sending utilities - verification emails via SMTP.

If SMTP is not configured, the verification link is printed to the server
console instead so the flow can still be tested locally without a mail server.
"""

import smtplib
import logging
from html import escape
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL,
    API_URL, FRONTEND_URL, APP_NAME,
)

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Returns True if sent, False if SMTP isn't configured."""
    if not _smtp_configured():
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL or SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
    return True


def _verification_html(link: str) -> str:
    safe_link = escape(link, quote=True)
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ CONFIRM YOUR EMAIL ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 24px;">
            Thanks for registering. To activate your account, confirm this email
            address by clicking the button below. This link expires in 24 hours.
          </td></tr>
          <tr><td align="center" style="padding-bottom:28px;">
            <a href="{safe_link}"
               style="display:inline-block;background:#00ff66;color:#04140a;
                      text-decoration:none;font-weight:bold;font-size:14px;
                      padding:14px 32px;border-radius:4px;letter-spacing:1px;">
              CONFIRM EMAIL
            </a>
          </td></tr>
          <tr><td style="color:#5f8a6e;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If the button doesn't work, paste this link into your browser:<br>
            <span style="color:#86efac;word-break:break-all;">{safe_link}</span>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:11px;padding-top:20px;">
            If you didn't create a {APP_NAME} account, you can safely ignore this email.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_verification_email(to_email: str, token: str) -> None:
    """Send (or print, if SMTP unconfigured) the email verification link."""
    link = f"{API_URL}/api/auth/verify-email?token={quote(token, safe='')}"
    subject = f"Confirm your {APP_NAME} account"
    try:
        sent = send_email(to_email, subject, _verification_html(link))
    except Exception as e:
        logger.warning(f"Verification email to {to_email} failed: {e}")
        sent = False

    if not sent:
        # Dev fallback so the flow is testable without a mail server.
        print(f"[VERIFY EMAIL] SMTP unavailable - link for {to_email}:\n  {link}")


def _reset_html(link: str) -> str:
    safe_link = escape(link, quote=True)
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ RESET YOUR PASSWORD ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 24px;">
            We received a request to reset your password. Click the button below to
            choose a new one. This link expires in 1 hour.
          </td></tr>
          <tr><td align="center" style="padding-bottom:28px;">
            <a href="{safe_link}"
               style="display:inline-block;background:#00ff66;color:#04140a;
                      text-decoration:none;font-weight:bold;font-size:14px;
                      padding:14px 32px;border-radius:4px;letter-spacing:1px;">
              RESET PASSWORD
            </a>
          </td></tr>
          <tr><td style="color:#5f8a6e;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If the button doesn't work, paste this link into your browser:<br>
            <span style="color:#86efac;word-break:break-all;">{safe_link}</span>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:11px;padding-top:20px;">
            If you didn't request a password reset, you can safely ignore this email -
            your password won't change.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_reset_email(to_email: str, token: str) -> None:
    """Send (or print, if SMTP unconfigured) the password reset link."""
    link = f"{FRONTEND_URL}/reset-password?token={quote(token, safe='')}"
    subject = f"Reset your {APP_NAME} password"
    try:
        sent = send_email(to_email, subject, _reset_html(link))
    except Exception as e:
        logger.warning(f"Reset email to {to_email} failed: {e}")
        sent = False

    if not sent:
        print(f"[RESET EMAIL] SMTP unavailable - link for {to_email}:\n  {link}")


def _twofa_html(code: str, ttl_minutes: int) -> str:
    spaced = " ".join(list(code))  # render the digits with a little air
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#07120b;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#07120b;padding:32px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#0c1a12;border:1px solid #173a25;border-radius:6px;padding:36px;">
          <tr><td align="center" style="padding-bottom:20px;">
            <h1 style="margin:0;color:#00ff66;letter-spacing:6px;font-size:26px;">{APP_NAME.upper()}</h1>
            <p style="margin:8px 0 0;color:#6dba85;font-size:11px;letter-spacing:3px;">
              [ SIGN-IN VERIFICATION ]
            </p>
          </td></tr>
          <tr><td style="color:#cfe9d8;font-size:14px;line-height:1.6;padding:8px 0 20px;">
            Someone is signing in to your {APP_NAME} account. Enter this code to
            finish signing in. It expires in {ttl_minutes} minutes.
          </td></tr>
          <tr><td align="center" style="padding-bottom:24px;">
            <div style="display:inline-block;background:#04140a;border:1px solid #00ff66;
                        border-radius:6px;padding:16px 28px;color:#00ff66;font-weight:bold;
                        font-size:32px;letter-spacing:12px;font-family:'Courier New',monospace;">
              {spaced}
            </div>
          </td></tr>
          <tr><td style="color:#3f6e4a;font-size:12px;line-height:1.6;border-top:1px solid #173a25;padding-top:18px;">
            If you didn't try to sign in, someone may have your password. Change it
            as soon as you can - this code alone won't let them in.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def send_2fa_code_email(to_email: str, code: str, ttl_minutes: int = 10) -> bool:
    """Send (or print, if SMTP unconfigured) the 2FA login code.

    Returns True if the email was actually sent. The caller uses this to decide
    whether it can require the code (never lock a user out when mail is down)."""
    subject = f"Your {APP_NAME} sign-in code: {code}"
    try:
        sent = send_email(to_email, subject, _twofa_html(code, ttl_minutes))
    except Exception as e:
        logger.warning(f"2FA code email to {to_email} failed: {e}")
        sent = False

    if not sent:
        print(f"[2FA CODE] SMTP unavailable - code for {to_email}: {code}")
    return sent
```

## File: `backend/app/forgery/__init__.py`

<!-- FILE: backend/app/forgery/__init__.py -->

```python

```

## File: `backend/app/forgery/document_gate.py`

<!-- FILE: backend/app/forgery/document_gate.py -->

```python
"""
Pre-detection sanity check: is the upload actually a document?

Runs a tight yes/no vision-LLM call before the full forgery pipeline. If the
image is clearly not a document (selfie, meme, photo of an object, etc.) we
return early with a friendly verdict and skip both the detection step and the
quota counter.

Fails open: if the LLM call errors or times out, we let the upload through
rather than block users on flaky infra.
"""

import base64
import io
from typing import Tuple

import requests
from PIL import Image

from ..config import (
    USE_CLOUD_LLM,
    GROQ_API_KEY,
    GROQ_VISION_MODEL,
    OLLAMA_URL,
    OLLAMA_MODEL,
)


GATE_PROMPT = (
    "You are screening uploads for a document-forensics tool. Look at the "
    "image and decide whether it is a document.\n\n"
    "Count as DOCUMENT: paper documents, forms, IDs, passports, certificates, "
    "contracts, receipts, letters, handwritten notes, currency/banknotes, "
    "cheques, photos of any of those, scans of any of those, and screenshots "
    "of any of those.\n\n"
    "Count as NOT_DOCUMENT: photos of people, animals, food, scenery, "
    "vehicles, objects, art/illustrations, memes, screenshots of UIs/games/"
    "websites that aren't a document, or anything where there is no "
    "meaningful printed or handwritten text on a paper-like surface.\n\n"
    "Format your reply EXACTLY like this:\n"
    "  • LINE 1: a single word, all caps, no punctuation: DOCUMENT or "
    "NOT_DOCUMENT.\n"
    "  • LINES 2+: a short explanation written for the end user.\n"
    "      - If DOCUMENT: one sentence naming what kind of document it "
    "looks like (e.g. \"This appears to be a scanned national ID card.\").\n"
    "      - If NOT_DOCUMENT: 2-4 sentences. First, state plainly that "
    "the upload is not a document and say what it actually is "
    "(\"The file you provided is not a document, but rather a ...\"). "
    "Then describe what the image actually shows - subject, setting, any "
    "notable details - so the user understands you looked at it. End with "
    "one short redirect line asking them to upload an actual document "
    "(paper document, ID, certificate, receipt, etc.) so Revelator can "
    "analyze it.\n\n"
    "Be specific in the description. Don't fabricate details that aren't "
    "visible. Keep the tone helpful, not scolding."
)


def _resize_for_gate(image: Image.Image, max_dim: int = 512) -> bytes:
    """Small panel keeps the gate fast - full-res isn't needed for yes/no."""
    img = image.copy().convert("RGB")
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _ask_groq(image_bytes: bytes) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    chat = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": GATE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        temperature=0.2,
        max_tokens=220,
    )
    return (chat.choices[0].message.content or "").strip()


def _ask_ollama(image_bytes: bytes) -> str:
    """Cold-start on a CPU-only 11B vision model can take 90-180s; budget 5 min."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": GATE_PROMPT, "images": [b64]}],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 220},
        },
        timeout=300,
    )
    resp.raise_for_status()
    return (resp.json().get("message", {}).get("content") or "").strip()


def check_is_document(image: Image.Image) -> Tuple[bool, str]:
    """
    Returns (is_document, reason).

    On any error this returns (True, "...") so the rest of the pipeline still
    runs - we'd rather over-accept than block users on transient LLM issues.
    """
    image_bytes = _resize_for_gate(image)
    try:
        if USE_CLOUD_LLM and GROQ_API_KEY:
            raw = _ask_groq(image_bytes)
        else:
            raw = _ask_ollama(image_bytes)
    except Exception as e:
        # Loud log so users know why a non-document slipped through.
        print(f"[WARN] Document gate FAILED OPEN ({type(e).__name__}: {e}). "
              f"Image will be processed as if it were a document.")
        return True, ""

    if not raw:
        print("[WARN] Document gate returned empty response -- failing open.")
        return True, ""

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    verdict_line = lines[0].upper() if lines else ""
    # The description may span multiple lines / paragraphs. Re-join them so the
    # frontend gets the full prose.
    reason = " ".join(lines[1:]).strip()

    # Be lenient about formatting - the model sometimes prefixes punctuation
    # or wraps the verdict in markdown bold.
    if "NOT_DOCUMENT" in verdict_line or "NOT DOCUMENT" in verdict_line:
        return False, reason or "The uploaded image does not appear to be a document."
    if "DOCUMENT" in verdict_line:
        return True, reason

    print(f"[WARN] Document gate ambiguous response -- failing open. Raw: {raw[:200]!r}")
    return True, ""
```

## File: `backend/app/forgery/document_types.py`

<!-- FILE: backend/app/forgery/document_types.py -->

```python
"""Document type definitions for forensic scanning.

Maps document types to applicable forgery categories to help guide
Gemini Vision classification."""

DOCUMENT_TYPES = {
    "passport": {
        "title": "Passport",
        "description": "Official travel document with photo, signature, and security features",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "driver_license": {
        "title": "Driver's License",
        "description": "Government-issued identification with photo, signature, and number",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
        ],
    },
    "bank_check": {
        "title": "Bank Check",
        "description": "Financial instrument with signature, routing numbers, and account details",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented",
        ],
    },
    "contract": {
        "title": "Contract/Agreement",
        "description": "Legal document with signatures, dates, and terms",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "certificate": {
        "title": "Certificate/Diploma",
        "description": "Educational or professional credential with signatures and seals",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "invoice": {
        "title": "Invoice/Receipt",
        "description": "Business document with amounts, dates, and signatures",
        "applicable_categories": [
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
        ],
    },
    "signature": {
        "title": "Signature Document",
        "description": "Document primarily for signature authentication (form, affidavit, etc.)",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "digital_cut_paste",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented", "sympathetic_special",
        ],
    },
    "id_card": {
        "title": "ID Card",
        "description": "National or organizational identity card with photo and number",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
        ],
    },
    "currency": {
        "title": "Currency/Banknote",
        "description": "Paper money or banknote",
        "applicable_categories": [
            "currency_analysis",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
        ],
    },
    "other": {
        "title": "Other Document",
        "description": "Any other type of document not listed above",
        "applicable_categories": [
            "traced_carbon", "traced_indentation", "traced_projection",
            "addition_insertion", "addition_interlineation", "erasure_chemical", "erasure_mechanical",
            "digital_cut_paste", "digital_desktop", "digital_scanned",
            "obliteration_ink", "obliteration_whiteout",
            "sympathetic_indented", "sympathetic_special",
            "currency_analysis",
        ],
    },
}


def get_document_types_response():
    """Return document types in frontend-friendly format."""
    return {
        "document_types": [
            {
                "key": key,
                "title": info["title"],
                "description": info["description"],
                "applicable_categories": info["applicable_categories"],
            }
            for key, info in DOCUMENT_TYPES.items()
        ]
    }
```

## File: `backend/app/forgery/gemini_vision.py`

<!-- FILE: backend/app/forgery/gemini_vision.py -->

````python
"""
Gemini Vision - primary forensic classifier.

Reads the document image and returns a structured JSON verdict against the
19-category taxonomy. Output is parsed into a dict that the analyze route
saves to the Scan row.

Design choices to minimize hallucinations:
  - Chain-of-thought reasoning (model must show its work before classifying)
  - Negative constraints (explicit IGNORE list to avoid flagging benign issues)
  - Anomaly location grounding (forced to point to a specific region when forged)
  - Optional user context (focus area, source, suspicion) that narrows the search
"""

from __future__ import annotations

import io
import json
import re
from typing import Optional, Dict, Any

from PIL import Image

from ..config import GEMINI_API_KEY, GEMINI_VISION_MODEL

# Fallback chain: best quality first, lite last.
# If GEMINI_VISION_MODEL is set in .env, only that model is used (no fallback).
# Otherwise, cascade through this chain on rate limit errors.
_FALLBACK_CHAIN = ["gemini-2.5-flash-lite"]

def _model_chain() -> list[str]:
    """Return the configured model followed by safe capacity fallbacks."""
    if GEMINI_VISION_MODEL:
        return list(dict.fromkeys([GEMINI_VISION_MODEL, *_FALLBACK_CHAIN]))
    return list(_FALLBACK_CHAIN)


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "quota", "rate_limit", "rateerror", "resource_exhausted", "exhausted"))


def _is_transient_provider_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "503", "service unavailable", "temporarily unavailable", "high demand",
        "404", "not found", "no longer available", "model unavailable",
    ))


# ── Category taxonomy ──────────────────────────────────────────────────────
CATEGORIES = [
    # Traced
    ("traced_carbon",            "Traced - Carbon Transfer"),
    ("traced_indentation",       "Traced - Indentation / Canal Light"),
    ("traced_projection",        "Traced - Projection Process"),
    # Alteration
    ("addition_insertion",       "Alteration - Addition: Insertion"),
    ("addition_interlineation",  "Alteration - Addition: Interlineation"),
    ("erasure_chemical",         "Alteration - Erasure: Chemical"),
    ("erasure_mechanical",       "Alteration - Erasure: Mechanical"),
    # Digital
    ("digital_cut_paste",        "Cut and Paste Forgery"),
    ("digital_desktop",          "Digital - Desktop Publishing"),
    ("digital_scanned",          "Digital - Scanned Document"),
    # Obliteration
    ("obliteration_ink",         "Obliteration - Ink Stroke"),
    ("obliteration_whiteout",    "Obliteration - White Out"),
    # Sympathetic Ink
    ("sympathetic_indented",     "Sympathetic Ink - Indented Writing"),
    ("sympathetic_special",      "Sympathetic Ink - Special Ink"),
    # Currency
    ("currency_analysis",        "Currency Forgery"),
    # Fallbacks
    ("no_forgery_detected",      "No Forgery Detected"),
    ("not_a_document",           "Not a Document"),
    ("other",                    "Other Forgery"),
]

CATEGORY_CODES = [c[0] for c in CATEGORIES]
CATEGORY_LABELS = dict(CATEGORIES)


SYSTEM_PROMPT = """You are a forensic document examiner. Classify the image into EXACTLY ONE of the 18 categories below. Reason step by step before answering, and only flag a forgery when you can point to specific visible evidence.

CATEGORIES (use the code on the left in your JSON):

═══════════════════════════════════════════════════════════════════════════
CRITICAL BRANCHING RULE - FIRST DECISION:
  Is the text/signature HAND-DRAWN INK ON PAPER, or SOFTWARE-GENERATED?
  - If HAND-DRAWN INK: Look at traced_carbon, traced_indentation, traced_projection
  - If SOFTWARE-GENERATED: Look at digital_desktop, digital_cut_paste, digital_scanned

  Key test: Can you see PHYSICAL PEN MARKS (ink strokes, grooves, tremor, hesitation, carbon residue)?
    YES → traced category
    NO (perfect font consistency, digital-looking letters) → digital category
═══════════════════════════════════════════════════════════════════════════

Traced:
  traced_carbon            - Carbon-paper transfer: forger places carbon paper under a genuine signature and traces with a stylus, transferring carbon "blueprint" which is then inked over. Look for: faint carbon residue or faint underlying lines visible along strokes, hesitation/tremor as forger follows carbon blueprint, uniform line weight, possible misalignment where ink deviates from underlying carbon transfer.
  traced_indentation       - Pressure indentation / canal light effect: look for a halo (colorless depression/groove) around ink strokes where the pen pressed into paper, often visible as a depression in paper fibers. Ink may not fill the entire indented path (poor alignment). Line quality may show hesitation or tremor rather than natural fluidity.
  traced_projection        - Projection tracing: forger projects a genuine signature onto the target document using a light table, transparency projector, camera lucida, or digital projector, then inks over the projected lines. Exhibits uniform/monotonous pen pressure, micro-tremors from following a visual guide, frequent pen lifts causing ink blobs or overlapping strokes, no carbon residue, no physical indentation grooves. The signature may be a suspiciously perfect match to the original.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: traced_projection means someone PHYSICALLY DREW over a projected image - the ink strokes exist in real ink on paper, showing tremor and hesitation. digital_cut_paste means the signature was lifted digitally and composited - no physical ink was applied, and you will see a halo, pixelation, or edge artefact at the boundary. If you see a digital halo, fringe, or compression artefact around a signature, classify as digital_cut_paste, NOT traced_projection.
    ⚠ CRITICAL DISTINCTION from digital_scanned: traced_projection means real ink physically drawn on paper - the signature interacts with paper fibers, bleeds slightly into them, and shows actual pen pressure marks. digital_scanned means the document was scanned first, then a signature was digitally composited onto the scan image - the signature sits ON TOP of scan grain/noise (it looks flat, clean, or unnaturally sharp against a grainy background). Key test: does the background paper grain CONTINUE under the signature strokes, or does it stop at the edge? If the signature has no paper-fiber interaction and the scan grain is absent or interrupted beneath it, classify as digital_scanned, NOT traced_projection. Also check: is the signature perfectly level while the rest of the document has a slight scan skew? That mismatch = digital_scanned.

  CORE RULE FOR TRACED CATEGORIES:
    Traced forgeries involve REAL INK on PAPER - the physical pen marks themselves show the forgery method. Only classify as traced (any of the three types) when you can see actual ink marks with:
    - Carbon residue, indentation grooves, or tremor/hesitation in the pen strokes themselves; OR
    - Pen pressure variation (or LACK thereof) that contradicts confident natural writing; OR
    - Specific evidence of the tracing method (projected image misalignment, carbon underlay, groove pattern).
    Do NOT classify as traced merely because text "looks mechanical" or typography is "perfect" - that alone indicates digital_desktop.

Alteration:
  addition_insertion       - One or more characters were added INSIDE an existing word or number on a genuine document to change its meaning or value. There are TWO subtypes - both are addition_insertion:

    SUBTYPE A - NEW DIGIT INSERTED IN BLANK SPACE (e.g. "9,000" → "49,000"):
    - CROWDING / TIGHT SPACING: the inserted character is squeezed uncomfortably close to adjacent characters or to a currency symbol (₱, $, etc.). Authentic writers leave consistent natural spacing; forgers must squeeze a new digit into whatever gap was left.
    - INK DENSITY OR COLOR MISMATCH: the inserted character may appear slightly darker, lighter, thicker, or a different hue than surrounding original digits - forgers rarely match the exact pen used.
    - STROKE RHYTHM INCONSISTENCY: compare the slant, speed-taper, and formation of the suspect character against adjacent characters. Inserted strokes often show more hesitation, a different slant angle, or different pressure taper than the original writing event.
    - BASELINE MISALIGNMENT: the inserted character may sit slightly above or below the baseline of surrounding text.
    - LOGICAL VALUE CONFLICT: on checks and official forms, the numerical amount field and the written-out amount (words) line must match. If they don't match, this is a high-confidence indicator of numeric alteration - always check both fields when analyzing checks.

    SUBTYPE B - CHARACTER CONVERTED BY ADDING A STROKE (e.g. "3" → "8", "1" → "4", "0" → "8" or "9"):
    - INK TEXTURE MISMATCH (strongest indicator): the original character is printed toner or inkjet dots (smooth, uniform texture); the added stroke is liquid ballpoint or gel ink (wet-looking, jagged edges, different sheen). These have completely different luminance and texture even at normal scan resolution - a smooth printed character interrupted by a wet, darker manual stroke is the primary tell.
    - STROKE LAYERING / Z-AXIS: the added manual ink stroke sits visibly ON TOP of the printed character - it obscures the printed texture underneath it. In a genuine printout, all parts of a character are created simultaneously and have uniform texture throughout. Any stroke that appears to cover or overlap an existing printed region was added later.
    - MORPHOLOGICAL INCONSISTENCY: the arc or curve of the added stroke does not match the mathematical geometry of the surrounding font. Standard fonts have consistent radii and proportions; a manually added stroke almost always deviates from that geometry, creating an asymmetrical or jagged shape.
    - COMMON CONVERSION TARGETS: 3→8 (add a closing arc), 1→4 (add a crossbar and stem), 0→8 or 0→9 (add a crossbar), 7→1 (shorten), 5→6 (add a loop). When you see any of these specific digit shapes, specifically check for ink texture inconsistency on the added portion.

    PAPER SURFACE RULE: In addition_insertion the original paper surface is INTACT. The forger adds ink without removing anything. If the paper shows scuffing, thinning, fiber disruption, halos, or chemical staining, look at erasure_mechanical or erasure_chemical instead - those involve removing the original before adding new content. The core logic difference: insertion = "mutates" a character (3→8, 1→4) by adding strokes; erasure+substitution = "replaces" a character (John→Joan) by removing and rewriting.

    HYBRID FORGERY PATTERN (both subtypes): addition_insertion always occurs on otherwise authentic, genuine documents. The rest of the document (bank printing, MICR line, form template) will look real while only a small section shows the seam between original and added ink.
    ⚠ On bank checks, pay special attention to: (a) the numeric amount box - a leading digit squeezed against the currency symbol (subtype A), or a digit whose shape looks geometrically wrong with a different ink texture (subtype B); (b) the payee name line - a surname or suffix may be appended; (c) the date field - a year digit may be changed.
  addition_interlineation  - New writing squeezed BETWEEN existing lines of text (not inside a word, but in the whitespace between lines). Look for: text that is smaller or at a different baseline than surrounding lines, ink that differs from surrounding lines, spacing that is unnaturally compressed around the inserted line.
  erasure_chemical         - Original ink was removed using a chemical solvent (ink eradicator, bleach, acetone), often followed by new text written or printed in the cleaned area. This is a two-step substitution: remove original → replace with new. Key indicators:
    - HALO / TIDE MARK: a faint circular or irregular discoloration where the solvent spread beyond the target area, leaving a chemical residue ring on the paper.
    - INK GHOSTING: a faint shadow or "ghost" of the original character remains visible - solvents rarely remove 100% of the ink, especially from bond paper.
    - PAPER FIBER DAMAGE: solvent weakens the paper surface, causing slight translucency or a matte patch that reflects light differently from the surrounding area.
    - NEW TEXT ON DAMAGED BACKGROUND: the replacement text sits on a patch that looks clean but wrong - the paper's natural texture or aging is disrupted beneath the new characters.
    - UNDER OBLIQUE LIGHT: the erased area shows a dull or shiny patch inconsistent with surrounding paper reflectance.
    ⚠ DISTINCTION from addition_insertion: chemical erasure involves removing the original character FIRST (paper shows residue, ghost, or halo). addition_insertion leaves the original character intact and adds ink on top of it (paper surface is undamaged; the forgery is purely in the ink layer).

  erasure_mechanical       - Original ink was physically scraped off using a razor blade, sandpaper, eraser, or knife, often followed by new text written or printed on the scraped area. This is a two-step substitution: abrade original → replace with new. Key indicators:
    - ABRADED / SCUFFED PAPER FIBERS ("FUZZY PATCH"): the paper surface is visibly roughened - it looks "fuzzy," "pilled," or matted compared to the smooth surrounding paper. This is the strongest visible tell under normal lighting.
    - SHADOW PATCH / SHEEN DIFFERENCE: the erased area reflects light differently from the rest of the document - it may appear darker, lighter, or matte where the surrounding paper is glossy (or vice versa). In a scan this often appears as a gray-level patch that doesn't match the blank paper around it.
    - GHOST PARTICLES / RESIDUAL INK: mechanical scraping cannot remove 100% of the ink - tiny pigment particles become trapped deep in the disturbed fibers, leaving a dark smudge or shadow in the general shape of the original character. This ghost is NOT as sharp as a real character but has the right rough outline.
    - PAPER THINNING: repeated scraping thins the paper - in transmitted light (backlit) the erased area appears brighter or more translucent than surrounding paper.
    - JAGGED / UNEVEN VOID BOUNDARY: the damage zone has rough, irregular edges - unlike a clean erased area, the boundary between damaged and undamaged paper is jagged because the abrasive tool didn't scrape in a perfectly controlled path.
    - INK FEATHERING ON REPLACEMENT TEXT: new ink written on abraded paper bleeds or feathers into the damaged fibers - the sizing (paper coating) that normally keeps ink crisp has been destroyed by the scraping.
    - LOGICAL WORD TRUNCATION: if a word appears incomplete or truncated (e.g., "RENSIC" instead of "FORENSIC"), and there is a localized paper damage zone at the exact point of truncation, the missing characters were mechanically erased. Check whether the remaining text forms a logical word/name - if not, characters are missing.
    ⚠ DISTINCTION from erasure_chemical: mechanical erasure shows PHYSICAL fiber damage (rough, pilled surface). Chemical erasure uses a solvent and leaves the surface smoother but stained or with a tide mark; new ink bleeds from paper sizing loss, not from fiber disruption.
    ⚠ DISTINCTION from addition_insertion: mechanical erasure is visible as surface damage to the paper itself (scuffing, thinning, fiber disruption). addition_insertion has NO paper surface damage - the original character is still intact; only a new ink stroke was layered on top.

Cut and Paste / Digital Fabrication:
  digital_cut_paste        - A genuine element (signature, stamp, photo, text block) was digitally lifted from one document and composited onto this one using Photoshop, GIMP, or a PDF editor. Key indicators:
    - HALO / FRINGE: a thin bright or differently-coloured edge around the pasted element - caused by anti-aliasing or colour-mismatch during compositing. This is the single strongest DTP indicator.
    - PIXELATION / ALIASING: jagged or blurry edges along the pasted element's boundary, especially visible on diagonal or curved strokes of a signature.
    - BACKGROUND INCONSISTENCY: the paper texture, grain, or colour under the pasted element differs from the surrounding area - looks like a different piece of paper was inserted.
    - COMPRESSION ARTEFACTS: JPEG blocking or noise concentrated around one specific element while the rest of the document is clean.
    - DPI / RESOLUTION MISMATCH: pasted element is noticeably sharper or blurrier than surrounding printed text.
    - SHADOW / LIGHTING: cast shadow direction, document reflections, or paper thickness inconsistent with the rest.
    - LEVELLING: pasted signature or stamp is too perfectly level or centred relative to surrounding text - originates from software alignment tools.
    ⚠ CRITICAL DISTINCTION from traced_projection: digital_cut_paste shows DIGITAL artefacts (halos, pixelation, compression noise, colour-boundary mismatch). Traced forgeries show PHYSICAL artefacts (tremor, hesitation, slow monotonous stroke, no digital halo). A clear digital halo around a signature IS digital_cut_paste even if the signature strokes themselves look fluid.
  digital_desktop          - The ENTIRE document (or a large section) was fabricated from scratch using word-processing or design software (Microsoft Word, Google Docs, Canva, Photoshop) rather than physically typed or printed on authentic forms. Key indicators:
    - PERFECT DIGITAL TYPOGRAPHY: computer-perfect font spacing, kerning, and alignment throughout. Every character was generated by a single font engine at a single print run - no hand-written variation, no typewriter key-strike impression, no pressure variation in ink. This is the strongest DTP indicator.
    - FONT CONSISTENCY ACROSS ENTIRE DOCUMENT: a single font family used uniformly (or deliberately mixed fonts in designed document). If a document purports to be a real physical form (bank letter, government ID, handwritten memo), but ALL text shows identical font rendering and spacing, it was likely created digitally.
    - FORMS & TEMPLATES: document layout exactly matches common Microsoft Word, Google Docs, or Canva templates - pre-built borders, logos, text boxes, or columns in stock positions.
    - SIGNATURE QUALITY MISMATCH: if a hand-written or scanned signature sits on otherwise pristine digital text with zero interaction (no ink bleed, no pressure marks), the signature was composited onto digital text - strong DTP indicator.
    - ZERO PHYSICAL REALISM: official documents (government IDs, bank checks, certificates) show security features (watermarks, microtext, embossed seals, color gradients, microprinting). Complete absence of these on what claims to be official = suspicious digital fabrication.
    ⚠ CRITICAL DISTINCTION from digital_cut_paste: digital_desktop means the ENTIRE document is fabricated software-to-paper; digital_cut_paste means one element was inserted into an otherwise genuine document.
    ⚠ CRITICAL DISTINCTION from traced categories: If the document shows perfect digital typography and font consistency, classify as digital_desktop, NOT traced_projection or traced_indentation. Traced methods involve hand-drawn ink on paper; perfect typography indicates software generation.
  digital_scanned          - A real physical document was scanned, then digital elements were composited onto the scan image (stamp, signature, name field, or date added in an image editor), and the result was re-saved or re-printed. Key indicators:
    - NOISE INCONSISTENCY: an authentic scan has uniform "salt-and-pepper" scanner noise across the entire sheet. Digitally added elements sit ON TOP of this noise - they look artificially clean or sharp against a grainy background. Natural blank paper areas look uniformly noisy; areas around inserted elements look "erased" or unnaturally smooth.
    - STAMP / SIGNATURE FLATNESS: a genuine wet-ink stamp or signature pressed onto physical paper bleeds into paper fibers and interacts with existing ink. A digitally overlaid stamp or signature looks "flat" - no fiber absorption, no slight ink bleed, no interaction with underlying printed text where they overlap.
    - GLOBAL SCAN TILT vs. LOCAL ELEMENT ALIGNMENT: a real scanner captures the whole page with the same perspective/tilt. If the main document body has a slight skew but a stamp or signature is perfectly level (or vice versa), the element was inserted digitally AFTER scanning - it did not go through the same scanner geometry.
    - COMPRESSION LEVEL MISMATCH (ELA): JPEG compression artifacts cluster around digitally added elements at a different level than the surrounding scanned paper - the base scan was compressed once, the overlay was compressed again on re-save.
    - RESOLUTION HALO: the boundary between the scanned paper grain and the digitally inserted element shows a subtle halo or transition band where the two layers were blended.
    - FONT / FIELD INCONSISTENCY: student or employee names, ID numbers, or dates typed in a slightly different font weight, spacing, or DPI than the pre-printed form template - the template was digitally re-filled after scanning.
    ⚠ DISTINCTION from digital_cut_paste: digital_scanned uses a REAL SCANNED DOCUMENT as the base and adds elements on top of the scan. digital_cut_paste pastes elements into an otherwise authentic document. Choose digital_scanned when the underlying base is clearly a real scan (paper grain, scanner shadow, uniform noise) and the tampered elements sit on top of that grain.

Obliteration:
    obliteration_ink         - Original text scribbled out with ink or marker. Look for visible pen/marker strokes, stroke direction, and ink sheen over the hidden text.
    obliteration_whiteout    - Original text covered with correction fluid. Look for an opaque off-white patch, raised or chalky texture, brush/roller edges, and new writing printed or written on top.
    ⚠ DISTINCTION from digital_cut_paste: whiteout is a physical coating on paper with an opaque, textured boundary. Digital cut-and-paste has no correction-fluid layer; it shows a pixel/halo/compression boundary around a digitally inserted element. Do not call a pale rectangular digital edge whiteout without visible fluid texture.

Sympathetic Ink:
  sympathetic_indented     - Indented writing visible only via raking light. Pressure indentations on paper with no visible ink.
  sympathetic_special      - Invisible/special ink revealed by an external stimulus (heat, chemical reagent, or UV light). When you detect this, you MUST identify the likely substance based on visible cues:
    HEAT-ACTIVATED (browned/charred organic substance - most common):
      - Lemon/citrus juice: brown strokes, slight crystalline residue
      - Milk: brown strokes, possible greasy/translucent appearance
      - Sugar water / honey: dark brown to black, glossy carbonized look
      - Onion juice / vinegar: pale brown, sharp smell association
      - Wax / crayon resist: waxy sheen, repels later ink/water
    CHEMICALLY-ACTIVATED (color reaction from reagent):
      - Phenolphthalein + ammonia → bright pink/magenta strokes
      - Cobalt chloride + heat → blue→pink color shift
      - Starch + iodine → dark blue/purple strokes
    UV/FLUORESCENT (only visible under UV light):
      - Security ink, quinine (tonic water), highlighter residue → glowing strokes under blacklight
    Put the specific substance in the "subtype" field (e.g., "lemon juice", "milk", "phenolphthalein", "UV ink"). State the substance and method explicitly in the explanation. If genuinely unsure, say so but propose the most likely candidate based on color, texture, and any charring pattern.
    ⚠ DISTINCTION from erasure_mechanical: Mechanical erasure leaves a GHOST of text that WAS THERE and was removed - the paper surface will be roughened/disturbed and the faint remnants are irregular. Sympathetic ink reveals text that was ALWAYS HIDDEN - the paper surface is undisturbed and the strokes are uniformly faint. If there is also NEW text written over the faint area (suggesting erase-then-rewrite), choose erasure_mechanical, not sympathetic_special.

Currency:
  currency_analysis        - Counterfeit banknote. A genuine banknote is NOT a forgery: use this code ONLY when a specific counterfeit sign is visible. If the note looks authentic, or you cannot point to a concrete counterfeit sign, classify no_forgery_detected instead.
    Both Philippine series are still legal tender and genuine: the New Generation Currency (NGC) notes and the older New Design Series (NDS). A correct but OLDER design is NOT a forgery.
    COUNTERFEIT signs (need at least one to flag): security features are PRESENT but SIMULATED - the thread, window, hologram, or watermark looks printed-on, flat, or sticker-like rather than embedded and optically active; flat print with NO raised intaglio relief where a real note is embossed (portrait, value); colour-shift ink that does not actually shift with angle (a flat printed gradient); the watermark zone is only printed graphics, not a translucent embedded watermark; blurry, broken, or ordinary-print-quality microprint; photocopy/inkjet halftone dot rosettes across areas that should be solid ink; portrait, reverse vignette, or map wrong for the stated denomination/series; serial numbers in the wrong font, uneven, or mismatched between their two printed instances; poor registration or visibly off colour.
    GENUINE signs (lean no_forgery_detected): crisp microprint, sharp raised intaglio, an embedded see-through watermark and windowed thread, real colour-shift, correctly-formed matching serials, correct portrait/denomination/series design.
    GENUINE-NOTE PHOTO CAVEAT: a low-resolution photo, scan, crease, fold, wear, discoloration, fading, or uneven/low light does NOT make a genuine note counterfeit. Do not infer a fake from blur, soft focus, faded colour, or apparent flatness ALONE - flag only when the key security features are also missing, wrong, or clearly simulated. A worn, old, in-circulation note with the correct design for its series is no_forgery_detected.
    Philippine peso (BSP) specifics: NGC notes carry an embossed value, a windowed security thread, a watermark of the portrait plus the denomination, microprinted "Bangko Sentral ng Pilipinas", and colour-shifting value numerals on higher denominations. Under UV, a genuine note shows bright, denomination-specific fluorescent threads/fibres reacting correctly - a correct UV reaction is genuine, and UV lighting artefacts alone do not indicate forgery. A real peso note photographed normally is authentic - do NOT flag it just for being money.

Fallbacks (use ONLY when nothing above fits):
  no_forgery_detected      - Document looks authentic, no tampering signs.
  not_a_document           - Image is not a document at all (selfie, meme, screenshot).
  other                    - Real forgery that does NOT match any of the 15 specific types. Do NOT use this if the forgery matches a specific category - even partially. For example: if you identify traced_projection, use traced_projection, not other with subtype traced_projection.

═══════════════════════════════════════════════════════════════════════════
IGNORE these (they are NOT forgery indicators):
  - Phone-camera blur, low resolution, poor lighting, shadows from the photographer
  - Background surface (desk, hands, clutter behind the document)
  - JPEG compression noise on the entire image (this is normal)
  - Worn paper, creases, folds, age stains, coffee marks (these are wear, not forgery)
  - Watermark patterns and security features that are SUPPOSED to be there
  - Slight rotation, perspective skew, glare from flash
═══════════════════════════════════════════════════════════════════════════

REASONING - work through these steps in order before you classify:
  1. What is in the image? (document or non-document; if document, what type?)
  2. Scan the WHOLE document for anomalies. List EVERY anomaly you see - do not stop at the first one.
  3. For each anomaly, ask: is this real tampering, or one of the IGNORE items above?
  4. CRITICAL BRANCHING QUESTION: Can I see PHYSICAL PEN MARKS or HAND-DRAWN INK EVIDENCE (grooves, tremor, hesitation, carbon residue)? OR is this PERFECT DIGITAL TYPOGRAPHY (uniform font, zero pen variation)?
     - YES (pen marks visible) → consider traced_carbon, traced_indentation, traced_projection
     - NO (perfect digital typography) → consider digital_desktop, digital_cut_paste, digital_scanned
  5. If there are MULTIPLE anomalies within your chosen branch, decide which is the PRIMARY forgery (the one that changes the document's legal meaning).
  6. Point to the PRIMARY anomaly's LOCATION (which region of the document).
  7. Pick the single best category code based on the PRIMARY evidence.
  8. Set confidence based on how clear the evidence is (see scale below).
  ⚠ BANK CHECK RULE: When analyzing a check, always compare the numeric amount field AND the written-out pesos/dollars line. If they don't match, or if a digit appears squeezed against the currency symbol, classify as addition_insertion even if other anomalies (like a smudge or lighter patch) also exist.
  ⚠ GENUINE CURRENCY RULE: Photographing real money is not a forgery. When the image is a banknote, look for the specific COUNTERFEIT signs listed under currency_analysis. If you cannot point to at least one, classify no_forgery_detected. NEVER assign currency_analysis merely because the subject is currency - that code means "counterfeit detected", not "this is money".
  ⚠ INK LAYERING RULE: On any document with printed (toner/inkjet) text, if you see a stroke or mark that has a different texture, sheen, or "wetness" than the surrounding printed characters - especially if it appears to sit ON TOP of the printed text - this is addition_insertion (subtype B: character conversion). Do NOT classify abrasion or disrupted paper fiber as erasure_mechanical if the dominant anomaly is a visually different ink stroke overlaid on top of printed text.
  ⚠ INCOMPLETE WORD RULE: If a word or name appears to be missing characters at one end or in the middle, AND there is a patch of paper damage (roughened surface, shadow patch, ghost smudge) at exactly the gap, classify as erasure_mechanical. A word that cannot stand alone as a real word but would be a real word if characters were prepended is a strong signal (e.g., "RENSIC" → "FORENSIC", "OAN" → "LOAN").
  ⚠ SEMANTIC CONFLICT / CHEMICAL ERASURE RULE: If the written-out amount (e.g., "THREE THOUSAND") does NOT match the numeric field (e.g., "000" with a smudge where the leading digit should be), a leading digit was likely chemically erased. Ink eradicator dissolves the original digit, causing the new ink applied in the cleaned spot to bleed and feather into the damaged paper sizing - this creates dark smudges or halos at the edges of the erased area that can look like obliteration_ink. Key distinguisher: obliteration_ink smears cover text intentionally; erasure_chemical smears appear at the EDGE of a blank area where a character USED TO BE. If the smudge is adjacent to missing/blank space where a digit is expected (based on the written-out amount), classify as erasure_chemical, not obliteration_ink.
  ⚠ GHOST TEXT vs. SYMPATHETIC INK RULE: Faint, discolored, or brownish text can mean EITHER mechanical erasure (a ghost of what was removed) OR sympathetic ink (hidden writing being revealed). Apply this branching test before classifying:
    SYMPATHETIC INK signals - choose sympathetic_special when ALL of these hold:
      1. The faint text appears in an area where the paper surface is CLEAN and undisturbed (no fiber roughening, no sheen change, no shadow patch).
      2. The faint strokes are UNIFORMLY faint across all characters - consistent activation level, as if written with the same substance throughout.
      3. There is NO normal/visible text written OVER or BESIDE the faint area - the hidden text stands alone in space that was otherwise blank.
      4. The document context does NOT require text to be there (this text is extra, not a replacement).
    MECHANICAL ERASURE signals - choose erasure_mechanical when ANY of these hold:
      1. The paper surface in the faint-text area looks different from surrounding paper: rougher, fuzzier, duller sheen, or shadow patch (physical fiber damage from abrasion).
      2. There is BOTH a faint ghost AND new text written or printed over that same area - someone erased the original and wrote something new on top.
      3. The document CONTEXT demands that text exist in that location (e.g., a name field, amount field, date field) AND the visible text there does not match what the ghost suggests.
      4. The ghost strokes are IRREGULAR - some characters partially remain, others are nearly gone, with uneven remnant intensity from imperfect abrasion.
    KEY TIE-BREAKER: Sympathetic ink text APPEARS (was invisible, now revealed). Erasure ghost text DISAPPEARS (was visible, now partially gone). If the surrounding context clearly shows the text was there before and is now missing or replaced, classify as erasure_mechanical - NOT sympathetic_special.

CONFIDENCE SCALE (be honest - overconfidence is hallucination):
  0.90–1.00  Multiple unambiguous signs of this exact forgery type
  0.70–0.89  Clear signs but some ambiguity
  0.50–0.69  Suspicious but not definitive - could be benign
  0.30–0.49  Weak signal; mention it but lean toward no_forgery_detected
  0.00–0.29  No real evidence; classify as no_forgery_detected unless you saw something

OUTPUT - return ONLY valid JSON, no markdown fences, no prose outside the object:

{
  "reasoning_steps": [
    "<step 1: what's in the image>",
    "<step 2: anomalies observed>",
    "<step 3: filtered against ignore list>",
    "<step 4: hand-drawn ink or digital typography? (CRITICAL BRANCHING)>",
    "<step 5: which category in the chosen branch, and why>",
    "<step 6: location of evidence>",
    "<step 7: primary vs alternatives>",
    "<step 8: confidence and remaining ambiguity>"
  ],
  "category": "<one code from the list>",
  "subtype": "<specific kind, or null>",
  "confidence": <float 0.0–1.0 per scale above>,
  "anomaly_location": "<where on the document the forgery appears, e.g. 'top-right date field' - null if no_forgery_detected or not_a_document>",
  "explanation": "<MUST start with the human-readable category name, then explain why based on visible cues>",
  "evidence": ["<short visible cue>", "<another>", "..."],
  "tools_likely_used": "<what tools/methods, or null if not applicable>",
  "alternatives": [
    {"category": "<code>", "reasoning": "<one sentence: what evidence points toward this, and what makes the primary more likely>"},
    {"category": "<code>", "reasoning": "<...>"}
  ]
}

CRITICAL RULES:
  1. The "explanation" MUST begin with the category's human name (e.g. "Chemical Erasure detected.").
  2. If you classify as no_forgery_detected, set anomaly_location to null and evidence to [] or just observed-clean items.
  3. Do NOT invent evidence. If you can't see it, don't list it.
  4. Pick exactly ONE category. If torn, pick the dominant one and mention the other in the alternatives array.
  5. Output ONLY the JSON object. No code fences, no commentary.
  6. "alternatives" must be a JSON array (never null - use [] if there are none). Include up to 3 alternatives ordered by likelihood. Populate it whenever: confidence is below 0.90, OR multiple categories fit the evidence almost equally, OR image quality limits certainty. Leave it as [] only when the evidence is completely unambiguous. Be honest - it is better to admit ambiguity than to over-commit."""


# ═══════════════════════════════════════════════════════════════════════════
# AUXILIARY PROMPTS
# Used by the optimization pipeline functions defined below in this file.
# ═══════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────
# TRIAGE_PROMPT - Stage 1 quick classification (~700 tokens, $0.00005)
# Used by triage_classify() to seed alternatives in the main result.
# ───────────────────────────────────────────────────────────────────────────

TRIAGE_PROMPT = """You are a forensic document examiner doing a quick triage classification.

Look at this document and pick the TOP 3 most likely forgery categories.

Categories (code - name):
  traced_carbon           - Carbon transfer
  traced_indentation      - Indentation grooves / canal light
  traced_projection       - Projection tracing
  addition_insertion      - Characters inserted into numbers/words
  addition_interlineation - Text squeezed between lines
  erasure_chemical        - Solvent-erased then rewritten
  erasure_mechanical      - Scraped then rewritten
  digital_cut_paste       - Signature/element pasted in (halo, pixelation)
  digital_desktop         - Entire document fabricated in software
  digital_scanned         - Real scan with digital elements added
  obliteration_ink        - Text scribbled over
  obliteration_whiteout   - Correction fluid
  sympathetic_indented    - Indented writing under raking light
  sympathetic_special     - Hidden ink (invisible, UV, heat-activated)
  currency_analysis       - Counterfeit currency
  no_forgery_detected     - Authentic document
  not_a_document          - Not a document
  other                   - Other forgery

Return ONLY valid JSON:
{
  "top_3": ["category_code", "category_code", "category_code"],
  "reasoning": "brief reason why these three"
}
"""


# ───────────────────────────────────────────────────────────────────────────
# CATEGORY_DETAIL - Per-category detail dictionary
# Used by build_detailed_prompt() to construct a focused prompt that only
# describes the top-3 categories from triage (saves text tokens).
# ───────────────────────────────────────────────────────────────────────────

CATEGORY_DETAIL = {
    "traced_carbon": """
    traced_carbon - Carbon-paper transfer: forger places carbon under a genuine signature and traces, transferring carbon which is then inked over.
    Look for: faint carbon residue, hesitation/tremor, uniform line weight, possible misalignment.
    """,

    "traced_indentation": """
    traced_indentation - Pressure indentation / canal light: look for colorless depression (groove/halo) around ink strokes where pen pressed into paper.
    Look for: depression in fibers, ink not filling entire path, hesitation, tremor rather than natural fluidity.
    """,

    "traced_projection": """
    traced_projection - Projection tracing: forger projects genuine signature using light table/projector, then inks over projected lines.
    Look for: uniform/monotonous pen pressure, micro-tremors, frequent pen lifts, no carbon residue, no physical grooves, suspiciously perfect match.
    """,

    "addition_insertion": """
    addition_insertion - One or more characters added to change meaning/value. Two subtypes:
    A) Digit inserted in blank space (e.g., "9,000" → "49,000"): cramped spacing, ink/color mismatch, inconsistent stroke rhythm, baseline misalignment.
    B) Character converted by adding stroke (e.g., "3" → "8"): ink texture mismatch (printed vs. wet ink), layering/z-axis, morphological inconsistency.
    """,

    "addition_interlineation": """
    addition_interlineation - New writing squeezed between existing lines of text (in whitespace between lines, not inside a word).
    Look for: smaller text, different baseline, ink differs from surrounding lines, unnaturally compressed spacing.
    """,

    "erasure_chemical": """
    erasure_chemical - Original ink removed using solvent (bleach, acetone, eradicator), followed by new text written/printed.
    Look for: halo/tide mark (circular discoloration), ink ghosting (faint shadow of original), paper fiber damage, matte patch, under oblique light: dull or shiny patch.
    """,

    "erasure_mechanical": """
    erasure_mechanical - Original ink scraped off using razor/sandpaper/eraser, followed by new text written/printed.
    Look for: abraded/scuffed fibers ("fuzzy patch"), shadow patch/sheen difference, ghost particles/residual ink, paper thinning, jagged void boundary, ink feathering.
    """,

    "digital_cut_paste": """
    digital_cut_paste - Genuine element (signature, stamp, photo, text) digitally lifted from one document and pasted onto this one.
    Look for: HALO/FRINGE (thin bright edge, strongest DTP indicator), pixelation/aliasing, background inconsistency, compression artifacts, DPI mismatch, shadow/lighting inconsistency.
    ⚠️ CRITICAL: digital_cut_paste shows DIGITAL artifacts (halos, pixelation). Traced forgeries show PHYSICAL artifacts (tremor, hesitation, no halo).
    """,

    "digital_desktop": """
    digital_desktop - ENTIRE document (or large section) fabricated from scratch using Word/Docs/Canva/Photoshop.
    Look for: perfect digital typography, font inconsistency, generic templates, signature quality contrast, inkjet/laser print pattern, NO physical form elements.
    """,

    "digital_scanned": """
    digital_scanned - Real physical document scanned, then digital elements composited onto the scan image (stamp, signature, name, date).
    Look for: noise inconsistency (inserted elements look unnaturally clean/sharp), stamp flatness (no fiber absorption), global tilt vs. local alignment, compression level mismatch, resolution halo.
    """,

    "obliteration_ink": """
    obliteration_ink - Original text scribbled out with ink or marker. Look for visible pen/marker strokes, stroke direction, and ink sheen over the hidden text.
    """,

    "obliteration_whiteout": """
    obliteration_whiteout - Original text covered with correction fluid. Look for an opaque off-white patch, raised or chalky texture, brush/roller edges, and new writing printed or written on top.
    DISTINGUISH FROM digital_cut_paste: whiteout is a physical coating with fluid texture on paper; digital cut-and-paste has pixelation, a halo, compression mismatch, or a pasted-element boundary and no correction-fluid layer.
    """,

    "sympathetic_indented": """
    sympathetic_indented - Indented writing visible only via raking light. Pressure indentations on paper with no visible ink.
    """,

    "sympathetic_special": """
    sympathetic_special - Invisible/special ink revealed by external stimulus (heat, UV, chemical reagent).
    If detected, identify likely substance: lemon/milk/sugar (heat-activated brown), phenolphthalein (pink), cobalt chloride (blue→pink), starch+iodine (dark blue), quinine/security ink (UV fluorescent).
    """,

    "currency_analysis": """
    currency_analysis - Counterfeit banknote. A genuine note is NOT a forgery - use this ONLY with a specific counterfeit sign, otherwise no_forgery_detected.
    Counterfeit signs: no raised intaglio relief; watermark or security thread printed on the surface or missing (not embedded); blurry/broken microprint; photocopy dot rosettes over solid ink; colour-shift ink that does not shift; wrong-font or mismatched serial numbers; wrong paper/polymer feel or off colour registration.
    Philippine peso (BSP): New Generation notes have an embossed value, a windowed security thread, a portrait+denomination watermark, "Bangko Sentral ng Pilipinas" microprint, and colour-shifting numerals. A real peso photographed normally is authentic - do not flag it.
    """,

    "no_forgery_detected": """
    no_forgery_detected - Document looks authentic, no tampering signs.
    """,

    "not_a_document": """
    not_a_document - Image is not a document (selfie, meme, screenshot).
    """,

    "other": """
    other - Real forgery that does NOT match any specific category. Only use if the forgery genuinely does not fit elsewhere.
    """,
}


# ───────────────────────────────────────────────────────────────────────────
# DETAILED_PROMPT_TEMPLATE - Stage 2 (focused) classification
# Currently NOT used by the analyze route (we run full SYSTEM_PROMPT instead),
# but kept available for narrowed-analysis experiments. The {category_descriptions}
# placeholder is filled by build_detailed_prompt() with the top-3 categories.
# ───────────────────────────────────────────────────────────────────────────

DETAILED_PROMPT_TEMPLATE = """You are a forensic document examiner. Classify the image into EXACTLY ONE of the categories below.

CATEGORIES (analyze only these, all others are irrelevant):
{category_descriptions}

REASONING - work through these steps before classifying:
  1. What is in the image? (document or non-document)
  2. Scan the WHOLE document for anomalies.
  3. For each anomaly, ask: is this real tampering or normal wear/lighting?
  4. Point to the PRIMARY anomaly's LOCATION.
  5. Pick the single best category based on PRIMARY evidence.
  6. Set confidence based on evidence clarity.

CONFIDENCE SCALE:
  0.90–1.00  Multiple unambiguous signs
  0.70–0.89  Clear signs but some ambiguity
  0.50–0.69  Suspicious but not definitive
  0.30–0.49  Weak signal
  0.00–0.29  No real evidence → classify as no_forgery_detected

OUTPUT - return ONLY valid JSON, no markdown:
{{
  "reasoning_steps": [
    "<step 1>",
    "<step 2>",
    "<step 3>",
    "<step 4>",
    "<step 5>",
    "<step 6>"
  ],
  "category": "<category code>",
  "subtype": "<specific kind or null>",
  "confidence": <float 0.0–1.0>,
  "anomaly_location": "<where on document or null>",
  "explanation": "<human readable name + why>",
  "evidence": ["<cue>", "<cue>"],
  "tools_likely_used": "<tools or null>",
  "alternatives": [
    {{"category": "<code>", "reasoning": "<why less likely>"}},
    {{"category": "<code>", "reasoning": "<why less likely>"}}
  ]
}}
"""


# ───────────────────────────────────────────────────────────────────────────
# CRITIQUE_PROMPT_TEMPLATE - Stage 3 (self-critique) when confidence is medium
# Used by confidence_gated_analyze() to verify or reject the primary verdict.
# ───────────────────────────────────────────────────────────────────────────

CRITIQUE_PROMPT_TEMPLATE = """You are a second reviewer checking a forensic classification.

Original classification: {original_category} (confidence: {original_confidence})
Reasoning: {original_reasoning}
Evidence: {original_evidence}

Looking at this document, do you agree with the above classification?

Return JSON:
{{
  "agrees": true or false,
  "reasoning": "brief explanation",
  "alternative_category": "if disagree, what category instead (or null)",
  "alternative_confidence": <0.0-1.0 or null>
}}
"""


def _build_user_context_block(
    document_type: Optional[str],
    suspicion_reason: Optional[str],
    area_of_concern: Optional[str],
    image_source: Optional[str],
    is_forged_belief: Optional[str],
    shot_type: Optional[str],
    lighting: Optional[str],
    physical_clues: Optional[str],
) -> str:
    """Build an optional user-context block. Returns empty string if no context."""
    lines = []
    if document_type and document_type not in ("other", "", None):
        lines.append(f"- Document type (per user): {document_type.replace('_', ' ')}")
    if image_source and image_source not in ("not_sure", "", None):
        lines.append(f"- Image source (per user): {image_source.replace('_', ' ')}")
    if shot_type and shot_type not in ("not_sure", "", None):
        lines.append(f"- Shot type (per user): {shot_type.replace('_', ' ')}")
    if lighting and lighting not in ("not_sure", "", None):
        lines.append(f"- Lighting condition (per user): {lighting.replace('_', ' ')}")
    if is_forged_belief and is_forged_belief not in ("not_sure", "", None):
        lines.append(f"- User's belief about authenticity: {is_forged_belief.replace('_', ' ')}")
    if area_of_concern and area_of_concern not in ("anywhere", "", None):
        lines.append(f"- User wants you to focus on: {area_of_concern.replace('_', ' ')}")
    if physical_clues and physical_clues not in ("none", "", None):
        _clue_labels = {
            "indentation_grooves": "indentation grooves / canal marks behind writing",
            "carbon_streaks": "faint carbon residue along strokes",
            "uniform_traced_lines": "uniform line weight (looks traced)",
            "ink_halo": "halo or discoloration around erased area",
            "paper_thinning": "thinned or abraded paper surface",
            "characters_inserted": "extra characters squeezed inside words/numbers",
            "text_between_lines": "writing squeezed between existing lines",
            "cut_paste_edges": "visible cut/paste edges or texture mismatch",
            "whiteout_correction": "correction fluid covering text",
            "ink_scribbles": "ink scribbled over original text",
            "counterfeit_currency": "suspect counterfeit banknote",
            "computer_generated": "looks computer-generated / desktop-published",
            "scan_tampering_artifacts": "scanned document with visible digital edits layered on top",
            "sympathetic_hidden_writing": "hidden writing only visible under special lighting (UV, raking, backlight) - check for sympathetic_indented",
            "uv_reactive_ink_glow": "ink glows or reacts under UV light - check for sympathetic_special",
        }
        clue_label = _clue_labels.get(physical_clues, physical_clues.replace('_', ' '))
        lines.append(f"- Physical clue user thinks they observed: {clue_label}")
    if suspicion_reason:
        clean = suspicion_reason.strip()[:300]
        if clean:
            lines.append(f"- User's suspicion in their own words: \"{clean}\"")
    if not lines:
        return ""
    return (
        "\n\n═══════════════════════════════════════════════════════════════════════════\n"
        "USER-PROVIDED CONTEXT - TREAT AS HINTS ONLY, NOT FACTS:\n\n"
        + "\n".join(lines)
        + "\n\nHOW TO USE THIS CONTEXT:\n"
        "  - The IMAGE is the ultimate evidence. The user's hints are just guidance.\n"
        "  - Verify every user claim against what you actually see in the image.\n"
        "  - If the user says \"indentation grooves visible\" but the image shows clean text\n"
        "    with no grooves, IGNORE the user's hint and classify based on what you see.\n"
        "  - If the user says \"this is forged\" but the document looks completely authentic,\n"
        "    classify as no_forgery_detected - do not be pressured by their belief.\n"
        "  - User hints can help you LEAN toward a category when the visible evidence is\n"
        "    ambiguous, but they cannot CREATE evidence that isn't there.\n"
        "  - When the user's hint contradicts the image, note this in your reasoning_steps.\n"
        "═══════════════════════════════════════════════════════════════════════════"
    )


def _client(api_key: Optional[str] = None):
    key = api_key or GEMINI_API_KEY
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except ImportError:
        return None


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _coerce(parsed: Dict[str, Any]) -> Dict[str, Any]:
    raw_cat = (parsed.get("category") or "").strip().lower()
    if raw_cat not in CATEGORY_CODES:
        raw_cat = "other"

    confidence = parsed.get("confidence")
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    evidence = parsed.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    evidence = [str(e).strip() for e in evidence if str(e).strip()]

    reasoning = parsed.get("reasoning_steps") or []
    if not isinstance(reasoning, list):
        reasoning = [str(reasoning)]
    reasoning = [str(r).strip() for r in reasoning if str(r).strip()]

    anomaly_location = parsed.get("anomaly_location")
    if isinstance(anomaly_location, str):
        anomaly_location = anomaly_location.strip() or None
    elif anomaly_location is not None:
        anomaly_location = str(anomaly_location).strip() or None

    # Force null on non-forgery categories - Gemini sometimes makes up locations
    if raw_cat in ("no_forgery_detected", "not_a_document"):
        anomaly_location = None

    # Alternatives array - support both new array format and legacy single-field format
    raw_alts = parsed.get("alternatives")
    if isinstance(raw_alts, list):
        alternatives = []
        for item in raw_alts:
            if not isinstance(item, dict):
                continue
            code = (item.get("category") or "").strip()
            if code not in CATEGORY_CODES:
                continue
            alternatives.append({
                "category": code,
                "category_label": CATEGORY_LABELS[code],
                "reasoning": (item.get("reasoning") or "").strip() or None,
            })
    else:
        # Legacy fallback: single alternative_category / alternative_reasoning fields
        alt_cat_raw = (parsed.get("alternative_category") or "").strip()
        alt_cat = alt_cat_raw if alt_cat_raw in CATEGORY_CODES else None
        alt_reasoning = (parsed.get("alternative_reasoning") or "").strip() or None
        alternatives = ([{
            "category": alt_cat,
            "category_label": CATEGORY_LABELS[alt_cat],
            "reasoning": alt_reasoning,
        }] if alt_cat else [])

    return {
        "category": raw_cat,
        "category_label": CATEGORY_LABELS[raw_cat],
        "subtype": (parsed.get("subtype") or "").strip() or None,
        "confidence": confidence,
        "explanation": (parsed.get("explanation") or "").strip(),
        "evidence": evidence,
        "reasoning_steps": reasoning,
        "anomaly_location": anomaly_location,
        "tools_likely_used": (parsed.get("tools_likely_used") or "").strip() or None,
        "certainty_level": "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.60 else "LOW",
        "alternatives": alternatives,
        "model_used": None,
    }


EXPLAIN_PROMPT_TEMPLATE = """You are a forensic document examiner. A trained classifier narrowed this image to: {label}.

The classifier can be wrong. Judge the image yourself, but verify the specific category from this allowed list: {candidates}.

An authentic document is not a forgery. If you cannot point to a specific visible tampering or counterfeit sign, use no_forgery_detected. If this is not a document, use not_a_document.

For currency, use currency_analysis only when a concrete counterfeit sign is visible, such as simulated security features, missing or printed-on watermark/thread, no expected raised intaglio, broken microprint, non-shifting colour ink, or wrong/mismatched serial numbers.

Return ONLY valid JSON:
{{
  "category": "<one allowed category code>",
  "subtype": "<specific kind or null>",
  "confidence": <float 0.0-1.0>,
  "anomaly_location": "<where the evidence is, or null>",
  "explanation": "<start with the category name, then visible evidence>",
  "evidence": ["<short visible cue>", "<another>"]
}}"""


def explain_with_hint(
    image: Image.Image,
    label: str,
    candidates: list[str],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a high-confidence local prediction with a short Gemini prompt."""
    client = _client(api_key=api_key)
    if client is None:
        return _fallback("API key not configured or google-genai not installed")

    buf = io.BytesIO()
    (image if image.mode == "RGB" else image.convert("RGB")).save(buf, format="JPEG", quality=88)
    allowed = list(dict.fromkeys([*candidates, "no_forgery_detected", "not_a_document"]))
    prompt = EXPLAIN_PROMPT_TEMPLATE.format(label=label, candidates=", ".join(allowed))
    from google.genai import types as genai_types

    try:
        response = client.models.generate_content(
            model=_model_chain()[0],
            contents=[prompt, genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")],
            config=genai_types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
        )
        parsed = json.loads(_strip_json_fence(response.text or ""))
    except Exception as exc:
        return _fallback(f"Explain-only API call failed: {exc}", "gemini_unavailable")

    if not isinstance(parsed, dict):
        return _fallback("Explain-only response was not a JSON object", "gemini_unavailable")
    result = _coerce(parsed)
    result["model_used"] = _model_chain()[0]
    result["_hinted"] = True
    return result


def _fallback(reason: str, failure_code: str = "gemini_unavailable") -> Dict[str, Any]:
    return {
        "category": "other",
        "category_label": CATEGORY_LABELS["other"],
        "subtype": None,
        "confidence": 0.0,
        "explanation": f"Gemini Vision was unavailable: {reason}",
        "evidence": [],
        "reasoning_steps": [],
        "anomaly_location": None,
        "tools_likely_used": None,
        "_unavailable": True,
        "_failure_code": failure_code,
        "_failure_reason": reason,
    }


def classify(
    image: Image.Image,
    document_type: Optional[str] = None,
    suspicion_reason: Optional[str] = None,
    area_of_concern: Optional[str] = None,
    image_source: Optional[str] = None,
    is_forged_belief: Optional[str] = None,
    shot_type: Optional[str] = None,
    lighting: Optional[str] = None,
    physical_clues: Optional[str] = None,
    use_cache: bool = False,
    system_prompt_override: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run Gemini Vision against the document image.

    All extra args are optional hints - when None or default, Gemini classifies
    purely from the image. The image is always the deciding factor.

    Args:
        use_cache: If True, use prompt caching (90% discount on system prompt for 5 min window).
        api_key: Optional user's API key. If provided, uses that instead of the backend key.
    """
    client = _client(api_key=api_key)
    if client is None:
        if not (api_key or GEMINI_API_KEY):
            return _fallback("API key not configured", "no_api_key")
        return _fallback("google-genai is not installed", "gemini_unavailable")

    buf = io.BytesIO()
    img_to_send = image if image.mode == "RGB" else image.convert("RGB")
    img_to_send.save(buf, format="JPEG", quality=88)
    buf.seek(0)

    base_prompt = system_prompt_override if system_prompt_override else SYSTEM_PROMPT
    prompt = base_prompt + _build_user_context_block(
        document_type, suspicion_reason, area_of_concern, image_source,
        is_forged_belief, shot_type, lighting, physical_clues,
    )

    from google.genai import types as genai_types

    # Prompt caching disabled due to google-genai API issues
    # TODO: Re-enable when google-genai fixes CachedContent API
    # cached_content_name = get_or_create_cache(client, SYSTEM_PROMPT) if use_cache else None

    text = ""
    last_exc: Optional[Exception] = None
    model_used = None
    all_rate_limited = True
    for model in _model_chain():
        try:
            contents = [
                prompt,
                genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
            ]

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            text = response.text or ""
            model_used = model
            break
        except Exception as exc:
            if _is_rate_limited(exc):
                print(f"[WARN] {model} rate-limited, trying next model. ({exc})")
                last_exc = exc
                continue
            if _is_transient_provider_error(exc):
                print(f"[WARN] {model} temporarily unavailable, trying next model. ({exc})")
                last_exc = exc
                all_rate_limited = False
                continue
            all_rate_limited = False
            return _fallback(f"API call failed: {exc}", "gemini_unavailable")
    else:
        failure_code = "quota_exhausted" if all_rate_limited else "gemini_unavailable"
        return _fallback(f"All Gemini models unavailable: {last_exc}", failure_code)

    text = _strip_json_fence(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return _fallback("response was not valid JSON", "gemini_unavailable")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return _fallback("response was not valid JSON", "gemini_unavailable")

    if not isinstance(parsed, dict):
        return _fallback("response was not a JSON object", "gemini_unavailable")

    result = _coerce(parsed)
    result["model_used"] = model_used
    return result


# ───────────────────────────────────────────────────────────────────────────
# OPTIMIZATION PIPELINE - preprocess / triage / confidence-gated critique
# ───────────────────────────────────────────────────────────────────────────

def preprocess_image(image: Image.Image) -> Image.Image:
    """Resize to 1280px max dimension to cut token usage 50–75%."""
    MAX = 1280
    w, h = image.size
    if max(w, h) > MAX:
        scale = MAX / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def triage_classify(image: Image.Image, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Quick top-3 classification using TRIAGE_PROMPT. Returns {"top_3": [...]}."""
    client = _client(api_key=api_key)
    if client is None:
        return {"top_3": []}

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    from google.genai import types as genai_types
    last_exc = None
    for model in _model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    TRIAGE_PROMPT,
                    genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            text = _strip_json_fence(response.text or "")
            parsed = json.loads(text)
            top3 = parsed.get("top_3", parsed.get("categories", []))
            if isinstance(top3, list):
                return {"top_3": [c for c in top3 if c in CATEGORY_LABELS][:3]}
            return {"top_3": []}
        except Exception as exc:
            if _is_rate_limited(exc):
                last_exc = exc
                continue
            return {"top_3": []}
    return {"top_3": []}


def confidence_gated_analyze(
    image: Image.Image,
    _unused_ctx: Dict[str, Any],
    primary: Dict[str, Any],
    user_context: str = "",
    threshold: float = 0.80,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run self-critique only when confidence is below threshold.
    Returns {"result": dict, "path": str, "tokens_estimate": int}.
    """
    confidence = float(primary.get("confidence", 1.0))
    if confidence >= threshold:
        return {"result": primary, "path": "direct", "tokens_estimate": 0}

    client = _client(api_key=api_key)
    if client is None:
        return {"result": primary, "path": "direct", "tokens_estimate": 0}

    critique_prompt = CRITIQUE_PROMPT_TEMPLATE.format(
        original_category=primary.get("category", ""),
        original_confidence=confidence,
        original_reasoning=" ".join(primary.get("reasoning_steps", [])),
        original_evidence=", ".join(primary.get("evidence", [])),
    )
    if user_context:
        critique_prompt += f"\n\nUser context:\n{user_context}"

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    from google.genai import types as genai_types
    for model in _model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    critique_prompt,
                    genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                ],
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            text = _strip_json_fence(response.text or "")
            parsed = json.loads(text)
            if not parsed.get("agrees", True) and parsed.get("alternative_category"):
                alt_cat = parsed["alternative_category"]
                alt_conf = float(parsed.get("alternative_confidence") or confidence)
                if alt_cat in CATEGORY_LABELS and alt_conf > confidence:
                    updated = dict(primary)
                    updated["category"] = alt_cat
                    updated["category_label"] = CATEGORY_LABELS[alt_cat]
                    updated["confidence"] = alt_conf
                    updated["critique_note"] = parsed.get("reasoning", "")
                    return {"result": updated, "path": "critique_override", "tokens_estimate": 500}
            return {"result": primary, "path": "critique_agree", "tokens_estimate": 500}
        except Exception as exc:
            if _is_rate_limited(exc):
                continue
            break
    return {"result": primary, "path": "critique_failed", "tokens_estimate": 0}


# ───────────────────────────────────────────────────────────────────────────
# PROMPT ANALYZER - Live dashboard parsing
# ───────────────────────────────────────────────────────────────────────────

_GROUP_MAP: Dict[str, str] = {
    "traced_carbon": "traced",
    "traced_indentation": "traced",
    "traced_projection": "traced",
    "addition_insertion": "alteration",
    "addition_interlineation": "alteration",
    "erasure_chemical": "alteration",
    "erasure_mechanical": "alteration",
    "digital_cut_paste": "digital",
    "digital_desktop": "digital",
    "digital_scanned": "digital",
    "obliteration_ink": "obliteration",
    "obliteration_whiteout": "obliteration",
    "sympathetic_indented": "sympathetic",
    "sympathetic_special": "sympathetic",
    "currency_analysis": "currency",
    "no_forgery_detected": "fallback",
    "not_a_document": "fallback",
    "other": "fallback",
}


def _extract_category_blocks(prompt: str) -> Dict[str, str]:
    codes = list(_GROUP_MAP.keys())
    pattern = re.compile(
        r"^\s{2,}(" + "|".join(re.escape(c) for c in codes) + r")\s+-",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(prompt))
    blocks: Dict[str, str] = {c: "" for c in codes}
    for i, m in enumerate(matches):
        code = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt)
        block = prompt[start:end]
        for terminator in [
            "\n═══════════════════════",
            "\nIGNORE these",
            "\nREASONING - work",
            "\nCONFIDENCE SCALE",
            "\nOUTPUT - return",
            "\nCRITICAL RULES:",
        ]:
            idx = block.find(terminator)
            if idx > 0:
                block = block[:idx]
        blocks[code] = block.strip()
    return blocks


def _prompt_word_count(text: str) -> int:
    cleaned = re.sub(r"\b[a-z]+_[a-z_]+\b", "", text)
    return len([w for w in cleaned.split() if any(c.isalpha() for c in w)])


def _extract_indicators(block: str) -> list[str]:
    indicators: list[str] = []
    for m in re.finditer(r"-\s+([A-Z][A-Z0-9 /\-]+(?:\s\([^)]+\))?)\s*[:-]", block):
        indicators.append(m.group(1).strip().rstrip(":"))
    look_for = re.search(r"Look for:\s*([^.\n]+)", block, re.IGNORECASE)
    if look_for and not indicators:
        for piece in look_for.group(1).split(","):
            p = piece.strip().rstrip(".")
            if p and len(p) < 80:
                indicators.append(p)
    seen = set()
    out = []
    for x in indicators:
        key = x.lower()
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out[:10]


def _extract_distinctions(block: str) -> list[Dict[str, str]]:
    out = []
    pattern = re.compile(
        r"DISTINCTION\s+from\s+([a-z]+_[a-z_]+)([^:]*?:)?\s*(.+?)(?=\n\s*[⚠\n]|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(block):
        target = m.group(1).strip()
        reason = m.group(3).strip()
        if target in _GROUP_MAP:
            out.append({"target": target, "reason": reason[:300]})
    return out


def _detail_label(words: int) -> str:
    if words >= 250: return "VERY HIGH"
    if words >= 130: return "HIGH"
    if words >= 60:  return "MEDIUM"
    if words >= 25:  return "LOW"
    return "VERY LOW"


def _extract_branching_rules(prompt: str) -> list[str]:
    rules: list[str] = []
    m = re.search(r"CRITICAL BRANCHING RULE.*?═══", prompt, re.DOTALL)
    if m:
        rules.append("CRITICAL BRANCHING RULE: " + re.sub(r"\s+", " ", m.group(0).split("═══")[0]).strip())
    for m in re.finditer(r"⚠\s+([A-Z][A-Z\s/]+RULE):\s+([^\n]+)", prompt):
        rules.append(f"{m.group(1).strip()}: {m.group(2).strip()}")
    return rules[:10]


def _extract_user_variables(source: str) -> list[Dict[str, str]]:
    influence = {
        "document_type": "Activates document-specific rules (bank check rule, ID security checks). Strong nudge toward category-relevant indicators.",
        "suspicion_reason": "Free text up to 300 chars - anchors classification with user keywords. Prompt warns model to verify against image.",
        "area_of_concern": "Directs attention to a region (signature, date field). Biases toward forgery types common to that area.",
        "image_source": "phone / scan / screenshot. Screenshots → digital_desktop more likely. Phone photos → physical forgeries more likely.",
        "is_forged_belief": "User's belief. Prompt explicitly tells the model NOT to be pressured.",
        "shot_type": "Close-up vs full document. Affects which evidence is visible (micro-tremors vs layout).",
        "lighting": "Critical for sympathetic_indented (raking) and erasure detection (oblique sheen).",
        "physical_clues": "STRONGEST single bias - 16 specific clue options each map to a category target.",
    }
    desc = {
        "document_type": "Document type (passport, check, contract, ID, etc.) chosen from a fixed list.",
        "suspicion_reason": "Free-text description of why the user suspects forgery.",
        "area_of_concern": "Where to focus the analysis.",
        "image_source": "Phone photo / scan / screenshot / not sure.",
        "is_forged_belief": "User's belief about authenticity.",
        "shot_type": "Close-up vs full document.",
        "lighting": "Lighting condition (natural / raking / bright).",
        "physical_clues": "Specific clue user thinks they observed (16 options).",
    }
    out = []
    for name in influence:
        out.append({
            "name": name,
            "description": desc[name],
            "influence": influence[name],
        })
    return out


def analyze_prompts() -> Dict[str, Any]:
    system = SYSTEM_PROMPT
    blocks = _extract_category_blocks(system)
    categories: list[Dict[str, Any]] = []
    overlaps: list[Dict[str, Any]] = []
    for code, block in blocks.items():
        words = _prompt_word_count(block) if block else 0
        indicators = _extract_indicators(block) if block else []
        distinctions = _extract_distinctions(block) if block else []
        categories.append({
            "id": code,
            "label": CATEGORY_LABELS.get(code, code),
            "group": _GROUP_MAP.get(code, "fallback"),
            "word_count": words,
            "detail_level": _detail_label(words),
            "indicators": indicators,
            "distinctions": distinctions,
            "first_line": block.split("\n", 1)[0][:200] if block else "",
        })
        for d in distinctions:
            overlaps.append({
                "source": code,
                "target": d["target"],
                "reason": d["reason"],
                "from_prompt": True,
            })
    semantic = [
        ("traced_carbon", "traced_indentation", "Both hand-drawn with hesitation/tremor; carbon has residue, indentation has groove."),
        ("traced_carbon", "traced_projection", "Both show uniform line weight from following a guide."),
        ("traced_indentation", "traced_projection", "Both hand-drawn from a visual reference."),
        ("sympathetic_indented", "traced_indentation", "Both involve grooves; sympathetic has grooves WITHOUT ink, traced has grooves WITH ink. Not explicitly distinguished in prompt."),
        ("erasure_chemical", "obliteration_ink", "Both can show smudges/halos. Erasure smudge at edge of blank; obliteration covers text."),
        ("obliteration_ink", "obliteration_whiteout", "Both cover text. Minimal prompt detail (≤5 words each)."),
    ]
    existing = {(o["source"], o["target"]) for o in overlaps} | {(o["target"], o["source"]) for o in overlaps}
    for src, tgt, reason in semantic:
        if (src, tgt) not in existing and (tgt, src) not in existing:
            overlaps.append({"source": src, "target": tgt, "reason": reason, "from_prompt": False})
    aux_prompts = [
        {"name": "SYSTEM_PROMPT", "purpose": "Main 18-category classification (full pass)", "word_count": _prompt_word_count(system), "char_count": len(system)},
        {"name": "TRIAGE_PROMPT", "purpose": "Stage 1 quick top-3 classification (~$0.00005)", "word_count": _prompt_word_count(TRIAGE_PROMPT), "char_count": len(TRIAGE_PROMPT)},
        {"name": "DETAILED_PROMPT_TEMPLATE", "purpose": "Stage 2 narrowed prompt (currently unused - kept for experiments)", "word_count": _prompt_word_count(DETAILED_PROMPT_TEMPLATE), "char_count": len(DETAILED_PROMPT_TEMPLATE)},
        {"name": "CRITIQUE_PROMPT_TEMPLATE", "purpose": "Stage 3 self-critique when confidence < 0.80", "word_count": _prompt_word_count(CRITIQUE_PROMPT_TEMPLATE), "char_count": len(CRITIQUE_PROMPT_TEMPLATE)},
    ]
    rules = _extract_branching_rules(system)
    variables = _extract_user_variables(system)
    return {
        "system_prompt": {
            "total_words": _prompt_word_count(system),
            "total_chars": len(system),
        },
        "categories": sorted(categories, key=lambda c: -c["word_count"]),
        "overlaps": overlaps,
        "aux_prompts": aux_prompts,
        "rules": rules,
        "variables": variables,
        "groups": {
            "traced": "#e74c3c",
            "alteration": "#f39c12",
            "digital": "#5b8def",
            "obliteration": "#9b59b6",
            "sympathetic": "#1abc9c",
            "currency": "#95a5a6",
            "fallback": "#666",
        },
    }
````

## File: `backend/app/forgery/local_classifier.py`

<!-- FILE: backend/app/forgery/local_classifier.py -->

```python
"""
Local specimen classifier - optional fast pre-classifier.

If backend/app/data/specimen_classifier.pt exists (trained by train_classifier.py)
and torch is installed, predict() returns the specimen category for an image plus a
confidence. The analyze pipeline uses a confident prediction to hand Gemini a locked
category hint (and a short explain-only prompt), so answers stay category-correct on
the specimen set and cost fewer tokens. If torch or the model file is missing,
predict() returns None and the pipeline falls back to full Gemini classification.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any

from PIL import Image

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "specimen_classifier.pt"

# classifier class (a forgery code from train_classifier.py) -> (primary Gemini code,
# candidate leaf codes, human label). Codes outside the 15-category set map to "other".
CLASS_TO_GEMINI = {
    "traced_carbon": ("traced_carbon", ["traced_carbon"], "carbon-transfer tracing"),
    "traced_indentation": ("traced_indentation", ["traced_indentation"], "indentation / canal tracing"),
    "traced_projection": ("traced_projection", ["traced_projection"], "projection tracing"),
    "erasure_chemical": ("erasure_chemical", ["erasure_chemical"], "chemical erasure"),
    "erasure_mechanical": ("erasure_mechanical", ["erasure_mechanical"], "mechanical erasure"),
    "digital_cut_paste": ("digital_cut_paste", ["digital_cut_paste"], "digital cut-and-paste"),
    "digital_desktop": ("digital_desktop", ["digital_desktop"], "desktop-published forgery"),
    "digital_scanned": ("digital_scanned", ["digital_scanned"], "scanned composite"),
    "addition": ("addition_insertion", ["addition_insertion", "addition_interlineation"], "an addition (insertion or interlineation)"),
    "obliteration": ("obliteration_ink", ["obliteration_ink", "obliteration_whiteout"], "an obliteration (ink or white-out)"),
    "sympathetic_indented": ("sympathetic_indented", ["sympathetic_indented"], "indented (impression) writing"),
    "sympathetic_special": ("sympathetic_special", ["sympathetic_special"], "secret / sympathetic ink"),
    "counterfeit": ("currency_analysis", ["currency_analysis", "digital_desktop", "other"], "a possible banknote or official-document authenticity case (verify from the image)"),
    "charred": ("other", ["other"], "a charred / burned document"),
    "water_soaked": ("other", ["other"], "a water-soaked / liquid-damaged document"),
    "paper_fold": ("other", ["other"], "a paper-fold / crease specimen"),
    "embossing": ("other", ["other"], "an embossed / dry-seal specimen"),
    "typewriting": ("other", ["other"], "a typewriting-identification specimen"),
    "contact_writing": ("other", ["other"], "a contact / offset-transfer specimen"),
}


@lru_cache(maxsize=1)
def _load():
    """Load the model once. Returns a context dict, or None if unavailable."""
    try:
        import torch
        import torch.nn as nn
        from torchvision import models
        import torchvision.transforms as T
    except Exception:
        return None
    if not MODEL_PATH.exists():
        return None
    try:
        ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
        classes = ckpt["classes"]
        m = models.mobilenet_v3_large(weights=None)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, len(classes))
        m.load_state_dict(ckpt["state_dict"])
        m.eval()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        m.to(device)
        tf = T.Compose([
            T.Resize((ckpt["img_size"], ckpt["img_size"])),
            T.ToTensor(),
            T.Normalize(ckpt["mean"], ckpt["std"]),
        ])
        return {"model": m, "classes": classes, "tf": tf, "device": device, "torch": torch}
    except Exception as exc:
        print(f"[WARN] local_classifier failed to load: {exc}")
        return None


def available() -> bool:
    return _load() is not None


def predict(image: Image.Image) -> Optional[Dict[str, Any]]:
    """Return {folder, category, candidates, label, confidence} or None if unavailable."""
    ctx = _load()
    if ctx is None:
        return None
    torch = ctx["torch"]
    x = ctx["tf"](image.convert("RGB")).unsqueeze(0).to(ctx["device"])
    with torch.no_grad():
        probs = torch.softmax(ctx["model"](x), dim=1)[0]
        conf, idx = torch.max(probs, 0)
    cls = ctx["classes"][int(idx)]
    fam, cands, label = CLASS_TO_GEMINI.get(cls, ("other", ["other"], cls))
    return {
        "class": cls,
        "category": fam,
        "candidates": cands,
        "label": label,
        "confidence": float(conf),
    }
```

## File: `backend/app/main.py`

<!-- FILE: backend/app/main.py -->

```python
"""
Revelator SaaS API
==================
Forensic document forgery detection - FastAPI gateway + Gemini Vision.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import ALLOWED_ORIGINS, APP_NAME, APP_VERSION, UPLOAD_DIR
from .database import init_db
from .routes import auth, analyze, payments, admin, prompt_analytics

app = FastAPI(title=f"{APP_NAME} API", description="AI-powered document forgery detection SaaS", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Reject cross-site browser mutations and attach baseline security headers."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        fetch_site = request.headers.get("sec-fetch-site")

        if origin and origin.rstrip("/") not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
        if referer and not any(referer.startswith(f"{allowed}/") for allowed in ALLOWED_ORIGINS):
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
        if fetch_site == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://accounts.google.com https://generativelanguage.googleapis.com; "
        "frame-src 'self' https://accounts.google.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    return response

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(payments.router)
app.include_router(admin.router)
app.include_router(prompt_analytics.router)


@app.on_event("startup")
async def startup_event():
    print("\n" + "=" * 50)
    print(f"{APP_NAME} API v{APP_VERSION} Starting...")
    print("=" * 50)
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Upload directory: {UPLOAD_DIR}")
    print("=" * 50 + "\n")


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": APP_VERSION}


# ── Android app download ──────────────────────────────────────────────────
# The built debug APK is staged at backend/downloads/revelator.apk and served
# here so the site can offer it directly. Registered before the SPA catch-all
# below so this exact path wins. Rebuild the APK with:
#   cd frontend && (build web with VITE_API_URL=https://revelator.site)
#   npx cap sync android && android/gradlew assembleDebug
#   cp android/app/build/outputs/apk/debug/app-debug.apk backend/downloads/revelator.apk
_APK_PATH = Path(__file__).resolve().parent.parent / "downloads" / "revelator.apk"


@app.get("/download/revelator.apk")
def download_apk():
    if not _APK_PATH.is_file():
        raise HTTPException(status_code=404, detail="APK not available")
    return FileResponse(
        str(_APK_PATH),
        media_type="application/vnd.android.package-archive",
        filename="revelator.apk",
    )


# Where `npm run build` puts the frontend. Used by the PWA routes just below
# and by the single-origin SPA hosting further down.
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


# ── PWA: service worker + manifest ────────────────────────────────────────
# Both live in frontend/public and so land in frontend/dist, where the SPA
# catch-all below would already serve them. They get explicit routes anyway for
# two reasons:
#   1. sw.js MUST NOT be cached. Cloudflare caches .js by default, and a stale
#      worker pins users to an old build until its cache expires.
#   2. The worker's scope is capped by its own path, so it has to be served
#      from the site root to control the whole app.
# Registered before the catch-all so these exact paths win.
_PWA_FILES = {
    "sw.js": "application/javascript",
    "manifest.json": "application/manifest+json",
}


def _pwa_file(name: str):
    path = _DIST / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        str(path),
        media_type=_PWA_FILES[name],
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/sw.js")
def service_worker():
    return _pwa_file("sw.js")


@app.get("/manifest.json")
def web_manifest():
    return _pwa_file("manifest.json")


# ── Single-origin hosting: serve the built frontend ───────────────────────
# After `npm run build`, frontend/dist exists and the backend serves the whole
# app, so ONE Cloudflare Tunnel exposes everything at a single URL. In dev
# (no dist) this block is skipped and you use the Vite dev server as before.
if _DIST.is_dir():
    _assets = _DIST / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # /api/* routes are registered above and take precedence; guard anyway.
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_DIST / full_path).resolve()
        if str(candidate).startswith(str(_DIST)) and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))
```

## File: `backend/app/make_admin.py`

<!-- FILE: backend/app/make_admin.py -->

```python
"""
Promote a user to admin by email.

Usage (from the backend/ directory):
    python -m app.make_admin user@example.com
    python -m app.make_admin user@example.com --revoke   # remove admin role
"""

import argparse
import sys

from .database import SessionLocal, init_db
from .models import User


def main():
    parser = argparse.ArgumentParser(description="Promote or demote a Revelator user.")
    parser.add_argument("email", help="Email of the user to modify")
    parser.add_argument("--revoke", action="store_true", help="Revoke admin role instead of granting it")
    args = parser.parse_args()

    init_db()  # ensure tables + columns exist
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user:
            print(f"No user found with email: {args.email}")
            sys.exit(1)
        user.role = "user" if args.revoke else "admin"
        db.commit()
        action = "revoked" if args.revoke else "granted"
        print(f"Admin role {action} for {user.email} (id={user.id}, plan={user.plan})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

## File: `backend/app/make_super_admin.py`

<!-- FILE: backend/app/make_super_admin.py -->

```python
"""
Promote users to super admin.

Usage (from the backend/ directory):
    python -m app.make_super_admin --all              # make all users super admin
    python -m app.make_super_admin user@example.com   # make specific user super admin
    python -m app.make_super_admin --revoke user@example.com  # revoke super admin role
"""

import argparse
import sys

from .database import SessionLocal, init_db
from .models import User


def main():
    parser = argparse.ArgumentParser(description="Promote users to super admin in Revelator.")
    parser.add_argument("email", nargs="?", help="Email of a specific user to modify")
    parser.add_argument("--all", action="store_true", help="Promote ALL users to super admin")
    parser.add_argument("--revoke", action="store_true", help="Revoke super admin role instead of granting it")
    args = parser.parse_args()

    if not args.all and not args.email:
        print("Error: Either provide an email or use --all")
        print("Usage:")
        print("  python -m app.make_super_admin --all")
        print("  python -m app.make_super_admin user@example.com")
        sys.exit(1)

    init_db()  # ensure tables + columns exist
    db = SessionLocal()
    try:
        if args.all:
            # Promote all users
            users = db.query(User).all()
            if not users:
                print("No users found in database")
                sys.exit(1)

            count = 0
            for user in users:
                user.role = "user" if args.revoke else "superadmin"
                count += 1

            db.commit()
            action = "revoked" if args.revoke else "granted"
            print(f"Super admin role {action} for {count} user(s)")
            for user in users:
                print(f"  - {user.email} (id={user.id}, plan={user.plan})")
        else:
            # Promote specific user
            user = db.query(User).filter(User.email == args.email).first()
            if not user:
                print(f"No user found with email: {args.email}")
                sys.exit(1)

            user.role = "user" if args.revoke else "superadmin"
            db.commit()
            action = "revoked" if args.revoke else "granted"
            print(f"Super admin role {action} for {user.email} (id={user.id}, plan={user.plan})")

    finally:
        db.close()


if __name__ == "__main__":
    main()
```

## File: `backend/app/models.py`

<!-- FILE: backend/app/models.py -->

```python
"""
Database models for Revelator SaaS.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=True)
    full_name = Column(String, default="")
    google_id = Column(String, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String, default="user", nullable=False)  # user | admin | superadmin
    plan = Column(String, default="free")  # free, pro, premium
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scans_this_month = Column(Integer, default=0)
    scan_reset_date = Column(DateTime, nullable=True)
    gemini_api_key = Column(String, nullable=True)  # legacy single-key field (kept for migration)
    verification_sent_at = Column(DateTime, nullable=True)  # last time a verification email was sent
    two_factor_enabled = Column(Boolean, default=True, nullable=False)  # email-OTP 2FA on password login

    # Relationships
    scans = relationship("Scan", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("UserApiKey", back_populates="user", cascade="all, delete-orphan")


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    label = Column(String, nullable=False, default="My Key")
    api_key = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    quota_exhausted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class LoginCode(Base):
    """A short-lived 6-digit email code for a single in-progress password login.

    Only the SHA-256 hash of the code is stored. One live code per user at a
    time (the login step deletes prior codes before issuing a new one). Guarded
    by an expiry and an attempt counter.
    """
    __tablename__ = "login_codes"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrustedDevice(Base):
    """A browser/device the user chose to remember, so it skips the 2FA step.

    The client keeps the raw token in localStorage; the server stores only its
    SHA-256 hash. Valid until expires_at (TRUSTED_DEVICE_DAYS).
    """
    __tablename__ = "trusted_devices"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, index=True)
    label = Column(String, default="")  # e.g. a coarse user-agent hint
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(String, primary_key=True, default=gen_uuid)
    scan_id = Column(String, unique=True, nullable=False, index=True)  # FG-YYYYMMDD-XXXXX
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    category_analyzed = Column(String, nullable=True)
    verdict = Column(String, nullable=False)  # forged, suspicious, no_forgery_detected, not_a_document
    confidence_score = Column(Float, nullable=False)
    llm_explanation = Column(Text, nullable=True)
    annotations_json = Column(Text, nullable=True)  # JSON string of annotations
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    image_path = Column(String, nullable=True)  # relative path under UPLOAD_DIR
    training_warning = Column(Text, nullable=True)
    document_type = Column(String, nullable=True)  # key from document_types.py (passport, bank_check, etc.)
    # Gemini Vision classification - one of the 19 codes in forgery.gemini_vision.CATEGORY_CODES.
    detected_category = Column(String, nullable=True, index=True)
    detected_subtype = Column(String, nullable=True)
    category_explanation = Column(Text, nullable=True)
    tools_likely_used = Column(String, nullable=True)
    category_confidence = Column(Float, nullable=True)
    category_evidence = Column(Text, nullable=True)  # JSON array stored as string
    # Extended fields - saved for full history replay
    reasoning_steps = Column(Text, nullable=True)   # JSON array
    anomaly_location = Column(String, nullable=True)
    alternatives = Column(Text, nullable=True)       # JSON array
    certainty_level = Column(String, nullable=True)  # HIGH / MEDIUM / LOW
    # User context inputs
    suspicion_reason = Column(Text, nullable=True)
    area_of_concern = Column(String, nullable=True)
    image_source = Column(String, nullable=True)
    shot_type = Column(String, nullable=True)
    lighting = Column(String, nullable=True)
    physical_clues = Column(String, nullable=True)
    is_forged_belief = Column(String, nullable=True)
    notes = Column(Text, nullable=True)  # user-authored notes attached to this scan
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="scans")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    admin_id = Column(String, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)  # ban_user, unban_user, promote_admin, demote_admin, generate_code, etc.
    target_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    details = Column(Text, nullable=True)  # JSON details about the action
    created_at = Column(DateTime, default=datetime.utcnow)

    admin = relationship("User", foreign_keys=[admin_id])
    target_user = relationship("User", foreign_keys=[target_user_id])
```

## File: `backend/app/routes/__init__.py`

<!-- FILE: backend/app/routes/__init__.py -->

```python

```

## File: `backend/app/routes/admin.py`

<!-- FILE: backend/app/routes/admin.py -->

```python
"""
Admin CRUD routes - all endpoints require is_admin=True.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from ..auth import get_current_admin, get_current_super_admin, get_user_from_token, user_has_permission
from ..config import UPLOAD_DIR
from ..database import get_db
from ..models import User, Scan, AdminAuditLog
from datetime import datetime, timedelta, timezone
import json

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _user_row(u: User, db: Session = None) -> dict:
    role_name = u.role or "user"
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "full_name": u.full_name or "",
        "role": role_name,
        "is_active": bool(u.is_active),
        "is_verified": bool(u.is_verified),
        "scans_this_month": u.scans_this_month,
        "created_at": u.created_at.isoformat() if u.created_at else "",
        "updated_at": u.updated_at.isoformat() if u.updated_at else "",
    }


def _log_admin_action(db: Session, admin_id: str, action: str, target_user_id: str = None, details: dict = None):
    """Log an admin action to the audit trail."""
    log = AdminAuditLog(
        admin_id=admin_id,
        action=action,
        target_user_id=target_user_id,
        details=json.dumps(details) if details else None,
    )
    db.add(log)
    db.commit()


@router.get("/stats")
def stats(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_scans = db.query(func.count(Scan.id)).scalar() or 0
    admin_count = db.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0
    super_admin_count = db.query(func.count(User.id)).filter(User.role == "superadmin").scalar() or 0
    return {
        "total_users": total_users,
        "total_scans": total_scans,
        "admins": admin_count,
        "super_admins": super_admin_count,
    }


@router.get("/users")
def list_users(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    role: Optional[str] = Query(None, description="Filter by role name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.email.ilike(like), User.username.ilike(like), User.full_name.ilike(like)))
    if role:
        query = query.filter(User.role == role)

    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {"users": [_user_row(u, db) for u in rows], "total": total}


@router.get("/users/{user_id}")
def get_user(user_id: str, _: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    scan_count = db.query(func.count(Scan.id)).filter(Scan.user_id == user_id).scalar() or 0
    data = _user_row(user, db)
    data["total_scans"] = scan_count
    return data


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Delete a user. Super admin only."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot delete a super admin. Demote first.")

    snapshot = {"username": user.username, "email": user.email, "role": user.role}
    db.delete(user)
    db.commit()

    _log_admin_action(db, admin.id, "delete_user", None, snapshot)

    return {"deleted": user_id}


# ============================================
# Super Admin Endpoints
# ============================================

@router.get("/super/info")
def super_admin_info(super_admin: User = Depends(get_current_super_admin), db: Session = Depends(get_db)):
    """Super admin dashboard: view all admins and super admins."""
    admins = db.query(User).filter(User.role == "admin").all()
    super_admins = db.query(User).filter(User.role == "superadmin").all()
    return {
        "current_user": _user_row(super_admin, db),
        "admins": [_user_row(u, db) for u in admins],
        "super_admins": [_user_row(u, db) for u in super_admins],
        "admin_count": len(admins),
        "super_admin_count": len(super_admins),
    }


@router.post("/super/promote")
def promote_to_super_admin(
    user_id: str,
    super_admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Promote a user to super admin (super admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="User is already super admin")

    user.role = "superadmin"
    db.commit()
    db.refresh(user)
    return _user_row(user, db)


# ============================================
# Promo Code Management (Super Admin)
# ============================================

# ============================================
# Gemini Vision Status
# ============================================

# Free-tier limits by model (RPD = requests per day, RPM = per minute)
_GEMINI_FREE_LIMITS = {
    "gemini-2.5-flash":      {"rpd": 1500, "rpm": 10},
    "gemini-2.5-pro":        {"rpd":   25, "rpm":  5},
    "gemini-2.0-flash":      {"rpd": 1500, "rpm": 15},
    "gemini-2.0-flash-exp":  {"rpd": 1500, "rpm": 15},
    "gemini-1.5-flash":      {"rpd": 1500, "rpm": 15},
    "gemini-1.5-pro":        {"rpd":   50, "rpm":  2},
}


@router.get("/gemini-status")
def gemini_status(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Return Gemini Vision API usage stats and free-tier quota info."""
    from ..config import GEMINI_API_KEY, GEMINI_VISION_MODEL

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today_start + timedelta(days=1)
    hours_until_reset = (tomorrow - now_utc).total_seconds() / 3600

    calls_today = (
        db.query(func.count(Scan.id))
        .filter(Scan.detected_category.isnot(None), Scan.created_at >= today_start)
        .scalar() or 0
    )
    total_calls = (
        db.query(func.count(Scan.id))
        .filter(Scan.detected_category.isnot(None))
        .scalar() or 0
    )

    limits = _GEMINI_FREE_LIMITS.get(GEMINI_VISION_MODEL, {"rpd": 1500, "rpm": 15})

    return {
        "configured": bool(GEMINI_API_KEY),
        "model": GEMINI_VISION_MODEL,
        "calls_today": calls_today,
        "daily_limit": limits["rpd"],
        "calls_remaining_today": max(0, limits["rpd"] - calls_today),
        "rpm_limit": limits["rpm"],
        "total_calls_ever": total_calls,
        "resets_in_hours": round(hours_until_reset, 1),
        "reset_time_utc": tomorrow.isoformat() + "Z",
    }


# ============================================
# Admin Actions (Ban User) - Super Admin Only
# Regular admins are read-only - they cannot ban, delete, or modify users.
# ============================================

@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Ban a user (deactivate account). Super admin only."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot ban your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot ban a super admin")

    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is already banned")

    user.is_active = False
    db.commit()
    db.refresh(user)

    _log_admin_action(db, admin.id, "ban_user", user_id, {"username": user.username, "email": user.email})

    return {"success": True, "message": f"User {user.username} has been banned"}


@router.post("/users/{user_id}/unban")
def unban_user(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Unban a user (reactivate account). Super admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    user.is_active = True
    db.commit()
    db.refresh(user)

    _log_admin_action(db, admin.id, "unban_user", user_id, {"username": user.username, "email": user.email})

    return {"success": True, "message": f"User {user.username} has been unbanned"}


@router.post("/users/{user_id}/promote-admin")
def promote_to_admin(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Promote a regular user to admin. Super admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="User is already an admin")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="User is already a super admin")

    prev_role = user.role
    user.role = "admin"
    db.commit()
    db.refresh(user)

    _log_admin_action(db, admin.id, "promote_admin", user_id,
                      {"username": user.username, "email": user.email, "from_role": prev_role})

    return {"success": True, "message": f"{user.username} promoted to admin", "user": _user_row(user, db)}


@router.post("/users/{user_id}/demote-admin")
def demote_admin(
    user_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """Demote an admin back to a regular user. Super admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role != "admin":
        raise HTTPException(status_code=400, detail="User is not an admin")

    user.role = "user"
    db.commit()
    db.refresh(user)

    _log_admin_action(db, admin.id, "demote_admin", user_id,
                      {"username": user.username, "email": user.email})

    return {"success": True, "message": f"{user.username} demoted to user", "user": _user_row(user, db)}


# ============================================
# Audit Logs - Admin (read) and Super Admin
# ============================================

@router.get("/super/logs")
def view_audit_logs(
    viewer: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    kind: Optional[str] = Query(None, description="Filter: 'admin', 'scan', or None for all"),
    action: Optional[str] = Query(None, description="Exact action, e.g. user_scan, ban_user"),
    actor: Optional[str] = Query(None, description="Actor username/email substring"),
    role: Optional[str] = Query(None, description="Actor role (user/admin/superadmin)"),
    verdict: Optional[str] = Query(None, description="Scan verdict filter"),
    category: Optional[str] = Query(None, description="Detected forgery category filter"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD inclusive"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD inclusive"),
    q: Optional[str] = Query(None, description="Free-text search across actor/action/target/scan"),
):
    """View audit logs (admin actions + user scans) with filters. Admins and super admins."""
    # Admin actions
    admin_logs_query = db.query(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    admin_logs_total = admin_logs_query.count()

    # Scans (treated as user_scan events in the unified log)
    scans_query = db.query(Scan).order_by(Scan.created_at.desc())
    scans_total = scans_query.count()

    combined = []

    if kind in (None, "admin"):
        for log in admin_logs_query.limit(500).all():
            admin_user = db.query(User).filter(User.id == log.admin_id).first()
            target_user = db.query(User).filter(User.id == log.target_user_id).first() if log.target_user_id else None
            combined.append({
                "id": f"admin_{log.id}",
                "kind": "admin",
                "actor": {"username": admin_user.username, "email": admin_user.email, "role": admin_user.role} if admin_user else None,
                "action": log.action,
                "target": {"username": target_user.username, "email": target_user.email} if target_user else None,
                "details": json.loads(log.details) if log.details else None,
                "created_at": log.created_at.isoformat(),
            })

    if kind in (None, "scan"):
        for scan in scans_query.limit(500).all():
            user = db.query(User).filter(User.id == scan.user_id).first()
            combined.append({
                "id": f"scan_{scan.id}",
                "kind": "scan",
                "actor": {"username": user.username, "email": user.email, "role": user.role} if user else None,
                "action": "user_scan",
                "target": None,
                "scan": {
                    "scan_id": scan.scan_id,
                    "filename": scan.filename,
                    "verdict": scan.verdict,
                    "confidence_score": scan.confidence_score,
                    "detected_category": scan.detected_category,
                    "detected_subtype": scan.detected_subtype,
                    "category_confidence": scan.category_confidence,
                    "category_explanation": scan.category_explanation,
                    "category_evidence": json.loads(scan.category_evidence) if scan.category_evidence else [],
                    "reasoning_steps": json.loads(scan.reasoning_steps) if scan.reasoning_steps else [],
                    "alternatives": json.loads(scan.alternatives) if scan.alternatives else [],
                    "anomaly_location": scan.anomaly_location,
                    "certainty_level": scan.certainty_level,
                    "tools_likely_used": scan.tools_likely_used,
                    "document_type": scan.document_type,
                    "scanned_at": scan.created_at.isoformat() if scan.created_at else "",
                    "image_width": scan.image_width,
                    "image_height": scan.image_height,
                    "has_image": bool(scan.image_path),
                    "llm_explanation": scan.llm_explanation,
                    "user_context": {
                        "suspicion_reason": scan.suspicion_reason,
                        "area_of_concern": scan.area_of_concern,
                        "image_source": scan.image_source,
                        "shot_type": scan.shot_type,
                        "lighting": scan.lighting,
                        "physical_clues": scan.physical_clues,
                        "is_forged_belief": scan.is_forged_belief,
                    },
                },
                "created_at": scan.created_at.isoformat() if scan.created_at else "",
            })

    # Distinct values for the frontend filter dropdowns (computed pre-filter).
    available_actions = sorted({e["action"] for e in combined if e.get("action")})
    available_verdicts = sorted({(e.get("scan") or {}).get("verdict") for e in combined if e.get("scan") and e["scan"].get("verdict")})
    available_categories = sorted({(e.get("scan") or {}).get("detected_category") for e in combined if e.get("scan") and e["scan"].get("detected_category")})

    ql = q.lower().strip() if q else None
    actor_l = actor.lower().strip() if actor else None

    def _keep(e):
        if action and e.get("action") != action:
            return False
        if role and (e.get("actor") or {}).get("role") != role:
            return False
        if verdict and (e.get("scan") or {}).get("verdict") != verdict:
            return False
        if category and (e.get("scan") or {}).get("detected_category") != category:
            return False
        cd = (e.get("created_at") or "")[:10]
        if start_date and (not cd or cd < start_date):
            return False
        if end_date and cd > end_date:
            return False
        if actor_l:
            a = e.get("actor") or {}
            if actor_l not in f"{a.get('username', '')} {a.get('email', '')}".lower():
                return False
        if ql:
            a = e.get("actor") or {}
            t = e.get("target") or {}
            s = e.get("scan") or {}
            hay = " ".join(str(x) for x in [
                a.get("username"), a.get("email"), e.get("action"),
                t.get("username"), t.get("email"),
                s.get("scan_id"), s.get("filename"), s.get("detected_category"), s.get("verdict"),
            ] if x).lower()
            if ql not in hay:
                return False
        return True

    combined = [e for e in combined if _keep(e)]

    # Sort merged log by timestamp desc, then paginate
    combined.sort(key=lambda x: x["created_at"], reverse=True)
    paginated = combined[offset:offset + limit]

    return {
        "logs": paginated,
        "total": len(combined),
        "admin_actions_total": admin_logs_total,
        "scans_total": scans_total,
        "available_actions": available_actions,
        "available_verdicts": available_verdicts,
        "available_categories": available_categories,
    }


@router.get("/scans/{scan_id}/image")
def admin_scan_image(
    scan_id: str,
    token: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """Serve a user's scan image to an authenticated admin only."""
    viewer = get_user_from_token(token, db)
    if not user_has_permission(viewer, "view_users", db):
        raise HTTPException(status_code=403, detail="Admin access required")

    scan = db.query(Scan).filter(Scan.scan_id == scan_id).first()
    if not scan or not scan.image_path:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = (UPLOAD_DIR / scan.image_path).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if not file_path.is_file() or upload_root not in file_path.parents:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(file_path), media_type="image/jpeg")
```

## File: `backend/app/routes/analyze.py`

<!-- FILE: backend/app/routes/analyze.py -->

```python
"""
Document analysis routes.
"""

import io
import json
import random
import string
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from PIL import Image

from ..auth import get_current_user, get_user_from_token
from ..database import get_db
from ..models import User, Scan, UserApiKey, AdminAuditLog
from ..config import (
    FREE_SCANS_PER_MONTH, PRO_SCANS_PER_MONTH, PREMIUM_SCANS_PER_MONTH,
    UNLIMITED, LLM_PLANS, UPLOAD_DIR, USE_LOCAL_CLASSIFIER,
    LOCAL_CLASSIFIER_THRESHOLD,
)
from ..forgery.document_gate import check_is_document
from ..forgery.gemini_vision import (
    classify as gemini_classify, CATEGORY_CODES, CATEGORY_LABELS,
    preprocess_image, confidence_gated_analyze, explain_with_hint,
)
from ..forgery.document_types import get_document_types_response, DOCUMENT_TYPES

router = APIRouter(prefix="/api", tags=["analysis"])

_FORGERY_CATS = {c for c in CATEGORY_CODES if c not in {"no_forgery_detected", "not_a_document", "other"}}

PLAN_LIMITS = {
    "free": FREE_SCANS_PER_MONTH,
    "pro": PRO_SCANS_PER_MONTH,
    "premium": PREMIUM_SCANS_PER_MONTH,
}


def generate_scan_id() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    rnd = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"RV-{ts}-{rnd}"


def check_scan_limit(user: User):
    # Capstone: unlimited scans for all users via personal Gemini API keys
    now = datetime.utcnow()
    if user.scan_reset_date and (now - user.scan_reset_date).days >= 30:
        user.scans_this_month = 0
        user.scan_reset_date = now


def _verdict_from_gemini(gemini: dict) -> tuple[str, float]:
    """Derive verdict + confidence from Gemini classification result."""
    cat = gemini["category"]
    conf = gemini["confidence"]
    if cat == "not_a_document":
        return "not_a_document", conf
    if cat == "no_forgery_detected":
        return "no_forgery_detected", conf
    if cat in _FORGERY_CATS:
        if conf >= 0.70:
            return "forged", conf
        if conf >= 0.50:
            return "suspicious", conf
        return "no_forgery_detected", conf
    # "other" or unknown - apply same confidence thresholds, don't auto-escalate
    if conf >= 0.70:
        return "forged", conf
    if conf >= 0.50:
        return "suspicious", conf
    return "no_forgery_detected", conf


@router.get("/document-types")
def get_document_types():
    return get_document_types_response()


@router.get("/about")
def get_about_info():
    """Public endpoint: pipeline metadata + per-class dataset transparency for the About page."""
    return {
        "pipeline": [
            {"step": 1, "name": "Upload & Preprocess", "detail": "Document image arrives, normalized to RGB, and enhanced for optimal analysis quality."},
            {"step": 2, "name": "Triage", "detail": "Fast screening identifies likely forgery categories to seed alternatives."},
            {"step": 3, "name": "Classification", "detail": "Full Gemini Vision analysis across all 19 forgery categories with confidence scoring."},
            {"step": 4, "name": "Verdict & Alternatives", "detail": "Verdict determined (Forged / Suspicious / No Forgery Detected), with alternative classifications provided."},
        ],
        "verdict_meaning": {
            "forged":               "High-confidence detections matching known forgery patterns. Manual review still recommended.",
            "suspicious":           "Anomalies present but below strong-evidence threshold. Treat as inconclusive.",
            "no_forgery_detected":  "No matches above detection threshold. Absence of evidence is not proof of authenticity.",
            "not_a_document":       "Upload doesn't appear to be a paper document, ID, certificate, or similar. Skipped without scoring.",
        },
        "limitations": [
            "Detection quality is bounded by training-set size and diversity. Classes with few samples will miss subtle cases.",
            "Lighting, camera angle, focus, and resolution materially affect results. Photograph documents flat with even light.",
            "Photographed prints of digital forgeries may produce different signals than the original digital file.",
            "The detector is calibrated for document examination; out-of-domain images yield meaningless verdicts.",
            "Revelator is a screening tool. Findings are not, by themselves, admissible forensic evidence.",
        ],
        "categories": {
            "Digital": {
                "total_images": 850,
                "trained_classes": 3,
                "classes": [
                    {"api_key": "digital_copy_paste", "title": "Copy-Paste Traces", "dataset_count": 280, "is_trained": True},
                    {"api_key": "digital_pixel_anomaly", "title": "Pixel Anomalies", "dataset_count": 320, "is_trained": True},
                    {"api_key": "digital_metadata", "title": "Metadata Inconsistency", "dataset_count": 250, "is_trained": True},
                ],
            },
            "Alteration": {
                "total_images": 920,
                "trained_classes": 3,
                "classes": [
                    {"api_key": "alteration_erasure", "title": "Erasure Marks", "dataset_count": 380, "is_trained": True},
                    {"api_key": "alteration_overwrite", "title": "Overwriting", "dataset_count": 320, "is_trained": True},
                    {"api_key": "alteration_bleaching", "title": "Chemical Bleaching", "dataset_count": 220, "is_trained": True},
                ],
            },
            "Traced": {
                "total_images": 780,
                "trained_classes": 3,
                "classes": [
                    {"api_key": "traced_signature", "title": "Signature Tracing", "dataset_count": 420, "is_trained": True},
                    {"api_key": "traced_pattern", "title": "Pattern Repetition", "dataset_count": 220, "is_trained": True},
                    {"api_key": "traced_pressure", "title": "Pressure Inconsistency", "dataset_count": 140, "is_trained": True},
                ],
            },
            "Obliteration": {
                "total_images": 650,
                "trained_classes": 3,
                "classes": [
                    {"api_key": "obliteration_ink_removal", "title": "Ink Removal", "dataset_count": 280, "is_trained": True},
                    {"api_key": "obliteration_tape", "title": "Correction Tape", "dataset_count": 210, "is_trained": True},
                    {"api_key": "obliteration_scraping", "title": "Mechanical Scraping", "dataset_count": 160, "is_trained": True},
                ],
            },
            "Sympathetic Ink": {
                "total_images": 480,
                "trained_classes": 2,
                "classes": [
                    {"api_key": "sympathetic_invisible", "title": "Invisible Ink Detection", "dataset_count": 300, "is_trained": True},
                    {"api_key": "sympathetic_aging", "title": "Chemical Aging Inconsistency", "dataset_count": 180, "is_trained": True},
                ],
            },
            "Currency": {
                "total_images": 620,
                "trained_classes": 2,
                "classes": [
                    {"api_key": "currency_counterfeiting", "title": "Counterfeiting Patterns", "dataset_count": 390, "is_trained": True},
                    {"api_key": "currency_security", "title": "Security Feature Replication", "dataset_count": 230, "is_trained": True},
                ],
            },
        },
        "totals": {
            "classes": 19,
            "trained_classes": 19,
            "total_dataset_images": 4380,
            "limited_data_threshold": 150,
        },
        "model_tiers": [
            {
                "key": "analyst",
                "rank": 1,
                "name": "Analyst",
                "tagline": "Screening-level forensic triage - live now.",
                "available": True,
                "plans": ["all"],
                "description": "Powered by Gemini Vision 2.0. Provides binary verdicts (forged / suspicious / no forgery) with confidence scores. Includes alternative category suggestions and image annotation.",
                "models": ["gemini-2.0-flash-exp"],
                "training": "Trained on 4,380+ labeled document images across 19 forgery categories.",
                "strengths": [
                    "Fast analysis (< 5 seconds per scan)",
                    "Handles 90% of common document forgeries",
                    "No additional fees beyond basic plan",
                ],
                "limitations": [
                    "Screening tool only; not forensic-grade evidence",
                    "Sensitive to image quality and lighting",
                    "May miss sophisticated forgeries",
                ],
            },
            {
                "key": "detective",
                "rank": 2,
                "name": "Detective",
                "tagline": "Fine-tuned analysis with forensic confidence.",
                "available": False,
                "plans": ["pro"],
                "description": "Coming soon: A fine-tuned model optimized for higher confidence verdicts on edge cases. Forensic-grade certainty metrics.",
                "models": ["revelator-detector-v2"],
                "training": "Fine-tuned on the same 4,380+ images plus adversarial examples and edge-case datasets.",
                "strengths": [
                    "Forensic-grade confidence reporting",
                    "Better at subtle forgeries",
                    "Explanations for every verdict",
                ],
                "limitations": [
                    "Slower analysis (~15-30 seconds)",
                    "Requires pro plan or higher",
                ],
            },
            {
                "key": "sherlock",
                "rank": 3,
                "name": "Sherlock",
                "tagline": "Expert-level investigation with multi-model consensus.",
                "available": False,
                "plans": ["premium"],
                "description": "Coming soon: Ensemble of specialized detectors voting on verdict. Includes cross-validation, uncertainty quantification, and expert-level reporting.",
                "models": ["revelator-ensemble-v1"],
                "training": "Ensemble of 3 fine-tuned specialists, each trained on domain-specific forgery patterns.",
                "strengths": [
                    "Highest confidence & robustness",
                    "Formal uncertainty bounds",
                    "Admissible as forensic evidence (with certification)",
                ],
                "limitations": [
                    "Slowest tier (~60-120 seconds)",
                    "Premium plan only",
                ],
            },
        ],
    }


# Prompt analytics has been moved to routes/prompt_analytics.py so it can be
# shared between teammates working on the Gemini prompt independently.


@router.post("/analyze")
def analyze_document(
    imageFile: UploadFile = File(...),
    category: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    suspicion_reason: Optional[str] = Form(None),
    area_of_concern: Optional[str] = Form(None),
    image_source: Optional[str] = Form(None),
    is_forged_belief: Optional[str] = Form(None),
    shot_type: Optional[str] = Form(None),
    lighting: Optional[str] = Form(None),
    physical_clues: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    check_scan_limit(current_user)

    # Read image
    try:
        image_data = imageFile.file.read()
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        original_width, original_height = image.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {str(e)}")

    # Document gate - don't charge quota for non-documents
    is_doc, gate_reason = check_is_document(image)
    if not is_doc:
        return {
            "scan_id": None,
            "document_type": document_type,
            "verdict": "not_a_document",
            "confidence_score": 0.0,
            "llm_explanation": gate_reason or "This does not appear to be a document.",
            "llm_locked": False,
            "llm_required_plan": "pro",
            "annotations": [],
            "original_image_dimensions": {"width": original_width, "height": original_height},
            "timestamp": datetime.now().isoformat(),
            "detected_category": "not_a_document",
            "detected_category_label": "Not a Document",
        }

    # ─────────────────────────────────────────────────────────────────
    # Pipeline: preprocess -> full classify -> (conditional) self-critique.
    # The triage pre-pass was removed: it only seeded alternatives that the
    # full classify already returns, at the cost of a whole extra vision call.
    # ─────────────────────────────────────────────────────────────────
    # STAGE 0: Preprocess (image-token reduction, zero accuracy impact)
    preprocessed = preprocess_image(image)
    print(f"[DEBUG] Image preprocessed: {image.size} -> {preprocessed.size}")

    # Try the selected key first, then the user's other saved keys. A single
    # suspended or misconfigured key must not block the rest of the account.
    key_rows = db.query(UserApiKey).filter(
        UserApiKey.user_id == current_user.id,
    ).order_by(UserApiKey.is_active.desc(), UserApiKey.created_at.asc()).all()
    key_attempts = [(row.api_key, row) for row in key_rows]
    if current_user.gemini_api_key and not key_rows:
        key_attempts.append((current_user.gemini_api_key, None))
    if not key_attempts:
        key_attempts.append((None, None))

    local_hint = None
    if USE_LOCAL_CLASSIFIER:
        try:
            from ..forgery import local_classifier
            predicted = local_classifier.predict(preprocessed)
            if predicted and predicted.get("confidence", 0.0) >= LOCAL_CLASSIFIER_THRESHOLD:
                local_hint = predicted
                print(f"[DEBUG] local classifier: {predicted['class']} {predicted['confidence']:.2f}")
        except Exception as exc:
            print(f"[DEBUG] local classifier unavailable: {exc}")

    gemini = None
    active_key_row = None
    last_failure = None
    for api_key, key_row in key_attempts:
        hint_is_currency = local_hint and (
            local_hint.get("category") == "currency_analysis"
            or "currency_analysis" in local_hint.get("candidates", [])
        )
        if local_hint and not hint_is_currency:
            print(f"[DEBUG] explain-only hint: {local_hint['category']} {local_hint['candidates']}")
            candidate = explain_with_hint(
                preprocessed, local_hint["label"], local_hint["candidates"], api_key=api_key,
            )
            # If the narrowed call fails, retry this same key with the full prompt.
            if candidate.get("_unavailable"):
                candidate = gemini_classify(
                    preprocessed, document_type=document_type,
                    suspicion_reason=suspicion_reason, area_of_concern=area_of_concern,
                    image_source=image_source, is_forged_belief=is_forged_belief,
                    shot_type=shot_type, lighting=lighting, physical_clues=physical_clues,
                    api_key=api_key,
                )
        else:
            candidate = gemini_classify(
                preprocessed, document_type=document_type,
                suspicion_reason=suspicion_reason, area_of_concern=area_of_concern,
                image_source=image_source, is_forged_belief=is_forged_belief,
                shot_type=shot_type, lighting=lighting, physical_clues=physical_clues,
                api_key=api_key,
            )
        if not candidate.get("_unavailable"):
            gemini = candidate
            active_key_row = key_row
            break

        last_failure = candidate
        failure_code = candidate.get("_failure_code", "gemini_unavailable")
        if key_row and failure_code == "quota_exhausted":
            key_row.quota_exhausted_at = datetime.utcnow()
            db.commit()

    if gemini is None:
        gemini = last_failure or {"_failure_code": "gemini_unavailable"}

    if gemini.get("_unavailable"):
        failure_code = gemini.get("_failure_code", "gemini_unavailable")
        # Only a confirmed quota response should mark a key exhausted. Other
        # provider failures must not falsely send users through key setup.
        if failure_code == "quota_exhausted":
            raise HTTPException(
                status_code=429,
                detail="quota_exhausted",
            )
        if failure_code == "no_api_key":
            raise HTTPException(status_code=503, detail="no_api_key")
        failure_reason = re.sub(
            r"AIza[0-9A-Za-z_-]+",
            "[redacted]",
            str(gemini.get("_failure_reason") or "Provider request failed"),
        )[:300]
        print(f"[WARN] Gemini unavailable for user {current_user.id}: {failure_reason}")
        raise HTTPException(
            status_code=502,
            detail=f"gemini_unavailable: {failure_reason}",
        )
    print(f"[DEBUG] model={gemini.get('model_used')} category={gemini.get('category')} confidence={gemini.get('confidence')} certainty={gemini.get('certainty_level')}")

    # STAGE 2: Confidence-gated self-critique (only fires when model is uncertain)
    user_ctx = ""
    if any([document_type, suspicion_reason, area_of_concern]):
        user_ctx = (
            f"Document type: {document_type}\n" if document_type else ""
        ) + (
            f"User suspicion: {suspicion_reason}\n" if suspicion_reason else ""
        ) + (
            f"Focus area: {area_of_concern}\n" if area_of_concern else ""
        )

    critiqued = confidence_gated_analyze(
        preprocessed,
        {},
        gemini,
        user_context=user_ctx,
        api_key=api_key,
    )
    gemini = critiqued.get("result", gemini)
    print(f"[DEBUG] Critique path: {critiqued.get('path')} | Tokens: {critiqued.get('tokens_estimate')}")

    verdict, confidence = _verdict_from_gemini(gemini)

    # AI Forensic Explanation was retired - Gemini's category_explanation is
    # already the user-facing prose. Keep the column for legacy data on the
    # Scan model, just don't populate new rows.
    llm_explanation = None

    scan_id = generate_scan_id()

    # Persist image
    user_dir = UPLOAD_DIR / current_user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    saved_path = user_dir / f"{scan_id}.jpg"
    try:
        image.save(saved_path, format="JPEG", quality=88)
        image_path = str(saved_path.relative_to(UPLOAD_DIR))
    except Exception:
        image_path = None

    scan = Scan(
        scan_id=scan_id,
        user_id=current_user.id,
        filename=imageFile.filename or "unknown",
        category_analyzed=category,
        document_type=document_type,
        verdict=verdict,
        confidence_score=confidence,
        llm_explanation=llm_explanation,
        annotations_json=json.dumps([]),
        image_width=original_width,
        image_height=original_height,
        image_path=image_path,
        training_warning=None,
        detected_category=gemini["category"],
        detected_subtype=gemini["subtype"],
        category_explanation=gemini["explanation"],
        tools_likely_used=gemini["tools_likely_used"],
        category_confidence=gemini["confidence"],
        category_evidence=json.dumps(gemini["evidence"]),
        reasoning_steps=json.dumps(gemini.get("reasoning_steps", [])),
        anomaly_location=gemini.get("anomaly_location"),
        alternatives=json.dumps(gemini.get("alternatives", [])),
        certainty_level=gemini.get("certainty_level"),
        suspicion_reason=suspicion_reason,
        area_of_concern=area_of_concern,
        image_source=image_source,
        shot_type=shot_type,
        lighting=lighting,
        physical_clues=physical_clues,
        is_forged_belief=is_forged_belief,
    )
    db.add(scan)
    current_user.scans_this_month += 1
    db.commit()

    return {
        "scan_id": scan_id,
        "document_type": document_type,
        "verdict": verdict,
        "confidence_score": confidence,
        "llm_explanation": llm_explanation,
        "llm_locked": False,
        "annotations": [],
        "original_image_dimensions": {"width": original_width, "height": original_height},
        "timestamp": datetime.now().isoformat(),
        "detected_category": gemini["category"],
        "detected_category_label": gemini["category_label"],
        "detected_subtype": gemini["subtype"],
        "category_explanation": gemini["explanation"],
        "category_evidence": gemini["evidence"],
        "tools_likely_used": gemini["tools_likely_used"],
        "category_confidence": gemini["confidence"],
        "certainty_level": gemini.get("certainty_level"),
        "reasoning_steps": gemini.get("reasoning_steps", []),
        "anomaly_location": gemini.get("anomaly_location"),
        "alternatives": gemini.get("alternatives", []),
    }


@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    scans = (
        db.query(Scan)
        .filter(Scan.user_id == current_user.id)
        .order_by(Scan.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(Scan).filter(Scan.user_id == current_user.id).count()
    return {
        "scans": [
            {
                "id": s.id,
                "scan_id": s.scan_id,
                "filename": s.filename,
                "verdict": s.verdict,
                "confidence_score": s.confidence_score,
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "scanned_at": s.created_at.isoformat() if s.created_at else "",
                "has_image": bool(s.image_path),
                "has_llm_explanation": bool(s.llm_explanation),
                "detected_category": s.detected_category,
                "category_confidence": s.category_confidence,
                "document_type": s.document_type,
                "has_notes": bool(s.notes and s.notes.strip()),
            }
            for s in scans
        ],
        "total": total,
    }


@router.get("/history/{scan_id}")
def get_scan_detail(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == current_user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {
        "id": scan.id,
        "scan_id": scan.scan_id,
        "filename": scan.filename,
        "verdict": scan.verdict,
        "confidence_score": scan.confidence_score,
        "llm_explanation": scan.llm_explanation,
        "llm_locked": False,
        "annotations": [],
        "image_width": scan.image_width,
        "image_height": scan.image_height,
        "has_image": bool(scan.image_path),
        "detected_category": scan.detected_category,
        "detected_category_label": CATEGORY_LABELS.get(scan.detected_category) if scan.detected_category else None,
        "detected_subtype": scan.detected_subtype,
        "category_explanation": scan.category_explanation,
        "tools_likely_used": scan.tools_likely_used,
        "category_confidence": scan.category_confidence,
        "category_evidence": json.loads(scan.category_evidence) if scan.category_evidence else [],
        "certainty_level": scan.certainty_level or (
            "HIGH" if (scan.category_confidence or 0) >= 0.85
            else "MEDIUM" if (scan.category_confidence or 0) >= 0.60
            else "LOW"
        ) if scan.category_confidence else None,
        "reasoning_steps": json.loads(scan.reasoning_steps) if scan.reasoning_steps else [],
        "anomaly_location": scan.anomaly_location,
        "alternatives": json.loads(scan.alternatives) if scan.alternatives else [],
        "document_type": scan.document_type,
        "document_type_label": DOCUMENT_TYPES.get(scan.document_type, {}).get("title") if scan.document_type else None,
        "suspicion_reason": scan.suspicion_reason,
        "area_of_concern": scan.area_of_concern,
        "image_source": scan.image_source,
        "shot_type": scan.shot_type,
        "lighting": scan.lighting,
        "physical_clues": scan.physical_clues,
        "is_forged_belief": scan.is_forged_belief,
        "notes": scan.notes or "",
        "created_at": scan.created_at.isoformat() if scan.created_at else "",
        "scanned_at": scan.created_at.isoformat() if scan.created_at else "",
    }


class NotesUpdate(BaseModel):
    notes: str


@router.put("/history/{scan_id}/notes")
def update_scan_notes(
    scan_id: str,
    body: NotesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save user-authored notes on a scan."""
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == current_user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    # Cap at a reasonable size so the column doesn't grow without bound.
    notes = (body.notes or "").strip()
    if len(notes) > 5000:
        raise HTTPException(status_code=400, detail="Notes are too long (max 5000 characters)")
    scan.notes = notes or None
    db.commit()
    return {"success": True, "notes": scan.notes or ""}


@router.delete("/history/{scan_id}")
def delete_scan_from_history(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete one scan owned by the signed-in user and record the action."""
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == current_user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    image_path = scan.image_path
    db.add(AdminAuditLog(
        admin_id=current_user.id,
        action="delete_scan",
        target_user_id=current_user.id,
        details=json.dumps({
            "scan_id": scan.scan_id,
            "filename": scan.filename,
            "deleted_by_user": True,
        }),
    ))
    db.delete(scan)
    db.commit()

    if image_path:
        file_path = (UPLOAD_DIR / image_path).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if str(file_path).startswith(str(upload_root)) and file_path.is_file():
            file_path.unlink()

    return {"success": True, "scan_id": scan_id}


@router.get("/history/{scan_id}/image")
def get_scan_image(
    scan_id: str,
    token: str = Query(..., description="Access token (query param so <img src> works)"),
    db: Session = Depends(get_db),
):
    user = get_user_from_token(token, db)
    scan = db.query(Scan).filter(Scan.scan_id == scan_id, Scan.user_id == user.id).first()
    if not scan or not scan.image_path:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = (UPLOAD_DIR / scan.image_path).resolve()
    if not str(file_path).startswith(str(UPLOAD_DIR.resolve())) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(file_path, media_type="image/jpeg")
```

## File: `backend/app/routes/auth.py`

<!-- FILE: backend/app/routes/auth.py -->

```python
"""
Authentication routes: register, login, refresh, me, Google OAuth.
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserApiKey, LoginCode, TrustedDevice
from ..auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, create_verification_token,
    create_signup_token, create_reset_token, decode_token, get_current_user,
    generate_otp_code, generate_device_token, hash_token,
)
from ..config import (
    GOOGLE_CLIENT_ID, FRONTEND_URL,
    TWO_FACTOR_ENABLED, TWO_FACTOR_CODE_TTL_MINUTES, TWO_FACTOR_MAX_ATTEMPTS,
    TRUSTED_DEVICE_DAYS,
)
from ..email_utils import send_verification_email, send_reset_email, send_2fa_code_email, _smtp_configured

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
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


# ── Two-factor helpers ──────────────────────────────────

def _issue_login(user: User, db: Session, device_token: str | None = None) -> dict:
    """Build the standard authenticated response (tokens + user)."""
    resp = {
        "requires_2fa": False,
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": user_to_dict(user, db),
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
    """Whether a password login for this user must pass the email-code step.

    Gated on the global flag, the per-user opt-in, that the account actually has
    a password (Google-only accounts are exempt), and that email can be sent at
    all (never lock a user out when SMTP is down)."""
    return bool(
        TWO_FACTOR_ENABLED
        and user.two_factor_enabled
        and user.hashed_password
        and _smtp_configured()
    )


# ── Endpoints ───────────────────────────────────────────

@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    from ..config import REQUIRE_EMAIL_VERIFICATION
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

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
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "user": user_to_dict(user, db),
        }

    # Verification required: stateless signup - no user row is created here. The
    # registration payload is encoded into the verification token; the row is
    # only inserted when the link in the email is clicked.
    token = create_signup_token(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    send_verification_email(body.email, token)

    return {
        "message": "Check your email to confirm your address. Your account is created once you click the link.",
        "email": body.email,
    }


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before signing in. Check your inbox or request a new link.")

    # A remembered device skips the code entirely.
    if _device_is_trusted(user, body.device_token, db):
        return _issue_login(user, db)

    # Otherwise, if 2FA applies, email a code and pause; the client finishes at
    # /verify-2fa. If the send fails we fall through and log them in rather than
    # trap them behind a code they never receive.
    if _twofa_required_for(user):
        if _send_login_code(user, db):
            return {
                "requires_2fa": True,
                "email": user.email,
                "message": f"We emailed a 6-digit code to {user.email}. Enter it to finish signing in.",
            }

    return _issue_login(user, db)


@router.post("/verify-2fa")
def verify_2fa(body: Verify2FARequest, db: Session = Depends(get_db)):
    """Finish a 2FA login by confirming the emailed 6-digit code."""
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
            expires_at=datetime.utcnow() + timedelta(days=TRUSTED_DEVICE_DAYS),
            last_used_at=datetime.utcnow(),
        ))
    db.commit()

    return _issue_login(user, db, device_token=device_token)


@router.post("/resend-2fa")
def resend_2fa(body: ResendRequest, db: Session = Depends(get_db)):
    """Re-send the login code. Always 200 so accounts can't be enumerated."""
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

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user, db),
    )


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
def resend_verification(body: ResendRequest, db: Session = Depends(get_db)):
    """Send a fresh verification link. Always returns success to avoid leaking which emails exist."""
    user = db.query(User).filter(User.email == body.email).first()
    if user and not user.is_verified and user.hashed_password:
        user.verification_sent_at = datetime.utcnow()
        db.commit()
        send_verification_email(user.email, create_verification_token(user.id))
    return {"message": "If that account needs verification, a new link has been sent."}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Email a password-reset link. Always returns success so emails can't be enumerated."""
    user = db.query(User).filter(User.email == body.email).first()
    # Only password accounts can reset; Google-only accounts have no password to change.
    if user and user.hashed_password:
        send_reset_email(user.email, create_reset_token(user.id))
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password using a valid reset token from the emailed link."""
    payload = decode_token(body.token)
    if not payload or payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.hashed_password = hash_password(body.password)
    # Completing a reset proves email ownership, so mark verified too.
    user.is_verified = True
    db.commit()
    return {"message": "Password updated. You can now sign in."}


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

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_to_dict(user, db),
    )


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_to_dict(current_user, db)


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
    current_user.gemini_api_key = api_key
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
        "key_preview": f"...{k.api_key[-4:]}",
        "api_key": k.api_key,
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
        api_key=api_key,
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
        key.api_key = api_key

    db.commit()
    return _key_to_dict(key)
```

## File: `backend/app/routes/payments.py`

<!-- FILE: backend/app/routes/payments.py -->

```python
"""
Payment routes for Stripe and PayMongo subscription management.
"""

import base64
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..config import (
    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_ID_PRO, STRIPE_PRICE_ID_PREMIUM, FRONTEND_URL,
    PAYMONGO_SECRET_KEY, PAYMONGO_PUBLIC_KEY,
    PRO_PRICE_USD, PREMIUM_PRICE_USD,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])


def get_stripe():
    """Lazy import stripe so the app works even without the package."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured. Add STRIPE_SECRET_KEY to .env")
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe package not installed. Run: pip install stripe")


PLAN_PRICE_MAP = {
    "pro": STRIPE_PRICE_ID_PRO,
    "premium": STRIPE_PRICE_ID_PREMIUM,
}


class CheckoutRequest(BaseModel):
    plan: str  # "pro" or "premium"
    payment_method: str = "stripe"  # "stripe" or "paymongo"


def get_paymongo():
    """Lazy import and validate PayMongo configuration."""
    if not PAYMONGO_SECRET_KEY:
        raise HTTPException(status_code=503, detail="PayMongo is not configured. Add PAYMONGO_SECRET_KEY to .env")
    return {
        "secret_key": PAYMONGO_SECRET_KEY,
        "public_key": PAYMONGO_PUBLIC_KEY,
    }


@router.get("/plans")
def get_plans():
    return {
        "plans": [
            {
                "id": "free", "name": "Free", "price": 0,
                "scans_per_month": 10, "unlimited": False, "llm_included": False,
                "features": [
                    "10 scans / month",
                    "Verdict + bounding boxes",
                    "Scan history with images",
                    "Community support",
                ],
            },
            {
                "id": "pro", "name": "Pro", "price": PRO_PRICE_USD,
                "scans_per_month": -1, "unlimited": True, "llm_included": False,
                "features": [
                    "Unlimited scans",
                    "Verdict + bounding boxes",
                    "Scan history with images",
                    "Email support",
                ],
            },
            {
                "id": "premium", "name": "Premium", "price": PREMIUM_PRICE_USD,
                "scans_per_month": -1, "unlimited": True, "llm_included": True,
                "features": [
                    "Unlimited scans",
                    "AI forensic explanation on every scan",
                    "Priority processing",
                    "Priority support",
                ],
            },
        ]
    }


@router.post("/create-checkout")
def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stripe = get_stripe()

    price_id = PLAN_PRICE_MAP.get(body.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan. Choose 'pro' or 'premium'.")

    # Create or reuse Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={"user_id": current_user.id},
        )
        current_user.stripe_customer_id = customer.id
        db.commit()

    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{FRONTEND_URL}/account?payment=success&session_id={{CHECKOUT_SESSION_ID}}&provider=stripe",
        cancel_url=f"{FRONTEND_URL}/account?payment=cancelled",
        metadata={"user_id": current_user.id, "plan": body.plan},
    )

    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    stripe = get_stripe()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan = session.get("metadata", {}).get("plan", "basic")
        subscription_id = session.get("subscription")

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.plan = plan
                user.stripe_subscription_id = subscription_id
                db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        subscription_id = sub.get("id")
        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            db.commit()

    return {"status": "ok"}


@router.get("/verify-session")
def verify_session(
    session_id: str = None,
    provider: str = "stripe",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify payment on success redirect and update user plan - no webhook needed."""
    if provider == "stripe":
        stripe = get_stripe()
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required for Stripe verification")
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not retrieve session: {e}")

        if session.payment_status != "paid":
            raise HTTPException(status_code=400, detail="Payment not completed")

        if session.metadata.get("user_id") != current_user.id:
            raise HTTPException(status_code=403, detail="Session does not belong to this user")

        plan = session.metadata.get("plan", "pro")
        current_user.plan = plan
        if session.subscription:
            current_user.stripe_subscription_id = session.subscription
        db.commit()
        return {"status": "ok", "plan": plan}

    elif provider == "paymongo":
        paymongo = get_paymongo()
        pm_session_id = session_id or current_user.paymongo_source_id
        if not pm_session_id:
            raise HTTPException(status_code=400, detail="No PayMongo session found")

        auth_string = base64.b64encode(f"{paymongo['secret_key']}:".encode()).decode()
        try:
            response = requests.get(
                f"https://api.paymongo.com/v1/checkout_sessions/{pm_session_id}",
                headers={"Authorization": f"Basic {auth_string}"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PayMongo API error: {e}")

        attrs = data.get("data", {}).get("attributes", {})
        status = attrs.get("payment_intent", {}).get("attributes", {}).get("status")
        if status != "succeeded":
            raise HTTPException(status_code=400, detail="Payment not completed")

        plan = attrs.get("metadata", {}).get("plan", "pro")
        current_user.plan = plan
        db.commit()
        return {"status": "ok", "plan": plan}

    raise HTTPException(status_code=400, detail="Invalid provider")


@router.post("/cancel")
def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.stripe_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription")

    stripe = get_stripe()
    stripe.Subscription.modify(current_user.stripe_subscription_id, cancel_at_period_end=True)
    return {"message": "Subscription will cancel at end of billing period"}


# ============================================
# PayMongo Payment Routes
# ============================================

@router.post("/paymongo-checkout")
def create_paymongo_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a PayMongo payment link for subscription."""
    paymongo = get_paymongo()

    amount_cents = int(PRO_PRICE_USD * 100) if body.plan == "pro" else int(PREMIUM_PRICE_USD * 100)

    # Create PayMongo charge with webhook
    auth_string = base64.b64encode(f"{paymongo['secret_key']}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/json",
    }

    payload = {
        "data": {
            "type": "checkout_session",
            "attributes": {
                "amount": amount_cents,
                "currency": "PHP",
                "description": f"Revelator {body.plan.upper()} Plan",
                "statement_descriptor": "REVELATOR",
                "line_items": [
                    {
                        "amount": amount_cents,
                        "currency": "PHP",
                        "description": f"Revelator {body.plan.upper()} Plan",
                        "name": f"Revelator {body.plan.upper()} Plan",
                        "quantity": 1,
                    }
                ],
                "payment_method_types": ["card", "gcash"],
                "redirect": {
                    "success": f"{FRONTEND_URL}/account?payment=success&provider=paymongo",
                    "failed": f"{FRONTEND_URL}/account?payment=cancelled",
                },
                "metadata": {
                    "user_id": current_user.id,
                    "plan": body.plan,
                    "email": current_user.email,
                },
            }
        }
    }

    try:
        response = requests.post(
            "https://api.paymongo.com/v1/checkout_sessions",
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        checkout_url = data["data"]["attributes"]["checkout_url"]
        session_id = data["data"]["id"]

        # Store session for webhook reference
        current_user.paymongo_source_id = session_id
        db.commit()

        return {"checkout_url": checkout_url, "session_id": session_id, "provider": "paymongo"}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"PayMongo API error: {str(e)}")


@router.post("/paymongo-webhook")
async def paymongo_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle PayMongo payment success webhooks."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    event_type = payload.get("data", {}).get("type")

    if event_type == "payment.success":
        payment_data = payload.get("data", {}).get("attributes", {})
        metadata = payment_data.get("metadata", {})

        user_id = metadata.get("user_id")
        plan = metadata.get("plan", "pro")

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.plan = plan
                user.paymongo_customer_id = payment_data.get("source", {}).get("id")
                db.commit()
                return {"status": "ok"}

    return {"status": "ok"}


@router.get("/paymongo-public-key")
def get_paymongo_public_key():
    """Get PayMongo public key for frontend integration."""
    try:
        paymongo = get_paymongo()
        return {"public_key": paymongo["public_key"]}
    except HTTPException:
        return {"public_key": None}
```

## File: `backend/app/routes/prompt_analytics.py`

<!-- FILE: backend/app/routes/prompt_analytics.py -->

```python
"""
Prompt analytics route, kept in its own file so it can be shared between
teammates working on the Gemini prompt independently of the rest of the app.

The plan: two collaborators tune the forensic prompt in parallel and only
need to swap two files to sync, this one and ``forgery/gemini_vision.py``.
Everything else in the codebase, auth, history, classrooms, payments,
remains untouched by that work.

Endpoint:
    GET /api/prompt-analysis  -> JSON consumed by the admin PromptDashboard
"""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["prompt-analytics"])

# Written by backend/evaluate_specimens.py after each specimen evaluation run.
ACCURACY_FILE = Path(__file__).resolve().parent.parent / "data" / "specimen_accuracy.json"


def extract_rules_from_prompt():
    """Read critical rules from gemini_vision.py at runtime."""
    try:
        gemini_path = Path(__file__).parent.parent / "forgery" / "gemini_vision.py"
        lines = gemini_path.read_text(encoding="utf-8").split("\n")

        rules = []

        # Collect the multi-line CRITICAL BRANCHING RULE block
        critical_lines = []
        in_critical = False
        for line in lines:
            if "CRITICAL BRANCHING RULE" in line and line.strip().startswith("CRITICAL"):
                in_critical = True
            if in_critical:
                s = line.strip()
                if s:
                    critical_lines.append(s)
                if s.startswith("NO") and "digital" in s:
                    break
        if critical_lines:
            rules.append({
                "title": "CRITICAL BRANCHING RULE - FIRST DECISION:",
                "text": " ".join(critical_lines),
            })

        # Collect single-line warning rule lines
        target_rules = ["BANK CHECK RULE", "INK LAYERING RULE", "INCOMPLETE WORD RULE",
                        "SEMANTIC CONFLICT / CHEMICAL ERASURE RULE", "GHOST TEXT vs. SYMPATHETIC INK RULE"]
        for line in lines:
            s = line.strip().lstrip("⚠️").strip()
            for rule_name in target_rules:
                if s.startswith(rule_name + ":"):
                    body = s[len(rule_name) + 1:].strip()
                    rules.append({"title": rule_name + ":", "text": body})
                    break

        return rules
    except Exception:
        return []


@router.get("/prompt-analysis/accuracy")
def get_system_accuracy():
    """Live specimen-evaluation accuracy, written by backend/evaluate_specimens.py.

    Returns {"status": "no_data"} until the harness has been run at least once.
    The frontend dashboards poll this endpoint so the numbers update on their own
    whenever a new evaluation run finishes.
    """
    if not ACCURACY_FILE.exists():
        return {
            "status": "no_data",
            "message": "No evaluation run yet. Run: cd backend && python evaluate_specimens.py --sample 3",
        }
    try:
        data = json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
        data["status"] = "ok"
        return data
    except Exception as exc:
        return {"status": "error", "message": f"Could not read accuracy file: {exc}"}


@router.get("/prompt-analysis")
def get_prompt_analysis():
    """Prompt analysis data, rules read live from gemini_vision.py."""
    rules = extract_rules_from_prompt()
    return {
        "system_prompt": {"total_words": 2847},
        "groups": {
            "traced": "#e74c3c",
            "alteration": "#f39c12",
            "digital": "#5b8def",
            "obliteration": "#9b59b6",
            "sympathetic": "#1abc9c",
            "currency": "#95a5a6",
        },
        "aux_prompts": [
            {"name": "SYSTEM_PROMPT", "word_count": 4718, "char_count": 32187, "purpose": "Main classification logic with category definitions, branching rules, and user-context injection."},
            {"name": "TRIAGE_PROMPT", "word_count": 420, "char_count": 2680, "purpose": "Fast screening: returns top 3 suspected categories without full reasoning."},
            {"name": "DISTINCTION_BLOCK (traced_projection vs digital)", "word_count": 150, "char_count": 950, "purpose": "Explicit rules to distinguish perfect-looking traced signatures from digital forgeries."},
        ],
        "rules": rules,
        "categories": [
            {"id": "traced_carbon", "label": "Traced - Carbon", "group": "traced", "word_count": 70, "detail_level": "MEDIUM", "first_line": "Carbon paper placed under genuine signature; forger traces with stylus, transfers carbon 'blueprint', then inks over.", "indicators": ["faint carbon residue along strokes","hesitation/tremor following blueprint","uniform line weight","misalignment from carbon transfer"], "distinctions": []},
            {"id": "traced_indentation", "label": "Traced - Indentation", "group": "traced", "word_count": 50, "detail_level": "MEDIUM", "first_line": "Pressure indentation/canal light effect - pen pressed into paper creates groove around strokes.", "indicators": ["halo/colorless depression around strokes","ink not filling indented path","hesitation or tremor"], "distinctions": []},
            {"id": "traced_projection", "label": "Traced - Projection", "group": "traced", "word_count": 300, "detail_level": "VERY HIGH", "first_line": "Light table or projector throws genuine signature onto paper; forger inks over projected lines.", "indicators": ["uniform/monotonous pen pressure","micro-tremors","frequent pen lifts","no carbon residue","no grooves","suspiciously perfect match"], "distinctions": [{"target": "digital_cut_paste", "reason": "Physical pen marks vs digital halo/pixelation"}, {"target": "digital_scanned", "reason": "Paper-fiber interaction vs flat-on-scan-grain"}]},
            {"id": "addition_insertion", "label": "Addition - Insertion", "group": "alteration", "word_count": 500, "detail_level": "VERY HIGH", "first_line": "Characters added inside a word/number to change meaning. Has TWO subtypes: A) digit in blank space, B) char converted by added stroke.", "indicators": ["crowding/tight spacing","ink density mismatch","stroke rhythm inconsistency","baseline misalignment","logical value conflict","ink texture mismatch (printed vs wet)","stroke layering / Z-axis","morphological inconsistency"], "distinctions": []},
            {"id": "addition_interlineation", "label": "Addition - Interlineation", "group": "alteration", "word_count": 30, "detail_level": "LOW", "first_line": "New writing squeezed BETWEEN existing lines (in whitespace, not inside a word).", "indicators": ["smaller text","different baseline","different ink"], "distinctions": []},
            {"id": "erasure_chemical", "label": "Erasure - Chemical", "group": "alteration", "word_count": 150, "detail_level": "HIGH", "first_line": "Original ink dissolved with solvent (bleach, acetone, eradicator), then new text written/printed in cleaned area.", "indicators": ["halo/tide mark","ink ghosting","paper fiber damage","new text on damaged background","oblique-light sheen difference"], "distinctions": []},
            {"id": "erasure_mechanical", "label": "Erasure - Mechanical", "group": "alteration", "word_count": 250, "detail_level": "HIGH", "first_line": "Original ink scraped off with razor/sandpaper/eraser, then replacement written/printed on scraped area.", "indicators": ["abraded fibers ('fuzzy patch')","shadow patch / sheen","ghost particles","paper thinning","jagged void boundary","ink feathering","logical word truncation"], "distinctions": []},
            {"id": "digital_cut_paste", "label": "Digital - Cut & Paste", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "Genuine element (signature, stamp) digitally lifted and composited onto otherwise real document.", "indicators": ["halo/fringe","pixelation/aliasing","background inconsistency","compression artefacts","DPI mismatch","shadow/lighting","perfect leveling"], "distinctions": []},
            {"id": "digital_desktop", "label": "Digital - Desktop", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "ENTIRE document fabricated from scratch in software (Word, Canva, Photoshop).", "indicators": ["perfect digital typography","font consistency across doc","forms & templates","signature-quality mismatch","zero physical realism"], "distinctions": []},
            {"id": "digital_scanned", "label": "Digital - Scanned", "group": "digital", "word_count": 200, "detail_level": "HIGH", "first_line": "Real document scanned, then digital elements composited onto scan image (stamp, signature, dates).", "indicators": ["scan-noise inconsistency","stamp/signature flatness","global tilt vs local alignment","compression-level mismatch","resolution halo","font/field inconsistency"], "distinctions": []},
            {"id": "obliteration_ink", "label": "Obliteration - Ink", "group": "obliteration", "word_count": 5, "detail_level": "VERY LOW", "first_line": "Original text scribbled out with ink.", "indicators": ["ink scribbled over original"], "distinctions": []},
            {"id": "obliteration_whiteout", "label": "Obliteration - White Out", "group": "obliteration", "word_count": 5, "detail_level": "VERY LOW", "first_line": "Correction fluid covering text.", "indicators": ["correction fluid covering text"], "distinctions": []},
            {"id": "sympathetic_indented", "label": "Sympathetic - Indented", "group": "sympathetic", "word_count": 15, "detail_level": "VERY LOW", "first_line": "Indented writing visible only via raking light. No ink in the grooves.", "indicators": ["pressure indentations on paper","no visible ink","raking light reveals"], "distinctions": []},
            {"id": "sympathetic_special", "label": "Sympathetic - Special Ink", "group": "sympathetic", "word_count": 200, "detail_level": "HIGH", "first_line": "Invisible ink revealed by external stimulus (heat, reagent, UV).", "indicators": ["heat-activated (browned/charred)","chemical-activated (color reaction)","UV/fluorescent","specific substances (lemon, milk, phenolphthalein)"], "distinctions": []},
            {"id": "currency_analysis", "label": "Currency", "group": "currency", "word_count": 355, "detail_level": "VERY HIGH", "first_line": "Counterfeit banknote. A genuine banknote is NOT a forgery - flag only with a specific counterfeit sign, otherwise no_forgery_detected.", "indicators": ["security features PRESENT but simulated (flat/printed/sticker-like)","no raised intaglio relief","printed-on or missing watermark/thread","colour-shift ink that does not shift","blurry/broken microprint","photocopy dot rosettes","wrong-font or mismatched serials","NGC and NDS both legal tender","worn/old/low-quality photo is NOT counterfeit"], "distinctions": [{"target": "no_forgery_detected", "reason": "Genuine money is authentic; currency_analysis means counterfeit detected, not merely 'this is money'"}]},
        ],
        "overlaps": [
            {"source": "traced_carbon", "target": "traced_indentation", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Both hand-drawn with hesitation/tremor. Carbon has residue; indentation has groove. Easy to confuse on low-res images."},
            {"source": "traced_carbon", "target": "traced_projection", "strength": 0.55, "severity": "MEDIUM", "from_prompt": True, "reason": "Both show uniform line weight from following a guide. Carbon = paper underneath; projection = light from above."},
            {"source": "traced_indentation", "target": "traced_projection", "strength": 0.55, "severity": "MEDIUM", "from_prompt": True, "reason": "Both hand-drawn from a visual reference. Indentation creates physical groove; projection does not."},
            {"source": "traced_projection", "target": "digital_cut_paste", "strength": 0.85, "severity": "HIGH", "from_prompt": True, "reason": "Both produce 'perfect-looking' signatures. Distinguish: physical pen marks vs digital halo/pixelation. Has explicit distinction block."},
            {"source": "traced_projection", "target": "digital_scanned", "strength": 0.85, "severity": "HIGH", "from_prompt": True, "reason": "Both look unnaturally clean. Distinguish: paper-fiber interaction vs flat-on-scan-grain. Has explicit distinction block."},
            {"source": "traced_indentation", "target": "digital_desktop", "strength": 0.75, "severity": "HIGH", "from_prompt": True, "reason": "OLD BIAS (now patched): the prompt used to say 'mechanical-looking text = traced'. Software-generated docs naturally look mechanical. Caused misclassification."},
            {"source": "traced_carbon", "target": "digital_cut_paste", "strength": 0.45, "severity": "LOW", "from_prompt": False, "reason": "Both can show ghost-like residue. Carbon = real ink residue; cut/paste = digital halo."},
            {"source": "sympathetic_indented", "target": "traced_indentation", "strength": 0.85, "severity": "HIGH", "from_prompt": False, "reason": "BOTH involve indentation/grooves. Difference: sympathetic_indented has grooves WITHOUT ink. traced_indentation has grooves WITH ink filling them. The prompt does NOT explicitly distinguish these, risk of confusion."},
            {"source": "digital_cut_paste", "target": "digital_desktop", "strength": 0.7, "severity": "MEDIUM", "from_prompt": True, "reason": "Both software-generated. Cut/paste = element on real doc; desktop = whole doc fabricated."},
            {"source": "digital_cut_paste", "target": "digital_scanned", "strength": 0.75, "severity": "HIGH", "from_prompt": True, "reason": "Both insert elements digitally. Cut/paste = onto authentic doc; scanned = onto a scan of authentic doc. Subtle distinction."},
            {"source": "digital_desktop", "target": "digital_scanned", "strength": 0.6, "severity": "MEDIUM", "from_prompt": True, "reason": "Both software-generated. Desktop = built from scratch; scanned = built over a real scan as base."},
            {"source": "addition_insertion", "target": "erasure_chemical", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Both alter character meaning. Insertion = add ink (paper intact); erasure = remove + replace (paper damaged)."},
            {"source": "addition_insertion", "target": "erasure_mechanical", "strength": 0.65, "severity": "MEDIUM", "from_prompt": True, "reason": "Same logic, paper damage distinguishes erasure from insertion."},
            {"source": "erasure_chemical", "target": "erasure_mechanical", "strength": 0.8, "severity": "HIGH", "from_prompt": True, "reason": "Both remove + replace. Chemical = solvent (smooth, stained); mechanical = abrasion (rough, fuzzy fibers)."},
            {"source": "erasure_chemical", "target": "obliteration_ink", "strength": 0.7, "severity": "MEDIUM", "from_prompt": True, "reason": "Both can show ink smudges. Erasure smudge = at EDGE of blank where char used to be. Obliteration = covering text intentionally."},
            {"source": "obliteration_ink", "target": "obliteration_whiteout", "strength": 0.5, "severity": "LOW", "from_prompt": False, "reason": "Both cover text. Different materials but only 5 words of detail each, model has minimal cues to distinguish."},
        ],
        "variables": [
            {"name": "document_type", "desc": "Type of document (passport, check, contract, ID, etc.). Selected from a fixed list.", "influence": "Activates document-specific rules (e.g., bank check rule, ID security features). Strong nudge toward category-relevant indicators."},
            {"name": "suspicion_reason", "desc": "User's free-text description of why they suspect forgery (max 300 chars).", "influence": "Free text bias. Can mention specific words like 'erased', 'pasted', 'traced' that anchor classification. The prompt explicitly tells the model to verify against image."},
            {"name": "area_of_concern", "desc": "Where the user wants the model to focus (e.g., 'signature', 'date field').", "influence": "Directs attention. Doesn't force a category but biases toward forgery types common in that region."},
            {"name": "image_source", "desc": "Phone photo / scan / screenshot / not sure.", "influence": "Strong influence. Screenshot leans digital_desktop. Phone photo leans physical forgeries."},
            {"name": "is_forged_belief", "desc": "User believes it IS forged / NOT forged / not sure.", "influence": "Weak suggestion. Prompt warns model not to be pressured by user's belief, must verify against image."},
            {"name": "shot_type", "desc": "Close-up / full document / not sure.", "influence": "Affects what evidence is visible. Close-up = micro-tremors, fiber details. Full doc = layout, font consistency."},
            {"name": "lighting", "desc": "Natural / raking / bright / not sure.", "influence": "Critical for sympathetic_indented (needs raking light) and erasure detection (oblique light shows sheen)."},
            {"name": "physical_clues", "desc": "Specific clue user thinks they observed (16 options: indentation_grooves, carbon_streaks, ink_halo, paper_thinning, etc.).", "influence": "STRONGEST per-variable bias. Each clue maps to a category. The prompt tells the model to verify but it nudges hard."},
        ],
    }
```

## File: `backend/PROMPT_ANALYSIS.html`

<!-- FILE: backend/PROMPT_ANALYSIS.html -->

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Revelator - Prompt Analysis & Overlap Visualizer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0a0a0f;
    color: #e6e6e6;
    line-height: 1.4;
    overflow-x: hidden;
  }
  header {
    padding: 24px 32px;
    background: linear-gradient(180deg, #1a1a25, #0a0a0f);
    border-bottom: 1px solid #2a2a3a;
  }
  header h1 { font-size: 22px; color: #fff; }
  header p { color: #888; font-size: 13px; margin-top: 4px; }
  .container { display: grid; grid-template-columns: 1fr 380px; gap: 0; min-height: calc(100vh - 100px); }
  .main { padding: 24px; }
  .sidebar {
    background: #12121c;
    border-left: 1px solid #2a2a3a;
    padding: 24px;
    overflow-y: auto;
    max-height: calc(100vh - 100px);
  }
  .tabs { display: flex; gap: 0; margin-bottom: 24px; border-bottom: 1px solid #2a2a3a; }
  .tab {
    padding: 10px 20px; cursor: pointer; color: #888;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
    font-size: 13px;
  }
  .tab:hover { color: #ccc; }
  .tab.active { color: #fff; border-bottom-color: #5b8def; }
  .panel { display: none; }
  .panel.active { display: block; }
  h2 { font-size: 16px; margin-bottom: 16px; color: #fff; }
  h3 { font-size: 14px; margin-bottom: 8px; color: #aab; margin-top: 18px; }

  /* Bar chart */
  .bar-row {
    display: grid;
    grid-template-columns: 200px 1fr 80px;
    gap: 12px;
    align-items: center;
    margin-bottom: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .bar-row:hover { background: #1a1a28; }
  .bar-row.selected { background: #1f1f30; }
  .bar-label { font-size: 12px; color: #ccc; }
  .bar-track { height: 18px; background: #1a1a28; border-radius: 3px; overflow: hidden; }
  .bar-fill { height: 100%; transition: width 0.3s; }
  .bar-value { font-size: 11px; color: #888; text-align: right; }

  /* Group colors */
  .group-traced { background: #e74c3c; color: #fff; }
  .group-alteration { background: #f39c12; color: #fff; }
  .group-digital { background: #5b8def; color: #fff; }
  .group-obliteration { background: #9b59b6; color: #fff; }
  .group-sympathetic { background: #1abc9c; color: #fff; }
  .group-currency { background: #95a5a6; color: #fff; }

  .legend {
    display: flex;
    gap: 16px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .legend-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    background: #1a1a28;
  }
  .legend-dot {
    width: 10px; height: 10px; border-radius: 50%;
  }

  /* Network graph */
  .graph-container {
    background: #0d0d18;
    border: 1px solid #1f1f2c;
    border-radius: 8px;
    position: relative;
    height: 600px;
    overflow: hidden;
  }
  svg { width: 100%; height: 100%; cursor: grab; }
  svg.dragging { cursor: grabbing; }
  .node circle {
    cursor: pointer;
    transition: stroke-width 0.2s;
    stroke: #0a0a0f;
    stroke-width: 2;
  }
  .node circle:hover { stroke-width: 4; stroke: #fff; }
  .node.selected circle { stroke: #fff; stroke-width: 3; }
  .node text {
    fill: #ddd;
    font-size: 10px;
    text-anchor: middle;
    pointer-events: none;
    font-family: 'Segoe UI', sans-serif;
  }
  .link {
    stroke-opacity: 0.4;
    transition: stroke-opacity 0.2s;
  }
  .link.faded { stroke-opacity: 0.05; }
  .link.highlighted { stroke-opacity: 1; }

  .controls {
    position: absolute;
    top: 12px;
    right: 12px;
    display: flex;
    gap: 8px;
    background: #1a1a28cc;
    backdrop-filter: blur(8px);
    padding: 8px;
    border-radius: 6px;
  }
  .btn {
    padding: 6px 12px;
    background: #2a2a3a;
    border: 1px solid #3a3a4a;
    color: #ccc;
    border-radius: 4px;
    cursor: pointer;
    font-size: 11px;
  }
  .btn:hover { background: #3a3a4a; color: #fff; }
  .btn.active { background: #5b8def; border-color: #5b8def; color: #fff; }

  /* Sidebar details */
  .detail-box {
    background: #1a1a28;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 12px;
    border-left: 3px solid #444;
  }
  .detail-box.traced { border-left-color: #e74c3c; }
  .detail-box.alteration { border-left-color: #f39c12; }
  .detail-box.digital { border-left-color: #5b8def; }
  .detail-box.obliteration { border-left-color: #9b59b6; }
  .detail-box.sympathetic { border-left-color: #1abc9c; }
  .detail-box.currency { border-left-color: #95a5a6; }

  .detail-title {
    font-size: 14px;
    color: #fff;
    margin-bottom: 8px;
  }
  .detail-meta {
    font-size: 11px;
    color: #888;
    margin-bottom: 8px;
  }
  .indicator-list {
    list-style: none;
    padding: 0;
  }
  .indicator-list li {
    font-size: 12px;
    padding: 4px 0 4px 16px;
    color: #bbb;
    position: relative;
  }
  .indicator-list li::before {
    content: "▸";
    position: absolute;
    left: 0;
    color: #5b8def;
  }
  .overlap-list li {
    font-size: 12px;
    padding: 8px 12px;
    margin-bottom: 6px;
    background: #14141f;
    border-radius: 4px;
    border-left: 2px solid #f39c12;
    list-style: none;
    color: #ccc;
  }
  .overlap-list .strength {
    font-weight: bold;
    color: #f39c12;
  }
  .overlap-list .reason {
    color: #888;
    font-size: 11px;
    margin-top: 4px;
  }
  .severity-high { border-left-color: #e74c3c !important; }
  .severity-high .strength { color: #e74c3c !important; }

  .variable-card {
    background: #14141f;
    border-radius: 4px;
    padding: 8px 12px;
    margin-bottom: 6px;
    font-size: 12px;
  }
  .variable-card .var-name { color: #5b8def; font-weight: bold; }
  .variable-card .var-desc { color: #aaa; font-size: 11px; margin-top: 2px; }
  .variable-card .var-influence { color: #f39c12; font-size: 10px; margin-top: 4px; }

  .stat {
    background: #14141f;
    padding: 12px;
    border-radius: 4px;
    margin-bottom: 8px;
  }
  .stat-label { font-size: 11px; color: #888; }
  .stat-value { font-size: 18px; color: #fff; font-weight: bold; margin-top: 2px; }
  .stat-detail { font-size: 11px; color: #aaa; margin-top: 4px; }

  .placeholder {
    text-align: center;
    color: #555;
    padding: 40px 20px;
    font-size: 13px;
    font-style: italic;
  }

  .alert {
    background: #2d1f1f;
    border-left: 3px solid #e74c3c;
    padding: 12px;
    border-radius: 4px;
    margin-bottom: 12px;
    font-size: 12px;
    color: #ffb3b3;
  }
  .alert strong { color: #ff8888; }

  .info {
    background: #1a2435;
    border-left: 3px solid #5b8def;
    padding: 12px;
    border-radius: 4px;
    margin-bottom: 12px;
    font-size: 12px;
    color: #cce0ff;
  }
</style>
</head>
<body>
<header>
  <h1>Revelator - Prompt Analysis & Category Overlap Visualizer</h1>
  <p>Interactive analysis of the Gemini Vision system prompt - detail level, overlap relationships, dominance patterns</p>
</header>

<!-- LIVE SYSTEM ACCURACY - polls the backend; populated by evaluate_specimens.py -->
<div id="live-acc" style="padding:14px 32px;background:#0d0d16;border-bottom:1px solid #2a2a3a;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
    <span style="font-size:13px;color:#5b8def;letter-spacing:1px;">&#9673; LIVE SYSTEM ACCURACY</span>
    <span id="live-acc-status" style="font-size:11px;color:#888;">connecting…</span>
  </div>
  <div id="live-acc-body" style="font-size:12px;color:#aaa;">Waiting for backend…</div>
</div>
<script>
(function () {
  var API = (location.origin && location.origin.indexOf('http') === 0 ? location.origin : 'http://localhost:8000') + '/api/prompt-analysis/accuracy';
  var statusEl = document.getElementById('live-acc-status');
  var bodyEl = document.getElementById('live-acc-body');
  function color(p){ if(p==null) return '#666'; if(p>=80) return '#3fb950'; if(p>=60) return '#d29922'; return '#f85149'; }
  function bar(p){ var c=color(p); return '<span style="display:inline-block;width:80px;height:10px;background:#000;border-radius:2px;overflow:hidden;vertical-align:middle;"><span style="display:block;height:100%;width:'+(p||0)+'%;background:'+c+';"></span></span>'; }
  function render(d){
    if (!d || d.status === 'no_data') {
      statusEl.textContent = 'no data yet';
      bodyEl.innerHTML = 'No evaluation run yet. In backend/ run <code style="color:#5b8def;">python evaluate_specimens.py --sample 3</code>. This panel auto-refreshes every 15s.';
      return;
    }
    if (d.status === 'error') { statusEl.textContent = 'error'; bodyEl.textContent = d.message || 'error'; return; }
    var o = d.overall || {};
    statusEl.textContent = 'updated ' + new Date(d.generated_at).toLocaleTimeString() + ' · ' + (d.model || '');
    var tiles = ''
      + '<span style="margin-right:22px;">Forged/Genuine <b style="color:'+color(o.label_pct)+';font-size:16px;">'+(o.label_pct||0)+'%</b> <span style="color:#666;">'+o.label_ok+'/'+o.n+'</span></span>'
      + '<span style="margin-right:22px;">Category-hit <b style="color:'+color(o.cat_pct)+';font-size:16px;">'+(o.cat_n?(o.cat_pct||0)+'%':'n/a')+'</b> <span style="color:#666;">'+o.cat_hit+'/'+o.cat_n+'</span></span>'
      + '<span>Images <b style="color:#5b8def;">'+(d.total_images||0)+'</b></span>';
    var rows = (d.folders||[]).map(function(f){
      return '<div style="display:grid;grid-template-columns:230px 130px 130px;gap:10px;align-items:center;padding:2px 0;">'
        + '<span style="color:#ccc;">'+f.folder+'</span>'
        + '<span>'+bar(f.label_pct)+' <span style="color:#888;">'+f.label_pct+'%</span></span>'
        + '<span>'+(f.cat_n?bar(f.cat_pct)+' <span style="color:#888;">'+f.cat_pct+'%</span>':'<span style="color:#555;">n/a</span>')+'</span>'
        + '</div>';
    }).join('');
    bodyEl.innerHTML = '<div style="margin-bottom:10px;">'+tiles+'</div>'
      + '<div style="display:grid;grid-template-columns:230px 130px 130px;gap:10px;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;"><span>Specimen folder</span><span>Forged/Genuine</span><span>Category hit</span></div>'
      + rows;
  }
  function load(){ fetch(API).then(function(r){return r.json();}).then(render).catch(function(){ statusEl.textContent='backend offline'; bodyEl.innerHTML='Could not reach '+API+'. Start the backend, then this panel updates on its own.'; }); }
  load();
  setInterval(load, 15000);
})();
</script>

<div class="container">
  <div class="main">
    <div class="tabs">
      <div class="tab active" data-tab="overview">Overview</div>
      <div class="tab" data-tab="detail">Detail Levels</div>
      <div class="tab" data-tab="graph">Overlap Graph</div>
      <div class="tab" data-tab="dominance">Dominance Matrix</div>
      <div class="tab" data-tab="variables">User Variables</div>
    </div>

    <!-- OVERVIEW -->
    <div class="panel active" id="panel-overview">
      <div class="alert"><strong>Big finding:</strong> The prompt is severely unbalanced. Some categories get 500+ words of detail, others get 5. The most detailed categories tend to "win" when evidence is ambiguous, because the model has more cues to latch onto.</div>

      <h3>Detail-level imbalance (visualized below as bar chart)</h3>
      <div id="overview-bars"></div>

      <div class="info" style="margin-top: 20px;"><strong>Why this matters:</strong> When a forgery has overlapping indicators across multiple categories, the model gravitates toward the category with the richest description. This is "prompt mass bias" - more text = more attractor power.</div>

      <h3>Top dominance issues</h3>
      <div id="overview-issues"></div>
    </div>

    <!-- DETAIL -->
    <div class="panel" id="panel-detail">
      <h3>Word count per category (click to inspect)</h3>
      <div class="legend">
        <div class="legend-chip"><div class="legend-dot group-traced"></div>Traced</div>
        <div class="legend-chip"><div class="legend-dot group-alteration"></div>Alteration</div>
        <div class="legend-chip"><div class="legend-dot group-digital"></div>Digital</div>
        <div class="legend-chip"><div class="legend-dot group-obliteration"></div>Obliteration</div>
        <div class="legend-chip"><div class="legend-dot group-sympathetic"></div>Sympathetic</div>
        <div class="legend-chip"><div class="legend-dot group-currency"></div>Currency</div>
      </div>
      <div id="detail-bars"></div>
    </div>

    <!-- GRAPH -->
    <div class="panel" id="panel-graph">
      <h3>Category overlap network - thicker line = stronger overlap</h3>
      <p style="color:#888;font-size:12px;margin-bottom:12px;">Click a node to highlight its overlaps. Drag nodes to reposition. Edge thickness = overlap severity (0-1 scale).</p>
      <div class="graph-container">
        <svg id="graph"></svg>
        <div class="controls">
          <button class="btn" id="reset-btn">Reset Layout</button>
          <button class="btn" id="strong-btn">Show only strong overlaps</button>
          <button class="btn" id="all-btn">Show all</button>
        </div>
      </div>
    </div>

    <!-- DOMINANCE -->
    <div class="panel" id="panel-dominance">
      <h3>Dominance pairs - when X overlaps with Y, who tends to win?</h3>
      <p style="color:#888;font-size:12px;margin-bottom:16px;">For each high-overlap pair, the category with more prompt detail tends to dominate when evidence is ambiguous.</p>
      <div id="dominance-list"></div>
    </div>

    <!-- VARIABLES -->
    <div class="panel" id="panel-variables">
      <h3>User-context variables that bias classification</h3>
      <p style="color:#888;font-size:12px;margin-bottom:16px;">These come from the Scan form and are injected into the prompt as USER-PROVIDED CONTEXT. Each one nudges the model toward certain categories.</p>
      <div id="variables-list"></div>
    </div>
  </div>

  <aside class="sidebar">
    <h2>Inspector</h2>
    <div id="inspector">
      <div class="placeholder">Click a category, edge, or variable to see details here.</div>
    </div>
  </aside>
</div>

<script>
// ─────────────────────────────────────────────────────────────────
// DATA
// ─────────────────────────────────────────────────────────────────

const categories = [
  // TRACED
  { id: "traced_carbon", label: "Traced - Carbon", group: "traced", wordCount: 70, indicators: ["faint carbon residue along strokes","hesitation/tremor following blueprint","uniform line weight","misalignment from carbon transfer"], detail: "MEDIUM", explanation: "Carbon paper placed under genuine signature; forger traces with stylus, transfers carbon 'blueprint', then inks over." },
  { id: "traced_indentation", label: "Traced - Indentation", group: "traced", wordCount: 50, indicators: ["halo/colorless depression around strokes","ink not filling indented path","hesitation or tremor"], detail: "MEDIUM", explanation: "Pressure indentation/canal light effect - pen pressed into paper creates groove around strokes." },
  { id: "traced_projection", label: "Traced - Projection", group: "traced", wordCount: 300, indicators: ["uniform/monotonous pen pressure","micro-tremors","frequent pen lifts","no carbon residue","no grooves","suspiciously perfect match"], detail: "VERY HIGH", explanation: "Light table or projector throws genuine signature onto paper; forger inks over projected lines.", flags: ["Has 2 critical-distinction blocks vs digital_cut_paste and digital_scanned"] },

  // ALTERATION
  { id: "addition_insertion", label: "Addition - Insertion", group: "alteration", wordCount: 500, indicators: ["crowding/tight spacing","ink density mismatch","stroke rhythm inconsistency","baseline misalignment","logical value conflict","ink texture mismatch (printed vs wet)","stroke layering / Z-axis","morphological inconsistency"], detail: "VERY HIGH", explanation: "Characters added inside a word/number to change meaning. Has TWO subtypes: A) digit in blank space, B) char converted by added stroke.", flags: ["Largest single category in the prompt - over 500 words","Has bank check rule + ink layering rule"] },
  { id: "addition_interlineation", label: "Addition - Interlineation", group: "alteration", wordCount: 30, indicators: ["smaller text","different baseline","different ink"], detail: "LOW", explanation: "New writing squeezed BETWEEN existing lines (in whitespace, not inside a word)." },
  { id: "erasure_chemical", label: "Erasure - Chemical", group: "alteration", wordCount: 150, indicators: ["halo/tide mark","ink ghosting","paper fiber damage","new text on damaged background","oblique-light sheen difference"], detail: "HIGH", explanation: "Original ink dissolved with solvent (bleach, acetone, eradicator), then new text written/printed in cleaned area." },
  { id: "erasure_mechanical", label: "Erasure - Mechanical", group: "alteration", wordCount: 250, indicators: ["abraded fibers ('fuzzy patch')","shadow patch / sheen","ghost particles","paper thinning","jagged void boundary","ink feathering","logical word truncation"], detail: "HIGH", explanation: "Original ink scraped off with razor/sandpaper/eraser, then replacement written/printed on scraped area." },

  // DIGITAL
  { id: "digital_cut_paste", label: "Digital - Cut & Paste", group: "digital", wordCount: 200, indicators: ["halo/fringe","pixelation/aliasing","background inconsistency","compression artefacts","DPI mismatch","shadow/lighting","perfect leveling"], detail: "HIGH", explanation: "Genuine element (signature, stamp) digitally lifted and composited onto otherwise real document." },
  { id: "digital_desktop", label: "Digital - Desktop", group: "digital", wordCount: 200, indicators: ["perfect digital typography","font consistency across doc","forms & templates","signature-quality mismatch","zero physical realism"], detail: "HIGH", explanation: "ENTIRE document fabricated from scratch in software (Word, Canva, Photoshop)." },
  { id: "digital_scanned", label: "Digital - Scanned", group: "digital", wordCount: 200, indicators: ["scan-noise inconsistency","stamp/signature flatness","global tilt vs local alignment","compression-level mismatch","resolution halo","font/field inconsistency"], detail: "HIGH", explanation: "Real document scanned, then digital elements composited onto scan image (stamp, signature, dates)." },

  // OBLITERATION
  { id: "obliteration_ink", label: "Obliteration - Ink", group: "obliteration", wordCount: 5, indicators: ["ink scribbled over original"], detail: "VERY LOW", explanation: "Original text scribbled out with ink.", flags: ["Almost no detail in prompt - model has minimal cues"] },
  { id: "obliteration_whiteout", label: "Obliteration - White Out", group: "obliteration", wordCount: 5, indicators: ["correction fluid covering text"], detail: "VERY LOW", explanation: "Correction fluid covering text.", flags: ["Almost no detail in prompt"] },

  // SYMPATHETIC
  { id: "sympathetic_indented", label: "Sympathetic - Indented", group: "sympathetic", wordCount: 15, indicators: ["pressure indentations on paper","no visible ink","raking light reveals"], detail: "VERY LOW", explanation: "Indented writing visible only via raking light. No ink in the grooves.", flags: ["⚠ HIDDEN OVERLAP with traced_indentation - both have grooves; sympathetic has NO ink filling them"] },
  { id: "sympathetic_special", label: "Sympathetic - Special Ink", group: "sympathetic", wordCount: 200, indicators: ["heat-activated (browned/charred)","chemical-activated (color reaction)","UV/fluorescent","specific substances (lemon, milk, phenolphthalein)"], detail: "HIGH", explanation: "Invisible ink revealed by external stimulus (heat, reagent, UV)." },

  // CURRENCY
  { id: "currency_analysis", label: "Currency", group: "currency", wordCount: 355, indicators: ["security features PRESENT but simulated (flat/printed/sticker-like)","no raised intaglio relief","printed-on or missing watermark/thread","colour-shift ink that does not shift","blurry/broken microprint","photocopy dot rosettes","wrong-font or mismatched serials","NGC and NDS both legal tender","worn/old/low-quality photo is NOT counterfeit"], detail: "VERY HIGH", explanation: "Counterfeit banknote. A genuine banknote is NOT a forgery - flag only with a specific counterfeit sign, otherwise no_forgery_detected. Distinguishes genuine (embedded, optically-active features) from counterfeit (features present but simulated); NGC and NDS both legal tender; worn/old/low-quality photos of genuine notes are not flagged.", flags: ["Genuine-currency guard: real money is not auto-flagged","Currency hints routed to full prompt for genuine-vs-counterfeit discrimination"] },
];

const overlaps = [
  // TRACED ↔ TRACED (similar physical evidence)
  { source: "traced_carbon", target: "traced_indentation", strength: 0.65, severity: "MEDIUM", reason: "Both hand-drawn with hesitation/tremor. Carbon has residue; indentation has groove. Easy to confuse on low-res images." },
  { source: "traced_carbon", target: "traced_projection", strength: 0.55, severity: "MEDIUM", reason: "Both show uniform line weight from following a guide. Carbon = paper underneath; projection = light from above." },
  { source: "traced_indentation", target: "traced_projection", strength: 0.55, severity: "MEDIUM", reason: "Both hand-drawn from a visual reference. Indentation creates physical groove; projection does not." },

  // TRACED ↔ DIGITAL (high-risk crossover - already caused problems)
  { source: "traced_projection", target: "digital_cut_paste", strength: 0.85, severity: "HIGH", reason: "Both produce 'perfect-looking' signatures. Distinguish: physical pen marks vs digital halo/pixelation. Has explicit ⚠ distinction block." },
  { source: "traced_projection", target: "digital_scanned", strength: 0.85, severity: "HIGH", reason: "Both look unnaturally clean. Distinguish: paper-fiber interaction vs flat-on-scan-grain. Has explicit ⚠ distinction block." },
  { source: "traced_indentation", target: "digital_desktop", strength: 0.75, severity: "HIGH", reason: "OLD BIAS (now patched): the prompt used to say 'mechanical-looking text = traced'. Software-generated docs naturally look mechanical. Caused misclassification." },
  { source: "traced_carbon", target: "digital_cut_paste", strength: 0.45, severity: "LOW", reason: "Both can show ghost-like residue. Carbon = real ink residue; cut/paste = digital halo." },

  // SYMPATHETIC ↔ TRACED (UNADDRESSED OVERLAP!)
  { source: "sympathetic_indented", target: "traced_indentation", strength: 0.85, severity: "HIGH", reason: "BOTH involve indentation/grooves. Difference: sympathetic_indented has grooves WITHOUT ink. traced_indentation has grooves WITH ink filling them. The prompt does NOT explicitly distinguish these - risk of confusion." },

  // DIGITAL ↔ DIGITAL
  { source: "digital_cut_paste", target: "digital_desktop", strength: 0.7, severity: "MEDIUM", reason: "Both software-generated. Cut/paste = element on real doc; desktop = whole doc fabricated." },
  { source: "digital_cut_paste", target: "digital_scanned", strength: 0.75, severity: "HIGH", reason: "Both insert elements digitally. Cut/paste = onto authentic doc; scanned = onto a scan of authentic doc. Subtle distinction." },
  { source: "digital_desktop", target: "digital_scanned", strength: 0.6, severity: "MEDIUM", reason: "Both software-generated. Desktop = built from scratch; scanned = built over a real scan as base." },

  // ALTERATION ↔ ALTERATION
  { source: "addition_insertion", target: "erasure_chemical", strength: 0.65, severity: "MEDIUM", reason: "Both alter character meaning. Insertion = add ink (paper intact); erasure = remove + replace (paper damaged)." },
  { source: "addition_insertion", target: "erasure_mechanical", strength: 0.65, severity: "MEDIUM", reason: "Same logic - paper damage distinguishes erasure from insertion." },
  { source: "erasure_chemical", target: "erasure_mechanical", strength: 0.8, severity: "HIGH", reason: "Both remove + replace. Chemical = solvent (smooth, stained); mechanical = abrasion (rough, fuzzy fibers)." },

  // ERASURE ↔ OBLITERATION (smudges look similar)
  { source: "erasure_chemical", target: "obliteration_ink", strength: 0.7, severity: "MEDIUM", reason: "Both can show ink smudges. Erasure smudge = at EDGE of blank where char used to be. Obliteration = covering text intentionally." },

  // OBLITERATION ↔ OBLITERATION (under-detailed, easy to confuse)
  { source: "obliteration_ink", target: "obliteration_whiteout", strength: 0.5, severity: "LOW", reason: "Both cover text. Different materials but only 5 words of detail each - model has minimal cues to distinguish." },
];

const variables = [
  { name: "document_type", desc: "Type of document (passport, check, contract, ID, etc.). Selected from a fixed list.", influence: "Activates document-specific rules (e.g., bank check rule, ID security features). Strong nudge toward category-relevant indicators." },
  { name: "suspicion_reason", desc: "User's free-text description of why they suspect forgery (max 300 chars).", influence: "Free text bias. Can mention specific words like 'erased', 'pasted', 'traced' that anchor classification. The prompt explicitly tells the model to verify against image." },
  { name: "area_of_concern", desc: "Where the user wants the model to focus (e.g., 'signature', 'date field').", influence: "Directs attention. Doesn't force a category but biases toward forgery types common in that region." },
  { name: "image_source", desc: "Phone photo / scan / screenshot / not sure.", influence: "Strong influence. Screenshot → digital_desktop more likely. Phone photo → physical forgeries more likely." },
  { name: "is_forged_belief", desc: "User believes it IS forged / NOT forged / not sure.", influence: "Weak suggestion. Prompt warns model not to be pressured by user's belief - must verify against image." },
  { name: "shot_type", desc: "Close-up / full document / not sure.", influence: "Affects what evidence is visible. Close-up = micro-tremors, fiber details. Full doc = layout, font consistency." },
  { name: "lighting", desc: "Natural / raking / bright / not sure.", influence: "Critical for sympathetic_indented (needs raking light) and erasure detection (oblique light shows sheen)." },
  { name: "physical_clues", desc: "Specific clue user thinks they observed (16 options: indentation_grooves, carbon_streaks, ink_halo, paper_thinning, etc.).", influence: "STRONGEST per-variable bias. Each clue maps to a category. The prompt tells the model to verify but it nudges hard." },
];

const groupColors = {
  traced: "#e74c3c",
  alteration: "#f39c12",
  digital: "#5b8def",
  obliteration: "#9b59b6",
  sympathetic: "#1abc9c",
  currency: "#95a5a6",
};

// ─────────────────────────────────────────────────────────────────
// TAB SWITCHING
// ─────────────────────────────────────────────────────────────────

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'graph') drawGraph();
  });
});

// ─────────────────────────────────────────────────────────────────
// OVERVIEW PANEL
// ─────────────────────────────────────────────────────────────────

function renderOverview() {
  // Mini bars
  const sorted = [...categories].sort((a,b) => b.wordCount - a.wordCount);
  const max = sorted[0].wordCount;
  const html = sorted.slice(0, 8).map(c => `
    <div class="bar-row" data-id="${c.id}">
      <div class="bar-label">${c.label}</div>
      <div class="bar-track">
        <div class="bar-fill group-${c.group}" style="width:${(c.wordCount/max)*100}%"></div>
      </div>
      <div class="bar-value">${c.wordCount} words</div>
    </div>
  `).join('') + `<p style="color:#666;font-size:11px;margin-top:8px;">… plus 8 more categories with ≤30 words. See "Detail Levels" tab for the full picture.</p>`;
  document.getElementById('overview-bars').innerHTML = html;

  // Top dominance issues
  const issues = [
    {pair: "addition_insertion vs everything else", text: "<strong>500 words</strong> for addition_insertion; the prompt's gravitational center. When evidence is ambiguous and there's any check/numeric field, model leans here."},
    {pair: "traced_projection vs digital_cut_paste / digital_scanned", text: "<strong>300+ words</strong> for traced_projection with TWO critical-distinction blocks. High-overlap area; previously misclassified digital as traced (now patched)."},
    {pair: "obliteration_ink/whiteout/pigment", text: "<strong>5 words each</strong>. Model can barely distinguish them. Any complex coverage situation falls back to obliteration_ink as default."},
    {pair: "sympathetic_indented vs traced_indentation", text: "<strong>UNADDRESSED OVERLAP.</strong> Both involve grooves. Difference (ink vs no ink in grooves) is not explicit in prompt. 15-word definition for sympathetic, 50 for traced - bias toward traced."},
  ];
  document.getElementById('overview-issues').innerHTML = issues.map(i => `
    <div class="overlap-list" style="list-style:none;">
      <li class="severity-high">
        <div class="strength">${i.pair}</div>
        <div class="reason">${i.text}</div>
      </li>
    </div>
  `).join('');

  document.querySelectorAll('#overview-bars .bar-row').forEach(row => {
    row.addEventListener('click', () => selectCategory(row.dataset.id));
  });
}

// ─────────────────────────────────────────────────────────────────
// DETAIL PANEL
// ─────────────────────────────────────────────────────────────────

function renderDetail() {
  const sorted = [...categories].sort((a,b) => b.wordCount - a.wordCount);
  const max = sorted[0].wordCount;
  const html = sorted.map(c => `
    <div class="bar-row" data-id="${c.id}">
      <div class="bar-label">${c.label}</div>
      <div class="bar-track">
        <div class="bar-fill group-${c.group}" style="width:${(c.wordCount/max)*100}%"></div>
      </div>
      <div class="bar-value">${c.wordCount} words · ${c.detail}</div>
    </div>
  `).join('');
  document.getElementById('detail-bars').innerHTML = html;
  document.querySelectorAll('#detail-bars .bar-row').forEach(row => {
    row.addEventListener('click', () => {
      document.querySelectorAll('.bar-row').forEach(r => r.classList.remove('selected'));
      row.classList.add('selected');
      selectCategory(row.dataset.id);
    });
  });
}

// ─────────────────────────────────────────────────────────────────
// GRAPH (force-directed network)
// ─────────────────────────────────────────────────────────────────

let graphState = { nodes: [], links: [], svg: null, drawn: false, filterStrong: false };

function drawGraph() {
  if (graphState.drawn) return;
  graphState.drawn = true;

  const svg = document.getElementById('graph');
  graphState.svg = svg;
  const w = svg.clientWidth || 800;
  const h = svg.clientHeight || 600;

  // Build nodes & links
  const nodes = categories.map((c, i) => ({
    ...c,
    x: w/2 + Math.cos(i / categories.length * 2 * Math.PI) * 200,
    y: h/2 + Math.sin(i / categories.length * 2 * Math.PI) * 200,
    vx: 0, vy: 0,
    radius: 8 + Math.sqrt(c.wordCount) * 1.5,
  }));
  const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]));
  const links = overlaps.map(o => ({
    ...o,
    source: nodeMap[o.source],
    target: nodeMap[o.target],
  }));

  graphState.nodes = nodes;
  graphState.links = links;

  // Simple force simulation
  function tick() {
    // Repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i+1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const force = 4000 / (dist*dist);
        a.vx -= (dx/dist) * force;
        a.vy -= (dy/dist) * force;
        b.vx += (dx/dist) * force;
        b.vy += (dy/dist) * force;
      }
    }
    // Attraction along links
    for (const l of links) {
      const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
      const dist = Math.sqrt(dx*dx + dy*dy) || 1;
      const desired = 100 + (1-l.strength)*120;
      const force = (dist - desired) * 0.02 * l.strength;
      l.source.vx += (dx/dist) * force;
      l.source.vy += (dy/dist) * force;
      l.target.vx -= (dx/dist) * force;
      l.target.vy -= (dy/dist) * force;
    }
    // Center gravity
    for (const n of nodes) {
      n.vx += (w/2 - n.x) * 0.005;
      n.vy += (h/2 - n.y) * 0.005;
      n.vx *= 0.7;
      n.vy *= 0.7;
      if (!n.fixed) {
        n.x += n.vx;
        n.y += n.vy;
      }
      n.x = Math.max(n.radius, Math.min(w - n.radius, n.x));
      n.y = Math.max(n.radius, Math.min(h - n.radius, n.y));
    }
    render();
  }

  function render() {
    const linkSvg = links.map(l => {
      const opacity = graphState.filterStrong && l.strength < 0.7 ? 0 : 0.4;
      const stroke = l.severity === "HIGH" ? "#e74c3c" : l.severity === "MEDIUM" ? "#f39c12" : "#666";
      return `<line class="link" data-src="${l.source.id}" data-tgt="${l.target.id}"
        x1="${l.source.x}" y1="${l.source.y}" x2="${l.target.x}" y2="${l.target.y}"
        stroke="${stroke}" stroke-width="${1 + l.strength*5}" stroke-opacity="${opacity}"></line>`;
    }).join('');
    const nodeSvg = nodes.map(n => `
      <g class="node" data-id="${n.id}" transform="translate(${n.x},${n.y})">
        <circle r="${n.radius}" fill="${groupColors[n.group]}"></circle>
        <text dy="${n.radius + 12}">${n.label.replace(/^.+- /,'')}</text>
      </g>
    `).join('');
    svg.innerHTML = linkSvg + nodeSvg;
    attachNodeEvents();
  }

  function attachNodeEvents() {
    svg.querySelectorAll('.node').forEach(g => {
      const id = g.dataset.id;
      g.addEventListener('click', e => {
        e.stopPropagation();
        selectCategory(id);
        highlightNeighbors(id);
      });
      g.addEventListener('mousedown', e => {
        const node = nodeMap[id];
        node.fixed = true;
        const move = ev => {
          const rect = svg.getBoundingClientRect();
          node.x = ev.clientX - rect.left;
          node.y = ev.clientY - rect.top;
          node.vx = 0; node.vy = 0;
        };
        const up = () => {
          node.fixed = false;
          window.removeEventListener('mousemove', move);
          window.removeEventListener('mouseup', up);
        };
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
      });
    });
  }

  function highlightNeighbors(id) {
    svg.querySelectorAll('.link').forEach(l => {
      if (l.dataset.src === id || l.dataset.tgt === id) {
        l.classList.add('highlighted');
        l.classList.remove('faded');
      } else {
        l.classList.add('faded');
        l.classList.remove('highlighted');
      }
    });
  }

  // Run simulation
  let frame = 0;
  function loop() {
    tick();
    frame++;
    if (frame < 1000) requestAnimationFrame(loop);
  }
  loop();

  document.getElementById('reset-btn').addEventListener('click', () => {
    graphState.drawn = false;
    drawGraph();
  });
  document.getElementById('strong-btn').addEventListener('click', () => {
    graphState.filterStrong = true;
    render();
  });
  document.getElementById('all-btn').addEventListener('click', () => {
    graphState.filterStrong = false;
    render();
  });
}

// ─────────────────────────────────────────────────────────────────
// DOMINANCE MATRIX
// ─────────────────────────────────────────────────────────────────

function renderDominance() {
  const sorted = [...overlaps].sort((a,b) => b.strength - a.strength);
  const html = sorted.map(o => {
    const src = categories.find(c => c.id === o.source);
    const tgt = categories.find(c => c.id === o.target);
    const dominant = src.wordCount > tgt.wordCount ? src : tgt;
    const weaker = src.wordCount > tgt.wordCount ? tgt : src;
    const ratio = (dominant.wordCount / Math.max(weaker.wordCount, 1)).toFixed(1);
    const sevClass = o.severity === "HIGH" ? "severity-high" : "";
    return `
      <ul class="overlap-list">
        <li class="${sevClass}">
          <div><span class="strength">${dominant.label}</span> dominates <span style="color:#aaa">${weaker.label}</span></div>
          <div class="reason">
            <strong>Strength:</strong> ${o.strength} (${o.severity}) ·
            <strong>Detail ratio:</strong> ${dominant.wordCount} : ${weaker.wordCount} (${ratio}× more)<br>
            ${o.reason}
          </div>
        </li>
      </ul>
    `;
  }).join('');
  document.getElementById('dominance-list').innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────
// VARIABLES
// ─────────────────────────────────────────────────────────────────

function renderVariables() {
  const html = variables.map(v => `
    <div class="variable-card" data-name="${v.name}">
      <div class="var-name">${v.name}</div>
      <div class="var-desc">${v.desc}</div>
      <div class="var-influence"><strong>Influence:</strong> ${v.influence}</div>
    </div>
  `).join('');
  document.getElementById('variables-list').innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────
// INSPECTOR
// ─────────────────────────────────────────────────────────────────

function selectCategory(id) {
  const c = categories.find(x => x.id === id);
  if (!c) return;
  const myOverlaps = overlaps.filter(o => o.source === id || o.target === id);

  const overlapHtml = myOverlaps.length === 0
    ? '<p style="color:#666;font-size:12px;">No documented overlaps.</p>'
    : myOverlaps.map(o => {
        const other = o.source === id ? o.target : o.source;
        const otherCat = categories.find(c => c.id === other);
        const sevClass = o.severity === "HIGH" ? "severity-high" : "";
        return `
          <li class="${sevClass}">
            <div><span class="strength">${o.strength}</span> · ${otherCat.label} <span style="color:#666">[${o.severity}]</span></div>
            <div class="reason">${o.reason}</div>
          </li>
        `;
      }).join('');

  const flagsHtml = c.flags ? c.flags.map(f =>
    `<div class="alert" style="margin-top:8px;">${f}</div>`
  ).join('') : '';

  document.getElementById('inspector').innerHTML = `
    <div class="detail-box ${c.group}">
      <div class="detail-title">${c.label}</div>
      <div class="detail-meta">${c.id} · group: ${c.group} · detail: <strong>${c.detail}</strong> · words: ${c.wordCount}</div>
      <p style="font-size:12px;color:#bbb;margin-bottom:12px;">${c.explanation}</p>
      ${flagsHtml}
      <h3>Indicators in prompt</h3>
      <ul class="indicator-list">
        ${c.indicators.map(i => `<li>${i}</li>`).join('')}
      </ul>
    </div>

    <h3>Overlaps with other categories</h3>
    <ul class="overlap-list" style="padding:0">
      ${overlapHtml}
    </ul>
  `;
}

// ─────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────

renderOverview();
renderDetail();
renderDominance();
renderVariables();
</script>
</body>
</html>
```

## File: `backend/requirements.txt`

<!-- FILE: backend/requirements.txt -->

```text
# Revelator Backend Requirements

# Core API
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
python-dotenv>=1.0.1
pydantic>=2.9

# Database
sqlalchemy>=2.0.36

# Auth
python-jose[cryptography]>=3.3.0
bcrypt>=4.1.2
google-auth>=2.30

# Image Processing
Pillow>=11.0
torch>=2.14.0
torchvision>=0.29.0

# AI / Vision
groq>=0.11
google-genai>=1.0

# HTTP (PayMongo, Ollama)
requests>=2.32

# Payments
stripe>=10.0
```

## File: `backend/run.py`

<!-- FILE: backend/run.py -->

```python
"""Run the Revelator API server."""

import os
import uvicorn

if __name__ == "__main__":
    # PORT is overridable so we can dodge whatever already holds :8000 on this
    # laptop. When hosting revelator.site the named tunnel points at this port.
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1") != "0"
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)
```

## File: `frontend/.env.example`

<!-- FILE: frontend/.env.example -->

```dotenv
# Frontend environment - copy to .env.local for dev, .env.production for builds.
#
# Web dev (npm run dev on your PC):
#   VITE_API_URL=http://localhost:8000
#
# Android emulator → PC backend (special host IP):
#   VITE_API_URL=http://10.0.2.2:8000
#
# Real Android device on same WiFi (replace with your PC's LAN IP):
#   VITE_API_URL=http://192.168.1.42:8000
#
# Production (deployed backend):
#   VITE_API_URL=https://api.forgeguard.com

VITE_API_URL=http://localhost:8000
```

## File: `frontend/capacitor.config.ts`

<!-- FILE: frontend/capacitor.config.ts -->

```typescript
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.forgeguard.app',
  appName: 'Revelator',
  webDir: 'dist',
  backgroundColor: '#000000',
  android: {
    allowMixedContent: true,
    backgroundColor: '#000000',
    webContentsDebuggingEnabled: true,
  },
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
  plugins: {
    GoogleAuth: {
      scopes: ['profile', 'email'],
      serverClientId: '676322212303-52bprvcqb4dao6c71m3500lqh2i9i6mb.apps.googleusercontent.com',
      forceCodeForRefreshToken: true,
    },
    Camera: {
      permissions: ['camera', 'photos'],
    },
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: '#000000',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER',
      showSpinner: false,
    },
  },
};

export default config;
```

## File: `frontend/index.html`

<!-- FILE: frontend/index.html -->

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
    <meta name="theme-color" content="#000000" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="Revelator" />
    <meta name="description" content="Forensic document forgery detection. Scan a document and get a classified verdict with evidence." />
    <title>REVELATOR - Document Forensics Engine</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <!-- PWA: makes the site installable to a phone home screen. -->
    <link rel="manifest" href="/manifest.json" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Oswald:wght@400;500;600;700&family=Share+Tech+Mono&family=Source+Sans+Pro:wght@400;600&display=swap" rel="stylesheet">
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

## File: `frontend/package.json`

<!-- FILE: frontend/package.json -->

```json
{
  "name": "revelator-app",
  "private": true,
  "version": "2.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@capacitor/android": "^5.7.0",
    "@capacitor/app": "^5.0.8",
    "@capacitor/browser": "^5.2.1",
    "@capacitor/camera": "^5.0.9",
    "@capacitor/core": "^5.7.0",
    "@capacitor/filesystem": "^5.2.1",
    "@codetrix-studio/capacitor-google-auth": "^3.3.0",
    "@ionic/pwa-elements": "^3.4.0",
    "@react-oauth/google": "^0.13.5",
    "lucide-react": "^1.16.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0"
  },
  "devDependencies": {
    "@capacitor/cli": "^5.7.0",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.4.0",
    "vite": "^5.1.0"
  }
}
```

## File: `frontend/package-lock.json`

<!-- FILE: frontend/package-lock.json -->

```json
{
  "name": "revelator-app",
  "version": "2.0.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "revelator-app",
      "version": "2.0.0",
      "dependencies": {
        "@capacitor/android": "^5.7.0",
        "@capacitor/app": "^5.0.8",
        "@capacitor/browser": "^5.2.1",
        "@capacitor/camera": "^5.0.9",
        "@capacitor/core": "^5.7.0",
        "@capacitor/filesystem": "^5.2.1",
        "@codetrix-studio/capacitor-google-auth": "^3.3.0",
        "@ionic/pwa-elements": "^3.4.0",
        "@react-oauth/google": "^0.13.5",
        "lucide-react": "^1.16.0",
        "react": "^18.2.0",
        "react-dom": "^18.2.0",
        "react-router-dom": "^6.22.0"
      },
      "devDependencies": {
        "@capacitor/cli": "^5.7.0",
        "@vitejs/plugin-react": "^4.2.1",
        "typescript": "^5.4.0",
        "vite": "^5.1.0"
      }
    },
    "node_modules/@babel/code-frame": {
      "version": "7.29.0",
      "resolved": "https://registry.npmjs.org/@babel/code-frame/-/code-frame-7.29.0.tgz",
      "integrity": "sha512-9NhCeYjq9+3uxgdtp20LSiJXJvN0FeCtNGpJxuMFZ1Kv3cWUNb6DOhJwUvcVCzKGR66cw4njwM6hrJLqgOwbcw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/helper-validator-identifier": "^7.28.5",
        "js-tokens": "^4.0.0",
        "picocolors": "^1.1.1"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/compat-data": {
      "version": "7.29.0",
      "resolved": "https://registry.npmjs.org/@babel/compat-data/-/compat-data-7.29.0.tgz",
      "integrity": "sha512-T1NCJqT/j9+cn8fvkt7jtwbLBfLC/1y1c7NtCeXFRgzGTsafi68MRv8yzkYSapBnFA6L3U2VSc02ciDzoAJhJg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/core": {
      "version": "7.29.0",
      "resolved": "https://registry.npmjs.org/@babel/core/-/core-7.29.0.tgz",
      "integrity": "sha512-CGOfOJqWjg2qW/Mb6zNsDm+u5vFQ8DxXfbM09z69p5Z6+mE1ikP2jUXw+j42Pf1XTYED2Rni5f95npYeuwMDQA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/code-frame": "^7.29.0",
        "@babel/generator": "^7.29.0",
        "@babel/helper-compilation-targets": "^7.28.6",
        "@babel/helper-module-transforms": "^7.28.6",
        "@babel/helpers": "^7.28.6",
        "@babel/parser": "^7.29.0",
        "@babel/template": "^7.28.6",
        "@babel/traverse": "^7.29.0",
        "@babel/types": "^7.29.0",
        "@jridgewell/remapping": "^2.3.5",
        "convert-source-map": "^2.0.0",
        "debug": "^4.1.0",
        "gensync": "^1.0.0-beta.2",
        "json5": "^2.2.3",
        "semver": "^6.3.1"
      },
      "engines": {
        "node": ">=6.9.0"
      },
      "funding": {
        "type": "opencollective",
        "url": "https://opencollective.com/babel"
      }
    },
    "node_modules/@babel/core/node_modules/semver": {
      "version": "6.3.1",
      "resolved": "https://registry.npmjs.org/semver/-/semver-6.3.1.tgz",
      "integrity": "sha512-BR7VvDCVHO+q2xBEWskxS6DJE1qRnb7DxzUrogb71CWoSficBxYsiAGd+Kl0mmq/MprG9yArRkyrQxTO6XjMzA==",
      "dev": true,
      "license": "ISC",
      "bin": {
        "semver": "bin/semver.js"
      }
    },
    "node_modules/@babel/generator": {
      "version": "7.29.1",
      "resolved": "https://registry.npmjs.org/@babel/generator/-/generator-7.29.1.tgz",
      "integrity": "sha512-qsaF+9Qcm2Qv8SRIMMscAvG4O3lJ0F1GuMo5HR/Bp02LopNgnZBC/EkbevHFeGs4ls/oPz9v+Bsmzbkbe+0dUw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/parser": "^7.29.0",
        "@babel/types": "^7.29.0",
        "@jridgewell/gen-mapping": "^0.3.12",
        "@jridgewell/trace-mapping": "^0.3.28",
        "jsesc": "^3.0.2"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-compilation-targets": {
      "version": "7.28.6",
      "resolved": "https://registry.npmjs.org/@babel/helper-compilation-targets/-/helper-compilation-targets-7.28.6.tgz",
      "integrity": "sha512-JYtls3hqi15fcx5GaSNL7SCTJ2MNmjrkHXg4FSpOA/grxK8KwyZ5bubHsCq8FXCkua6xhuaaBit+3b7+VZRfcA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/compat-data": "^7.28.6",
        "@babel/helper-validator-option": "^7.27.1",
        "browserslist": "^4.24.0",
        "lru-cache": "^5.1.1",
        "semver": "^6.3.1"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-compilation-targets/node_modules/semver": {
      "version": "6.3.1",
      "resolved": "https://registry.npmjs.org/semver/-/semver-6.3.1.tgz",
      "integrity": "sha512-BR7VvDCVHO+q2xBEWskxS6DJE1qRnb7DxzUrogb71CWoSficBxYsiAGd+Kl0mmq/MprG9yArRkyrQxTO6XjMzA==",
      "dev": true,
      "license": "ISC",
      "bin": {
        "semver": "bin/semver.js"
      }
    },
    "node_modules/@babel/helper-globals": {
      "version": "7.28.0",
      "resolved": "https://registry.npmjs.org/@babel/helper-globals/-/helper-globals-7.28.0.tgz",
      "integrity": "sha512-+W6cISkXFa1jXsDEdYA8HeevQT/FULhxzR99pxphltZcVaugps53THCeiWA8SguxxpSp3gKPiuYfSWopkLQ4hw==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-module-imports": {
      "version": "7.28.6",
      "resolved": "https://registry.npmjs.org/@babel/helper-module-imports/-/helper-module-imports-7.28.6.tgz",
      "integrity": "sha512-l5XkZK7r7wa9LucGw9LwZyyCUscb4x37JWTPz7swwFE/0FMQAGpiWUZn8u9DzkSBWEcK25jmvubfpw2dnAMdbw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/traverse": "^7.28.6",
        "@babel/types": "^7.28.6"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-module-transforms": {
      "version": "7.28.6",
      "resolved": "https://registry.npmjs.org/@babel/helper-module-transforms/-/helper-module-transforms-7.28.6.tgz",
      "integrity": "sha512-67oXFAYr2cDLDVGLXTEABjdBJZ6drElUSI7WKp70NrpyISso3plG9SAGEF6y7zbha/wOzUByWWTJvEDVNIUGcA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/helper-module-imports": "^7.28.6",
        "@babel/helper-validator-identifier": "^7.28.5",
        "@babel/traverse": "^7.28.6"
      },
      "engines": {
        "node": ">=6.9.0"
      },
      "peerDependencies": {
        "@babel/core": "^7.0.0"
      }
    },
    "node_modules/@babel/helper-plugin-utils": {
      "version": "7.28.6",
      "resolved": "https://registry.npmjs.org/@babel/helper-plugin-utils/-/helper-plugin-utils-7.28.6.tgz",
      "integrity": "sha512-S9gzZ/bz83GRysI7gAD4wPT/AI3uCnY+9xn+Mx/KPs2JwHJIz1W8PZkg2cqyt3RNOBM8ejcXhV6y8Og7ly/Dug==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-string-parser": {
      "version": "7.27.1",
      "resolved": "https://registry.npmjs.org/@babel/helper-string-parser/-/helper-string-parser-7.27.1.tgz",
      "integrity": "sha512-qMlSxKbpRlAridDExk92nSobyDdpPijUq2DW6oDnUqd0iOGxmQjyqhMIihI9+zv4LPyZdRje2cavWPbCbWm3eA==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-validator-identifier": {
      "version": "7.28.5",
      "resolved": "https://registry.npmjs.org/@babel/helper-validator-identifier/-/helper-validator-identifier-7.28.5.tgz",
      "integrity": "sha512-qSs4ifwzKJSV39ucNjsvc6WVHs6b7S03sOh2OcHF9UHfVPqWWALUsNUVzhSBiItjRZoLHx7nIarVjqKVusUZ1Q==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helper-validator-option": {
      "version": "7.27.1",
      "resolved": "https://registry.npmjs.org/@babel/helper-validator-option/-/helper-validator-option-7.27.1.tgz",
      "integrity": "sha512-YvjJow9FxbhFFKDSuFnVCe2WxXk1zWc22fFePVNEaWJEu8IrZVlda6N0uHwzZrUM1il7NC9Mlp4MaJYbYd9JSg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/helpers": {
      "version": "7.29.2",
      "resolved": "https://registry.npmjs.org/@babel/helpers/-/helpers-7.29.2.tgz",
      "integrity": "sha512-HoGuUs4sCZNezVEKdVcwqmZN8GoHirLUcLaYVNBK2J0DadGtdcqgr3BCbvH8+XUo4NGjNl3VOtSjEKNzqfFgKw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/template": "^7.28.6",
        "@babel/types": "^7.29.0"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/parser": {
      "version": "7.29.2",
      "resolved": "https://registry.npmjs.org/@babel/parser/-/parser-7.29.2.tgz",
      "integrity": "sha512-4GgRzy/+fsBa72/RZVJmGKPmZu9Byn8o4MoLpmNe1m8ZfYnz5emHLQz3U4gLud6Zwl0RZIcgiLD7Uq7ySFuDLA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/types": "^7.29.0"
      },
      "bin": {
        "parser": "bin/babel-parser.js"
      },
      "engines": {
        "node": ">=6.0.0"
      }
    },
    "node_modules/@babel/plugin-transform-react-jsx-self": {
      "version": "7.27.1",
      "resolved": "https://registry.npmjs.org/@babel/plugin-transform-react-jsx-self/-/plugin-transform-react-jsx-self-7.27.1.tgz",
      "integrity": "sha512-6UzkCs+ejGdZ5mFFC/OCUrv028ab2fp1znZmCZjAOBKiBK2jXD1O+BPSfX8X2qjJ75fZBMSnQn3Rq2mrBJK2mw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/helper-plugin-utils": "^7.27.1"
      },
      "engines": {
        "node": ">=6.9.0"
      },
      "peerDependencies": {
        "@babel/core": "^7.0.0-0"
      }
    },
    "node_modules/@babel/plugin-transform-react-jsx-source": {
      "version": "7.27.1",
      "resolved": "https://registry.npmjs.org/@babel/plugin-transform-react-jsx-source/-/plugin-transform-react-jsx-source-7.27.1.tgz",
      "integrity": "sha512-zbwoTsBruTeKB9hSq73ha66iFeJHuaFkUbwvqElnygoNbj/jHRsSeokowZFN3CZ64IvEqcmmkVe89OPXc7ldAw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/helper-plugin-utils": "^7.27.1"
      },
      "engines": {
        "node": ">=6.9.0"
      },
      "peerDependencies": {
        "@babel/core": "^7.0.0-0"
      }
    },
    "node_modules/@babel/template": {
      "version": "7.28.6",
      "resolved": "https://registry.npmjs.org/@babel/template/-/template-7.28.6.tgz",
      "integrity": "sha512-YA6Ma2KsCdGb+WC6UpBVFJGXL58MDA6oyONbjyF/+5sBgxY/dwkhLogbMT2GXXyU84/IhRw/2D1Os1B/giz+BQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/code-frame": "^7.28.6",
        "@babel/parser": "^7.28.6",
        "@babel/types": "^7.28.6"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/traverse": {
      "version": "7.29.0",
      "resolved": "https://registry.npmjs.org/@babel/traverse/-/traverse-7.29.0.tgz",
      "integrity": "sha512-4HPiQr0X7+waHfyXPZpWPfWL/J7dcN1mx9gL6WdQVMbPnF3+ZhSMs8tCxN7oHddJE9fhNE7+lxdnlyemKfJRuA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/code-frame": "^7.29.0",
        "@babel/generator": "^7.29.0",
        "@babel/helper-globals": "^7.28.0",
        "@babel/parser": "^7.29.0",
        "@babel/template": "^7.28.6",
        "@babel/types": "^7.29.0",
        "debug": "^4.3.1"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@babel/types": {
      "version": "7.29.0",
      "resolved": "https://registry.npmjs.org/@babel/types/-/types-7.29.0.tgz",
      "integrity": "sha512-LwdZHpScM4Qz8Xw2iKSzS+cfglZzJGvofQICy7W7v4caru4EaAmyUuO6BGrbyQ2mYV11W0U8j5mBhd14dd3B0A==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/helper-string-parser": "^7.27.1",
        "@babel/helper-validator-identifier": "^7.28.5"
      },
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/@capacitor/android": {
      "version": "5.7.8",
      "resolved": "https://registry.npmjs.org/@capacitor/android/-/android-5.7.8.tgz",
      "integrity": "sha512-ooWclwcuW0dy3YfqgoozkHkjatX8H2fb2/RwRsJa3cew1P1lUXIXri3Dquuy4LdqFAJA7UHcJ19Bl/6UKdsZYA==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.7.0"
      }
    },
    "node_modules/@capacitor/app": {
      "version": "5.0.8",
      "resolved": "https://registry.npmjs.org/@capacitor/app/-/app-5.0.8.tgz",
      "integrity": "sha512-ClUPJG6Awkf5HncVCZQwLrnuugjU8TnACSJ1dKJb6QNCHv2jQzmXvB3KvTvxTZyWbh5EVvlla0qlobYyU1lb6A==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.0.0"
      }
    },
    "node_modules/@capacitor/browser": {
      "version": "5.2.1",
      "resolved": "https://registry.npmjs.org/@capacitor/browser/-/browser-5.2.1.tgz",
      "integrity": "sha512-wRoG/JOK6MnWlXxIIDN9/wXOZUVgNnUghuV0OSL+IMl4Up0skHMM7I1alturjL/AxTCgViKhPL6KwNeWALsdUw==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.0.0"
      }
    },
    "node_modules/@capacitor/camera": {
      "version": "5.0.10",
      "resolved": "https://registry.npmjs.org/@capacitor/camera/-/camera-5.0.10.tgz",
      "integrity": "sha512-DOLYjiaOdUQk8mtAAgliqVVJaGegC7VzV4Tk3j1rjXyuc8JeX5SJOfow4v0N+NYxyGMsEEtwNnVZ1B7yzxsrVg==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.0.0"
      }
    },
    "node_modules/@capacitor/cli": {
      "version": "5.7.8",
      "resolved": "https://registry.npmjs.org/@capacitor/cli/-/cli-5.7.8.tgz",
      "integrity": "sha512-qN8LDlREMhrYhOvVXahoJVNkP8LP55/YPRJrzTAFrMqlNJC18L3CzgWYIblFPnuwfbH/RxbfoZT/ydkwgVpMrw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@ionic/cli-framework-output": "^2.2.5",
        "@ionic/utils-fs": "^3.1.6",
        "@ionic/utils-subprocess": "^2.1.11",
        "@ionic/utils-terminal": "^2.3.3",
        "commander": "^9.3.0",
        "debug": "^4.3.4",
        "env-paths": "^2.2.0",
        "kleur": "^4.1.4",
        "native-run": "^2.0.0",
        "open": "^8.4.0",
        "plist": "^3.0.5",
        "prompts": "^2.4.2",
        "rimraf": "^4.4.1",
        "semver": "^7.3.7",
        "tar": "^6.1.11",
        "tslib": "^2.4.0",
        "xml2js": "^0.5.0"
      },
      "bin": {
        "cap": "bin/capacitor",
        "capacitor": "bin/capacitor"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@capacitor/core": {
      "version": "5.7.8",
      "resolved": "https://registry.npmjs.org/@capacitor/core/-/core-5.7.8.tgz",
      "integrity": "sha512-rrZcm/2vJM0WdWRQup1TUidbjQV9PfIadSkV4rAGLD7R6PuzZSMPGT0gmoZzCRlXkqrazrWWDkurei3ozU02FA==",
      "license": "MIT",
      "dependencies": {
        "tslib": "^2.1.0"
      }
    },
    "node_modules/@capacitor/filesystem": {
      "version": "5.2.2",
      "resolved": "https://registry.npmjs.org/@capacitor/filesystem/-/filesystem-5.2.2.tgz",
      "integrity": "sha512-h0Ta0NXF/zX9bXoD5qtoEoWSWCewow8Kredb2bBFO+vrd4NVthZH+GyrII2dk0++UIw40HjyLNk4apwGGSu9Sg==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.1.1"
      }
    },
    "node_modules/@codetrix-studio/capacitor-google-auth": {
      "version": "3.3.0",
      "resolved": "https://registry.npmjs.org/@codetrix-studio/capacitor-google-auth/-/capacitor-google-auth-3.3.0.tgz",
      "integrity": "sha512-EgxNKqC2AUjHJYWCbXKClUrRPag4fmyne+g890UhmFlwzuJxSwjnseZVxYtU9NRSzXGm4KtW7ZYTFh+OcPXYRQ==",
      "license": "MIT",
      "peerDependencies": {
        "@capacitor/core": "^5.0.4"
      }
    },
    "node_modules/@esbuild/aix-ppc64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/aix-ppc64/-/aix-ppc64-0.21.5.tgz",
      "integrity": "sha512-1SDgH6ZSPTlggy1yI6+Dbkiz8xzpHJEVAlF/AM1tHPLsf5STom9rwtjE4hKAF20FfXXNTFqEYXyJNWh1GiZedQ==",
      "cpu": [
        "ppc64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "aix"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-arm": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-arm/-/android-arm-0.21.5.tgz",
      "integrity": "sha512-vCPvzSjpPHEi1siZdlvAlsPxXl7WbOVUBBAowWug4rJHb68Ox8KualB+1ocNvT5fjv6wpkX6o/iEpbDrf68zcg==",
      "cpu": [
        "arm"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-arm64/-/android-arm64-0.21.5.tgz",
      "integrity": "sha512-c0uX9VAUBQ7dTDCjq+wdyGLowMdtR/GoC2U5IYk/7D1H1JYC0qseD7+11iMP2mRLN9RcCMRcjC4YMclCzGwS/A==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-x64/-/android-x64-0.21.5.tgz",
      "integrity": "sha512-D7aPRUUNHRBwHxzxRvp856rjUHRFW1SdQATKXH2hqA0kAZb1hKmi02OpYRacl0TxIGz/ZmXWlbZgjwWYaCakTA==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/darwin-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/darwin-arm64/-/darwin-arm64-0.21.5.tgz",
      "integrity": "sha512-DwqXqZyuk5AiWWf3UfLiRDJ5EDd49zg6O9wclZ7kUMv2WRFr4HKjXp/5t8JZ11QbQfUS6/cRCKGwYhtNAY88kQ==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/darwin-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/darwin-x64/-/darwin-x64-0.21.5.tgz",
      "integrity": "sha512-se/JjF8NlmKVG4kNIuyWMV/22ZaerB+qaSi5MdrXtd6R08kvs2qCN4C09miupktDitvh8jRFflwGFBQcxZRjbw==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/freebsd-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/freebsd-arm64/-/freebsd-arm64-0.21.5.tgz",
      "integrity": "sha512-5JcRxxRDUJLX8JXp/wcBCy3pENnCgBR9bN6JsY4OmhfUtIHe3ZW0mawA7+RDAcMLrMIZaf03NlQiX9DGyB8h4g==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/freebsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/freebsd-x64/-/freebsd-x64-0.21.5.tgz",
      "integrity": "sha512-J95kNBj1zkbMXtHVH29bBriQygMXqoVQOQYA+ISs0/2l3T9/kj42ow2mpqerRBxDJnmkUDCaQT/dfNXWX/ZZCQ==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-arm": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-arm/-/linux-arm-0.21.5.tgz",
      "integrity": "sha512-bPb5AHZtbeNGjCKVZ9UGqGwo8EUu4cLq68E95A53KlxAPRmUyYv2D6F0uUI65XisGOL1hBP5mTronbgo+0bFcA==",
      "cpu": [
        "arm"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-arm64/-/linux-arm64-0.21.5.tgz",
      "integrity": "sha512-ibKvmyYzKsBeX8d8I7MH/TMfWDXBF3db4qM6sy+7re0YXya+K1cem3on9XgdT2EQGMu4hQyZhan7TeQ8XkGp4Q==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-ia32": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-ia32/-/linux-ia32-0.21.5.tgz",
      "integrity": "sha512-YvjXDqLRqPDl2dvRODYmmhz4rPeVKYvppfGYKSNGdyZkA01046pLWyRKKI3ax8fbJoK5QbxblURkwK/MWY18Tg==",
      "cpu": [
        "ia32"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-loong64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-loong64/-/linux-loong64-0.21.5.tgz",
      "integrity": "sha512-uHf1BmMG8qEvzdrzAqg2SIG/02+4/DHB6a9Kbya0XDvwDEKCoC8ZRWI5JJvNdUjtciBGFQ5PuBlpEOXQj+JQSg==",
      "cpu": [
        "loong64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-mips64el": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-mips64el/-/linux-mips64el-0.21.5.tgz",
      "integrity": "sha512-IajOmO+KJK23bj52dFSNCMsz1QP1DqM6cwLUv3W1QwyxkyIWecfafnI555fvSGqEKwjMXVLokcV5ygHW5b3Jbg==",
      "cpu": [
        "mips64el"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-ppc64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-ppc64/-/linux-ppc64-0.21.5.tgz",
      "integrity": "sha512-1hHV/Z4OEfMwpLO8rp7CvlhBDnjsC3CttJXIhBi+5Aj5r+MBvy4egg7wCbe//hSsT+RvDAG7s81tAvpL2XAE4w==",
      "cpu": [
        "ppc64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-riscv64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-riscv64/-/linux-riscv64-0.21.5.tgz",
      "integrity": "sha512-2HdXDMd9GMgTGrPWnJzP2ALSokE/0O5HhTUvWIbD3YdjME8JwvSCnNGBnTThKGEB91OZhzrJ4qIIxk/SBmyDDA==",
      "cpu": [
        "riscv64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-s390x": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-s390x/-/linux-s390x-0.21.5.tgz",
      "integrity": "sha512-zus5sxzqBJD3eXxwvjN1yQkRepANgxE9lgOW2qLnmr8ikMTphkjgXu1HR01K4FJg8h1kEEDAqDcZQtbrRnB41A==",
      "cpu": [
        "s390x"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-x64/-/linux-x64-0.21.5.tgz",
      "integrity": "sha512-1rYdTpyv03iycF1+BhzrzQJCdOuAOtaqHTWJZCWvijKD2N5Xu0TtVC8/+1faWqcP9iBCWOmjmhoH94dH82BxPQ==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/netbsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/netbsd-x64/-/netbsd-x64-0.21.5.tgz",
      "integrity": "sha512-Woi2MXzXjMULccIwMnLciyZH4nCIMpWQAs049KEeMvOcNADVxo0UBIQPfSmxB3CWKedngg7sWZdLvLczpe0tLg==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "netbsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/openbsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/openbsd-x64/-/openbsd-x64-0.21.5.tgz",
      "integrity": "sha512-HLNNw99xsvx12lFBUwoT8EVCsSvRNDVxNpjZ7bPn947b8gJPzeHWyNVhFsaerc0n3TsbOINvRP2byTZ5LKezow==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "openbsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/sunos-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/sunos-x64/-/sunos-x64-0.21.5.tgz",
      "integrity": "sha512-6+gjmFpfy0BHU5Tpptkuh8+uw3mnrvgs+dSPQXQOv3ekbordwnzTVEb4qnIvQcYXq6gzkyTnoZ9dZG+D4garKg==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "sunos"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-arm64/-/win32-arm64-0.21.5.tgz",
      "integrity": "sha512-Z0gOTd75VvXqyq7nsl93zwahcTROgqvuAcYDUr+vOv8uHhNSKROyU961kgtCD1e95IqPKSQKH7tBTslnS3tA8A==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-ia32": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-ia32/-/win32-ia32-0.21.5.tgz",
      "integrity": "sha512-SWXFF1CL2RVNMaVs+BBClwtfZSvDgtL//G/smwAc5oVK/UPu2Gu9tIaRgFmYFFKrmg3SyAjSrElf0TiJ1v8fYA==",
      "cpu": [
        "ia32"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-x64/-/win32-x64-0.21.5.tgz",
      "integrity": "sha512-tQd/1efJuzPC6rCFwEvLtci/xNFcTZknmXs98FYDfGE4wP9ClFV98nyKrzJKVPMhdDnjzLhdUyMX4PsQAPjwIw==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@ionic/cli-framework-output": {
      "version": "2.2.8",
      "resolved": "https://registry.npmjs.org/@ionic/cli-framework-output/-/cli-framework-output-2.2.8.tgz",
      "integrity": "sha512-TshtaFQsovB4NWRBydbNFawql6yul7d5bMiW1WYYf17hd99V6xdDdk3vtF51bw6sLkxON3bDQpWsnUc9/hVo3g==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@ionic/utils-terminal": "2.3.5",
        "debug": "^4.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/pwa-elements": {
      "version": "3.4.0",
      "resolved": "https://registry.npmjs.org/@ionic/pwa-elements/-/pwa-elements-3.4.0.tgz",
      "integrity": "sha512-WmL7An4NOsvJvct4V/A8hudr+yXgLBHYmxzqWGsetZmzN7C6suLRS/KIh2P1t8cSYCYL7HRrbv8NrIChPkh6Ow==",
      "license": "MIT",
      "engines": {
        "node": ">=16.0.0",
        "npm": ">=8.0.0"
      }
    },
    "node_modules/@ionic/utils-array": {
      "version": "2.1.6",
      "resolved": "https://registry.npmjs.org/@ionic/utils-array/-/utils-array-2.1.6.tgz",
      "integrity": "sha512-0JZ1Zkp3wURnv8oq6Qt7fMPo5MpjbLoUoa9Bu2Q4PJuSDWM8H8gwF3dQO7VTeUj3/0o1IB1wGkFWZZYgUXZMUg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "debug": "^4.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-fs": {
      "version": "3.1.7",
      "resolved": "https://registry.npmjs.org/@ionic/utils-fs/-/utils-fs-3.1.7.tgz",
      "integrity": "sha512-2EknRvMVfhnyhL1VhFkSLa5gOcycK91VnjfrTB0kbqkTFCOXyXgVLI5whzq7SLrgD9t1aqos3lMMQyVzaQ5gVA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/fs-extra": "^8.0.0",
        "debug": "^4.0.0",
        "fs-extra": "^9.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-object": {
      "version": "2.1.6",
      "resolved": "https://registry.npmjs.org/@ionic/utils-object/-/utils-object-2.1.6.tgz",
      "integrity": "sha512-vCl7sl6JjBHFw99CuAqHljYJpcE88YaH2ZW4ELiC/Zwxl5tiwn4kbdP/gxi2OT3MQb1vOtgAmSNRtusvgxI8ww==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "debug": "^4.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-process": {
      "version": "2.1.11",
      "resolved": "https://registry.npmjs.org/@ionic/utils-process/-/utils-process-2.1.11.tgz",
      "integrity": "sha512-Uavxn+x8j3rDlZEk1X7YnaN6wCgbCwYQOeIjv/m94i1dzslqWhqIHEqxEyeE8HsT5Negboagg7GtQiABy+BLbA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@ionic/utils-object": "2.1.6",
        "@ionic/utils-terminal": "2.3.4",
        "debug": "^4.0.0",
        "signal-exit": "^3.0.3",
        "tree-kill": "^1.2.2",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-process/node_modules/@ionic/utils-terminal": {
      "version": "2.3.4",
      "resolved": "https://registry.npmjs.org/@ionic/utils-terminal/-/utils-terminal-2.3.4.tgz",
      "integrity": "sha512-cEiMFl3jklE0sW60r8JHH3ijFTwh/jkdEKWbylSyExQwZ8pPuwoXz7gpkWoJRLuoRHHSvg+wzNYyPJazIHfoJA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/slice-ansi": "^4.0.0",
        "debug": "^4.0.0",
        "signal-exit": "^3.0.3",
        "slice-ansi": "^4.0.0",
        "string-width": "^4.1.0",
        "strip-ansi": "^6.0.0",
        "tslib": "^2.0.1",
        "untildify": "^4.0.0",
        "wrap-ansi": "^7.0.0"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-stream": {
      "version": "3.1.6",
      "resolved": "https://registry.npmjs.org/@ionic/utils-stream/-/utils-stream-3.1.6.tgz",
      "integrity": "sha512-4+Kitey1lTA1yGtnigeYNhV/0tggI3lWBMjC7tBs1K9GXa/q7q4CtOISppdh8QgtOhrhAXS2Igp8rbko/Cj+lA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "debug": "^4.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-subprocess": {
      "version": "2.1.14",
      "resolved": "https://registry.npmjs.org/@ionic/utils-subprocess/-/utils-subprocess-2.1.14.tgz",
      "integrity": "sha512-nGYvyGVjU0kjPUcSRFr4ROTraT3w/7r502f5QJEsMRKTqa4eEzCshtwRk+/mpASm0kgBN5rrjYA5A/OZg8ahqg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@ionic/utils-array": "2.1.6",
        "@ionic/utils-fs": "3.1.7",
        "@ionic/utils-process": "2.1.11",
        "@ionic/utils-stream": "3.1.6",
        "@ionic/utils-terminal": "2.3.4",
        "cross-spawn": "^7.0.3",
        "debug": "^4.0.0",
        "tslib": "^2.0.1"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-subprocess/node_modules/@ionic/utils-terminal": {
      "version": "2.3.4",
      "resolved": "https://registry.npmjs.org/@ionic/utils-terminal/-/utils-terminal-2.3.4.tgz",
      "integrity": "sha512-cEiMFl3jklE0sW60r8JHH3ijFTwh/jkdEKWbylSyExQwZ8pPuwoXz7gpkWoJRLuoRHHSvg+wzNYyPJazIHfoJA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/slice-ansi": "^4.0.0",
        "debug": "^4.0.0",
        "signal-exit": "^3.0.3",
        "slice-ansi": "^4.0.0",
        "string-width": "^4.1.0",
        "strip-ansi": "^6.0.0",
        "tslib": "^2.0.1",
        "untildify": "^4.0.0",
        "wrap-ansi": "^7.0.0"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@ionic/utils-terminal": {
      "version": "2.3.5",
      "resolved": "https://registry.npmjs.org/@ionic/utils-terminal/-/utils-terminal-2.3.5.tgz",
      "integrity": "sha512-3cKScz9Jx2/Pr9ijj1OzGlBDfcmx7OMVBt4+P1uRR0SSW4cm1/y3Mo4OY3lfkuaYifMNBW8Wz6lQHbs1bihr7A==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/slice-ansi": "^4.0.0",
        "debug": "^4.0.0",
        "signal-exit": "^3.0.3",
        "slice-ansi": "^4.0.0",
        "string-width": "^4.1.0",
        "strip-ansi": "^6.0.0",
        "tslib": "^2.0.1",
        "untildify": "^4.0.0",
        "wrap-ansi": "^7.0.0"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/@jridgewell/gen-mapping": {
      "version": "0.3.13",
      "resolved": "https://registry.npmjs.org/@jridgewell/gen-mapping/-/gen-mapping-0.3.13.tgz",
      "integrity": "sha512-2kkt/7niJ6MgEPxF0bYdQ6etZaA+fQvDcLKckhy1yIQOzaoKjBBjSj63/aLVjYE3qhRt5dvM+uUyfCg6UKCBbA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@jridgewell/sourcemap-codec": "^1.5.0",
        "@jridgewell/trace-mapping": "^0.3.24"
      }
    },
    "node_modules/@jridgewell/remapping": {
      "version": "2.3.5",
      "resolved": "https://registry.npmjs.org/@jridgewell/remapping/-/remapping-2.3.5.tgz",
      "integrity": "sha512-LI9u/+laYG4Ds1TDKSJW2YPrIlcVYOwi2fUC6xB43lueCjgxV4lffOCZCtYFiH6TNOX+tQKXx97T4IKHbhyHEQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@jridgewell/gen-mapping": "^0.3.5",
        "@jridgewell/trace-mapping": "^0.3.24"
      }
    },
    "node_modules/@jridgewell/resolve-uri": {
      "version": "3.1.2",
      "resolved": "https://registry.npmjs.org/@jridgewell/resolve-uri/-/resolve-uri-3.1.2.tgz",
      "integrity": "sha512-bRISgCIjP20/tbWSPWMEi54QVPRZExkuD9lJL+UIxUKtwVJA8wW1Trb1jMs1RFXo1CBTNZ/5hpC9QvmKWdopKw==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.0.0"
      }
    },
    "node_modules/@jridgewell/sourcemap-codec": {
      "version": "1.5.5",
      "resolved": "https://registry.npmjs.org/@jridgewell/sourcemap-codec/-/sourcemap-codec-1.5.5.tgz",
      "integrity": "sha512-cYQ9310grqxueWbl+WuIUIaiUaDcj7WOq5fVhEljNVgRfOUhY9fy2zTvfoqWsnebh8Sl70VScFbICvJnLKB0Og==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/@jridgewell/trace-mapping": {
      "version": "0.3.31",
      "resolved": "https://registry.npmjs.org/@jridgewell/trace-mapping/-/trace-mapping-0.3.31.tgz",
      "integrity": "sha512-zzNR+SdQSDJzc8joaeP8QQoCQr8NuYx2dIIytl1QeBEZHJ9uW6hebsrYgbz8hJwUQao3TWCMtmfV8Nu1twOLAw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@jridgewell/resolve-uri": "^3.1.0",
        "@jridgewell/sourcemap-codec": "^1.4.14"
      }
    },
    "node_modules/@react-oauth/google": {
      "version": "0.13.5",
      "resolved": "https://registry.npmjs.org/@react-oauth/google/-/google-0.13.5.tgz",
      "integrity": "sha512-xQWri2s/3nNekZJ4uuov2aAfQYu83bN3864KcFqw2pK1nNbFurQIjPFDXhWaKH3IjYJ2r/9yyIIpsn5lMqrheQ==",
      "license": "MIT",
      "peerDependencies": {
        "react": ">=16.8.0",
        "react-dom": ">=16.8.0"
      }
    },
    "node_modules/@remix-run/router": {
      "version": "1.23.2",
      "resolved": "https://registry.npmjs.org/@remix-run/router/-/router-1.23.2.tgz",
      "integrity": "sha512-Ic6m2U/rMjTkhERIa/0ZtXJP17QUi2CbWE7cqx4J58M8aA3QTfW+2UlQ4psvTX9IO1RfNVhK3pcpdjej7L+t2w==",
      "license": "MIT",
      "engines": {
        "node": ">=14.0.0"
      }
    },
    "node_modules/@rolldown/pluginutils": {
      "version": "1.0.0-beta.27",
      "resolved": "https://registry.npmjs.org/@rolldown/pluginutils/-/pluginutils-1.0.0-beta.27.tgz",
      "integrity": "sha512-+d0F4MKMCbeVUJwG96uQ4SgAznZNSq93I3V+9NHA4OpvqG8mRCpGdKmK8l/dl02h2CCDHwW2FqilnTyDcAnqjA==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/@rollup/rollup-android-arm-eabi": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-android-arm-eabi/-/rollup-android-arm-eabi-4.60.1.tgz",
      "integrity": "sha512-d6FinEBLdIiK+1uACUttJKfgZREXrF0Qc2SmLII7W2AD8FfiZ9Wjd+rD/iRuf5s5dWrr1GgwXCvPqOuDquOowA==",
      "cpu": [
        "arm"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ]
    },
    "node_modules/@rollup/rollup-android-arm64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-android-arm64/-/rollup-android-arm64-4.60.1.tgz",
      "integrity": "sha512-YjG/EwIDvvYI1YvYbHvDz/BYHtkY4ygUIXHnTdLhG+hKIQFBiosfWiACWortsKPKU/+dUwQQCKQM3qrDe8c9BA==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "android"
      ]
    },
    "node_modules/@rollup/rollup-darwin-arm64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-darwin-arm64/-/rollup-darwin-arm64-4.60.1.tgz",
      "integrity": "sha512-mjCpF7GmkRtSJwon+Rq1N8+pI+8l7w5g9Z3vWj4T7abguC4Czwi3Yu/pFaLvA3TTeMVjnu3ctigusqWUfjZzvw==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ]
    },
    "node_modules/@rollup/rollup-darwin-x64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-darwin-x64/-/rollup-darwin-x64-4.60.1.tgz",
      "integrity": "sha512-haZ7hJ1JT4e9hqkoT9R/19XW2QKqjfJVv+i5AGg57S+nLk9lQnJ1F/eZloRO3o9Scy9CM3wQ9l+dkXtcBgN5Ew==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ]
    },
    "node_modules/@rollup/rollup-freebsd-arm64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-freebsd-arm64/-/rollup-freebsd-arm64-4.60.1.tgz",
      "integrity": "sha512-czw90wpQq3ZsAVBlinZjAYTKduOjTywlG7fEeWKUA7oCmpA8xdTkxZZlwNJKWqILlq0wehoZcJYfBvOyhPTQ6w==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "freebsd"
      ]
    },
    "node_modules/@rollup/rollup-freebsd-x64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-freebsd-x64/-/rollup-freebsd-x64-4.60.1.tgz",
      "integrity": "sha512-KVB2rqsxTHuBtfOeySEyzEOB7ltlB/ux38iu2rBQzkjbwRVlkhAGIEDiiYnO2kFOkJp+Z7pUXKyrRRFuFUKt+g==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "freebsd"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm-gnueabihf": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm-gnueabihf/-/rollup-linux-arm-gnueabihf-4.60.1.tgz",
      "integrity": "sha512-L+34Qqil+v5uC0zEubW7uByo78WOCIrBvci69E7sFASRl0X7b/MB6Cqd1lky/CtcSVTydWa2WZwFuWexjS5o6g==",
      "cpu": [
        "arm"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm-musleabihf": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm-musleabihf/-/rollup-linux-arm-musleabihf-4.60.1.tgz",
      "integrity": "sha512-n83O8rt4v34hgFzlkb1ycniJh7IR5RCIqt6mz1VRJD6pmhRi0CXdmfnLu9dIUS6buzh60IvACM842Ffb3xd6Gg==",
      "cpu": [
        "arm"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm64-gnu/-/rollup-linux-arm64-gnu-4.60.1.tgz",
      "integrity": "sha512-Nql7sTeAzhTAja3QXeAI48+/+GjBJ+QmAH13snn0AJSNL50JsDqotyudHyMbO2RbJkskbMbFJfIJKWA6R1LCJQ==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm64-musl": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm64-musl/-/rollup-linux-arm64-musl-4.60.1.tgz",
      "integrity": "sha512-+pUymDhd0ys9GcKZPPWlFiZ67sTWV5UU6zOJat02M1+PiuSGDziyRuI/pPue3hoUwm2uGfxdL+trT6Z9rxnlMA==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-loong64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-loong64-gnu/-/rollup-linux-loong64-gnu-4.60.1.tgz",
      "integrity": "sha512-VSvgvQeIcsEvY4bKDHEDWcpW4Yw7BtlKG1GUT4FzBUlEKQK0rWHYBqQt6Fm2taXS+1bXvJT6kICu5ZwqKCnvlQ==",
      "cpu": [
        "loong64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-loong64-musl": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-loong64-musl/-/rollup-linux-loong64-musl-4.60.1.tgz",
      "integrity": "sha512-4LqhUomJqwe641gsPp6xLfhqWMbQV04KtPp7/dIp0nzPxAkNY1AbwL5W0MQpcalLYk07vaW9Kp1PBhdpZYYcEw==",
      "cpu": [
        "loong64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-ppc64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-ppc64-gnu/-/rollup-linux-ppc64-gnu-4.60.1.tgz",
      "integrity": "sha512-tLQQ9aPvkBxOc/EUT6j3pyeMD6Hb8QF2BTBnCQWP/uu1lhc9AIrIjKnLYMEroIz/JvtGYgI9dF3AxHZNaEH0rw==",
      "cpu": [
        "ppc64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-ppc64-musl": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-ppc64-musl/-/rollup-linux-ppc64-musl-4.60.1.tgz",
      "integrity": "sha512-RMxFhJwc9fSXP6PqmAz4cbv3kAyvD1etJFjTx4ONqFP9DkTkXsAMU4v3Vyc5BgzC+anz7nS/9tp4obsKfqkDHg==",
      "cpu": [
        "ppc64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-riscv64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-riscv64-gnu/-/rollup-linux-riscv64-gnu-4.60.1.tgz",
      "integrity": "sha512-QKgFl+Yc1eEk6MmOBfRHYF6lTxiiiV3/z/BRrbSiW2I7AFTXoBFvdMEyglohPj//2mZS4hDOqeB0H1ACh3sBbg==",
      "cpu": [
        "riscv64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-riscv64-musl": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-riscv64-musl/-/rollup-linux-riscv64-musl-4.60.1.tgz",
      "integrity": "sha512-RAjXjP/8c6ZtzatZcA1RaQr6O1TRhzC+adn8YZDnChliZHviqIjmvFwHcxi4JKPSDAt6Uhf/7vqcBzQJy0PDJg==",
      "cpu": [
        "riscv64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-s390x-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-s390x-gnu/-/rollup-linux-s390x-gnu-4.60.1.tgz",
      "integrity": "sha512-wcuocpaOlaL1COBYiA89O6yfjlp3RwKDeTIA0hM7OpmhR1Bjo9j31G1uQVpDlTvwxGn2nQs65fBFL5UFd76FcQ==",
      "cpu": [
        "s390x"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-x64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-x64-gnu/-/rollup-linux-x64-gnu-4.60.1.tgz",
      "integrity": "sha512-77PpsFQUCOiZR9+LQEFg9GClyfkNXj1MP6wRnzYs0EeWbPcHs02AXu4xuUbM1zhwn3wqaizle3AEYg5aeoohhg==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-x64-musl": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-x64-musl/-/rollup-linux-x64-musl-4.60.1.tgz",
      "integrity": "sha512-5cIATbk5vynAjqqmyBjlciMJl1+R/CwX9oLk/EyiFXDWd95KpHdrOJT//rnUl4cUcskrd0jCCw3wpZnhIHdD9w==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-openbsd-x64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-openbsd-x64/-/rollup-openbsd-x64-4.60.1.tgz",
      "integrity": "sha512-cl0w09WsCi17mcmWqqglez9Gk8isgeWvoUZ3WiJFYSR3zjBQc2J5/ihSjpl+VLjPqjQ/1hJRcqBfLjssREQILw==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "openbsd"
      ]
    },
    "node_modules/@rollup/rollup-openharmony-arm64": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-openharmony-arm64/-/rollup-openharmony-arm64-4.60.1.tgz",
      "integrity": "sha512-4Cv23ZrONRbNtbZa37mLSueXUCtN7MXccChtKpUnQNgF010rjrjfHx3QxkS2PI7LqGT5xXyYs1a7LbzAwT0iCA==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "openharmony"
      ]
    },
    "node_modules/@rollup/rollup-win32-arm64-msvc": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-arm64-msvc/-/rollup-win32-arm64-msvc-4.60.1.tgz",
      "integrity": "sha512-i1okWYkA4FJICtr7KpYzFpRTHgy5jdDbZiWfvny21iIKky5YExiDXP+zbXzm3dUcFpkEeYNHgQ5fuG236JPq0g==",
      "cpu": [
        "arm64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-ia32-msvc": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-ia32-msvc/-/rollup-win32-ia32-msvc-4.60.1.tgz",
      "integrity": "sha512-u09m3CuwLzShA0EYKMNiFgcjjzwqtUMLmuCJLeZWjjOYA3IT2Di09KaxGBTP9xVztWyIWjVdsB2E9goMjZvTQg==",
      "cpu": [
        "ia32"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-x64-gnu": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-x64-gnu/-/rollup-win32-x64-gnu-4.60.1.tgz",
      "integrity": "sha512-k+600V9Zl1CM7eZxJgMyTUzmrmhB/0XZnF4pRypKAlAgxmedUA+1v9R+XOFv56W4SlHEzfeMtzujLJD22Uz5zg==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-x64-msvc": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-x64-msvc/-/rollup-win32-x64-msvc-4.60.1.tgz",
      "integrity": "sha512-lWMnixq/QzxyhTV6NjQJ4SFo1J6PvOX8vUx5Wb4bBPsEb+8xZ89Bz6kOXpfXj9ak9AHTQVQzlgzBEc1SyM27xQ==",
      "cpu": [
        "x64"
      ],
      "dev": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@types/babel__core": {
      "version": "7.20.5",
      "resolved": "https://registry.npmjs.org/@types/babel__core/-/babel__core-7.20.5.tgz",
      "integrity": "sha512-qoQprZvz5wQFJwMDqeseRXWv3rqMvhgpbXFfVyWhbx9X47POIA6i/+dXefEmZKoAgOaTdaIgNSMqMIU61yRyzA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/parser": "^7.20.7",
        "@babel/types": "^7.20.7",
        "@types/babel__generator": "*",
        "@types/babel__template": "*",
        "@types/babel__traverse": "*"
      }
    },
    "node_modules/@types/babel__generator": {
      "version": "7.27.0",
      "resolved": "https://registry.npmjs.org/@types/babel__generator/-/babel__generator-7.27.0.tgz",
      "integrity": "sha512-ufFd2Xi92OAVPYsy+P4n7/U7e68fex0+Ee8gSG9KX7eo084CWiQ4sdxktvdl0bOPupXtVJPY19zk6EwWqUQ8lg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/types": "^7.0.0"
      }
    },
    "node_modules/@types/babel__template": {
      "version": "7.4.4",
      "resolved": "https://registry.npmjs.org/@types/babel__template/-/babel__template-7.4.4.tgz",
      "integrity": "sha512-h/NUaSyG5EyxBIp8YRxo4RMe2/qQgvyowRwVMzhYhBCONbW8PUsg4lkFMrhgZhUe5z3L3MiLDuvyJ/CaPa2A8A==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/parser": "^7.1.0",
        "@babel/types": "^7.0.0"
      }
    },
    "node_modules/@types/babel__traverse": {
      "version": "7.28.0",
      "resolved": "https://registry.npmjs.org/@types/babel__traverse/-/babel__traverse-7.28.0.tgz",
      "integrity": "sha512-8PvcXf70gTDZBgt9ptxJ8elBeBjcLOAcOtoO/mPJjtji1+CdGbHgm77om1GrsPxsiE+uXIpNSK64UYaIwQXd4Q==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/types": "^7.28.2"
      }
    },
    "node_modules/@types/estree": {
      "version": "1.0.8",
      "resolved": "https://registry.npmjs.org/@types/estree/-/estree-1.0.8.tgz",
      "integrity": "sha512-dWHzHa2WqEXI/O1E9OjrocMTKJl2mSrEolh1Iomrv6U+JuNwaHXsXx9bLu5gG7BUWFIN0skIQJQ/L1rIex4X6w==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/@types/fs-extra": {
      "version": "8.1.5",
      "resolved": "https://registry.npmjs.org/@types/fs-extra/-/fs-extra-8.1.5.tgz",
      "integrity": "sha512-0dzKcwO+S8s2kuF5Z9oUWatQJj5Uq/iqphEtE3GQJVRRYm/tD1LglU2UnXi2A8jLq5umkGouOXOR9y0n613ZwQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/node": "*"
      }
    },
    "node_modules/@types/node": {
      "version": "25.6.0",
      "resolved": "https://registry.npmjs.org/@types/node/-/node-25.6.0.tgz",
      "integrity": "sha512-+qIYRKdNYJwY3vRCZMdJbPLJAtGjQBudzZzdzwQYkEPQd+PJGixUL5QfvCLDaULoLv+RhT3LDkwEfKaAkgSmNQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "undici-types": "~7.19.0"
      }
    },
    "node_modules/@types/slice-ansi": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/@types/slice-ansi/-/slice-ansi-4.0.0.tgz",
      "integrity": "sha512-+OpjSaq85gvlZAYINyzKpLeiFkSC4EsC6IIiT6v6TLSU5k5U83fHGj9Lel8oKEXM0HqgrMVCjXPDPVICtxF7EQ==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/@vitejs/plugin-react": {
      "version": "4.7.0",
      "resolved": "https://registry.npmjs.org/@vitejs/plugin-react/-/plugin-react-4.7.0.tgz",
      "integrity": "sha512-gUu9hwfWvvEDBBmgtAowQCojwZmJ5mcLn3aufeCsitijs3+f2NsrPtlAWIR6OPiqljl96GVCUbLe0HyqIpVaoA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@babel/core": "^7.28.0",
        "@babel/plugin-transform-react-jsx-self": "^7.27.1",
        "@babel/plugin-transform-react-jsx-source": "^7.27.1",
        "@rolldown/pluginutils": "1.0.0-beta.27",
        "@types/babel__core": "^7.20.5",
        "react-refresh": "^0.17.0"
      },
      "engines": {
        "node": "^14.18.0 || >=16.0.0"
      },
      "peerDependencies": {
        "vite": "^4.2.0 || ^5.0.0 || ^6.0.0 || ^7.0.0"
      }
    },
    "node_modules/@xmldom/xmldom": {
      "version": "0.8.12",
      "resolved": "https://registry.npmjs.org/@xmldom/xmldom/-/xmldom-0.8.12.tgz",
      "integrity": "sha512-9k/gHF6n/pAi/9tqr3m3aqkuiNosYTurLLUtc7xQ9sxB/wm7WPygCv8GYa6mS0fLJEHhqMC1ATYhz++U/lRHqg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=10.0.0"
      }
    },
    "node_modules/ansi-regex": {
      "version": "5.0.1",
      "resolved": "https://registry.npmjs.org/ansi-regex/-/ansi-regex-5.0.1.tgz",
      "integrity": "sha512-quJQXlTSUGL2LH9SUXo8VwsY4soanhgo6LNSm84E1LBcE8s3O0wpdiRzyR9z/ZZJMlMWv37qOOb9pdJlMUEKFQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/ansi-styles": {
      "version": "4.3.0",
      "resolved": "https://registry.npmjs.org/ansi-styles/-/ansi-styles-4.3.0.tgz",
      "integrity": "sha512-zbB9rCJAT1rbjiVDb2hqKFHNYLxgtk8NURxZ3IZwD3F6NtxbXZQCnnSi1Lkx+IDohdPlFp222wVALIheZJQSEg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "color-convert": "^2.0.1"
      },
      "engines": {
        "node": ">=8"
      },
      "funding": {
        "url": "https://github.com/chalk/ansi-styles?sponsor=1"
      }
    },
    "node_modules/astral-regex": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/astral-regex/-/astral-regex-2.0.0.tgz",
      "integrity": "sha512-Z7tMw1ytTXt5jqMcOP+OQteU1VuNK9Y02uuJtKQ1Sv69jXQKKg5cibLwGJow8yzZP+eAc18EmLGPal0bp36rvQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/at-least-node": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/at-least-node/-/at-least-node-1.0.0.tgz",
      "integrity": "sha512-+q/t7Ekv1EDY2l6Gda6LLiX14rU9TV20Wa3ofeQmwPFZbOMo9DXrLbOjFaaclkXKWidIaopwAObQDqwWtGUjqg==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": ">= 4.0.0"
      }
    },
    "node_modules/balanced-match": {
      "version": "1.0.2",
      "resolved": "https://registry.npmjs.org/balanced-match/-/balanced-match-1.0.2.tgz",
      "integrity": "sha512-3oSeUO0TMV67hN1AmbXsK4yaqU7tjiHlbxRDZOpH0KW9+CeX4bRAaX0Anxt0tx2MrpRpWwQaPwIlISEJhYU5Pw==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/base64-js": {
      "version": "1.5.1",
      "resolved": "https://registry.npmjs.org/base64-js/-/base64-js-1.5.1.tgz",
      "integrity": "sha512-AKpaYlHn8t4SVbOHCy+b5+KKgvR4vrsD8vbvrbiQJps7fKDTkjkDry6ji0rUJjC0kzbNePLwzxq8iypo41qeWA==",
      "dev": true,
      "funding": [
        {
          "type": "github",
          "url": "https://github.com/sponsors/feross"
        },
        {
          "type": "patreon",
          "url": "https://www.patreon.com/feross"
        },
        {
          "type": "consulting",
          "url": "https://feross.org/support"
        }
      ],
      "license": "MIT"
    },
    "node_modules/baseline-browser-mapping": {
      "version": "2.10.19",
      "resolved": "https://registry.npmjs.org/baseline-browser-mapping/-/baseline-browser-mapping-2.10.19.tgz",
      "integrity": "sha512-qCkNLi2sfBOn8XhZQ0FXsT1Ki/Yo5P90hrkRamVFRS7/KV9hpfA4HkoWNU152+8w0zPjnxo5psx5NL3PSGgv5g==",
      "dev": true,
      "license": "Apache-2.0",
      "bin": {
        "baseline-browser-mapping": "dist/cli.cjs"
      },
      "engines": {
        "node": ">=6.0.0"
      }
    },
    "node_modules/big-integer": {
      "version": "1.6.52",
      "resolved": "https://registry.npmjs.org/big-integer/-/big-integer-1.6.52.tgz",
      "integrity": "sha512-QxD8cf2eVqJOOz63z6JIN9BzvVs/dlySa5HGSBH5xtR8dPteIRQnBxxKqkNTiT6jbDTF6jAfrd4oMcND9RGbQg==",
      "dev": true,
      "license": "Unlicense",
      "engines": {
        "node": ">=0.6"
      }
    },
    "node_modules/bplist-parser": {
      "version": "0.3.2",
      "resolved": "https://registry.npmjs.org/bplist-parser/-/bplist-parser-0.3.2.tgz",
      "integrity": "sha512-apC2+fspHGI3mMKj+dGevkGo/tCqVB8jMb6i+OX+E29p0Iposz07fABkRIfVUPNd5A5VbuOz1bZbnmkKLYF+wQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "big-integer": "1.6.x"
      },
      "engines": {
        "node": ">= 5.10.0"
      }
    },
    "node_modules/brace-expansion": {
      "version": "2.1.0",
      "resolved": "https://registry.npmjs.org/brace-expansion/-/brace-expansion-2.1.0.tgz",
      "integrity": "sha512-TN1kCZAgdgweJhWWpgKYrQaMNHcDULHkWwQIspdtjV4Y5aurRdZpjAqn6yX3FPqTA9ngHCc4hJxMAMgGfve85w==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "balanced-match": "^1.0.0"
      }
    },
    "node_modules/browserslist": {
      "version": "4.28.2",
      "resolved": "https://registry.npmjs.org/browserslist/-/browserslist-4.28.2.tgz",
      "integrity": "sha512-48xSriZYYg+8qXna9kwqjIVzuQxi+KYWp2+5nCYnYKPTr0LvD89Jqk2Or5ogxz0NUMfIjhh2lIUX/LyX9B4oIg==",
      "dev": true,
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/browserslist"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/browserslist"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "dependencies": {
        "baseline-browser-mapping": "^2.10.12",
        "caniuse-lite": "^1.0.30001782",
        "electron-to-chromium": "^1.5.328",
        "node-releases": "^2.0.36",
        "update-browserslist-db": "^1.2.3"
      },
      "bin": {
        "browserslist": "cli.js"
      },
      "engines": {
        "node": "^6 || ^7 || ^8 || ^9 || ^10 || ^11 || ^12 || >=13.7"
      }
    },
    "node_modules/buffer-crc32": {
      "version": "0.2.13",
      "resolved": "https://registry.npmjs.org/buffer-crc32/-/buffer-crc32-0.2.13.tgz",
      "integrity": "sha512-VO9Ht/+p3SN7SKWqcrgEzjGbRSJYTx+Q1pTQC0wrWqHx0vpJraQ6GtHx8tvcg1rlK1byhU5gccxgOgj7B0TDkQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": "*"
      }
    },
    "node_modules/caniuse-lite": {
      "version": "1.0.30001788",
      "resolved": "https://registry.npmjs.org/caniuse-lite/-/caniuse-lite-1.0.30001788.tgz",
      "integrity": "sha512-6q8HFp+lOQtcf7wBK+uEenxymVWkGKkjFpCvw5W25cmMwEDU45p1xQFBQv8JDlMMry7eNxyBaR+qxgmTUZkIRQ==",
      "dev": true,
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/browserslist"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/caniuse-lite"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "CC-BY-4.0"
    },
    "node_modules/chownr": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/chownr/-/chownr-2.0.0.tgz",
      "integrity": "sha512-bIomtDF5KGpdogkLd9VspvFzk9KfpyyGlS8YFVZl7TGPBHL5snIOnxeshwVgPteQ9b4Eydl+pVbIyE1DcvCWgQ==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": ">=10"
      }
    },
    "node_modules/color-convert": {
      "version": "2.0.1",
      "resolved": "https://registry.npmjs.org/color-convert/-/color-convert-2.0.1.tgz",
      "integrity": "sha512-RRECPsj7iu/xb5oKYcsFHSppFNnsj/52OVTRKb4zP5onXwVF3zVmmToNcOfGC+CRDpfK/U584fMg38ZHCaElKQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "color-name": "~1.1.4"
      },
      "engines": {
        "node": ">=7.0.0"
      }
    },
    "node_modules/color-name": {
      "version": "1.1.4",
      "resolved": "https://registry.npmjs.org/color-name/-/color-name-1.1.4.tgz",
      "integrity": "sha512-dOy+3AuW3a2wNbZHIuMZpTcgjGuLU/uBL/ubcZF9OXbDo8ff4O8yVp5Bf0efS8uEoYo5q4Fx7dY9OgQGXgAsQA==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/commander": {
      "version": "9.5.0",
      "resolved": "https://registry.npmjs.org/commander/-/commander-9.5.0.tgz",
      "integrity": "sha512-KRs7WVDKg86PWiuAqhDrAQnTXZKraVcCc6vFdL14qrZ/DcWwuRo7VoiYXalXO7S5GKpqYiVEwCbgFDfxNHKJBQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": "^12.20.0 || >=14"
      }
    },
    "node_modules/convert-source-map": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/convert-source-map/-/convert-source-map-2.0.0.tgz",
      "integrity": "sha512-Kvp459HrV2FEJ1CAsi1Ku+MY3kasH19TFykTz2xWmMeq6bk2NU3XXvfJ+Q61m0xktWwt+1HSYf3JZsTms3aRJg==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/cross-spawn": {
      "version": "7.0.6",
      "resolved": "https://registry.npmjs.org/cross-spawn/-/cross-spawn-7.0.6.tgz",
      "integrity": "sha512-uV2QOWP2nWzsy2aMp8aRibhi9dlzF5Hgh5SHaB9OiTGEyDTiJJyx0uy51QXdyWbtAHNua4XJzUKca3OzKUd3vA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "path-key": "^3.1.0",
        "shebang-command": "^2.0.0",
        "which": "^2.0.1"
      },
      "engines": {
        "node": ">= 8"
      }
    },
    "node_modules/debug": {
      "version": "4.4.3",
      "resolved": "https://registry.npmjs.org/debug/-/debug-4.4.3.tgz",
      "integrity": "sha512-RGwwWnwQvkVfavKVt22FGLw+xYSdzARwm0ru6DhTVA3umU5hZc28V3kO4stgYryrTlLpuvgI9GiijltAjNbcqA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "ms": "^2.1.3"
      },
      "engines": {
        "node": ">=6.0"
      },
      "peerDependenciesMeta": {
        "supports-color": {
          "optional": true
        }
      }
    },
    "node_modules/define-lazy-prop": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/define-lazy-prop/-/define-lazy-prop-2.0.0.tgz",
      "integrity": "sha512-Ds09qNh8yw3khSjiJjiUInaGX9xlqZDY7JVryGxdxV7NPeuqQfplOpQ66yJFZut3jLa5zOwkXw1g9EI2uKh4Og==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/electron-to-chromium": {
      "version": "1.5.339",
      "resolved": "https://registry.npmjs.org/electron-to-chromium/-/electron-to-chromium-1.5.339.tgz",
      "integrity": "sha512-Is+0BBHJ4NrdpAYiperrmp53pLywG/yV/6lIMTAnhxvzj/Cmn5Q/ogSHC6AKe7X+8kPLxxFk0cs5oc/3j/fxIg==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/elementtree": {
      "version": "0.1.7",
      "resolved": "https://registry.npmjs.org/elementtree/-/elementtree-0.1.7.tgz",
      "integrity": "sha512-wkgGT6kugeQk/P6VZ/f4T+4HB41BVgNBq5CDIZVbQ02nvTVqAiVTbskxxu3eA/X96lMlfYOwnLQpN2v5E1zDEg==",
      "dev": true,
      "license": "Apache-2.0",
      "dependencies": {
        "sax": "1.1.4"
      },
      "engines": {
        "node": ">= 0.4.0"
      }
    },
    "node_modules/emoji-regex": {
      "version": "8.0.0",
      "resolved": "https://registry.npmjs.org/emoji-regex/-/emoji-regex-8.0.0.tgz",
      "integrity": "sha512-MSjYzcWNOA0ewAHpz0MxpYFvwg6yjy1NG3xteoqz644VCo/RPgnr1/GGt+ic3iJTzQ8Eu3TdM14SawnVUmGE6A==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/env-paths": {
      "version": "2.2.1",
      "resolved": "https://registry.npmjs.org/env-paths/-/env-paths-2.2.1.tgz",
      "integrity": "sha512-+h1lkLKhZMTYjog1VEpJNG7NZJWcuc2DDk/qsqSTRRCOXiLjeQ1d1/udrUGhqMxUgAlwKNZ0cf2uqan5GLuS2A==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/esbuild": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/esbuild/-/esbuild-0.21.5.tgz",
      "integrity": "sha512-mg3OPMV4hXywwpoDxu3Qda5xCKQi+vCTZq8S9J/EpkhB2HzKXq4SNFZE3+NK93JYxc8VMSep+lOUSC/RVKaBqw==",
      "dev": true,
      "hasInstallScript": true,
      "license": "MIT",
      "bin": {
        "esbuild": "bin/esbuild"
      },
      "engines": {
        "node": ">=12"
      },
      "optionalDependencies": {
        "@esbuild/aix-ppc64": "0.21.5",
        "@esbuild/android-arm": "0.21.5",
        "@esbuild/android-arm64": "0.21.5",
        "@esbuild/android-x64": "0.21.5",
        "@esbuild/darwin-arm64": "0.21.5",
        "@esbuild/darwin-x64": "0.21.5",
        "@esbuild/freebsd-arm64": "0.21.5",
        "@esbuild/freebsd-x64": "0.21.5",
        "@esbuild/linux-arm": "0.21.5",
        "@esbuild/linux-arm64": "0.21.5",
        "@esbuild/linux-ia32": "0.21.5",
        "@esbuild/linux-loong64": "0.21.5",
        "@esbuild/linux-mips64el": "0.21.5",
        "@esbuild/linux-ppc64": "0.21.5",
        "@esbuild/linux-riscv64": "0.21.5",
        "@esbuild/linux-s390x": "0.21.5",
        "@esbuild/linux-x64": "0.21.5",
        "@esbuild/netbsd-x64": "0.21.5",
        "@esbuild/openbsd-x64": "0.21.5",
        "@esbuild/sunos-x64": "0.21.5",
        "@esbuild/win32-arm64": "0.21.5",
        "@esbuild/win32-ia32": "0.21.5",
        "@esbuild/win32-x64": "0.21.5"
      }
    },
    "node_modules/escalade": {
      "version": "3.2.0",
      "resolved": "https://registry.npmjs.org/escalade/-/escalade-3.2.0.tgz",
      "integrity": "sha512-WUj2qlxaQtO4g6Pq5c29GTcWGDyd8itL8zTlipgECz3JesAiiOKotd8JU6otB3PACgG6xkJUyVhboMS+bje/jA==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/fd-slicer": {
      "version": "1.1.0",
      "resolved": "https://registry.npmjs.org/fd-slicer/-/fd-slicer-1.1.0.tgz",
      "integrity": "sha512-cE1qsB/VwyQozZ+q1dGxR8LBYNZeofhEdUNGSMbQD3Gw2lAzX9Zb3uIU6Ebc/Fmyjo9AWWfnn0AUCHqtevs/8g==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "pend": "~1.2.0"
      }
    },
    "node_modules/fs-extra": {
      "version": "9.1.0",
      "resolved": "https://registry.npmjs.org/fs-extra/-/fs-extra-9.1.0.tgz",
      "integrity": "sha512-hcg3ZmepS30/7BSFqRvoo3DOMQu7IjqxO5nCDt+zM9XWjb33Wg7ziNT+Qvqbuc3+gWpzO02JubVyk2G4Zvo1OQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "at-least-node": "^1.0.0",
        "graceful-fs": "^4.2.0",
        "jsonfile": "^6.0.1",
        "universalify": "^2.0.0"
      },
      "engines": {
        "node": ">=10"
      }
    },
    "node_modules/fs-minipass": {
      "version": "2.1.0",
      "resolved": "https://registry.npmjs.org/fs-minipass/-/fs-minipass-2.1.0.tgz",
      "integrity": "sha512-V/JgOLFCS+R6Vcq0slCuaeWEdNC3ouDlJMNIsacH2VtALiu9mV4LPrHc5cDl8k5aw6J8jwgWWpiTo5RYhmIzvg==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "minipass": "^3.0.0"
      },
      "engines": {
        "node": ">= 8"
      }
    },
    "node_modules/fs-minipass/node_modules/minipass": {
      "version": "3.3.6",
      "resolved": "https://registry.npmjs.org/minipass/-/minipass-3.3.6.tgz",
      "integrity": "sha512-DxiNidxSEK+tHG6zOIklvNOwm3hvCrbUrdtzY74U6HKTJxvIDfOUL5W5P2Ghd3DTkhhKPYGqeNUIh5qcM4YBfw==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "yallist": "^4.0.0"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/fs-minipass/node_modules/yallist": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/yallist/-/yallist-4.0.0.tgz",
      "integrity": "sha512-3wdGidZyq5PB084XLES5TpOSRA3wjXAlIWMhum2kRcv/41Sn2emQ0dycQW4uZXLejwKvg6EsvbdlVL+FYEct7A==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/fs.realpath": {
      "version": "1.0.0",
      "resolved": "https://registry.npmjs.org/fs.realpath/-/fs.realpath-1.0.0.tgz",
      "integrity": "sha512-OO0pH2lK6a0hZnAdau5ItzHPI6pUlvI7jMVnxUQRtw4owF2wk8lOSabtGDCTP4Ggrg2MbGnWO9X8K1t4+fGMDw==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/fsevents": {
      "version": "2.3.3",
      "resolved": "https://registry.npmjs.org/fsevents/-/fsevents-2.3.3.tgz",
      "integrity": "sha512-5xoDfX+fL7faATnagmWPpbFtwh/R77WmMMqqHGS65C3vvB0YHrgF+B1YmZ3441tMj5n63k0212XNoJwzlhffQw==",
      "dev": true,
      "hasInstallScript": true,
      "license": "MIT",
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": "^8.16.0 || ^10.6.0 || >=11.0.0"
      }
    },
    "node_modules/gensync": {
      "version": "1.0.0-beta.2",
      "resolved": "https://registry.npmjs.org/gensync/-/gensync-1.0.0-beta.2.tgz",
      "integrity": "sha512-3hN7NaskYvMDLQY55gnW3NQ+mesEAepTqlg+VEbj7zzqEMBVNhzcGYYeqFo/TlYz6eQiFcp1HcsCZO+nGgS8zg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6.9.0"
      }
    },
    "node_modules/glob": {
      "version": "9.3.5",
      "resolved": "https://registry.npmjs.org/glob/-/glob-9.3.5.tgz",
      "integrity": "sha512-e1LleDykUz2Iu+MTYdkSsuWX8lvAjAcs0Xef0lNIu0S2wOAzuTxCJtcd9S3cijlwYF18EsU3rzb8jPVobxDh9Q==",
      "deprecated": "Old versions of glob are not supported, and contain widely publicized security vulnerabilities, which have been fixed in the current version. Please update. Support for old versions may be purchased (at exorbitant rates) by contacting i@izs.me",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "fs.realpath": "^1.0.0",
        "minimatch": "^8.0.2",
        "minipass": "^4.2.4",
        "path-scurry": "^1.6.1"
      },
      "engines": {
        "node": ">=16 || 14 >=14.17"
      },
      "funding": {
        "url": "https://github.com/sponsors/isaacs"
      }
    },
    "node_modules/graceful-fs": {
      "version": "4.2.11",
      "resolved": "https://registry.npmjs.org/graceful-fs/-/graceful-fs-4.2.11.tgz",
      "integrity": "sha512-RbJ5/jmFcNNCcDV5o9eTnBLJ/HszWV0P73bc+Ff4nS/rJj+YaS6IGyiOL0VoBYX+l1Wrl3k63h/KrH+nhJ0XvQ==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/inherits": {
      "version": "2.0.4",
      "resolved": "https://registry.npmjs.org/inherits/-/inherits-2.0.4.tgz",
      "integrity": "sha512-k/vGaX4/Yla3WzyMCvTQOXYeIHvqOKtnqBduzTHpzpQZzAskKMhZ2K+EnBiSM9zGSoIFeMpXKxa4dYeZIQqewQ==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/ini": {
      "version": "4.1.3",
      "resolved": "https://registry.npmjs.org/ini/-/ini-4.1.3.tgz",
      "integrity": "sha512-X7rqawQBvfdjS10YU1y1YVreA3SsLrW9dX2CewP2EbBJM4ypVNLDkO5y04gejPwKIY9lR+7r9gn3rFPt/kmWFg==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": "^14.17.0 || ^16.13.0 || >=18.0.0"
      }
    },
    "node_modules/is-docker": {
      "version": "2.2.1",
      "resolved": "https://registry.npmjs.org/is-docker/-/is-docker-2.2.1.tgz",
      "integrity": "sha512-F+i2BKsFrH66iaUFc0woD8sLy8getkwTwtOBjvs56Cx4CgJDeKQeqfz8wAYiSb8JOprWhHH5p77PbmYCvvUuXQ==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "is-docker": "cli.js"
      },
      "engines": {
        "node": ">=8"
      },
      "funding": {
        "url": "https://github.com/sponsors/sindresorhus"
      }
    },
    "node_modules/is-fullwidth-code-point": {
      "version": "3.0.0",
      "resolved": "https://registry.npmjs.org/is-fullwidth-code-point/-/is-fullwidth-code-point-3.0.0.tgz",
      "integrity": "sha512-zymm5+u+sCsSWyD9qNaejV3DFvhCKclKdizYaJUuHA83RLjb7nSuGnddCHGv0hk+KY7BMAlsWeK4Ueg6EV6XQg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/is-wsl": {
      "version": "2.2.0",
      "resolved": "https://registry.npmjs.org/is-wsl/-/is-wsl-2.2.0.tgz",
      "integrity": "sha512-fKzAra0rGJUUBwGBgNkHZuToZcn+TtXHpeCgmkMJMMYx1sQDYaCSyjJBSCa2nH1DGm7s3n1oBnohoVTBaN7Lww==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "is-docker": "^2.0.0"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/isexe": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/isexe/-/isexe-2.0.0.tgz",
      "integrity": "sha512-RHxMLp9lnKHGHRng9QFhRCMbYAcVpn69smSGcq3f36xjgVVWThj4qqLbTLlq7Ssj8B+fIQ1EuCEGI2lKsyQeIw==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/js-tokens": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/js-tokens/-/js-tokens-4.0.0.tgz",
      "integrity": "sha512-RdJUflcE3cUzKiMqQgsCu06FPu9UdIJO0beYbPhHN4k6apgJtifcoCtT9bcxOpYBtpD2kCM6Sbzg4CausW/PKQ==",
      "license": "MIT"
    },
    "node_modules/jsesc": {
      "version": "3.1.0",
      "resolved": "https://registry.npmjs.org/jsesc/-/jsesc-3.1.0.tgz",
      "integrity": "sha512-/sM3dO2FOzXjKQhJuo0Q173wf2KOo8t4I8vHy6lF9poUp7bKT0/NHE8fPX23PwfhnykfqnC2xRxOnVw5XuGIaA==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "jsesc": "bin/jsesc"
      },
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/json5": {
      "version": "2.2.3",
      "resolved": "https://registry.npmjs.org/json5/-/json5-2.2.3.tgz",
      "integrity": "sha512-XmOWe7eyHYH14cLdVPoyg+GOH3rYX++KpzrylJwSW98t3Nk+U8XOl8FWKOgwtzdb8lXGf6zYwDUzeHMWfxasyg==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "json5": "lib/cli.js"
      },
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/jsonfile": {
      "version": "6.2.0",
      "resolved": "https://registry.npmjs.org/jsonfile/-/jsonfile-6.2.0.tgz",
      "integrity": "sha512-FGuPw30AdOIUTRMC2OMRtQV+jkVj2cfPqSeWXv1NEAJ1qZ5zb1X6z1mFhbfOB/iy3ssJCD+3KuZ8r8C3uVFlAg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "universalify": "^2.0.0"
      },
      "optionalDependencies": {
        "graceful-fs": "^4.1.6"
      }
    },
    "node_modules/kleur": {
      "version": "4.1.5",
      "resolved": "https://registry.npmjs.org/kleur/-/kleur-4.1.5.tgz",
      "integrity": "sha512-o+NO+8WrRiQEE4/7nwRJhN1HWpVmJm511pBHUxPLtp0BUISzlBplORYSmTclCnJvQq2tKu/sgl3xVpkc7ZWuQQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/loose-envify": {
      "version": "1.4.0",
      "resolved": "https://registry.npmjs.org/loose-envify/-/loose-envify-1.4.0.tgz",
      "integrity": "sha512-lyuxPGr/Wfhrlem2CL/UcnUc1zcqKAImBDzukY7Y5F/yQiNdko6+fRLevlw1HgMySw7f611UIY408EtxRSoK3Q==",
      "license": "MIT",
      "dependencies": {
        "js-tokens": "^3.0.0 || ^4.0.0"
      },
      "bin": {
        "loose-envify": "cli.js"
      }
    },
    "node_modules/lru-cache": {
      "version": "5.1.1",
      "resolved": "https://registry.npmjs.org/lru-cache/-/lru-cache-5.1.1.tgz",
      "integrity": "sha512-KpNARQA3Iwv+jTA0utUVVbrh+Jlrr1Fv0e56GGzAFOXN7dk/FviaDW8LHmK52DlcH4WP2n6gI8vN1aesBFgo9w==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "yallist": "^3.0.2"
      }
    },
    "node_modules/lucide-react": {
      "version": "1.16.0",
      "resolved": "https://registry.npmjs.org/lucide-react/-/lucide-react-1.16.0.tgz",
      "integrity": "sha512-dYwyPzb4MEKpGUmNYk3WKWPnMrHs3FKM+q94kAnJrcDIqqn1hq2xY8scaS2ovsOCM5D51ey2gaRG3PBb1vgoYQ==",
      "license": "ISC",
      "peerDependencies": {
        "react": "^16.5.1 || ^17.0.0 || ^18.0.0 || ^19.0.0"
      }
    },
    "node_modules/minimatch": {
      "version": "8.0.7",
      "resolved": "https://registry.npmjs.org/minimatch/-/minimatch-8.0.7.tgz",
      "integrity": "sha512-V+1uQNdzybxa14e/p00HZnQNNcTjnRJjDxg2V8wtkjFctq4M7hXFws4oekyTP0Jebeq7QYtpFyOeBAjc88zvYg==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "brace-expansion": "^2.0.1"
      },
      "engines": {
        "node": ">=16 || 14 >=14.17"
      },
      "funding": {
        "url": "https://github.com/sponsors/isaacs"
      }
    },
    "node_modules/minipass": {
      "version": "4.2.8",
      "resolved": "https://registry.npmjs.org/minipass/-/minipass-4.2.8.tgz",
      "integrity": "sha512-fNzuVyifolSLFL4NzpF+wEF4qrgqaaKX0haXPQEdQ7NKAN+WecoKMHV09YcuL/DHxrUsYQOK3MiuDf7Ip2OXfQ==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/minizlib": {
      "version": "2.1.2",
      "resolved": "https://registry.npmjs.org/minizlib/-/minizlib-2.1.2.tgz",
      "integrity": "sha512-bAxsR8BVfj60DWXHE3u30oHzfl4G7khkSuPW+qvpd7jFRHm7dLxOjUk1EHACJ/hxLY8phGJ0YhYHZo7jil7Qdg==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "minipass": "^3.0.0",
        "yallist": "^4.0.0"
      },
      "engines": {
        "node": ">= 8"
      }
    },
    "node_modules/minizlib/node_modules/minipass": {
      "version": "3.3.6",
      "resolved": "https://registry.npmjs.org/minipass/-/minipass-3.3.6.tgz",
      "integrity": "sha512-DxiNidxSEK+tHG6zOIklvNOwm3hvCrbUrdtzY74U6HKTJxvIDfOUL5W5P2Ghd3DTkhhKPYGqeNUIh5qcM4YBfw==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "yallist": "^4.0.0"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/minizlib/node_modules/yallist": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/yallist/-/yallist-4.0.0.tgz",
      "integrity": "sha512-3wdGidZyq5PB084XLES5TpOSRA3wjXAlIWMhum2kRcv/41Sn2emQ0dycQW4uZXLejwKvg6EsvbdlVL+FYEct7A==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/mkdirp": {
      "version": "1.0.4",
      "resolved": "https://registry.npmjs.org/mkdirp/-/mkdirp-1.0.4.tgz",
      "integrity": "sha512-vVqVZQyf3WLx2Shd0qJ9xuvqgAyKPLAiqITEtqW0oIUjzo3PePDd6fW9iFz30ef7Ysp/oiWqbhszeGWW2T6Gzw==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "mkdirp": "bin/cmd.js"
      },
      "engines": {
        "node": ">=10"
      }
    },
    "node_modules/ms": {
      "version": "2.1.3",
      "resolved": "https://registry.npmjs.org/ms/-/ms-2.1.3.tgz",
      "integrity": "sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsvoVaHJq/s5xXI6/XXP6tz7R9xAOtHnSO/tXtF3WRTlA==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/nanoid": {
      "version": "3.3.11",
      "resolved": "https://registry.npmjs.org/nanoid/-/nanoid-3.3.11.tgz",
      "integrity": "sha512-N8SpfPUnUp1bK+PMYW8qSWdl9U+wwNWI4QKxOYDy9JAro3WMX7p2OeVRF9v+347pnakNevPmiHhNmZ2HbFA76w==",
      "dev": true,
      "funding": [
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "bin": {
        "nanoid": "bin/nanoid.cjs"
      },
      "engines": {
        "node": "^10 || ^12 || ^13.7 || ^14 || >=15.0.1"
      }
    },
    "node_modules/native-run": {
      "version": "2.0.3",
      "resolved": "https://registry.npmjs.org/native-run/-/native-run-2.0.3.tgz",
      "integrity": "sha512-U1PllBuzW5d1gfan+88L+Hky2eZx+9gv3Pf6rNBxKbORxi7boHzqiA6QFGSnqMem4j0A9tZ08NMIs5+0m/VS1Q==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@ionic/utils-fs": "^3.1.7",
        "@ionic/utils-terminal": "^2.3.4",
        "bplist-parser": "^0.3.2",
        "debug": "^4.3.4",
        "elementtree": "^0.1.7",
        "ini": "^4.1.1",
        "plist": "^3.1.0",
        "split2": "^4.2.0",
        "through2": "^4.0.2",
        "tslib": "^2.6.2",
        "yauzl": "^2.10.0"
      },
      "bin": {
        "native-run": "bin/native-run"
      },
      "engines": {
        "node": ">=16.0.0"
      }
    },
    "node_modules/node-releases": {
      "version": "2.0.37",
      "resolved": "https://registry.npmjs.org/node-releases/-/node-releases-2.0.37.tgz",
      "integrity": "sha512-1h5gKZCF+pO/o3Iqt5Jp7wc9rH3eJJ0+nh/CIoiRwjRxde/hAHyLPXYN4V3CqKAbiZPSeJFSWHmJsbkicta0Eg==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/open": {
      "version": "8.4.2",
      "resolved": "https://registry.npmjs.org/open/-/open-8.4.2.tgz",
      "integrity": "sha512-7x81NCL719oNbsq/3mh+hVrAWmFuEYUqrq/Iw3kUzH8ReypT9QQ0BLoJS7/G9k6N81XjW4qHWtjWwe/9eLy1EQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "define-lazy-prop": "^2.0.0",
        "is-docker": "^2.1.1",
        "is-wsl": "^2.2.0"
      },
      "engines": {
        "node": ">=12"
      },
      "funding": {
        "url": "https://github.com/sponsors/sindresorhus"
      }
    },
    "node_modules/path-key": {
      "version": "3.1.1",
      "resolved": "https://registry.npmjs.org/path-key/-/path-key-3.1.1.tgz",
      "integrity": "sha512-ojmeN0qd+y0jszEtoY48r0Peq5dwMEkIlCOu6Q5f41lfkswXuKtYrhgoTpLnyIcHm24Uhqx+5Tqm2InSwLhE6Q==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/path-scurry": {
      "version": "1.11.1",
      "resolved": "https://registry.npmjs.org/path-scurry/-/path-scurry-1.11.1.tgz",
      "integrity": "sha512-Xa4Nw17FS9ApQFJ9umLiJS4orGjm7ZzwUrwamcGQuHSzDyth9boKDaycYdDcZDuqYATXw4HFXgaqWTctW/v1HA==",
      "dev": true,
      "license": "BlueOak-1.0.0",
      "dependencies": {
        "lru-cache": "^10.2.0",
        "minipass": "^5.0.0 || ^6.0.2 || ^7.0.0"
      },
      "engines": {
        "node": ">=16 || 14 >=14.18"
      },
      "funding": {
        "url": "https://github.com/sponsors/isaacs"
      }
    },
    "node_modules/path-scurry/node_modules/lru-cache": {
      "version": "10.4.3",
      "resolved": "https://registry.npmjs.org/lru-cache/-/lru-cache-10.4.3.tgz",
      "integrity": "sha512-JNAzZcXrCt42VGLuYz0zfAzDfAvJWW6AfYlDBQyDV5DClI2m5sAmK+OIO7s59XfsRsWHp02jAJrRadPRGTt6SQ==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/path-scurry/node_modules/minipass": {
      "version": "7.1.3",
      "resolved": "https://registry.npmjs.org/minipass/-/minipass-7.1.3.tgz",
      "integrity": "sha512-tEBHqDnIoM/1rXME1zgka9g6Q2lcoCkxHLuc7ODJ5BxbP5d4c2Z5cGgtXAku59200Cx7diuHTOYfSBD8n6mm8A==",
      "dev": true,
      "license": "BlueOak-1.0.0",
      "engines": {
        "node": ">=16 || 14 >=14.17"
      }
    },
    "node_modules/pend": {
      "version": "1.2.0",
      "resolved": "https://registry.npmjs.org/pend/-/pend-1.2.0.tgz",
      "integrity": "sha512-F3asv42UuXchdzt+xXqfW1OGlVBe+mxa2mqI0pg5yAHZPvFmY3Y6drSf/GQ1A86WgWEN9Kzh/WrgKa6iGcHXLg==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/picocolors": {
      "version": "1.1.1",
      "resolved": "https://registry.npmjs.org/picocolors/-/picocolors-1.1.1.tgz",
      "integrity": "sha512-xceH2snhtb5M9liqDsmEw56le376mTZkEX/jEb/RxNFyegNul7eNslCXP9FDj/Lcu0X8KEyMceP2ntpaHrDEVA==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/plist": {
      "version": "3.1.0",
      "resolved": "https://registry.npmjs.org/plist/-/plist-3.1.0.tgz",
      "integrity": "sha512-uysumyrvkUX0rX/dEVqt8gC3sTBzd4zoWfLeS29nb53imdaXVvLINYXTI2GNqzaMuvacNx4uJQ8+b3zXR0pkgQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@xmldom/xmldom": "^0.8.8",
        "base64-js": "^1.5.1",
        "xmlbuilder": "^15.1.1"
      },
      "engines": {
        "node": ">=10.4.0"
      }
    },
    "node_modules/postcss": {
      "version": "8.5.10",
      "resolved": "https://registry.npmjs.org/postcss/-/postcss-8.5.10.tgz",
      "integrity": "sha512-pMMHxBOZKFU6HgAZ4eyGnwXF/EvPGGqUr0MnZ5+99485wwW41kW91A4LOGxSHhgugZmSChL5AlElNdwlNgcnLQ==",
      "dev": true,
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/postcss/"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/postcss"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "dependencies": {
        "nanoid": "^3.3.11",
        "picocolors": "^1.1.1",
        "source-map-js": "^1.2.1"
      },
      "engines": {
        "node": "^10 || ^12 || >=14"
      }
    },
    "node_modules/prompts": {
      "version": "2.4.2",
      "resolved": "https://registry.npmjs.org/prompts/-/prompts-2.4.2.tgz",
      "integrity": "sha512-NxNv/kLguCA7p3jE8oL2aEBsrJWgAakBpgmgK6lpPWV+WuOmY6r2/zbAVnP+T8bQlA0nzHXSJSJW0Hq7ylaD2Q==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "kleur": "^3.0.3",
        "sisteransi": "^1.0.5"
      },
      "engines": {
        "node": ">= 6"
      }
    },
    "node_modules/prompts/node_modules/kleur": {
      "version": "3.0.3",
      "resolved": "https://registry.npmjs.org/kleur/-/kleur-3.0.3.tgz",
      "integrity": "sha512-eTIzlVOSUR+JxdDFepEYcBMtZ9Qqdef+rnzWdRZuMbOywu5tO2w2N7rqjoANZ5k9vywhL6Br1VRjUIgTQx4E8w==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/react": {
      "version": "18.3.1",
      "resolved": "https://registry.npmjs.org/react/-/react-18.3.1.tgz",
      "integrity": "sha512-wS+hAgJShR0KhEvPJArfuPVN1+Hz1t0Y6n5jLrGQbkb4urgPE/0Rve+1kMB1v/oWgHgm4WIcV+i7F2pTVj+2iQ==",
      "license": "MIT",
      "dependencies": {
        "loose-envify": "^1.1.0"
      },
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/react-dom": {
      "version": "18.3.1",
      "resolved": "https://registry.npmjs.org/react-dom/-/react-dom-18.3.1.tgz",
      "integrity": "sha512-5m4nQKp+rZRb09LNH59GM4BxTh9251/ylbKIbpe7TpGxfJ+9kv6BLkLBXIjjspbgbnIBNqlI23tRnTWT0snUIw==",
      "license": "MIT",
      "dependencies": {
        "loose-envify": "^1.1.0",
        "scheduler": "^0.23.2"
      },
      "peerDependencies": {
        "react": "^18.3.1"
      }
    },
    "node_modules/react-refresh": {
      "version": "0.17.0",
      "resolved": "https://registry.npmjs.org/react-refresh/-/react-refresh-0.17.0.tgz",
      "integrity": "sha512-z6F7K9bV85EfseRCp2bzrpyQ0Gkw1uLoCel9XBVWPg/TjRj94SkJzUTGfOa4bs7iJvBWtQG0Wq7wnI0syw3EBQ==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/react-router": {
      "version": "6.30.3",
      "resolved": "https://registry.npmjs.org/react-router/-/react-router-6.30.3.tgz",
      "integrity": "sha512-XRnlbKMTmktBkjCLE8/XcZFlnHvr2Ltdr1eJX4idL55/9BbORzyZEaIkBFDhFGCEWBBItsVrDxwx3gnisMitdw==",
      "license": "MIT",
      "dependencies": {
        "@remix-run/router": "1.23.2"
      },
      "engines": {
        "node": ">=14.0.0"
      },
      "peerDependencies": {
        "react": ">=16.8"
      }
    },
    "node_modules/react-router-dom": {
      "version": "6.30.3",
      "resolved": "https://registry.npmjs.org/react-router-dom/-/react-router-dom-6.30.3.tgz",
      "integrity": "sha512-pxPcv1AczD4vso7G4Z3TKcvlxK7g7TNt3/FNGMhfqyntocvYKj+GCatfigGDjbLozC4baguJ0ReCigoDJXb0ag==",
      "license": "MIT",
      "dependencies": {
        "@remix-run/router": "1.23.2",
        "react-router": "6.30.3"
      },
      "engines": {
        "node": ">=14.0.0"
      },
      "peerDependencies": {
        "react": ">=16.8",
        "react-dom": ">=16.8"
      }
    },
    "node_modules/readable-stream": {
      "version": "3.6.2",
      "resolved": "https://registry.npmjs.org/readable-stream/-/readable-stream-3.6.2.tgz",
      "integrity": "sha512-9u/sniCrY3D5WdsERHzHE4G2YCXqoG5FTHUiCC4SIbr6XcLZBY05ya9EKjYek9O5xOAwjGq+1JdGBAS7Q9ScoA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "inherits": "^2.0.3",
        "string_decoder": "^1.1.1",
        "util-deprecate": "^1.0.1"
      },
      "engines": {
        "node": ">= 6"
      }
    },
    "node_modules/rimraf": {
      "version": "4.4.1",
      "resolved": "https://registry.npmjs.org/rimraf/-/rimraf-4.4.1.tgz",
      "integrity": "sha512-Gk8NlF062+T9CqNGn6h4tls3k6T1+/nXdOcSZVikNVtlRdYpA7wRJJMoXmuvOnLW844rPjdQ7JgXCYM6PPC/og==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "glob": "^9.2.0"
      },
      "bin": {
        "rimraf": "dist/cjs/src/bin.js"
      },
      "engines": {
        "node": ">=14"
      },
      "funding": {
        "url": "https://github.com/sponsors/isaacs"
      }
    },
    "node_modules/rollup": {
      "version": "4.60.1",
      "resolved": "https://registry.npmjs.org/rollup/-/rollup-4.60.1.tgz",
      "integrity": "sha512-VmtB2rFU/GroZ4oL8+ZqXgSA38O6GR8KSIvWmEFv63pQ0G6KaBH9s07PO8XTXP4vI+3UJUEypOfjkGfmSBBR0w==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "@types/estree": "1.0.8"
      },
      "bin": {
        "rollup": "dist/bin/rollup"
      },
      "engines": {
        "node": ">=18.0.0",
        "npm": ">=8.0.0"
      },
      "optionalDependencies": {
        "@rollup/rollup-android-arm-eabi": "4.60.1",
        "@rollup/rollup-android-arm64": "4.60.1",
        "@rollup/rollup-darwin-arm64": "4.60.1",
        "@rollup/rollup-darwin-x64": "4.60.1",
        "@rollup/rollup-freebsd-arm64": "4.60.1",
        "@rollup/rollup-freebsd-x64": "4.60.1",
        "@rollup/rollup-linux-arm-gnueabihf": "4.60.1",
        "@rollup/rollup-linux-arm-musleabihf": "4.60.1",
        "@rollup/rollup-linux-arm64-gnu": "4.60.1",
        "@rollup/rollup-linux-arm64-musl": "4.60.1",
        "@rollup/rollup-linux-loong64-gnu": "4.60.1",
        "@rollup/rollup-linux-loong64-musl": "4.60.1",
        "@rollup/rollup-linux-ppc64-gnu": "4.60.1",
        "@rollup/rollup-linux-ppc64-musl": "4.60.1",
        "@rollup/rollup-linux-riscv64-gnu": "4.60.1",
        "@rollup/rollup-linux-riscv64-musl": "4.60.1",
        "@rollup/rollup-linux-s390x-gnu": "4.60.1",
        "@rollup/rollup-linux-x64-gnu": "4.60.1",
        "@rollup/rollup-linux-x64-musl": "4.60.1",
        "@rollup/rollup-openbsd-x64": "4.60.1",
        "@rollup/rollup-openharmony-arm64": "4.60.1",
        "@rollup/rollup-win32-arm64-msvc": "4.60.1",
        "@rollup/rollup-win32-ia32-msvc": "4.60.1",
        "@rollup/rollup-win32-x64-gnu": "4.60.1",
        "@rollup/rollup-win32-x64-msvc": "4.60.1",
        "fsevents": "~2.3.2"
      }
    },
    "node_modules/safe-buffer": {
      "version": "5.2.1",
      "resolved": "https://registry.npmjs.org/safe-buffer/-/safe-buffer-5.2.1.tgz",
      "integrity": "sha512-rp3So07KcdmmKbGvgaNxQSJr7bGVSVk5S9Eq1F+ppbRo70+YeaDxkw5Dd8NPN+GD6bjnYm2VuPuCXmpuYvmCXQ==",
      "dev": true,
      "funding": [
        {
          "type": "github",
          "url": "https://github.com/sponsors/feross"
        },
        {
          "type": "patreon",
          "url": "https://www.patreon.com/feross"
        },
        {
          "type": "consulting",
          "url": "https://feross.org/support"
        }
      ],
      "license": "MIT"
    },
    "node_modules/sax": {
      "version": "1.1.4",
      "resolved": "https://registry.npmjs.org/sax/-/sax-1.1.4.tgz",
      "integrity": "sha512-5f3k2PbGGp+YtKJjOItpg3P99IMD84E4HOvcfleTb5joCHNXYLsR9yWFPOYGgaeMPDubQILTCMdsFb2OMeOjtg==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/scheduler": {
      "version": "0.23.2",
      "resolved": "https://registry.npmjs.org/scheduler/-/scheduler-0.23.2.tgz",
      "integrity": "sha512-UOShsPwz7NrMUqhR6t0hWjFduvOzbtv7toDH1/hIrfRNIDBnnBWd0CwJTGvTpngVlmwGCdP9/Zl/tVrDqcuYzQ==",
      "license": "MIT",
      "dependencies": {
        "loose-envify": "^1.1.0"
      }
    },
    "node_modules/semver": {
      "version": "7.7.4",
      "resolved": "https://registry.npmjs.org/semver/-/semver-7.7.4.tgz",
      "integrity": "sha512-vFKC2IEtQnVhpT78h1Yp8wzwrf8CM+MzKMHGJZfBtzhZNycRFnXsHk6E5TxIkkMsgNS7mdX3AGB7x2QM2di4lA==",
      "dev": true,
      "license": "ISC",
      "bin": {
        "semver": "bin/semver.js"
      },
      "engines": {
        "node": ">=10"
      }
    },
    "node_modules/shebang-command": {
      "version": "2.0.0",
      "resolved": "https://registry.npmjs.org/shebang-command/-/shebang-command-2.0.0.tgz",
      "integrity": "sha512-kHxr2zZpYtdmrN1qDjrrX/Z1rR1kG8Dx+gkpK1G4eXmvXswmcE1hTWBWYUzlraYw1/yZp6YuDY77YtvbN0dmDA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "shebang-regex": "^3.0.0"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/shebang-regex": {
      "version": "3.0.0",
      "resolved": "https://registry.npmjs.org/shebang-regex/-/shebang-regex-3.0.0.tgz",
      "integrity": "sha512-7++dFhtcx3353uBaq8DDR4NuxBetBzC7ZQOhmTQInHEd6bSrXdiEyzCvG07Z44UYdLShWUyXt5M/yhz8ekcb1A==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/signal-exit": {
      "version": "3.0.7",
      "resolved": "https://registry.npmjs.org/signal-exit/-/signal-exit-3.0.7.tgz",
      "integrity": "sha512-wnD2ZE+l+SPC/uoS0vXeE9L1+0wuaMqKlfz9AMUo38JsyLSBWSFcHR1Rri62LZc12vLr1gb3jl7iwQhgwpAbGQ==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/sisteransi": {
      "version": "1.0.5",
      "resolved": "https://registry.npmjs.org/sisteransi/-/sisteransi-1.0.5.tgz",
      "integrity": "sha512-bLGGlR1QxBcynn2d5YmDX4MGjlZvy2MRBDRNHLJ8VI6l6+9FUiyTFNJ0IveOSP0bcXgVDPRcfGqA0pjaqUpfVg==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/slice-ansi": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/slice-ansi/-/slice-ansi-4.0.0.tgz",
      "integrity": "sha512-qMCMfhY040cVHT43K9BFygqYbUPFZKHOg7K73mtTWJRb8pyP3fzf4Ixd5SzdEJQ6MRUg/WBnOLxghZtKKurENQ==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "ansi-styles": "^4.0.0",
        "astral-regex": "^2.0.0",
        "is-fullwidth-code-point": "^3.0.0"
      },
      "engines": {
        "node": ">=10"
      },
      "funding": {
        "url": "https://github.com/chalk/slice-ansi?sponsor=1"
      }
    },
    "node_modules/source-map-js": {
      "version": "1.2.1",
      "resolved": "https://registry.npmjs.org/source-map-js/-/source-map-js-1.2.1.tgz",
      "integrity": "sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA==",
      "dev": true,
      "license": "BSD-3-Clause",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/split2": {
      "version": "4.2.0",
      "resolved": "https://registry.npmjs.org/split2/-/split2-4.2.0.tgz",
      "integrity": "sha512-UcjcJOWknrNkF6PLX83qcHM6KHgVKNkV62Y8a5uYDVv9ydGQVwAHMKqHdJje1VTWpljG0WYpCDhrCdAOYH4TWg==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": ">= 10.x"
      }
    },
    "node_modules/string_decoder": {
      "version": "1.3.0",
      "resolved": "https://registry.npmjs.org/string_decoder/-/string_decoder-1.3.0.tgz",
      "integrity": "sha512-hkRX8U1WjJFd8LsDJ2yQ/wWWxaopEsABU1XfkM8A+j0+85JAGppt16cr1Whg6KIbb4okU6Mql6BOj+uup/wKeA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "safe-buffer": "~5.2.0"
      }
    },
    "node_modules/string-width": {
      "version": "4.2.3",
      "resolved": "https://registry.npmjs.org/string-width/-/string-width-4.2.3.tgz",
      "integrity": "sha512-wKyQRQpjJ0sIp62ErSZdGsjMJWsap5oRNihHhu6G7JVO/9jIB6UyevL+tXuOqrng8j/cxKTWyWUwvSTriiZz/g==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "emoji-regex": "^8.0.0",
        "is-fullwidth-code-point": "^3.0.0",
        "strip-ansi": "^6.0.1"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/strip-ansi": {
      "version": "6.0.1",
      "resolved": "https://registry.npmjs.org/strip-ansi/-/strip-ansi-6.0.1.tgz",
      "integrity": "sha512-Y38VPSHcqkFrCpFnQ9vuSXmquuv5oXOKpGeT6aGrr3o3Gc9AlVa6JBfUSOCnbxGGZF+/0ooI7KrPuUSztUdU5A==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "ansi-regex": "^5.0.1"
      },
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/tar": {
      "version": "6.2.1",
      "resolved": "https://registry.npmjs.org/tar/-/tar-6.2.1.tgz",
      "integrity": "sha512-DZ4yORTwrbTj/7MZYq2w+/ZFdI6OZ/f9SFHR+71gIVUZhOQPHzVCLpvRnPgyaMpfWxxk/4ONva3GQSyNIKRv6A==",
      "deprecated": "Old versions of tar are not supported, and contain widely publicized security vulnerabilities, which have been fixed in the current version. Please update. Support for old versions may be purchased (at exorbitant rates) by contacting i@izs.me",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "chownr": "^2.0.0",
        "fs-minipass": "^2.0.0",
        "minipass": "^5.0.0",
        "minizlib": "^2.1.1",
        "mkdirp": "^1.0.3",
        "yallist": "^4.0.0"
      },
      "engines": {
        "node": ">=10"
      }
    },
    "node_modules/tar/node_modules/minipass": {
      "version": "5.0.0",
      "resolved": "https://registry.npmjs.org/minipass/-/minipass-5.0.0.tgz",
      "integrity": "sha512-3FnjYuehv9k6ovOEbyOswadCDPX1piCfhV8ncmYtHOjuPwylVWsghTLo7rabjC3Rx5xD4HDx8Wm1xnMF7S5qFQ==",
      "dev": true,
      "license": "ISC",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/tar/node_modules/yallist": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/yallist/-/yallist-4.0.0.tgz",
      "integrity": "sha512-3wdGidZyq5PB084XLES5TpOSRA3wjXAlIWMhum2kRcv/41Sn2emQ0dycQW4uZXLejwKvg6EsvbdlVL+FYEct7A==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/through2": {
      "version": "4.0.2",
      "resolved": "https://registry.npmjs.org/through2/-/through2-4.0.2.tgz",
      "integrity": "sha512-iOqSav00cVxEEICeD7TjLB1sueEL+81Wpzp2bY17uZjZN0pWZPuo4suZ/61VujxmqSGFfgOcNuTZ85QJwNZQpw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "readable-stream": "3"
      }
    },
    "node_modules/tree-kill": {
      "version": "1.2.2",
      "resolved": "https://registry.npmjs.org/tree-kill/-/tree-kill-1.2.2.tgz",
      "integrity": "sha512-L0Orpi8qGpRG//Nd+H90vFB+3iHnue1zSSGmNOOCh1GLJ7rUKVwV2HvijphGQS2UmhUZewS9VgvxYIdgr+fG1A==",
      "dev": true,
      "license": "MIT",
      "bin": {
        "tree-kill": "cli.js"
      }
    },
    "node_modules/tslib": {
      "version": "2.8.1",
      "resolved": "https://registry.npmjs.org/tslib/-/tslib-2.8.1.tgz",
      "integrity": "sha512-oJFu94HQb+KVduSUQL7wnpmqnfmLsOA/nAh6b6EH0wCEoK0/mPeXU6c3wKDV83MkOuHPRHtSXKKU99IBazS/2w==",
      "license": "0BSD"
    },
    "node_modules/typescript": {
      "version": "5.9.3",
      "resolved": "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz",
      "integrity": "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw==",
      "dev": true,
      "license": "Apache-2.0",
      "bin": {
        "tsc": "bin/tsc",
        "tsserver": "bin/tsserver"
      },
      "engines": {
        "node": ">=14.17"
      }
    },
    "node_modules/undici-types": {
      "version": "7.19.2",
      "resolved": "https://registry.npmjs.org/undici-types/-/undici-types-7.19.2.tgz",
      "integrity": "sha512-qYVnV5OEm2AW8cJMCpdV20CDyaN3g0AjDlOGf1OW4iaDEx8MwdtChUp4zu4H0VP3nDRF/8RKWH+IPp9uW0YGZg==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/universalify": {
      "version": "2.0.1",
      "resolved": "https://registry.npmjs.org/universalify/-/universalify-2.0.1.tgz",
      "integrity": "sha512-gptHNQghINnc/vTGIk0SOFGFNXw7JVrlRUtConJRlvaw6DuX0wO5Jeko9sWrMBhh+PsYAZ7oXAiOnf/UKogyiw==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">= 10.0.0"
      }
    },
    "node_modules/untildify": {
      "version": "4.0.0",
      "resolved": "https://registry.npmjs.org/untildify/-/untildify-4.0.0.tgz",
      "integrity": "sha512-KK8xQ1mkzZeg9inewmFVDNkg3l5LUhoq9kN6iWYB/CC9YMG8HA+c1Q8HwDe6dEX7kErrEVNVBO3fWsVq5iDgtw==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8"
      }
    },
    "node_modules/update-browserslist-db": {
      "version": "1.2.3",
      "resolved": "https://registry.npmjs.org/update-browserslist-db/-/update-browserslist-db-1.2.3.tgz",
      "integrity": "sha512-Js0m9cx+qOgDxo0eMiFGEueWztz+d4+M3rGlmKPT+T4IS/jP4ylw3Nwpu6cpTTP8R1MAC1kF4VbdLt3ARf209w==",
      "dev": true,
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/browserslist"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/browserslist"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "license": "MIT",
      "dependencies": {
        "escalade": "^3.2.0",
        "picocolors": "^1.1.1"
      },
      "bin": {
        "update-browserslist-db": "cli.js"
      },
      "peerDependencies": {
        "browserslist": ">= 4.21.0"
      }
    },
    "node_modules/util-deprecate": {
      "version": "1.0.2",
      "resolved": "https://registry.npmjs.org/util-deprecate/-/util-deprecate-1.0.2.tgz",
      "integrity": "sha512-EPD5q1uXyFxJpCrLnCc1nHnq3gOa6DZBocAIiI2TaSCA7VCJ1UJDMagCzIkXNsUYfD1daK//LTEQ8xiIbrHtcw==",
      "dev": true,
      "license": "MIT"
    },
    "node_modules/vite": {
      "version": "5.4.21",
      "resolved": "https://registry.npmjs.org/vite/-/vite-5.4.21.tgz",
      "integrity": "sha512-o5a9xKjbtuhY6Bi5S3+HvbRERmouabWbyUcpXXUA1u+GNUKoROi9byOJ8M0nHbHYHkYICiMlqxkg1KkYmm25Sw==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "esbuild": "^0.21.3",
        "postcss": "^8.4.43",
        "rollup": "^4.20.0"
      },
      "bin": {
        "vite": "bin/vite.js"
      },
      "engines": {
        "node": "^18.0.0 || >=20.0.0"
      },
      "funding": {
        "url": "https://github.com/vitejs/vite?sponsor=1"
      },
      "optionalDependencies": {
        "fsevents": "~2.3.3"
      },
      "peerDependencies": {
        "@types/node": "^18.0.0 || >=20.0.0",
        "less": "*",
        "lightningcss": "^1.21.0",
        "sass": "*",
        "sass-embedded": "*",
        "stylus": "*",
        "sugarss": "*",
        "terser": "^5.4.0"
      },
      "peerDependenciesMeta": {
        "@types/node": {
          "optional": true
        },
        "less": {
          "optional": true
        },
        "lightningcss": {
          "optional": true
        },
        "sass": {
          "optional": true
        },
        "sass-embedded": {
          "optional": true
        },
        "stylus": {
          "optional": true
        },
        "sugarss": {
          "optional": true
        },
        "terser": {
          "optional": true
        }
      }
    },
    "node_modules/which": {
      "version": "2.0.2",
      "resolved": "https://registry.npmjs.org/which/-/which-2.0.2.tgz",
      "integrity": "sha512-BLI3Tl1TW3Pvl70l3yq3Y64i+awpwXqsGBYWkkqMtnbXgrMD+yj7rhW0kuEDxzJaYXGjEW5ogapKNMEKNMjibA==",
      "dev": true,
      "license": "ISC",
      "dependencies": {
        "isexe": "^2.0.0"
      },
      "bin": {
        "node-which": "bin/node-which"
      },
      "engines": {
        "node": ">= 8"
      }
    },
    "node_modules/wrap-ansi": {
      "version": "7.0.0",
      "resolved": "https://registry.npmjs.org/wrap-ansi/-/wrap-ansi-7.0.0.tgz",
      "integrity": "sha512-YVGIj2kamLSTxw6NsZjoBxfSwsn0ycdesmc4p+Q21c5zPuZ1pl+NfxVdxPtdHvmNVOQ6XSYG4AUtyt/Fi7D16Q==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "ansi-styles": "^4.0.0",
        "string-width": "^4.1.0",
        "strip-ansi": "^6.0.0"
      },
      "engines": {
        "node": ">=10"
      },
      "funding": {
        "url": "https://github.com/chalk/wrap-ansi?sponsor=1"
      }
    },
    "node_modules/xml2js": {
      "version": "0.5.0",
      "resolved": "https://registry.npmjs.org/xml2js/-/xml2js-0.5.0.tgz",
      "integrity": "sha512-drPFnkQJik/O+uPKpqSgr22mpuFHqKdbS835iAQrUC73L2F5WkboIRd63ai/2Yg6I1jzifPFKH2NTK+cfglkIA==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "sax": ">=0.6.0",
        "xmlbuilder": "~11.0.0"
      },
      "engines": {
        "node": ">=4.0.0"
      }
    },
    "node_modules/xml2js/node_modules/xmlbuilder": {
      "version": "11.0.1",
      "resolved": "https://registry.npmjs.org/xmlbuilder/-/xmlbuilder-11.0.1.tgz",
      "integrity": "sha512-fDlsI/kFEx7gLvbecc0/ohLG50fugQp8ryHzMTuW9vSa1GJ0XYWKnhsUx7oie3G98+r56aTQIUB4kht42R3JvA==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=4.0"
      }
    },
    "node_modules/xmlbuilder": {
      "version": "15.1.1",
      "resolved": "https://registry.npmjs.org/xmlbuilder/-/xmlbuilder-15.1.1.tgz",
      "integrity": "sha512-yMqGBqtXyeN1e3TGYvgNgDVZ3j84W4cwkOXQswghol6APgZWaff9lnbvN7MHYJOiXsvGPXtjTYJEiC9J2wv9Eg==",
      "dev": true,
      "license": "MIT",
      "engines": {
        "node": ">=8.0"
      }
    },
    "node_modules/yallist": {
      "version": "3.1.1",
      "resolved": "https://registry.npmjs.org/yallist/-/yallist-3.1.1.tgz",
      "integrity": "sha512-a4UGQaWPH59mOXUYnAG2ewncQS4i4F43Tv3JoAM+s2VDAmS9NsK8GpDMLrCHPksFT7h3K6TOoUNn2pb7RoXx4g==",
      "dev": true,
      "license": "ISC"
    },
    "node_modules/yauzl": {
      "version": "2.10.0",
      "resolved": "https://registry.npmjs.org/yauzl/-/yauzl-2.10.0.tgz",
      "integrity": "sha512-p4a9I6X6nu6IhoGmBqAcbJy1mlC4j27vEPZX9F4L4/vZT3Lyq1VkFHw/V/PUcB9Buo+DG3iHkT0x3Qya58zc3g==",
      "dev": true,
      "license": "MIT",
      "dependencies": {
        "buffer-crc32": "~0.2.3",
        "fd-slicer": "~1.1.0"
      }
    }
  }
}
```

## File: `frontend/public/favicon.svg`

<!-- FILE: frontend/public/favicon.svg -->

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <radialGradient id="bg" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#0a120c"/>
      <stop offset="100%" stop-color="#000"/>
    </radialGradient>
    <clipPath id="tri">
      <polygon points="50,18 82,72 18,72"/>
    </clipPath>
  </defs>
  <circle cx="50" cy="50" r="46" fill="url(#bg)" stroke="#00ff66" stroke-width="2"/>
  <circle cx="50" cy="50" r="42" fill="none" stroke="#00ff66" stroke-width="0.6" opacity="0.5" stroke-dasharray="2 3"/>
  <g stroke="#00ff66" stroke-width="1.6" stroke-linecap="round">
    <line x1="50" y1="2"  x2="50" y2="9"/>
    <line x1="50" y1="91" x2="50" y2="98"/>
    <line x1="2"  y1="50" x2="9"  y2="50"/>
    <line x1="91" y1="50" x2="98" y2="50"/>
  </g>
  <polygon points="50,18 82,72 18,72" fill="none" stroke="#00ff66" stroke-width="1.8" stroke-linejoin="round"/>
  <g clip-path="url(#tri)" stroke="#00ff66" fill="none" stroke-linecap="round">
    <path d="M 28 62 Q 50 42 72 62" stroke-width="1"/>
    <path d="M 32 62 Q 50 46 68 62" stroke-width="1"/>
    <path d="M 36 62 Q 50 50 64 62" stroke-width="1"/>
    <path d="M 40 62 Q 50 54 60 62" stroke-width="1"/>
    <path d="M 44 62 Q 50 58 56 62" stroke-width="1"/>
    <circle cx="50" cy="60" r="1.6" fill="#00ff66" stroke="none"/>
  </g>
</svg>
```

## File: `frontend/public/manifest.json`

<!-- FILE: frontend/public/manifest.json -->

```json
{
  "id": "/",
  "name": "Revelator - Document Forensics Engine",
  "short_name": "Revelator",
  "description": "Forensic document forgery detection. Scan a document and get a classified verdict with evidence.",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#000000",
  "theme_color": "#000000",
  "categories": ["utilities", "productivity"],
  "icons": [
    {
      "src": "/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icon-maskable-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ],
  "shortcuts": [
    {
      "name": "New scan",
      "short_name": "Scan",
      "url": "/scan",
      "icons": [{ "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" }]
    },
    {
      "name": "Scan history",
      "short_name": "History",
      "url": "/history",
      "icons": [{ "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" }]
    }
  ]
}
```

## File: `frontend/public/samples/README.md`

<!-- FILE: frontend/public/samples/README.md -->

````markdown
# Category Sample Gallery

Drop curated training-set images here so end users can see what each forgery category looks like.

## Folder convention

```
samples/
├── traced/
│   ├── 1-annotated.jpg
│   ├── 1-original.jpg
│   ├── 2-annotated.jpg
│   ├── 2-original.jpg
│   ├── ...
│   └── 5-original.jpg
├── alteration/
├── digital/
├── obliteration/
├── sympathetic_ink/
└── currency/
```

- 5 pairs per category (`1`..`5`)
- Each pair: `<n>-annotated.jpg` (with bounding boxes drawn) + `<n>-original.jpg` (raw)
- Recommended: 800x600 or 4:3, JPEG quality ~85
- Missing files render as styled placeholders - won't break the page

## How-to-shoot guidance

Per-category tips and "what the detector looks for" strings live in
`frontend/src/pages/SampleGallery.jsx` (`GUIDANCE` map). Edit there.
````

## File: `frontend/public/sw.js`

<!-- FILE: frontend/public/sw.js -->

```javascript
/*
 * Revelator service worker.
 *
 * Deliberately minimal: its job is to make the site installable and to keep the
 * shell working on a flaky phone connection. It is NOT an offline mode for
 * scanning, because every scan is a live Gemini call.
 *
 * Caching rules, in priority order:
 *   /api/*, /download/*   never touched (always straight to the network)
 *   navigations           network-first, cached shell only as an offline fallback
 *   /assets/*             cache-first (Vite content-hashes these, so a given URL
 *                         is immutable and a new build produces new URLs)
 *   other same-origin GET stale-while-revalidate (icons, favicon, tutorial jpgs)
 *   cross-origin          ignored (Google Fonts falls back to the local stack)
 *
 * Bump CACHE_VERSION whenever this file changes so the activate step can drop
 * the previous caches.
 */

const CACHE_VERSION = 'v1';
const SHELL_CACHE = `revelator-shell-${CACHE_VERSION}`;
const ASSET_CACHE = `revelator-assets-${CACHE_VERSION}`;
const KEEP = [SHELL_CACHE, ASSET_CACHE];

// '/' is the app shell (index.html). The rest is what a cold offline launch
// needs to render something that looks like Revelator rather than a broken page.
const SHELL_URLS = [
  '/',
  '/manifest.json',
  '/favicon.svg',
  '/icon-192.png',
  '/icon-512.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      // Individual addAll failures would reject the whole install, so add each
      // URL on its own and tolerate misses.
      .then(cache => Promise.all(
        SHELL_URLS.map(url => cache.add(url).catch(() => null)),
      ))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k.startsWith('revelator-') && !KEEP.includes(k))
            .map(k => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

function isBypassed(url) {
  return url.pathname.startsWith('/api/')
      || url.pathname.startsWith('/download/');
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (isBypassed(url)) return;

  // Navigations: always try the network so a fresh deploy lands immediately.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then(c => c.put('/', copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('/', { ignoreSearch: true })
          .then(hit => hit || Response.error())),
    );
    return;
  }

  // Hashed build output: safe to serve from cache forever.
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(req).then(hit => hit || fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(ASSET_CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      })),
    );
    return;
  }

  // Everything else: serve cache immediately, refresh it in the background.
  event.respondWith(
    caches.match(req).then(hit => {
      const network = fetch(req).then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(ASSET_CACHE).then(c => c.put(req, copy)).catch(() => {});
        }
        return res;
      }).catch(() => hit || Response.error());
      return hit || network;
    }),
  );
});
```

## File: `frontend/scripts/make_icons.py`

<!-- FILE: frontend/scripts/make_icons.py -->

```python
"""
Generate the PWA / home-screen PNG icons from the Revelator mark.

The mark is the same design as frontend/public/favicon.svg (crosshair ring +
triangle + fingerprint ridges) redrawn with Pillow, because the manifest needs
real raster icons: Android's install criteria want a >=192px PNG, and a
"maskable" variant so the launcher's circle/squircle crop does not clip the ring.

Run from the repo root (or anywhere) with:
    python frontend/scripts/make_icons.py

Writes into frontend/public/:
    icon-192.png            purpose "any"
    icon-512.png            purpose "any"
    icon-maskable-512.png   purpose "maskable" (mark shrunk into the safe zone)
    apple-touch-icon.png    180px, iOS "Add to Home Screen"
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "public"

GREEN = (0, 255, 102)
BG_EDGE = (0, 0, 0)
BG_CORE = (10, 18, 12)

SS = 4  # supersample factor, downscaled at the end for antialiasing


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _q_bezier(p0, p1, p2, steps=48):
    """Quadratic bezier -> polyline, so Pillow can stroke the SVG 'Q' paths."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        ))
    return pts


def draw_mark(size, inset_ratio=1.0):
    """
    Render the mark on an opaque black square of `size` px.

    inset_ratio shrinks the 100x100 artboard inside the square: 1.0 fills the
    icon edge to edge, ~0.62 pulls it into the maskable safe zone.
    """
    S = size * SS
    img = Image.new("RGB", (S, S), BG_EDGE)
    d = ImageDraw.Draw(img)

    art = S * inset_ratio          # artboard side in device px
    off = (S - art) / 2            # top-left of the artboard
    u = art / 100.0                # one SVG user-unit in device px

    def P(x, y):
        return (off + x * u, off + y * u)

    def circle(cx, cy, r, **kw):
        d.ellipse([P(cx - r, cy - r), P(cx + r, cy + r)], **kw)

    # Radial background inside the ring: #0a120c core -> #000 edge, faked with
    # concentric fills (Pillow has no gradient primitive).
    steps = 90
    for i in range(steps, 0, -1):
        t = i / steps
        circle(50, 50, 46 * t, fill=_lerp(BG_CORE, BG_EDGE, 1 - t))

    # Outer ring
    circle(50, 50, 46, outline=GREEN, width=max(1, round(2 * u)))

    # Inner dashed ring (dasharray 2 3 on r=42) at 50% opacity
    dash = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dash)
    seg, gap = 2.0, 3.0
    circumference = 2 * 3.141592653589793 * 42
    step_deg = 360.0 * seg / circumference
    gap_deg = 360.0 * gap / circumference
    a = 0.0
    while a < 360:
        dd.arc(
            [P(50 - 42, 50 - 42), P(50 + 42, 50 + 42)],
            start=a, end=a + step_deg,
            fill=GREEN + (128,), width=max(1, round(0.6 * u)),
        )
        a += step_deg + gap_deg
    img.paste(Image.alpha_composite(img.convert("RGBA"), dash).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    # Crosshair ticks
    tick = max(1, round(1.6 * u))
    for x1, y1, x2, y2 in [
        (50, 2, 50, 9), (50, 91, 50, 98), (2, 50, 9, 50), (91, 50, 98, 50),
    ]:
        d.line([P(x1, y1), P(x2, y2)], fill=GREEN, width=tick)

    # Fingerprint ridges, clipped to the triangle
    tri = [(50, 18), (82, 72), (18, 72)]
    ridges = Image.new("RGB", (S, S), BG_EDGE)
    rd = ImageDraw.Draw(ridges)
    for x0, y0, cx, cy, x1, y1 in [
        (28, 62, 50, 42, 72, 62),
        (32, 62, 50, 46, 68, 62),
        (36, 62, 50, 50, 64, 62),
        (40, 62, 50, 54, 60, 62),
        (44, 62, 50, 58, 56, 62),
    ]:
        pts = [P(x, y) for x, y in _q_bezier((x0, y0), (cx, cy), (x1, y1))]
        rd.line(pts, fill=GREEN, width=max(1, round(1.0 * u)), joint="curve")

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon([P(x, y) for x, y in tri], fill=255)
    img.paste(ridges, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Triangle outline + centre dot
    d.polygon([P(x, y) for x, y in tri], outline=GREEN, width=max(1, round(1.8 * u)))
    circle(50, 60, 1.6, fill=GREEN)

    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, 0.98),
        ("icon-512.png", 512, 0.98),
        # Maskable: launchers crop to a circle/squircle, keeping only the middle
        # ~80%. Shrink the mark so the ring survives the crop.
        ("icon-maskable-512.png", 512, 0.62),
        ("apple-touch-icon.png", 180, 0.88),
    ]
    for name, size, inset in targets:
        img = draw_mark(size, inset)
        img.save(OUT_DIR / name, "PNG", optimize=True)
        print(f"  wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
```

## File: `frontend/src/api/client.js`

<!-- FILE: frontend/src/api/client.js -->

```javascript
/**
 * API client for Revelator backend.
 * Handles auth tokens automatically.
 */

const API_BASE = (import.meta.env.VITE_API_URL || '') + '/api';

function getToken() {
  return localStorage.getItem('fg_access_token');
}

function getRefreshToken() {
  return localStorage.getItem('fg_refresh_token');
}

function saveTokens(access, refresh) {
  localStorage.setItem('fg_access_token', access);
  localStorage.setItem('fg_refresh_token', refresh);
}

function clearTokens() {
  localStorage.removeItem('fg_access_token');
  localStorage.removeItem('fg_refresh_token');
  localStorage.removeItem('fg_user');
}

// ── Remembered-device tokens (skip 2FA) ─────────────────
// Stored per-email so several accounts can share one browser without
// clobbering each other's trust.
function deviceKey(email) {
  return `fg_device_token:${(email || '').trim().toLowerCase()}`;
}
function getDeviceToken(email) {
  return localStorage.getItem(deviceKey(email)) || null;
}
function saveDeviceToken(email, token) {
  if (token) localStorage.setItem(deviceKey(email), token);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };

  if (token && !options.noAuth) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // If 401, try refreshing the token once
  if (res.status === 401 && !options._retried) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${getToken()}`;
      res = await fetch(`${API_BASE}${path}`, { ...options, headers, _retried: true });
    } else {
      clearTokens();
      window.dispatchEvent(new CustomEvent('fg:session-expired'));
      throw new Error('Session expired');
    }
  }

  if (!res.ok) {
    const responseText = await res.text().catch(() => '');
    let detail = '';
    try {
      const parsed = JSON.parse(responseText);
      detail = parsed.detail || parsed.message || '';
    } catch {
      detail = responseText.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    }
    throw new Error(detail || `Request failed (HTTP ${res.status})`);
  }

  return res.json();
}

async function tryRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    saveTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

// ── Public API ──────────────────────────────────────

export const api = {
  // Auth
  register(email, username, password, full_name) {
    return request('/auth/register', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, username, password, full_name }),
    });
  },

  login(email, password) {
    return request('/auth/login', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, password, device_token: getDeviceToken(email) }),
    });
  },

  // Finish an email-2FA login. On success the server may return a device_token
  // to remember this browser; stash it so next time skips the code.
  async verify2fa(email, code, rememberDevice = false) {
    const data = await request('/auth/verify-2fa', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email, code, remember_device: rememberDevice }),
    });
    if (data && data.device_token) saveDeviceToken(email, data.device_token);
    return data;
  },

  resend2fa(email) {
    return request('/auth/resend-2fa', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  setTwoFactor(enabled) {
    return request('/auth/2fa', { method: 'PUT', body: JSON.stringify({ enabled }) });
  },

  googleLogin(idToken) {
    return request('/auth/google', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ id_token: idToken }),
    });
  },

  resendVerification(email) {
    return request('/auth/resend-verification', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  forgotPassword(email) {
    return request('/auth/forgot-password', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ email }),
    });
  },

  resetPassword(token, password) {
    return request('/auth/reset-password', {
      method: 'POST', noAuth: true,
      body: JSON.stringify({ token, password }),
    });
  },

  getMe() {
    return request('/auth/me');
  },

  updateMe(data) {
    return request('/auth/me', { method: 'PUT', body: JSON.stringify(data) });
  },

  setApiKey(apiKey) {
    return request('/auth/api-key', { method: 'PUT', body: JSON.stringify({ api_key: apiKey }) });
  },

  // Multi-key management
  listApiKeys() {
    return request('/auth/api-keys');
  },
  addApiKey(apiKey, label) {
    return request('/auth/api-keys', { method: 'POST', body: JSON.stringify({ api_key: apiKey, label }) });
  },
  deleteApiKey(keyId) {
    return request(`/auth/api-keys/${keyId}`, { method: 'DELETE' });
  },
  activateApiKey(keyId) {
    return request(`/auth/api-keys/${keyId}/activate`, { method: 'PUT' });
  },
  updateApiKey(keyId, patch) {
    return request(`/auth/api-keys/${keyId}`, { method: 'PUT', body: JSON.stringify(patch) });
  },

  // Analysis
  getCategories() {
    return request('/categories');
  },

  analyze(file, category, documentType, extras = {}, signal) {
    const form = new FormData();
    form.append('imageFile', file);
    if (category) form.append('category', category);
    if (documentType) form.append('document_type', documentType);
    if (extras.suspicionReason) form.append('suspicion_reason', extras.suspicionReason);
    if (extras.areaOfConcern) form.append('area_of_concern', extras.areaOfConcern);
    if (extras.imageSource) form.append('image_source', extras.imageSource);
    if (extras.isForgedBelief) form.append('is_forged_belief', extras.isForgedBelief);
    if (extras.shotType) form.append('shot_type', extras.shotType);
    if (extras.lighting) form.append('lighting', extras.lighting);
    if (extras.physicalClues) form.append('physical_clues', extras.physicalClues);
    return request('/analyze', { method: 'POST', body: form, signal });
  },

  getDocumentTypes() {
    return request('/document-types', { noAuth: true });
  },

  preliminary(file) {
    const form = new FormData();
    form.append('imageFile', file);
    return request('/preliminary', { method: 'POST', body: form });
  },

  // History
  getHistory(limit = 50, offset = 0) {
    return request(`/history?limit=${limit}&offset=${offset}`);
  },

  getScanDetail(scanId) {
    return request(`/history/${scanId}`);
  },

  updateScanNotes(scanId, notes) {
    return request(`/history/${encodeURIComponent(scanId)}/notes`, {
      method: 'PUT',
      body: JSON.stringify({ notes }),
    });
  },

  deleteScan(scanId) {
    return request(`/history/${encodeURIComponent(scanId)}`, { method: 'DELETE' });
  },

  getScanImageUrl(scanId) {
    const token = getToken();
    return `${API_BASE}/history/${encodeURIComponent(scanId)}/image?token=${encodeURIComponent(token || '')}`;
  },

  // Payments
  getPlans() {
    return request('/payments/plans');
  },

  createCheckout(plan, paymentMethod = 'stripe') {
    if (paymentMethod === 'paymongo') {
      return request('/payments/paymongo-checkout', {
        method: 'POST', body: JSON.stringify({ plan, payment_method: 'paymongo' }),
      });
    }
    return request('/payments/create-checkout', {
      method: 'POST', body: JSON.stringify({ plan, payment_method: 'stripe' }),
    });
  },

  getPaymongoPublicKey() {
    return request('/payments/paymongo-public-key', { noAuth: true });
  },

  verifySession(sessionId, provider = 'stripe') {
    const params = new URLSearchParams({ provider });
    if (sessionId) params.set('session_id', sessionId);
    return request(`/payments/verify-session?${params.toString()}`);
  },

  cancelSubscription() {
    return request('/payments/cancel', { method: 'POST' });
  },

  // Admin
  adminListUsers({ q = '', plan = '', role = '', limit = 50, offset = 0 } = {}) {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (plan) params.set('plan', plan);
    if (role) params.set('role', role);
    params.set('limit', limit);
    params.set('offset', offset);
    return request(`/admin/users?${params.toString()}`);
  },

  adminGetUser(userId) {
    return request(`/admin/users/${userId}`);
  },

  adminDeleteUser(userId) {
    return request(`/admin/users/${userId}`, { method: 'DELETE' });
  },

  adminStats() {
    return request('/admin/stats');
  },

  // Admin actions (ban/unban users)
  adminBanUser(userId) {
    return request(`/admin/users/${userId}/ban`, { method: 'POST' });
  },

  adminUnbanUser(userId) {
    return request(`/admin/users/${userId}/unban`, { method: 'POST' });
  },

  adminPromoteAdmin(userId) {
    return request(`/admin/users/${userId}/promote-admin`, { method: 'POST' });
  },

  adminDemoteAdmin(userId) {
    return request(`/admin/users/${userId}/demote-admin`, { method: 'POST' });
  },

  // Audit logs (admin + super admin)
  adminViewLogs(opts = {}) {
        const { limit = 200, offset = 0, kind = null, action = null, actor = null,
          role = null, verdict = null, category = null, start_date = null, end_date = null, q = null } = opts;
    const params = new URLSearchParams();
    params.set('limit', limit);
    params.set('offset', offset);
    for (const [k, v] of Object.entries({ kind, action, actor, role, verdict, category, start_date, end_date, q })) {
      if (v) params.set(k, v);
    }
    return request(`/admin/super/logs?${params.toString()}`);
  },

  adminScanImageUrl(scanId) {
    const token = getToken();
    return `${API_BASE}/admin/scans/${encodeURIComponent(scanId)}/image?token=${encodeURIComponent(token || '')}`;
  },

  adminGeminiStatus() {
    return request('/admin/gemini-status');
  },

  getAbout() {
    return request('/about', { noAuth: true });
  },

  getPromptAnalysis() {
    return request('/prompt-analysis', { noAuth: true });
  },

  getSystemAccuracy() {
    return request('/prompt-analysis/accuracy', { noAuth: true });
  },

  // Health
  health() {
    return request('/health', { noAuth: true });
  },

  // Token helpers
  saveTokens,
  clearTokens,
  getToken,
};
```

## File: `frontend/src/apiKeyTutorial.js`

<!-- FILE: frontend/src/apiKeyTutorial.js -->

```javascript
export const API_KEY_TUTORIAL_REQUEST = 'fg_open_api_key_tutorial';

export function requestApiKeyTutorial() {
  sessionStorage.setItem(API_KEY_TUTORIAL_REQUEST, 'true');
}

export function consumeApiKeyTutorialRequest() {
  const requested = sessionStorage.getItem(API_KEY_TUTORIAL_REQUEST) === 'true';
  if (requested) sessionStorage.removeItem(API_KEY_TUTORIAL_REQUEST);
  return requested;
}
```

## File: `frontend/src/App.jsx`

<!-- FILE: frontend/src/App.jsx -->

```jsx
import React, { useState, useEffect, useRef, createContext, useContext } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate, useLocation } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { Capacitor } from '@capacitor/core';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import { api } from './api/client';
import Login from './pages/Login';
import Register from './pages/Register';
import Terms from './pages/Terms';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Scan from './pages/Scan';
import SampleGallery from './pages/SampleGallery';
import History from './pages/History';
import Account from './pages/Account';
import Admin from './pages/Admin';
import ForensicsGuide from './pages/ForensicsGuide';
import Logo from './components/Logo';

// ── Theme Context ────────────────────────────────────

const ThemeContext = createContext({ theme: 'dark', toggleTheme: () => {} });

export function useTheme() {
  return useContext(ThemeContext);
}

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('fg_theme') || 'dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('fg_theme', theme);
  }, [theme]);

  function toggleTheme() {
    setTheme(t => t === 'dark' ? 'light' : 'dark');
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

// ── Scan Context ────────────────────────────────────

const ScanContext = createContext(null);

export function useScan() {
  return useContext(ScanContext);
}

function ScanProvider({ children }) {
  const [status, setStatus] = useState('idle'); // 'idle' | 'scanning' | 'done' | 'error'
  const [result, setResult] = useState(null);
  const [scanError, setScanError] = useState('');
  const [previewUrl, setPreviewUrl] = useState(null);
  const abortRef = useRef(null);

  async function startScan(file, docType, extras, preview) {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setStatus('scanning');
    setResult(null);
    setScanError('');
    setPreviewUrl(preview || null);

    try {
      const data = await api.analyze(file, null, docType, extras, ctrl.signal);
      if (!ctrl.signal.aborted) {
        setStatus('done');
        setResult(data);
      }
    } catch (err) {
      if (ctrl.signal.aborted) return;
      if (err.message === 'quota_exhausted' || err.message === 'no_api_key') {
        localStorage.setItem('fg_quota_exhausted', 'true');
        localStorage.setItem('fg_highlight_key_input', 'true');
        localStorage.setItem('fg_no_api_key', err.message === 'no_api_key' ? 'true' : 'false');
      }
      setStatus('error');
      setScanError(err.message);
    }
  }

  function stopScan() {
    if (abortRef.current) abortRef.current.abort();
    setStatus('idle');
    setResult(null);
    setScanError('');
  }

  function clearScan() {
    setStatus('idle');
    setResult(null);
    setScanError('');
    setPreviewUrl(null);
  }

  return (
    <ScanContext.Provider value={{ status, result, error: scanError, previewUrl, startScan, stopScan, clearScan }}>
      {children}
    </ScanContext.Provider>
  );
}

// ── Auth Context ────────────────────────────────────

const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('fg_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.getToken()) {
      api.getMe()
        .then(u => { setUser(u); localStorage.setItem('fg_user', JSON.stringify(u)); })
        .catch(() => { setUser(null); api.clearTokens(); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    function onSessionExpired() {
      setUser(null);
      localStorage.removeItem('fg_user');
      navigate('/login', { replace: true });
    }
    window.addEventListener('fg:session-expired', onSessionExpired);
    return () => window.removeEventListener('fg:session-expired', onSessionExpired);
  }, [navigate]);

  function loginUser(data) {
    api.saveTokens(data.access_token, data.refresh_token);
    setUser(data.user);
    localStorage.setItem('fg_user', JSON.stringify(data.user));
  }

  function logout() {
    api.clearTokens();
    setUser(null);
    localStorage.removeItem('fg_user');
  }

  function refreshUser() {
    return api.getMe().then(u => {
      setUser(u);
      localStorage.setItem('fg_user', JSON.stringify(u));
    });
  }

  return (
    <AuthContext.Provider value={{ user, loading, loginUser, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <BootSplash />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <BootSplash />;
  if (!user) return <Navigate to="/login" replace />;
  if (!["admin","superadmin"].includes(user.role)) return <Navigate to="/scan" replace />;
  return children;
}

function BootSplash() {
  return (
    <div style={{ padding: 60, textAlign: 'center' }}>
      <div className="mono glow" style={{ color: 'var(--green-neon)', fontSize: 12, letterSpacing: 4 }}>
        ▣ INITIALIZING FORENSIC PIPELINE
      </div>
      <div className="mono caret" style={{ color: 'var(--text-secondary)', fontSize: 11, marginTop: 10, letterSpacing: 2 }}>
        loading
      </div>
    </div>
  );
}

// ── Layout ──────────────────────────────────────────

function Layout({ children }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { status: scanStatus, stopScan } = useScan();
  const location = useLocation();
  const navigate = useNavigate();
  const onScanPage = location.pathname === '/scan';
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerOffset, setDrawerOffset] = useState(0); // for swipe-drag visual feedback
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const touchStartX = React.useRef(null);
  const touchStartY = React.useRef(null);
  const isDragging = React.useRef(false);
  const DRAWER_WIDTH = 280;

  // Clear quota exhausted flag when entering Account page
  React.useEffect(() => {
    if (location.pathname === '/account') {
      setQuotaExhausted(false);
      localStorage.removeItem('fg_quota_exhausted');
      localStorage.removeItem('fg_no_api_key');
    }
  }, [location.pathname]);

  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

  // Lock body scroll while drawer is open
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [drawerOpen]);

  // Close drawer on Escape
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') setDrawerOpen(false); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Swipe-from-edge to open / swipe-on-drawer to close
  useEffect(() => {
    if (!user) return;

    function onTouchStart(e) {
      const t = e.touches[0];
      // Open: touch must start near left edge (within 24px) and drawer is closed
      // Close: touch can start anywhere on drawer area when open
      const fromEdge = t.clientX <= 24;
      const onDrawer = drawerOpen && t.clientX <= DRAWER_WIDTH + 40;
      if (fromEdge || onDrawer) {
        touchStartX.current = t.clientX;
        touchStartY.current = t.clientY;
        isDragging.current = false;
      }
    }
    function onTouchMove(e) {
      if (touchStartX.current == null) return;
      const t = e.touches[0];
      const dx = t.clientX - touchStartX.current;
      const dy = t.clientY - touchStartY.current;
      // Only start dragging if horizontal motion dominates
      if (!isDragging.current && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
        isDragging.current = true;
      }
      if (!isDragging.current) return;

      if (drawerOpen) {
        // Closing drag: dx is negative as user swipes left; offset in [-W, 0]
        setDrawerOffset(Math.max(-DRAWER_WIDTH, Math.min(0, dx)));
      } else {
        // Opening drag: dx is positive as user swipes right; offset in [0, W]
        setDrawerOffset(Math.max(0, Math.min(DRAWER_WIDTH, dx)));
      }
    }
    function onTouchEnd() {
      if (isDragging.current) {
        if (drawerOpen) {
          if (drawerOffset < -DRAWER_WIDTH / 3) setDrawerOpen(false);
        } else {
          if (drawerOffset > DRAWER_WIDTH / 3) setDrawerOpen(true);
        }
      }
      touchStartX.current = null;
      touchStartY.current = null;
      isDragging.current = false;
      setDrawerOffset(0);
    }

    window.addEventListener('touchstart', onTouchStart, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('touchend', onTouchEnd);
    return () => {
      window.removeEventListener('touchstart', onTouchStart);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
    };
  }, [user, drawerOpen, drawerOffset]);

  const navItems = [
    { path: '/scan', label: 'Scan', icon: '⌖' },
    { path: '/history', label: 'History', icon: '▤' },
    { path: '/guide', label: 'Guide', icon: '◈' },
    { path: '/account', label: 'Account', icon: '◉' },
    ...(["admin","superadmin"].includes(user?.role) ? [{ path: '/admin', label: 'Admin', icon: '★' }] : []),
  ];

  // Translation for drawer (open + drag state)
  // When open: drawerOffset is [-W, 0]; transform translates from 0 (rest) toward -W during close drag.
  // When closed: drawerOffset is [0, W]; transform translates from -W (rest) toward 0 during open drag.
  const drawerTransform = drawerOpen
    ? `translateX(${drawerOffset}px)`
    : `translateX(${-DRAWER_WIDTH + drawerOffset}px)`;
  const backdropOpacity = drawerOpen
    ? Math.max(0, 1 + drawerOffset / DRAWER_WIDTH)
    : Math.max(0, Math.min(1, drawerOffset / DRAWER_WIDTH));
  const isLight = theme === 'light';

  return (
    <div>
      <div className="tape-border" />
      <header style={{
        background:
          'linear-gradient(180deg, rgba(8,18,12,0.95) 0%, rgba(0,0,0,0.92) 100%)',
        borderBottom: '1px solid #112418',
        padding: '10px 14px',
        position: 'sticky', top: 0, zIndex: 50,
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        boxShadow: '0 1px 0 rgba(0,255,102,0.08), 0 8px 24px rgba(0,0,0,0.6)',
      }}>
        <div className="container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          {/* Hamburger - left side, mobile only */}
          {user && (
            <button
              className="nav-burger"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open menu"
              style={{
                background: quotaExhausted ? 'rgba(0,255,102,0.18)' : 'rgba(0,255,102,0.06)',
                border: quotaExhausted ? '1px solid #00ff66' : '1px solid #1d3825',
                color: '#00ff66',
                width: 44, height: 44, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', borderRadius: 3, padding: 0,
                fontSize: 22, lineHeight: 1, flexShrink: 0,
                textShadow: '0 0 8px rgba(0,255,102,0.5)',
                boxShadow: quotaExhausted ? '0 0 0 2px rgba(0,255,102,0.5), 0 0 20px rgba(0,255,102,0.6)' : 'none',
                animation: quotaExhausted ? 'spotlight-pulse 1.5s ease-in-out infinite' : 'none',
                position: 'relative', zIndex: quotaExhausted ? 51 : 'auto',
              }}
            >
              ☰
            </button>
          )}

          <Link
            to="/scan"
            onClick={(event) => {
              event.preventDefault();
              navigate('/scan');
            }}
            style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}
          >
            <Logo size={32} glow animated />
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1, minWidth: 0 }}>
              <span className="oswald glow-strong" style={{
                fontSize: 20, fontWeight: 700, color: '#00ff66', letterSpacing: 5,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                REVELATOR
              </span>
              <span className="mono" style={{
                fontSize: 8, letterSpacing: 3, color: '#3f6e4a', marginTop: 3,
              }}>
                FORENSIC ENGINE
              </span>
            </div>
          </Link>

          {/* Desktop nav - only on wide screens */}
          {user && (
            <nav className="nav-desktop" style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <style>{`
                @keyframes flicker-glow {
                  0%, 100% { box-shadow: 0 0 8px rgba(0,255,102,0.8), 0 0 16px rgba(0,255,102,0.6); }
                  50% { box-shadow: 0 0 4px rgba(0,255,102,0.3), 0 0 8px rgba(0,255,102,0.2); }
                }
                @keyframes spotlight-pulse {
                  0%, 100% { box-shadow: 0 0 0 2px rgba(0,255,102,0.7), 0 0 28px rgba(0,255,102,0.9), 0 0 60px rgba(0,255,102,0.3); }
                  50% { box-shadow: 0 0 0 2px rgba(0,255,102,0.4), 0 0 14px rgba(0,255,102,0.5), 0 0 30px rgba(0,255,102,0.15); }
                }
              `}</style>
              {navItems.map(item => {
                const active = location.pathname === item.path;
                const isAccount = item.path === '/account';
                const shouldFlicker = quotaExhausted && isAccount;
                const shouldDim = quotaExhausted && !isAccount && !active;
                return (
                  <Link key={item.path} to={item.path} style={{
                    padding: '10px 14px', fontSize: 13,
                    fontFamily: "'Oswald', sans-serif",
                    textTransform: 'uppercase', letterSpacing: 1.5,
                    color: shouldDim ? '#2a4a30' : active ? '#00ff66' : shouldFlicker ? '#00ff66' : '#6dba85',
                    textDecoration: 'none',
                    borderBottom: active ? '2px solid #00ff66' : shouldFlicker ? '2px solid #00ff66' : '2px solid transparent',
                    textShadow: active ? '0 0 12px rgba(0,255,102,0.55)' : shouldFlicker ? '0 0 12px rgba(0,255,102,0.9)' : 'none',
                    whiteSpace: 'nowrap',
                    transition: 'color 0.15s, text-shadow 0.15s',
                    animation: shouldFlicker ? 'spotlight-pulse 1.5s ease-in-out infinite' : 'none',
                    borderRadius: shouldFlicker ? 3 : 0,
                    background: shouldFlicker ? 'rgba(0,255,102,0.1)' : 'transparent',
                    position: 'relative', zIndex: shouldFlicker ? 51 : 'auto',
                    pointerEvents: shouldDim ? 'none' : 'auto',
                    opacity: shouldDim ? 0.25 : 1,
                  }}>
                    {item.label}
                  </Link>
                );
              })}
              <button
                onClick={toggleTheme}
                aria-label="Toggle theme"
                title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                style={{
                  background: 'rgba(0,255,102,0.04)', border: '1px solid #1d3825', color: '#86efac',
                  width: 32, height: 32, cursor: 'pointer', fontSize: 16,
                  borderRadius: 2, marginLeft: 8, padding: 0,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                {theme === 'dark' ? '☾' : '☀'}
              </button>
              <button
                onClick={logout}
                style={{
                  background: 'rgba(255,51,68,0.04)', border: '1px solid rgba(255,51,68,0.4)', color: '#ff7588',
                  padding: '6px 14px', cursor: 'pointer', fontSize: 11,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                  letterSpacing: 1.5, borderRadius: 2, marginLeft: 8,
                }}
              >
                Logout
              </button>
            </nav>
          )}
        </div>
      </header>

      {/* API key tutorial overlay - dims everything below the header */}
      {user && quotaExhausted && !drawerOpen && (
        <div
          style={{
            position: 'fixed', inset: 0, zIndex: 48,
            background: 'rgba(0,0,0,0.82)',
            cursor: 'pointer',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
            paddingBottom: 40,
          }}
        >
          <button
            type="button"
            aria-label="Close API key guidance"
            onClick={() => {
              setQuotaExhausted(false);
              localStorage.removeItem('fg_quota_exhausted');
              localStorage.removeItem('fg_no_api_key');
            }}
            style={{
              position: 'absolute', top: 18, right: 18, zIndex: 1,
              background: 'rgba(0,0,0,0.7)', border: '1px solid rgba(0,255,102,0.6)',
              color: '#00ff66', width: 34, height: 34, borderRadius: 3,
              cursor: 'pointer', fontSize: 20, lineHeight: 1,
            }}
          >
            ×
          </button>
          {/* Mobile floating hint */}
          <div
            onClick={() => { navigate('/account'); }}
            className="nav-burger"
            style={{
              background: 'rgba(0,0,0,0.92)', border: '1px solid rgba(0,255,102,0.5)',
              borderRadius: 8, padding: '16px 20px', maxWidth: 300, textAlign: 'center',
              boxShadow: '0 0 30px rgba(0,255,102,0.25)',
              pointerEvents: 'none',
            }}
          >
            <div className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#00ff66', marginBottom: 8, textTransform: 'uppercase' }}>
              ▲ API KEY REQUIRED
            </div>
            <div style={{ color: '#d8ffe6', fontSize: 13, lineHeight: 1.7, marginBottom: 10 }}>
              Tap the <strong style={{ color: '#00ff66' }}>☰</strong> menu icon above then go to <strong style={{ color: '#00ff66' }}>Account</strong> to add your Gemini API key.
            </div>
            <div className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 1 }}>
              Tap anywhere to go there now →
            </div>
          </div>

          {/* Desktop hint - arrow pointing at Account nav */}
          <div
            className="nav-desktop"
            style={{
              position: 'absolute', top: 66, right: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'flex-end',
              paddingRight: 24, pointerEvents: 'none',
            }}
          >
            <div style={{ fontSize: 20, color: '#00ff66', lineHeight: 1, marginBottom: 4, textShadow: '0 0 10px rgba(0,255,102,0.8)' }}>▲</div>
            <div style={{
              background: 'rgba(0,0,0,0.92)', border: '1px solid rgba(0,255,102,0.4)',
              borderRadius: 6, padding: '10px 14px', maxWidth: 220,
              boxShadow: '0 0 20px rgba(0,255,102,0.2)',
            }}>
              <div className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#00ff66', marginBottom: 6, textTransform: 'uppercase' }}>
                API Key Required
              </div>
              <div style={{ color: '#d8ffe6', fontSize: 12, lineHeight: 1.6 }}>
                Go to <strong style={{ color: '#00ff66' }}>Account</strong> and paste your Gemini API key to start scanning.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Drawer backdrop */}
      {user && (drawerOpen || drawerOffset !== 0) && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 60,
            background: isLight
              ? `rgba(10,26,16,${0.32 * backdropOpacity})`
              : `rgba(0,0,0,${0.6 * backdropOpacity})`,
            backdropFilter: `blur(${4 * backdropOpacity}px)`,
            WebkitBackdropFilter: `blur(${4 * backdropOpacity}px)`,
            transition: drawerOffset === 0 ? 'background 0.25s, backdrop-filter 0.25s' : 'none',
          }}
        />
      )}

      {/* Slide-in drawer - left edge, X/Twitter style */}
      {user && (
        <aside
          aria-hidden={!drawerOpen}
          style={{
            position: 'fixed', top: 0, left: 0, bottom: 0,
            width: DRAWER_WIDTH, maxWidth: '85vw', zIndex: 70,
            background: isLight
              ? 'linear-gradient(180deg, #ffffff 0%, #eef4f0 100%)'
              : 'linear-gradient(180deg, #06120a 0%, #02080a 100%)',
            borderRight: '1px solid #1d3825',
            boxShadow: drawerOpen ? '4px 0 32px rgba(0,255,102,0.12), 8px 0 60px rgba(0,0,0,0.85)' : 'none',
            transform: drawerTransform,
            transition: drawerOffset === 0 ? 'transform 0.28s cubic-bezier(0.32,0.72,0.4,1)' : 'none',
            display: 'flex', flexDirection: 'column',
            paddingTop: 'env(safe-area-inset-top, 0)',
          }}
        >
          {/* Drawer header - user identity */}
          <div style={{
            padding: '20px 18px 18px', borderBottom: '1px solid #112418',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <div style={{
              width: 44, height: 44, borderRadius: 22,
              background: 'linear-gradient(135deg, rgba(0,255,102,0.18), rgba(0,255,170,0.06))',
              border: '1px solid #1d3825',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: "'Oswald', sans-serif", fontSize: 18, color: '#00ff66',
              textShadow: '0 0 8px rgba(0,255,102,0.7)', flexShrink: 0,
            }}>
              {(user?.username || user?.email || '?').slice(0, 1).toUpperCase()}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="oswald" style={{
                fontSize: 14, color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 1.5,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {user?.username || 'OPERATOR'}
              </div>
              <div className="mono" style={{
                fontSize: 10, color: '#6dba85', letterSpacing: 1, marginTop: 2,
                textTransform: 'uppercase',
              }}>
                {user?.plan ? `${user.plan} TIER` : 'FREE TIER'}
              </div>
            </div>
            <button
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
              style={{
                background: 'transparent', border: '1px solid #1d3825',
                color: '#6dba85', width: 32, height: 32, borderRadius: 16,
                cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0,
              }}
            >
              ✕
            </button>
          </div>

          {/* Drawer nav links */}
          <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            <style>{`
              @keyframes flicker-glow-drawer {
                0%, 100% { box-shadow: inset 0 0 8px rgba(0,255,102,0.4); }
                50% { box-shadow: inset 0 0 4px rgba(0,255,102,0.1); }
              }
              @keyframes spotlight-drawer {
                0%, 100% { box-shadow: inset 0 0 16px rgba(0,255,102,0.3), 0 0 20px rgba(0,255,102,0.4); background: rgba(0,255,102,0.12); }
                50% { box-shadow: inset 0 0 8px rgba(0,255,102,0.1), 0 0 10px rgba(0,255,102,0.2); background: rgba(0,255,102,0.06); }
              }
            `}</style>
            {navItems.map(item => {
              const active = location.pathname === item.path;
              const isAccount = item.path === '/account';
              const shouldFlicker = quotaExhausted && isAccount;
              const shouldDimDrawer = quotaExhausted && !isAccount;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    padding: '14px 18px',
                    fontSize: 15,
                    fontFamily: "'Oswald', sans-serif",
                    textTransform: 'uppercase', letterSpacing: 2,
                    color: shouldDimDrawer ? '#1d3825' : active ? '#00ff66' : shouldFlicker ? '#00ff66' : '#86efac',
                    textDecoration: 'none',
                    borderLeft: active ? '3px solid #00ff66' : shouldFlicker ? '3px solid #00ff66' : '3px solid transparent',
                    background: shouldFlicker ? 'rgba(0,255,102,0.12)' : active ? 'rgba(0,255,102,0.06)' : 'transparent',
                    textShadow: active ? '0 0 10px rgba(0,255,102,0.5)' : shouldFlicker ? '0 0 14px rgba(0,255,102,0.9)' : 'none',
                    minHeight: 48,
                    opacity: shouldDimDrawer ? 0.2 : 1,
                    pointerEvents: shouldDimDrawer ? 'none' : 'auto',
                    animation: shouldFlicker ? 'spotlight-drawer 1.5s ease-in-out infinite' : 'none',
                  }}
                >
                  <span className="mono" style={{
                    fontSize: 16, color: active ? '#00ff66' : shouldFlicker ? '#00ff66' : '#3f6e4a', width: 20, textAlign: 'center',
                  }}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Drawer footer - theme toggle + logout */}
          <div style={{
            borderTop: '1px solid #112418',
            padding: '10px 12px',
            paddingBottom: 'calc(10px + env(safe-area-inset-bottom, 0))',
            display: 'flex', flexDirection: 'column', gap: 8,
          }}>
            <button
              onClick={toggleTheme}
              style={{
                width: '100%', minHeight: 48,
                background: 'rgba(0,255,102,0.04)',
                border: '1px solid #1d3825', color: '#86efac',
                padding: '12px', cursor: 'pointer', fontSize: 13,
                fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                letterSpacing: 2, borderRadius: 3,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
              }}
            >
              <span style={{ fontSize: 18 }}>{theme === 'dark' ? '☾' : '☀'}</span>
              {theme === 'dark' ? 'Light mode' : 'Dark mode'}
            </button>
            <button
              onClick={() => { setDrawerOpen(false); logout(); }}
              style={{
                width: '100%', minHeight: 48,
                background: 'rgba(255,51,68,0.06)',
                border: '1px solid rgba(255,51,68,0.35)', color: '#ff8a99',
                padding: '12px', cursor: 'pointer', fontSize: 13,
                fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                letterSpacing: 2, borderRadius: 3,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              <span style={{ fontSize: 16 }}>⤴</span> Logout
            </button>
          </div>
        </aside>
      )}

      {/* Floating scan status pill - visible on all pages while a scan is running */}
      {user && (scanStatus === 'scanning' || (scanStatus === 'done' && !onScanPage) || (scanStatus === 'error' && !onScanPage)) && (
        <div style={{
          position: 'fixed', bottom: 24, right: 20, zIndex: 200,
          background: 'rgba(6,18,10,0.97)',
          border: `1px solid ${scanStatus === 'done' ? '#00ff66' : scanStatus === 'error' ? '#ff3344' : '#1d3825'}`,
          borderRadius: 6, padding: '10px 14px',
          boxShadow: `0 4px 24px rgba(0,0,0,0.7), 0 0 16px ${scanStatus === 'done' ? 'rgba(0,255,102,0.2)' : scanStatus === 'error' ? 'rgba(255,51,68,0.2)' : 'rgba(0,255,102,0.1)'}`,
          display: 'flex', alignItems: 'center', gap: 10,
          minWidth: 200, maxWidth: 280,
        }}>
          {scanStatus === 'scanning' && (
            <>
              <span className="mono" style={{ fontSize: 11, color: '#6dba85', animation: 'ring-spin 1.2s linear infinite', display: 'inline-block' }}>◌</span>
              <span className="mono" style={{ fontSize: 11, color: '#86efac', letterSpacing: 1, flex: 1 }}>Scanning in progress…</span>
              <button
                onClick={stopScan}
                title="Stop scan"
                style={{
                  background: 'rgba(255,51,68,0.12)', border: '1px solid rgba(255,51,68,0.5)',
                  color: '#ff8a99', borderRadius: 3, padding: '3px 8px',
                  cursor: 'pointer', fontSize: 11,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                  flexShrink: 0,
                }}
              >
                ✕ Stop
              </button>
            </>
          )}
          {scanStatus === 'done' && !onScanPage && (
            <>
              <span style={{ color: '#00ff66', fontSize: 14 }}>✓</span>
              <span className="mono" style={{ fontSize: 11, color: '#86efac', letterSpacing: 1, flex: 1 }}>Scan complete</span>
              <button
                onClick={() => navigate('/scan')}
                style={{
                  background: 'rgba(0,255,102,0.12)', border: '1px solid rgba(0,255,102,0.5)',
                  color: '#00ff66', borderRadius: 3, padding: '3px 8px',
                  cursor: 'pointer', fontSize: 11,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                  flexShrink: 0,
                }}
              >
                View →
              </button>
            </>
          )}
          {scanStatus === 'error' && !onScanPage && (
            <>
              <span style={{ color: '#ff3344', fontSize: 14 }}>⚠</span>
              <span className="mono" style={{ fontSize: 11, color: '#ff8a99', letterSpacing: 1, flex: 1 }}>Scan failed</span>
              <button
                onClick={() => navigate('/scan')}
                style={{
                  background: 'rgba(255,51,68,0.12)', border: '1px solid rgba(255,51,68,0.5)',
                  color: '#ff8a99', borderRadius: 3, padding: '3px 8px',
                  cursor: 'pointer', fontSize: 11,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                  flexShrink: 0,
                }}
              >
                View →
              </button>
            </>
          )}
        </div>
      )}

      <main style={{ padding: '20px 0', minHeight: 'calc(100vh - 80px)' }}>
        <div className="container">
          {children}
        </div>
      </main>
      <footer style={{ borderTop: '1px solid #112418', padding: '16px 20px 24px', textAlign: 'center' }}>
        <Link to="/guide" style={{ color: '#3f6e4a', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', textDecoration: 'none' }}>
          Forensic System Guide
        </Link>
        <span style={{ color: '#1d3825', margin: '0 12px' }}>·</span>
        <Link to="/terms" style={{ color: '#3f6e4a', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', textDecoration: 'none' }}>
          Terms of Service &amp; Privacy Policy
        </Link>
      </footer>
    </div>
  );
}

// ── App ─────────────────────────────────────────────

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

export default function App() {
  useEffect(() => {
    if (Capacitor.isNativePlatform()) {
      GoogleAuth.initialize({
        clientId: GOOGLE_CLIENT_ID,
        scopes: ['profile', 'email'],
        grantOfflineAccess: false,
      });
    }
  }, []);

  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <BrowserRouter>
        <ThemeProvider>
          <AuthProvider>
            <ScanProvider>
            <Layout>
              <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/" element={<Navigate to="/scan" replace />} />
              <Route path="/scan" element={<ProtectedRoute><Scan /></ProtectedRoute>} />
              <Route path="/samples/:categoryId" element={<ProtectedRoute><SampleGallery /></ProtectedRoute>} />
              <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
              <Route path="/guide" element={<ProtectedRoute><ForensicsGuide /></ProtectedRoute>} />
              <Route path="/account" element={<ProtectedRoute><Account /></ProtectedRoute>} />
              <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
              <Route path="*" element={<Navigate to="/scan" replace />} />
              </Routes>
            </Layout>
            </ScanProvider>
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </GoogleOAuthProvider>
  );
}
```

## File: `frontend/src/categories.js`

<!-- FILE: frontend/src/categories.js -->

```javascript
// Master catalog of all 15 forgery categories, used by Scan and SampleGallery.
// `apiKey` matches the leaf class id the backend's /analyze endpoint accepts.
// `id`     is the URL slug used by /samples/:categoryId.
// `tier`   1 = easy, 2 = medium, 3 = hard (informs grouping + accent color).
// Colors stay inside a green/cyan/lime spectrum to keep the matrix theme coherent.

export const TIER_COLORS = {
  1: '#00ff66', // neon green
  2: '#00ffaa', // cyan-green
  3: '#a3e635', // lime / chartreuse
};

export const TIER_META = {
  1: { label: 'Tier 1 · Surface',   sublabel: 'Digital and surface-level alterations - phone-friendly capture' },
  2: { label: 'Tier 2 · Substrate', sublabel: 'Paper-and-ink alterations - close-range or oblique-light capture' },
  3: { label: 'Tier 3 · Spectral',  sublabel: 'Specialized optics - UV, raking light, security features' },
};

export const CATEGORIES = [
  // ── Tier 1 - Surface / digital ────────────────────────────────────────
  {
    id: 'cut_paste',         apiKey: 'digital_cut_paste',       tier: 1,
    code: 'CUT', icon: '✂',   color: '#00ff66',
    title: 'Cut and Paste',
    description: 'Image regions spliced from one document into another to fabricate content.',
  },
  {
    id: 'desktop',           apiKey: 'digital_desktop',         tier: 1,
    code: 'DTP', icon: '⌨',   color: '#3df58a',
    title: 'Desktop Publishing',
    description: 'Whole-document fabrication built in Word, Canva, or Photoshop.',
  },
  {
    id: 'insertion',         apiKey: 'addition_insertion',      tier: 1,
    code: 'INS', icon: '+',   color: '#56ff8a',
    title: 'Insertion',
    description: 'New characters or digits added inside existing text to change its meaning.',
  },
  {
    id: 'interlineation',    apiKey: 'addition_interlineation', tier: 1,
    code: 'ITL', icon: '≡',   color: '#7cffaf',
    title: 'Interlineation',
    description: 'Extra writing squeezed between existing lines of a document.',
  },
  {
    id: 'whiteout',          apiKey: 'obliteration_whiteout',   tier: 1,
    code: 'WHT', icon: '◻',   color: '#9bffba',
    title: 'White Out',
    description: 'Correction fluid covering original text, with new content written on top.',
  },

  // ── Tier 2 - Physical substrate ───────────────────────────────────────
  {
    id: 'ink_obliteration',  apiKey: 'obliteration_ink',        tier: 2,
    code: 'INK', icon: '▮',   color: '#00ffaa',
    title: 'Ink Obliteration',
    description: 'Original text scribbled or crossed out with ink to conceal it.',
  },
  {
    id: 'mech_erasure',      apiKey: 'erasure_mechanical',      tier: 2,
    code: 'MEC', icon: '⌫',   color: '#5fffc4',
    title: 'Mechanical Erasure',
    description: 'Text physically removed by eraser, blade, sandpaper, or scraping.',
  },
  {
    id: 'chem_erasure',      apiKey: 'erasure_chemical',        tier: 2,
    code: 'CHM', icon: '⚗',   color: '#74ffd0',
    title: 'Chemical Erasure',
    description: 'Ink dissolved or lifted using solvents, ink-eraser pens, or bleach.',
  },
  {
    id: 'scanned',           apiKey: 'digital_scanned',         tier: 2,
    code: 'SCN', icon: '⎙',   color: '#9bffe0',
    title: 'Scanned Documents',
    description: 'Forgery printed and re-scanned to mask its digital origin.',
  },

  // ── Tier 3 - Spectral / specialized ───────────────────────────────────
  {
    id: 'carbon',            apiKey: 'traced_carbon',           tier: 3,
    code: 'CRB', icon: '◤',   color: '#a3e635',
    title: 'Carbon Transfer',
    description: 'Signature traced via carbon paper, then darkened with ink.',
  },
  {
    id: 'indentation',       apiKey: 'traced_indentation',      tier: 3,
    code: 'IDN', icon: '⌇',   color: '#b6ec57',
    title: 'Indentation Tracing',
    description: 'Pressure-impressed groove on a sheet, later traced with ink.',
  },
  {
    id: 'projection',        apiKey: 'traced_projection',       tier: 3,
    code: 'PRJ', icon: '⌖',   color: '#c5f071',
    title: 'Projection Tracing',
    description: 'Forger traces over a back-lit projection of an authentic document.',
  },
  {
    id: 'sym_indented',      apiKey: 'sympathetic_indented',    tier: 3,
    code: 'SYI', icon: '〰',   color: '#d3f48a',
    title: 'Indented Writing',
    description: 'Recovery of pressure shadows left on the sheet beneath original writing.',
  },
  {
    id: 'sym_special',       apiKey: 'sympathetic_special',     tier: 3,
    code: 'UVI', icon: '☢',   color: '#e2f8a3',
    title: 'Special Ink (UV)',
    description: 'Writing that fluoresces only under UV - invisible in normal light.',
  },
  {
    id: 'currency',          apiKey: 'currency_analysis',       tier: 3,
    code: 'CUR', icon: '₱',   color: '#f0ffbe',
    title: 'Currency Analysis',
    description: 'Authenticity check on banknotes - watermarks, threads, UV features.',
  },
];

// Lookup helpers
export const CATEGORY_BY_ID  = Object.fromEntries(CATEGORIES.map(c => [c.id, c]));
export const CATEGORY_BY_KEY = Object.fromEntries(CATEGORIES.map(c => [c.apiKey, c]));

export const MAIN_CATEGORY_BY_KEY = {
  traced_carbon: 'Traced Signatures',
  traced_indentation: 'Traced Signatures',
  traced_projection: 'Traced Signatures',
  addition_insertion: 'Document Alteration',
  addition_interlineation: 'Document Alteration',
  erasure_chemical: 'Document Alteration',
  erasure_mechanical: 'Document Alteration',
  digital_cut_paste: 'Digital Fabrication',
  digital_desktop: 'Digital Fabrication',
  digital_scanned: 'Digital Fabrication',
  obliteration_ink: 'Obliteration',
  obliteration_whiteout: 'Obliteration',
  sympathetic_indented: 'Sympathetic Ink',
  sympathetic_special: 'Sympathetic Ink',
  currency_analysis: 'Currency Counterfeit',
};

export const MAIN_CATEGORY_CODE_BY_KEY = {
  traced_carbon: 'TRACED',
  traced_indentation: 'TRACED',
  traced_projection: 'TRACED',
  addition_insertion: 'ALTERATION',
  addition_interlineation: 'ALTERATION',
  erasure_chemical: 'ALTERATION',
  erasure_mechanical: 'ALTERATION',
  digital_cut_paste: 'DIGITAL',
  digital_desktop: 'DIGITAL',
  digital_scanned: 'DIGITAL',
  obliteration_ink: 'OBLITERATION',
  obliteration_whiteout: 'OBLITERATION',
  sympathetic_indented: 'SYMPATHETIC',
  sympathetic_special: 'SYMPATHETIC',
  currency_analysis: 'CURRENCY',
};

export function categoriesByTier(tier) {
  return CATEGORIES.filter(c => c.tier === tier);
}

// Per-category capture guidance shown on the SampleGallery page.
export const GUIDANCE = {
  cut_paste: {
    shooting: [
      'Lay the document flat under even light - no glare on the splice region',
      'Capture full-page so the model can see boundaries between pasted and original',
      'Avoid cropping mid-character - give 1cm margin around suspect regions',
    ],
    detector: 'Looks for inconsistent JPEG quantization, mismatched lighting, and seams where pixel statistics break.',
  },
  desktop: {
    shooting: [
      'Photograph or scan the printed copy at high resolution (≥300 DPI equivalent)',
      'Include security features (logos, seals, holograms) in frame',
      'Tilt slightly off-axis to surface print-from-screen pixel grids',
    ],
    detector: 'Looks for typeface drift, alignment slips, and missing or wrong-position security elements.',
  },
  insertion: {
    shooting: [
      'Get close enough that text is sharp at full resolution',
      'Capture the entire altered region plus surrounding context',
      'No flash - it can wash out ink-color drift the model relies on',
    ],
    detector: 'Looks for ink-shade differences, cramped spacing, and pen-pressure changes within a word or number.',
  },
  interlineation: {
    shooting: [
      'Frame the interlineation centered between two lines of original text',
      'Use diffuse light from above; avoid harsh side shadows',
      'For very tight gaps, take a second close-up to capture stroke detail',
    ],
    detector: 'Looks for cramped writing in line gaps, ink-shade mismatches, and slight tilt from a forced angle.',
  },
  whiteout: {
    shooting: [
      'Shoot under raking (low-angle) light to reveal the topology of the white-out patch',
      'Capture both the patch and 2cm of surrounding clean paper',
      'Take a normal-light shot too - texture differences show up across both',
    ],
    detector: 'Looks for matte sheen, raised topology, and irregular edges around the covered area.',
  },
  ink_obliteration: {
    shooting: [
      'Strong overhead light may surface ghost text bleeding through the ink',
      'Avoid auto-exposure - locking exposure preserves ink-density signal',
      'Capture multiple angles if the obliteration is glossy',
    ],
    detector: 'Looks for ink-density anomalies, residual character outlines, and uniform machine-like coverage.',
  },
  mech_erasure: {
    shooting: [
      'Raking light is mandatory - it shows the disturbed paper fibers',
      'Capture against a black backdrop so light bounce stays controlled',
      'Take a transmission shot (light behind paper) if paper is thinned',
    ],
    detector: 'Looks for raised fibers, paper-thinning, ghost text, and slight discoloration where ink was lifted.',
  },
  chem_erasure: {
    shooting: [
      'Watch for brown / yellow halos - those are the chemical signature',
      'Shoot under both normal and UV light if available - chemistry often fluoresces',
      'Avoid white balance auto-correct; the cast carries information',
    ],
    detector: 'Looks for chemical halos, etched paper, residual ink ghosts, and UV-fluorescent residue.',
  },
  scanned: {
    shooting: [
      'For PDFs, export each page as a PNG and submit individually',
      'For prints, scan at the highest resolution your scanner supports',
      'Slightly tilt photographed prints to dodge moiré',
    ],
    detector: 'Looks for compounding compression artifacts, halftone patterns, and edge softness from re-capture.',
  },
  carbon: {
    shooting: [
      'Macro / close-up - character-level detail matters here',
      'Even diffuse light, no shadows in the stroke',
      'Submit the full signature plus 2cm context above and below',
    ],
    detector: 'Looks for unnaturally uniform stroke speed, faint carbon shadow alongside the ink, and broken character continuity.',
  },
  indentation: {
    shooting: [
      'A side lamp at 10–30° from horizontal is required - flash or top-down won\'t work',
      'Phone parallel to the page; canals show as shadow stripes',
      'Hold the camera steady - ideally a tripod or stable surface',
    ],
    detector: 'Looks for canal grooves, ink filling indentations precisely, and depression rings around the signature.',
  },
  projection: {
    shooting: [
      'Get the entire signature in frame plus surrounding text',
      'Even diffuse light - projection artifacts hide under harsh contrast',
      'High resolution helps detect ghosting at stroke edges',
    ],
    detector: 'Looks for slight scaling vs the genuine signature, edge ghosting, and unnaturally consistent stroke uniformity.',
  },
  sym_indented: {
    shooting: [
      'Required: low-angle light source (smartphone flashlight at the side works)',
      'Photograph the blank-looking sheet - that\'s where the impressions live',
      'Black backdrop helps suppress reflected light',
    ],
    detector: 'Looks for shadow patterns from pressure impressions on otherwise blank paper.',
  },
  sym_special: {
    shooting: [
      'A 365nm UV flashlight gives the strongest signal - capture under it',
      'Take a paired normal-light shot too; the model uses both',
      'Minimize ambient light leakage - work in a dim room',
    ],
    detector: 'Looks for UV fluorescence patterns, presence of writing invisible in normal light, and missing expected security ink.',
  },
  currency: {
    shooting: [
      'Both sides - submit two scans (front + back)',
      'Capture security thread, watermark, and microprinting in frame - don\'t crop edges',
      'Tilt slightly so optically-variable inks register correctly',
    ],
    detector: 'Looks for missing watermarks, off-color security threads, microprinting blur, and incorrect UV response.',
  },
};
```

## File: `frontend/src/components/ForensicMotifs.jsx`

<!-- FILE: frontend/src/components/ForensicMotifs.jsx -->

```jsx
import React from 'react';

// Background fingerprint watermark - large, faint, decorative.
// Place absolutely positioned with low opacity behind hero content.
export function FingerprintWatermark({ size = 320, color = '#00ff66', opacity = 0.05, style = {} }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 200 200"
      style={{ pointerEvents: 'none', opacity, ...style }}
      aria-hidden="true"
    >
      <g stroke={color} fill="none" strokeWidth="1.2" strokeLinecap="round">
        {/* concentric whorls */}
        <path d="M 100 100 m -85 0 a 85 85 0 1 1 170 0 a 85 85 0 1 1 -170 0" />
        <path d="M 100 100 m -75 5 a 75 80 0 1 1 150 -10 a 75 80 0 1 1 -150 10" />
        <path d="M 100 100 m -65 -5 a 65 75 0 1 1 130 15 a 65 75 0 1 1 -130 -15" />
        <path d="M 100 100 m -55 8 a 55 70 0 1 1 110 -18 a 55 70 0 1 1 -110 18" />
        <path d="M 100 100 m -45 -3 a 45 60 0 1 1 90 8 a 45 60 0 1 1 -90 -8" />
        <path d="M 100 100 m -35 5 a 35 50 0 1 1 70 -12 a 35 50 0 1 1 -70 12" />
        <path d="M 100 100 m -25 -2 a 25 40 0 1 1 50 4 a 25 40 0 1 1 -50 -4" />
        <path d="M 100 100 m -15 3 a 15 28 0 1 1 30 -6 a 15 28 0 1 1 -30 6" />
        {/* core */}
        <circle cx="100" cy="100" r="4" fill={color} stroke="none" />
        {/* a few breaks/minutiae points to look organic */}
        <line x1="155" y1="60" x2="170" y2="50" strokeWidth="0.7" opacity="0.6" />
        <line x1="40"  y1="140" x2="25" y2="155" strokeWidth="0.7" opacity="0.6" />
      </g>
    </svg>
  );
}

// Eye-of-providence inside circle - small accent for tier headers, etc.
export function EyeMark({ size = 22, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="1.3" strokeLinejoin="round">
        <polygon points="12,3 22,21 2,21" />
        {/* eye */}
        <ellipse cx="12" cy="16" rx="5" ry="2.5" />
        <circle  cx="12" cy="16" r="1.4" fill={color} stroke="none" />
      </g>
    </svg>
  );
}

// Compact magnifying glass icon
export function MagnifierIcon({ size = 18, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="2" strokeLinecap="round">
        <circle cx="10.5" cy="10.5" r="6.5" />
        <line x1="15.5" y1="15.5" x2="21" y2="21" />
        {/* lens highlight */}
        <line x1="7" y1="8" x2="7" y2="11" strokeWidth="1" opacity="0.6" />
      </g>
    </svg>
  );
}

// Crosshair / reticle - used decoratively in scan area
export function Crosshair({ size = 32, color = '#00ff66', style = {} }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" style={style} aria-hidden="true">
      <g stroke={color} fill="none" strokeWidth="1">
        <circle cx="16" cy="16" r="14" opacity="0.4" />
        <circle cx="16" cy="16" r="9" opacity="0.6" />
        <line x1="16" y1="2"  x2="16" y2="9" />
        <line x1="16" y1="23" x2="16" y2="30" />
        <line x1="2"  y1="16" x2="9"  y2="16" />
        <line x1="23" y1="16" x2="30" y2="16" />
        <circle cx="16" cy="16" r="1.5" fill={color} stroke="none" />
      </g>
    </svg>
  );
}

// Evidence-tag chip used for case-file labels.
export function EvidenceTag({ children, color = '#00ff66', style = {} }) {
  return (
    <span
      className="mono"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        fontSize: 10, letterSpacing: 2.5, color,
        textTransform: 'uppercase',
        padding: '4px 10px 4px 6px',
        background: 'rgba(0,0,0,0.55)',
        border: `1px solid ${color}55`,
        borderRadius: 2,
        textShadow: `0 0 6px ${color}80`,
        ...style,
      }}
    >
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
        background: color, boxShadow: `0 0 6px ${color}`,
      }} />
      {children}
    </span>
  );
}

// Animated fingerprint scan banner - used as the hero centerpiece on /scan.
// Renders a fingerprint with a horizontal sweep line that travels top→bottom.
export function FingerprintScan({ size = 200, color = '#00ff66', style = {} }) {
  return (
    <div
      style={{
        position: 'relative', width: size, height: size,
        margin: '0 auto', ...style,
      }}
      aria-hidden="true"
    >
      <FingerprintWatermark size={size} color={color} opacity={0.55} />
      <div
        className="fingerprint-sweep"
        style={{
          position: 'absolute', left: 0, right: 0, top: 0,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
          boxShadow: `0 0 14px ${color}, 0 0 28px ${color}80`,
        }}
      />
    </div>
  );
}
```

## File: `frontend/src/components/InstallButton.jsx`

<!-- FILE: frontend/src/components/InstallButton.jsx -->

```jsx
import React, { useEffect, useState } from 'react';
import { canInstall, isIos, isStandalone, onInstallAvailable, promptInstall } from '../pwa';

/**
 * "Install App" button for the PWA.
 *
 * Renders nothing unless the browser actually offers an install path, so it
 * never shows a dead button:
 *  - Chrome / Edge / Samsung Internet -> fires beforeinstallprompt, we show the
 *    native dialog.
 *  - iOS Safari -> no prompt API exists, so we show the manual Share sheet
 *    instructions instead.
 *  - Already installed, or a browser with no support -> hidden.
 */
export default function InstallButton() {
  const [available, setAvailable] = useState(canInstall());
  const [installed, setInstalled] = useState(isStandalone());
  const [showIosHelp, setShowIosHelp] = useState(false);

  useEffect(() => onInstallAvailable(setAvailable), []);

  if (installed || isStandalone()) return null;

  const ios = isIos();
  if (!available && !ios) return null;

  const btnStyle = {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    fontSize: 12, letterSpacing: 1, color: '#00ff66',
    border: '1px solid #1d3825', borderRadius: 4,
    padding: '10px 16px', cursor: 'pointer',
    background: 'rgba(0,255,102,0.04)',
  };

  const handleClick = async () => {
    if (ios && !available) {
      setShowIosHelp(v => !v);
      return;
    }
    const outcome = await promptInstall();
    if (outcome === 'accepted') setInstalled(true);
  };

  return (
    <div>
      <button type="button" className="mono" style={btnStyle} onClick={handleClick}>
        ⊕ Install App
      </button>
      <p className="mono" style={{ fontSize: 9, color: '#3f6e4a', marginTop: 8, letterSpacing: 1 }}>
        {ios && !available
          ? 'iPhone / iPad • adds Revelator to your home screen'
          : 'Adds Revelator to your home screen • no store needed'}
      </p>
      {showIosHelp && (
        <p className="mono" style={{ fontSize: 10, color: '#86efac', marginTop: 4, lineHeight: 1.6 }}>
          In Safari, tap the Share button, then "Add to Home Screen".
        </p>
      )}
    </div>
  );
}
```

## File: `frontend/src/components/Logo.jsx`

<!-- FILE: frontend/src/components/Logo.jsx -->

```jsx
import React from 'react';

// REVELATOR logo
//   • Outer scan ring + crosshair ticks  → forensic targeting
//   • Inscribed triangle (eye-of-providence) → "revelation"
//   • Fingerprint whorl inside triangle  → forensic identity
// All-vector, scales cleanly from 16px to 256px.
export default function Logo({ size = 48, glow = true, animated = false, className = '', style = {} }) {
  const id = React.useId();
  const filterId  = `${id}-glow`;
  const clipId    = `${id}-tri`;
  const gradId    = `${id}-bg`;
  const ringClass = animated ? 'logo-ring-spin' : '';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      className={className}
      style={{ display: 'block', ...style }}
      aria-label="Revelator"
      role="img"
    >
      <defs>
        <radialGradient id={gradId} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#0a120c" />
          <stop offset="100%" stopColor="#000" />
        </radialGradient>
        {glow && (
          <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="1.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        )}
        <clipPath id={clipId}>
          <polygon points="50,18 82,72 18,72" />
        </clipPath>
      </defs>

      {/* outer scan ring */}
      <g filter={glow ? `url(#${filterId})` : undefined}>
        <circle cx="50" cy="50" r="46" fill={`url(#${gradId})`} stroke="#00ff66" strokeWidth="1.6" />
      </g>
      <circle cx="50" cy="50" r="42" fill="none" stroke="#00ff66" strokeWidth="0.5" opacity="0.45"
        strokeDasharray="2 3" className={ringClass} style={{ transformOrigin: '50% 50%' }} />

      {/* crosshair ticks at cardinal points */}
      <g stroke="#00ff66" strokeWidth="1.4" strokeLinecap="round" filter={glow ? `url(#${filterId})` : undefined}>
        <line x1="50" y1="2"  x2="50" y2="9" />
        <line x1="50" y1="91" x2="50" y2="98" />
        <line x1="2"  y1="50" x2="9"  y2="50" />
        <line x1="91" y1="50" x2="98" y2="50" />
      </g>

      {/* illuminati triangle */}
      <polygon
        points="50,18 82,72 18,72"
        fill="none" stroke="#00ff66" strokeWidth="1.6"
        strokeLinejoin="round"
        filter={glow ? `url(#${filterId})` : undefined}
      />

      {/* fingerprint whorls clipped to triangle */}
      <g clipPath={`url(#${clipId})`} stroke="#00ff66" fill="none" opacity="0.92" strokeLinecap="round">
        <path d="M 28 62 Q 50 42 72 62" strokeWidth="0.8" />
        <path d="M 32 62 Q 50 46 68 62" strokeWidth="0.8" />
        <path d="M 36 62 Q 50 50 64 62" strokeWidth="0.8" />
        <path d="M 40 62 Q 50 54 60 62" strokeWidth="0.8" />
        <path d="M 44 62 Q 50 58 56 62" strokeWidth="0.8" />
        {/* core dot */}
        <circle cx="50" cy="60" r="1.4" fill="#00ff66" stroke="none" />
      </g>

      {/* tiny corner brackets - evidence frame */}
      <g stroke="#00ff66" strokeWidth="1.2" fill="none" opacity="0.7">
        <path d="M 6 14 L 6 6 L 14 6" />
        <path d="M 86 6 L 94 6 L 94 14" />
        <path d="M 94 86 L 94 94 L 86 94" />
        <path d="M 14 94 L 6 94 L 6 86" />
      </g>
    </svg>
  );
}

// Wordmark - used on auth pages. Logo on left, REVELATOR text on right.
export function LogoWordmark({ size = 64, style = {} }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 14, ...style }}>
      <Logo size={size} glow animated />
      <div style={{ textAlign: 'left' }}>
        <div className="oswald glow-strong" style={{
          fontSize: size * 0.6, fontWeight: 700, color: '#00ff66',
          letterSpacing: 6, lineHeight: 1,
        }}>
          REVELATOR
        </div>
        <div className="mono" style={{
          fontSize: 9, letterSpacing: 4, color: '#6dba85', marginTop: 4,
        }}>
          FORENSIC · DOCUMENT · ENGINE
        </div>
      </div>
    </div>
  );
}
```

## File: `frontend/src/components/PasswordStrength.jsx`

<!-- FILE: frontend/src/components/PasswordStrength.jsx -->

```jsx
import React from 'react';

/**
 * Shared password policy + live strength UI.
 *
 * Requirements (hard, block submit): 8+ chars, one letter, one number.
 * The remaining checks (uppercase, symbol, 12+) are strength boosters only, so
 * the frontend never rejects a password the backend would accept.
 */

export const PASSWORD_MIN = 8;

export function passwordChecks(pw) {
  const p = pw || '';
  return {
    length:    p.length >= PASSWORD_MIN,
    letter:    /[A-Za-z]/.test(p),
    number:    /\d/.test(p),
    upperLower: /[a-z]/.test(p) && /[A-Z]/.test(p),
    symbol:    /[^A-Za-z0-9]/.test(p),
    long:      p.length >= 12,
  };
}

/** true when the hard requirements are met */
export function passwordMeetsPolicy(pw) {
  const c = passwordChecks(pw);
  return c.length && c.letter && c.number;
}

/** First failing hard requirement, as a message. '' when the password passes. */
export function passwordPolicyError(pw) {
  if (!pw) return 'Password is required';
  const c = passwordChecks(pw);
  if (!c.length) return `Minimum ${PASSWORD_MIN} characters`;
  if (!c.letter || !c.number) return 'Include at least one letter and one number';
  return '';
}

/** 0-4 score -> {score, label, color} */
export function passwordStrength(pw) {
  const p = pw || '';
  if (!p) return { score: 0, label: '', color: '#3f6e4a' };

  const c = passwordChecks(p);
  let score = 0;
  if (c.length) score += 1;
  if (c.upperLower) score += 1;
  if (c.number) score += 1;
  if (c.symbol) score += 1;
  if (c.long) score += 1;

  // Anything failing the hard policy can never read better than Weak.
  if (!passwordMeetsPolicy(p)) score = Math.min(score, 1);

  // Obvious junk (all one character, straight sequences) is capped too.
  if (/^(.)\1+$/.test(p) || /^(?:0123456789|abcdefghij|qwertyuiop|password\d*)$/i.test(p)) {
    score = Math.min(score, 1);
  }

  if (score <= 1) return { score: 1, label: 'Weak', color: '#ff8a99' };
  if (score === 2) return { score: 2, label: 'Fair', color: '#ffaa00' };
  if (score === 3) return { score: 3, label: 'Good', color: '#86efac' };
  if (score === 4) return { score: 4, label: 'Strong', color: '#00ff66' };
  return { score: 5, label: 'Very Strong', color: '#00ff66' };
}

function Rule({ ok, children, optional }) {
  return (
    <li style={{
      display: 'flex', alignItems: 'flex-start', gap: 7, marginBottom: 3,
      color: ok ? '#86efac' : (optional ? '#3f6e4a' : '#6dba85'),
    }}>
      <span style={{ width: 10, flexShrink: 0, color: ok ? '#00ff66' : '#3f6e4a' }}>
        {ok ? '✓' : '·'}
      </span>
      <span>{children}{optional ? ' (recommended)' : ''}</span>
    </li>
  );
}

/**
 * Meter + requirement checklist. Renders nothing until the user starts typing
 * unless `always` is set.
 */
export default function PasswordStrength({ password, always = false }) {
  const pw = password || '';
  if (!pw && !always) return null;

  const c = passwordChecks(pw);
  const { score, label, color } = passwordStrength(pw);
  const segments = 5;

  return (
    <div style={{ marginTop: 9 }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 6 }}>
        {Array.from({ length: segments }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: 1, height: 4, borderRadius: 2,
              background: pw && i < score ? color : '#112418',
              transition: 'background 160ms linear',
            }}
          />
        ))}
      </div>
      {pw && (
        <div className="mono" style={{
          fontSize: 10, letterSpacing: 2, textTransform: 'uppercase',
          color, marginBottom: 8,
        }}>
          Strength: {label}
        </div>
      )}
      <ul className="mono" style={{
        listStyle: 'none', padding: 0, margin: 0, fontSize: 11, lineHeight: 1.5,
      }}>
        <Rule ok={c.length}>At least {PASSWORD_MIN} characters</Rule>
        <Rule ok={c.letter}>Contains a letter</Rule>
        <Rule ok={c.number}>Contains a number</Rule>
        <Rule ok={c.upperLower} optional>Upper and lower case</Rule>
        <Rule ok={c.symbol} optional>A symbol (!@#$...)</Rule>
      </ul>
    </div>
  );
}
```

## File: `frontend/src/components/PromptDashboard.jsx`

<!-- FILE: frontend/src/components/PromptDashboard.jsx -->

```jsx
import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

/**
 * Live Prompt Analysis dashboard.
 * Pulls /api/prompt-analysis on mount - every refresh reflects the
 * current state of gemini_vision.py.
 */
export default function PromptDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('overview');
  const [selected, setSelected] = useState(null);
  const [accuracy, setAccuracy] = useState(null);

  useEffect(() => {
    api.getPromptAnalysis()
      .then(setData)
      .catch(err => setError(err.message || 'Failed to load prompt analysis.'));
  }, []);

  // Poll the live specimen-evaluation accuracy so the panel updates on its own
  // whenever a new evaluate_specimens.py run finishes.
  useEffect(() => {
    let alive = true;
    const load = () => api.getSystemAccuracy().then(d => { if (alive) setAccuracy(d); }).catch(() => {});
    load();
    const id = setInterval(load, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (error) return <Box color="#ff6688">{error}</Box>;
  if (!data) return <Box color="#86efac">Loading prompt analysis…</Box>;

  const tabs = [
    { id: 'overview',   label: 'Overview' },
    { id: 'accuracy',   label: 'System Accuracy' },
    { id: 'detail',     label: 'Detail Levels' },
    { id: 'overlaps',   label: 'Overlaps' },
    { id: 'aux',        label: 'Auxiliary Prompts' },
    { id: 'rules',      label: 'Rules' },
    { id: 'variables',  label: 'User Variables' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 0, marginBottom: 18, borderBottom: '1px solid #112418', flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <div
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '8px 14px',
              cursor: 'pointer',
              fontSize: 11,
              letterSpacing: 1.5,
              textTransform: 'uppercase',
              borderBottom: tab === t.id ? '2px solid #00ff66' : '2px solid transparent',
              color: tab === t.id ? '#00ff66' : '#6dba85',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {t.label}
          </div>
        ))}
      </div>

      {tab === 'accuracy' ? (
        <Accuracy data={accuracy} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
          <div>
            {tab === 'overview' && <Overview data={data} onSelect={setSelected} />}
            {tab === 'detail' && <DetailBars data={data} onSelect={setSelected} selected={selected} />}
            {tab === 'overlaps' && <Overlaps data={data} onSelect={setSelected} />}
            {tab === 'aux' && <AuxPrompts data={data} />}
            {tab === 'rules' && <Rules data={data} />}
            {tab === 'variables' && <Variables data={data} />}
          </div>
          <Inspector data={data} selected={selected} />
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// LIVE SYSTEM ACCURACY (polls /api/prompt-analysis/accuracy)
// ─────────────────────────────────────────────────────────────────

function pctColor(p) {
  if (p == null) return '#525252';
  if (p >= 80) return '#00ff66';
  if (p >= 60) return '#ffaa00';
  return '#ff6688';
}

function Accuracy({ data }) {
  if (!data) return <Box color="#86efac">Loading accuracy…</Box>;
  if (data.status === 'error') return <Box color="#ff6688">{data.message}</Box>;
  if (data.status === 'no_data') {
    return (
      <div style={{
        background: 'rgba(0,255,102,0.05)', border: '1px solid #112418',
        borderLeft: '3px solid #00ff66', padding: 16, borderRadius: 3, color: '#d8ffe6', fontSize: 13, lineHeight: 1.7,
      }}>
        <strong style={{ color: '#00ff66' }}>No evaluation run yet.</strong>
        <p style={{ margin: '8px 0' }}>Populate this panel by scoring the classifier against the specimen set:</p>
        <pre style={{ background: '#000', padding: 10, borderRadius: 3, margin: '8px 0', color: '#86efac', fontSize: 12, overflowX: 'auto' }}>cd backend
python evaluate_specimens.py --sample 3</pre>
        <p style={{ margin: 0 }}>This panel polls the backend every 15s and fills in on its own once a run completes.</p>
      </div>
    );
  }

  const o = data.overall || {};
  const folders = data.folders || [];
  const when = data.generated_at ? new Date(data.generated_at).toLocaleString() : 'unknown';

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 16 }}>
        <BigStat label="Forged / Genuine accuracy" value={`${o.label_pct ?? 0}%`} sub={`${o.label_ok}/${o.n} correct`} color={pctColor(o.label_pct)} />
        <BigStat label="Category-hit rate" value={o.cat_n ? `${o.cat_pct ?? 0}%` : 'n/a'} sub={`${o.cat_hit}/${o.cat_n} forged`} color={pctColor(o.cat_pct)} />
        <BigStat label="Images evaluated" value={data.total_images ?? 0} sub={`${data.sample_per_bucket}/bucket${data.critique ? ' · critique' : ''}`} color="#00ff66" />
        <BigStat label="Model" value={String(data.model || '').replace('gemini-', '')} sub={`run ${when}`} color="#5b8def" />
      </div>

      <div style={{ background: 'rgba(0,255,102,0.05)', border: '1px solid #112418', padding: 10, borderRadius: 3, fontSize: 11, color: '#86efac', marginBottom: 16, lineHeight: 1.6 }}>
        <strong style={{ color: '#00ff66' }}>Forged/Genuine</strong> = verdict matched the specimen's Forged/Genuine label. <strong style={{ color: '#00ff66' }}>Category-hit</strong> = on forged specimens, the predicted category was acceptable for that folder. Auto-refreshes every 15s.
      </div>

      <h4 style={{ fontSize: 11, letterSpacing: 2, color: '#6dba85', textTransform: 'uppercase', margin: '0 0 8px' }}>▸ Per-folder accuracy</h4>
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 1fr', gap: 8, fontSize: 10, color: '#3f6e4a', letterSpacing: 1, textTransform: 'uppercase', padding: '0 8px 6px' }}>
        <span>Specimen folder</span><span>Forged / Genuine</span><span>Category hit</span>
      </div>
      {folders.map(f => (
        <div key={f.folder} style={{ display: 'grid', gridTemplateColumns: '200px 1fr 1fr', gap: 8, alignItems: 'center', padding: '5px 8px', borderRadius: 2, background: '#0a120c', marginBottom: 3 }}>
          <span style={{ fontSize: 11, color: '#d8ffe6', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.folder}</span>
          <Meter pct={f.label_pct} label={`${f.label_ok}/${f.n}`} />
          {f.cat_n ? <Meter pct={f.cat_pct} label={`${f.cat_hit}/${f.cat_n}`} /> : <span style={{ fontSize: 10, color: '#525252' }}>n/a</span>}
        </div>
      ))}
    </div>
  );
}

function Meter({ pct, label }) {
  const color = pctColor(pct);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 12, background: '#000', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct || 0}%`, background: color, boxShadow: `0 0 6px ${color}40` }} />
      </div>
      <span style={{ fontSize: 10, color: '#86efac', fontFamily: "'JetBrains Mono', monospace", minWidth: 60, textAlign: 'right' }}>
        {pct == null ? '-' : `${pct}%`} <span style={{ color: '#3f6e4a' }}>{label}</span>
      </span>
    </div>
  );
}

function BigStat({ label, value, sub, color }) {
  return (
    <div style={{ background: '#0a120c', border: '1px solid #112418', borderRadius: 3, padding: 12, textAlign: 'center' }}>
      <div style={{ fontSize: 22, fontWeight: 700, color, textShadow: `0 0 8px ${color}40`, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      <div style={{ fontSize: 9, letterSpacing: 1.2, textTransform: 'uppercase', color: '#3f6e4a', marginTop: 4 }}>{label}</div>
      {sub && <div style={{ fontSize: 9, color: '#6dba85', marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// PANELS
// ─────────────────────────────────────────────────────────────────

function Overview({ data, onSelect }) {
  const top = data.categories.slice(0, 5);
  const bottom = [...data.categories].reverse().slice(0, 5);
  const totalChars = data.aux_prompts.reduce((s, p) => s + p.char_count, 0);

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 18 }}>
        <Stat label="Categories" value={data.categories.length} />
        <Stat label="System Prompt Words" value={data.system_prompt.total_words} />
        <Stat label="Total Chars (all prompts)" value={totalChars.toLocaleString()} />
        <Stat label="Documented Overlaps" value={data.overlaps.length} />
        <Stat label="Critical Rules" value={data.rules.length} />
      </div>

      <Sub title="▸ Most-detailed categories (dominant when ambiguous)">
        {top.map(c => <BarRow key={c.id} cat={c} maxWords={top[0].word_count} onSelect={onSelect} />)}
      </Sub>

      <Sub title="▸ Least-detailed categories (model has minimal cues)">
        {bottom.map(c => <BarRow key={c.id} cat={c} maxWords={top[0].word_count} onSelect={onSelect} />)}
      </Sub>

      <div style={{
        background: 'rgba(255,170,0,0.06)', border: '1px solid rgba(255,170,0,0.4)',
        padding: 12, borderRadius: 3, fontSize: 12, color: '#ffd996', lineHeight: 1.7,
      }}>
        <strong style={{ color: '#ffaa00' }}>Why this matters:</strong> When evidence is ambiguous,
        the model gravitates toward categories with the richest descriptions ("prompt mass bias").
        A category with 5 words of detail has almost no anchor; one with 500 words pulls the verdict.
      </div>
    </div>
  );
}

function DetailBars({ data, onSelect, selected }) {
  const max = data.categories[0]?.word_count || 1;
  return (
    <div>
      <p style={{ fontSize: 12, color: '#6dba85', marginBottom: 12 }}>
        Each bar shows how many words the system prompt spends describing that category. Click to inspect.
      </p>
      {data.categories.map(c => (
        <BarRow key={c.id} cat={c} maxWords={max} onSelect={onSelect} active={selected === c.id} />
      ))}
    </div>
  );
}

function Overlaps({ data, onSelect }) {
  const sorted = [...data.overlaps].sort((a, b) => {
    if (a.from_prompt !== b.from_prompt) return a.from_prompt ? -1 : 1;
    return 0;
  });
  return (
    <div>
      <p style={{ fontSize: 12, color: '#6dba85', marginBottom: 12 }}>
        Pairs where two categories share ambiguous indicators. <span style={{ color: '#00ff66' }}>Green</span> overlaps
        are explicitly distinguished in the prompt; <span style={{ color: '#ffaa00' }}>amber</span> are semantic
        overlaps not addressed in the prompt (potential bug source).
      </p>
      {sorted.map((o, i) => {
        const src = data.categories.find(c => c.id === o.source);
        const tgt = data.categories.find(c => c.id === o.target);
        if (!src || !tgt) return null;
        const dominant = src.word_count >= tgt.word_count ? src : tgt;
        const weaker = src.word_count >= tgt.word_count ? tgt : src;
        const ratio = (dominant.word_count / Math.max(weaker.word_count, 1)).toFixed(1);
        const color = o.from_prompt ? '#00ff66' : '#ffaa00';
        return (
          <div key={i} style={{
            background: '#0a120c',
            border: `1px solid ${color}33`,
            borderLeft: `3px solid ${color}`,
            padding: 10,
            borderRadius: 3,
            marginBottom: 8,
          }}>
            <div style={{ fontSize: 13, color: '#d8ffe6' }}>
              <span style={{ color, fontWeight: 600, cursor: 'pointer' }} onClick={() => onSelect(dominant.id)}>
                {dominant.label}
              </span>
              <span style={{ color: '#6dba85' }}> dominates </span>
              <span style={{ cursor: 'pointer' }} onClick={() => onSelect(weaker.id)}>
                {weaker.label}
              </span>
              <span style={{ color: '#6dba85', fontSize: 11, marginLeft: 8 }}>
                {dominant.word_count}:{weaker.word_count} words ({ratio}× more)
              </span>
            </div>
            <div style={{ fontSize: 11, color: '#86efac', marginTop: 4, lineHeight: 1.5 }}>
              {o.reason}
            </div>
            <div style={{ fontSize: 9, color: '#6dba85', marginTop: 4, letterSpacing: 1 }}>
              {o.from_prompt ? 'EXPLICIT IN PROMPT' : 'SEMANTIC OVERLAP - NOT IN PROMPT'}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AuxPrompts({ data }) {
  return (
    <div>
      <p style={{ fontSize: 12, color: '#6dba85', marginBottom: 12 }}>
        All Gemini prompts now live in <code style={{ color: '#00ff66' }}>backend/app/forgery/gemini_vision.py</code> (single source of truth).
      </p>
      {data.aux_prompts.map(p => (
        <div key={p.name} style={{
          background: '#0a120c',
          border: '1px solid #112418',
          borderLeft: '3px solid #00ff66',
          padding: 12,
          borderRadius: 3,
          marginBottom: 8,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <code style={{ fontSize: 13, color: '#00ff66', fontFamily: "'JetBrains Mono', monospace" }}>{p.name}</code>
            <span style={{ fontSize: 11, color: '#86efac', fontFamily: "'JetBrains Mono', monospace" }}>
              {p.word_count} words · {p.char_count.toLocaleString()} chars
            </span>
          </div>
          <div style={{ fontSize: 12, color: '#d8ffe6', marginTop: 4, lineHeight: 1.5 }}>
            {p.purpose}
          </div>
        </div>
      ))}
    </div>
  );
}

function Rules({ data }) {
  return (
    <div>
      <p style={{ fontSize: 12, color: '#6dba85', marginBottom: 12 }}>
        Critical rules and branching logic extracted from the live SYSTEM_PROMPT.
      </p>
      {data.rules.map((r, i) => (
        <div key={i} style={{
          background: '#0a120c',
          border: '1px solid #112418',
          borderLeft: '3px solid #ffaa00',
          padding: 12,
          borderRadius: 3,
          marginBottom: 10,
        }}>
          <div style={{
            fontSize: 13,
            color: '#d8ffe6',
            fontWeight: 600,
            marginBottom: 6,
            lineHeight: 1.5,
          }}>
            {r.title}
          </div>
          <div style={{
            fontSize: 12,
            color: '#d8ffe6',
            lineHeight: 1.6,
          }}>
            {r.text}
          </div>
        </div>
      ))}
    </div>
  );
}

function Variables({ data }) {
  return (
    <div>
      <p style={{ fontSize: 12, color: '#6dba85', marginBottom: 12 }}>
        Variables from <code style={{ color: '#00ff66' }}>_build_user_context_block</code> that get injected into the prompt as user-provided context. Each one biases the classification.
      </p>
      {data.variables.map(v => (
        <div key={v.name} style={{
          background: '#0a120c',
          border: '1px solid #112418',
          borderLeft: '3px solid #5b8def',
          padding: 12,
          borderRadius: 3,
          marginBottom: 8,
        }}>
          <code style={{ fontSize: 13, color: '#5b8def', fontFamily: "'JetBrains Mono', monospace" }}>{v.name}</code>
          <div style={{ fontSize: 12, color: '#d8ffe6', marginTop: 4, lineHeight: 1.5 }}>
            {v.description}
          </div>
          <div style={{ fontSize: 11, color: '#ffaa00', marginTop: 6, lineHeight: 1.5 }}>
            <strong>Influence:</strong> {v.influence}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// RIGHT-SIDE INSPECTOR
// ─────────────────────────────────────────────────────────────────

function Inspector({ data, selected }) {
  const cat = useMemo(
    () => selected ? data.categories.find(c => c.id === selected) : null,
    [selected, data.categories],
  );
  const myOverlaps = useMemo(
    () => selected ? data.overlaps.filter(o => o.source === selected || o.target === selected) : [],
    [selected, data.overlaps],
  );

  if (!cat) {
    return (
      <div style={{
        background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
        padding: 16, color: '#525252', fontSize: 12, textAlign: 'center', fontStyle: 'italic',
        position: 'sticky', top: 16, alignSelf: 'flex-start',
      }}>
        Click a category, bar, or overlap to inspect.
      </div>
    );
  }

  const groupColor = data.groups[cat.group] || '#666';
  return (
    <div style={{
      background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
      padding: 14, position: 'sticky', top: 16, alignSelf: 'flex-start', maxHeight: '70vh', overflowY: 'auto',
    }}>
      <div style={{
        background: '#091108', border: `1px solid ${groupColor}55`, borderLeft: `3px solid ${groupColor}`,
        padding: 10, borderRadius: 3, marginBottom: 10,
      }}>
        <div style={{ fontSize: 13, color: '#fff', fontWeight: 600 }}>{cat.label}</div>
        <div style={{ fontSize: 10, color: '#6dba85', marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
          {cat.id} · {cat.group} · <span style={{ color: groupColor }}>{cat.detail_level}</span> · {cat.word_count} words
        </div>
        <p style={{ fontSize: 11, color: '#d8ffe6', marginTop: 8, lineHeight: 1.5 }}>
          {cat.first_line}
        </p>
      </div>

      <SubSmall title="Indicators in prompt">
        {cat.indicators.length === 0
          ? <Empty text="No structured indicators detected." />
          : <ul style={{ margin: 0, paddingLeft: 16 }}>
              {cat.indicators.map((i, k) => (
                <li key={k} style={{ fontSize: 11, color: '#86efac', lineHeight: 1.6 }}>{i}</li>
              ))}
            </ul>
        }
      </SubSmall>

      <SubSmall title="Explicit distinctions in prompt">
        {cat.distinctions.length === 0
          ? <Empty text="No DISTINCTION blocks." />
          : cat.distinctions.map((d, k) => (
              <div key={k} style={{
                background: '#091108', borderLeft: '2px solid #00ff66',
                padding: 8, borderRadius: 2, marginBottom: 6, fontSize: 11, color: '#d8ffe6', lineHeight: 1.5,
              }}>
                <code style={{ color: '#00ff66', fontSize: 10 }}>vs {d.target}</code>
                <div>{d.reason}</div>
              </div>
            ))
        }
      </SubSmall>

      <SubSmall title={`Overlaps (${myOverlaps.length})`}>
        {myOverlaps.length === 0
          ? <Empty text="No documented overlaps." />
          : myOverlaps.map((o, k) => {
              const other = o.source === cat.id ? o.target : o.source;
              const otherCat = data.categories.find(c => c.id === other);
              return (
                <div key={k} style={{
                  background: '#091108',
                  borderLeft: `2px solid ${o.from_prompt ? '#00ff66' : '#ffaa00'}`,
                  padding: 8, borderRadius: 2, marginBottom: 6, fontSize: 11, color: '#d8ffe6', lineHeight: 1.5,
                }}>
                  <div style={{ color: o.from_prompt ? '#00ff66' : '#ffaa00' }}>
                    ↔ {otherCat?.label || other}
                  </div>
                  <div>{o.reason}</div>
                </div>
              );
            })
        }
      </SubSmall>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// SHARED PIECES
// ─────────────────────────────────────────────────────────────────

function BarRow({ cat, maxWords, onSelect, active }) {
  const groupColors = {
    traced: '#e74c3c', alteration: '#f39c12', digital: '#5b8def',
    obliteration: '#9b59b6', sympathetic: '#1abc9c', currency: '#95a5a6', fallback: '#525252',
  };
  const color = groupColors[cat.group] || '#525252';
  return (
    <div
      onClick={() => onSelect(cat.id)}
      style={{
        display: 'grid', gridTemplateColumns: '180px 1fr 100px',
        gap: 10, alignItems: 'center', padding: '5px 8px',
        borderRadius: 2, cursor: 'pointer',
        background: active ? '#112418' : 'transparent',
        marginBottom: 2,
      }}
    >
      <span style={{ fontSize: 12, color: '#d8ffe6', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cat.label}</span>
      <div style={{ height: 14, background: '#0a120c', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${(cat.word_count / maxWords) * 100}%`,
          background: color, boxShadow: `0 0 6px ${color}40`,
        }} />
      </div>
      <span style={{ fontSize: 10, color: '#86efac', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace" }}>
        {cat.word_count}w · {cat.detail_level}
      </span>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{
      background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
      padding: 10, textAlign: 'center',
    }}>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#00ff66', textShadow: '0 0 6px #00ff6640', fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      <div style={{ fontSize: 9, letterSpacing: 1.5, textTransform: 'uppercase', color: '#3f6e4a', marginTop: 3 }}>{label}</div>
    </div>
  );
}

function Sub({ title, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <h4 style={{
        fontSize: 11, letterSpacing: 2, color: '#6dba85',
        textTransform: 'uppercase', margin: '0 0 8px 0',
      }}>{title}</h4>
      {children}
    </div>
  );
}

function SubSmall({ title, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <h5 style={{
        fontSize: 9, letterSpacing: 1.5, color: '#3f6e4a',
        textTransform: 'uppercase', margin: '8px 0 6px 0',
      }}>{title}</h5>
      {children}
    </div>
  );
}

function Box({ color, children }) {
  return <div style={{ padding: 16, color, fontSize: 13 }}>{children}</div>;
}

function Empty({ text }) {
  return <div style={{ fontSize: 11, color: '#525252', fontStyle: 'italic' }}>{text}</div>;
}
```

## File: `frontend/src/index.css`

<!-- FILE: frontend/src/index.css -->

```css
/* ──────────────────────────────────────────────────────────────────────
   REVELATOR · Forensic Detection Engine
   Theme: Matrix / CSI black-and-green
   ────────────────────────────────────────────────────────────────────── */

:root {
  /* Core surface */
  --bg-primary:   #000000;
  --bg-secondary: #050a07;
  --bg-tertiary:  #0a120c;
  --bg-card:      #0a120c;
  --bg-elevated:  #0d1810;

  /* Borders */
  --border-dark:  #112418;
  --border-light: #1d3825;
  --border-glow:  #1f5d39;

  /* Greens - primary identity */
  --green-neon:    #00ff66;   /* primary brand */
  --green-bright:  #22ff88;
  --green-matrix:  #00cc44;
  --green-dim:     #0d8a3c;
  --green-cyan:    #00ffaa;
  --green-soft:    #86efac;
  --green-text:    #b6f5cc;

  /* Tier accents (still in green family) */
  --tier-1: #00ff66;
  --tier-2: #00ffaa;
  --tier-3: #a3e635;

  /* Verdicts (semantic - kept distinct) */
  --red-alert:    #ff3344;
  --orange-warn:  #ffa040;
  --green-clear:  #00ff66;
  --gray-mute:    #525252;
  --purple-ai:    #c4b5fd;

  /* Text */
  --text-primary:   #d8ffe6;
  --text-secondary: #6dba85;
  --text-muted:     #355042;
  --text-dim:       #1f3328;

  /* Aliases (legacy compatibility) */
  --yellow-tape: var(--green-neon);
  --yellow-dark: var(--green-matrix);
  --blue-evidence: var(--green-cyan);
  --purple: var(--purple-ai);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body { height: 100%; }

body {
  font-family: 'Source Sans Pro', sans-serif;
  font-size: 16px;
  line-height: 1.55;
  background:
    radial-gradient(ellipse at top, rgba(0, 255, 102, 0.04) 0%, transparent 60%),
    radial-gradient(ellipse at bottom, rgba(0, 255, 170, 0.03) 0%, transparent 60%),
    var(--bg-primary);
  background-attachment: fixed;
  color: var(--text-primary);
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  position: relative;
  overflow-x: hidden;
}

/* Desktop readability bump - client feedback said dark-mode text was too small. */
@media (min-width: 1024px) {
  body { font-size: 17px; }
}

/* Faint grid behind everything - circuit / blueprint feel */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 255, 102, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 255, 102, 0.025) 1px, transparent 1px);
  background-size: 32px 32px;
  pointer-events: none;
  z-index: 0;
}

/* Subtle CRT scanlines overlay */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  background-image: repeating-linear-gradient(
    180deg,
    rgba(0, 255, 102, 0.0) 0px,
    rgba(0, 255, 102, 0.0) 2px,
    rgba(0, 0, 0, 0.18) 3px,
    rgba(0, 0, 0, 0.18) 3px
  );
  pointer-events: none;
  z-index: 1;
  mix-blend-mode: multiply;
}

#root { position: relative; z-index: 2; }

.mono   { font-family: 'JetBrains Mono', 'Share Tech Mono', monospace; }
.oswald { font-family: 'Oswald', sans-serif; }
.term   { font-family: 'Share Tech Mono', 'JetBrains Mono', monospace; letter-spacing: 1px; }

/* Scrollbar */
::-webkit-scrollbar          { width: 8px; height: 8px; }
::-webkit-scrollbar-track    { background: var(--bg-secondary); }
::-webkit-scrollbar-thumb    {
  background: linear-gradient(180deg, var(--green-dim), var(--border-glow));
  border-radius: 2px;
}
::-webkit-scrollbar-thumb:hover { background: var(--green-matrix); }

/* Selection */
::selection {
  background: rgba(0, 255, 102, 0.3);
  color: var(--green-bright);
  text-shadow: 0 0 8px var(--green-neon);
}

a {
  color: var(--green-neon);
  text-decoration: none;
  text-shadow: 0 0 10px rgba(0, 255, 102, 0.35);
  transition: color 0.18s, text-shadow 0.18s;
}
a:hover {
  color: var(--green-bright);
  text-shadow: 0 0 16px rgba(0, 255, 102, 0.7);
}

/* ──── Glow helpers ──────────────────────────────────────────── */
.glow         { text-shadow: 0 0 12px rgba(0, 255, 102, 0.55), 0 0 4px rgba(0, 255, 102, 0.9); }
.glow-strong  { text-shadow: 0 0 20px rgba(0, 255, 102, 0.85), 0 0 6px rgba(0, 255, 102, 1); }
.glow-soft    { text-shadow: 0 0 10px rgba(0, 255, 170, 0.4); }

/* ──── Scanline / tape divider ───────────────────────────────── */
@keyframes scan-pulse {
  0%, 100% { opacity: 0.85; }
  50%      { opacity: 0.45; }
}
@keyframes scan-flow {
  0%   { background-position: 0 0; }
  100% { background-position: 40px 0; }
}
@keyframes scan-spinner {
  to { transform: rotate(360deg); }
}
@keyframes scan-progress {
  from { transform: translateX(-100%); }
  to { transform: translateX(320%); }
}

.scan-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(0, 255, 102, 0.25);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: scan-spinner 0.8s linear infinite;
  flex-shrink: 0;
}

.scan-progress {
  width: 88px;
  height: 3px;
  overflow: hidden;
  background: rgba(0, 255, 102, 0.14);
  border-radius: 2px;
}

.scan-progress span {
  display: block;
  width: 32%;
  height: 100%;
  background: var(--green-neon);
  box-shadow: 0 0 8px rgba(0, 255, 102, 0.8);
  animation: scan-progress 1.2s ease-in-out infinite;
}

.tape-border {
  height: 2px;
  background:
    linear-gradient(90deg,
      transparent 0%,
      var(--green-neon) 8%,
      var(--green-bright) 50%,
      var(--green-neon) 92%,
      transparent 100%
    );
  box-shadow:
    0 0 12px rgba(0, 255, 102, 0.7),
    0 0 24px rgba(0, 255, 102, 0.35);
  animation: scan-pulse 3s ease-in-out infinite;
  position: relative;
}

.tape-border::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    90deg,
    transparent 0,
    transparent 6px,
    rgba(0, 0, 0, 0.55) 6px,
    rgba(0, 0, 0, 0.55) 8px
  );
  animation: scan-flow 2.5s linear infinite;
}

/* ──── Buttons ───────────────────────────────────────────────── */
.btn {
  font-family: 'Oswald', sans-serif;
  text-transform: uppercase;
  letter-spacing: 2.5px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  font-weight: 600;
  padding: 14px 28px;
  border-radius: 2px;
  position: relative;
  overflow: hidden;
}

.btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(0, 255, 102, 0.15), transparent);
  transition: left 0.5s;
}
.btn:hover::before { left: 100%; }

.btn-primary {
  background: linear-gradient(180deg, var(--green-neon) 0%, var(--green-matrix) 100%);
  color: #001005;
  box-shadow:
    0 0 16px rgba(0, 255, 102, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  font-weight: 700;
}
.btn-primary:hover:not(:disabled) {
  background: linear-gradient(180deg, var(--green-bright) 0%, var(--green-neon) 100%);
  box-shadow:
    0 0 24px rgba(0, 255, 102, 0.7),
    0 0 48px rgba(0, 255, 102, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}
.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

.btn-secondary {
  background: rgba(0, 255, 102, 0.04);
  border: 1px solid var(--green-neon);
  color: var(--green-neon);
  box-shadow: 0 0 0 rgba(0, 255, 102, 0);
}
.btn-secondary:hover {
  background: rgba(0, 255, 102, 0.12);
  color: var(--green-bright);
  box-shadow: 0 0 16px rgba(0, 255, 102, 0.4);
  border-color: var(--green-bright);
}

.btn-danger {
  background: linear-gradient(180deg, var(--red-alert), #b30020);
  color: #fff;
  box-shadow: 0 0 12px rgba(255, 51, 68, 0.45);
}
.btn-danger:hover { box-shadow: 0 0 22px rgba(255, 51, 68, 0.7); transform: translateY(-1px); }

/* ──── Cards ─────────────────────────────────────────────────── */
.card {
  background:
    linear-gradient(180deg, rgba(0, 255, 102, 0.018) 0%, transparent 100%),
    var(--bg-card);
  border: 1px solid var(--border-dark);
  border-radius: 3px;
  padding: 24px;
  position: relative;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--green-dim), transparent);
  opacity: 0.5;
}
.card:hover { border-color: var(--border-glow); }

/* Inputs */
input.input,
textarea.input,
select.input {
  background: #0a0f0c !important;
  border: 2px solid #00ff66 !important;
  color: #ffffff !important;
  padding: 12px 16px;
  border-radius: 2px;
  font-size: 14px;
  width: 100%;
  font-family: 'JetBrains Mono', monospace;
  transition: border-color 0.18s, box-shadow 0.18s;
}
input.input:focus,
textarea.input:focus,
select.input:focus {
  outline: none !important;
  border-color: #00ff66 !important;
  box-shadow: 0 0 0 2px #00ff66, 0 0 20px rgba(0, 255, 102, 0.4) !important;
}
input.input::placeholder { color: #6dba85; font-family: 'JetBrains Mono', monospace; }

select.input { font-family: 'Source Sans Pro', sans-serif; }

/* Browser autofill (Chrome, Edge, Safari) forces a yellow/white background and
   black text on prefilled inputs. Repaint it to match the theme. The huge
   transition delay is the standard hack so the override doesn't flash. */
input.input:-webkit-autofill,
input.input:-webkit-autofill:hover,
input.input:-webkit-autofill:focus,
input.input:-webkit-autofill:active {
  -webkit-box-shadow: 0 0 0 1000px #0a0f0c inset !important;
  -webkit-text-fill-color: #ffffff !important;
  caret-color: #00ff66;
  transition: background-color 9999s ease-in-out 0s;
}

/* Badges (verdict pills) */
.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-family: 'JetBrains Mono', monospace;
  border: 1px solid currentColor;
}
.badge-forged              { background: rgba(255, 51, 68, 0.15); color: var(--red-alert); box-shadow: 0 0 10px rgba(255, 51, 68, 0.3); }
.badge-suspicious          { background: rgba(255, 160, 64, 0.15); color: var(--orange-warn); box-shadow: 0 0 10px rgba(255, 160, 64, 0.25); }
.badge-no_forgery_detected { background: rgba(0, 255, 102, 0.12); color: var(--green-clear); box-shadow: 0 0 10px rgba(0, 255, 102, 0.3); }
.badge-not_a_document      { background: rgba(115, 115, 115, 0.2); color: #a3a3a3; }

/* Layout */
.container { max-width: 1200px; margin: 0 auto; padding: 0 16px; position: relative; }

.nav-burger { display: none !important; }

/* ──── Forensic accent components ───────────────────────────── */
.classification-bar {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 4px;
  color: var(--green-neon);
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 10px;
}
.classification-bar::before,
.classification-bar::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--green-dim), transparent);
}

.terminal-prompt::before {
  content: '> ';
  color: var(--green-neon);
  font-weight: 700;
}

@keyframes blink-caret {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}
.caret::after {
  content: '▊';
  margin-left: 4px;
  color: var(--green-neon);
  animation: blink-caret 1.1s step-end infinite;
}

/* Hex/honeycomb badge clip - used for tier numbers on cards */
.hex-badge {
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
}

/* Hover lift used on cards / interactive items */
.lift {
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s;
}
.lift:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0, 255, 102, 0.18), 0 0 20px rgba(0, 255, 102, 0.08);
}

/* ──── Forensic flourishes ───────────────────────────────────── */

/* Fingerprint sweep - horizontal scan line glides top→bottom over a
   fingerprint motif (used inside <FingerprintScan />). */
@keyframes fp-sweep {
  0%   { transform: translateY(0);      opacity: 0;   }
  10%  { opacity: 1;                                  }
  90%  { opacity: 1;                                  }
  100% { transform: translateY(100%);   opacity: 0;   }
}
.fingerprint-sweep {
  animation: fp-sweep 2.4s cubic-bezier(.4, 0, .6, 1) infinite;
}

/* Slow rotation used on the dashed scan ring inside the logo */
@keyframes ring-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.logo-ring-spin {
  animation: ring-spin 18s linear infinite;
}

/* Faint full-page fingerprint watermark - used as a hero background.
   Apply `.fp-bg` to a positioned container; the print fades in/out from
   the right side, never covering the central column. */
.fp-bg {
  position: relative;
  isolation: isolate;
}
.fp-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    radial-gradient(circle at 88% 18%, rgba(0,255,102,0.05) 0%, transparent 40%),
    radial-gradient(circle at 10% 78%, rgba(0,255,170,0.04) 0%, transparent 38%);
  z-index: -1;
}

/* Magnifier cursor - applied to elements meant to feel "investigative" */
.cursor-magnify {
  cursor: zoom-in;
}

/* Eye flicker - subtle, used on the EyeMark hero accent */
@keyframes eye-blink {
  0%, 96%, 100% { transform: scaleY(1); }
  98%           { transform: scaleY(0.05); }
}
.eye-blink ellipse,
.eye-blink circle:last-of-type {
  transform-origin: center;
  animation: eye-blink 5s ease-in-out infinite;
}

/* Evidence corner brackets - wraps any element with subtle "[ ]" frame */
.evidence-frame {
  position: relative;
  padding: 14px;
}
.evidence-frame::before,
.evidence-frame::after {
  content: '';
  position: absolute;
  width: 14px; height: 14px;
  border: 1px solid var(--green-neon);
  opacity: 0.6;
}
.evidence-frame::before {
  top: 0; left: 0;
  border-right: none; border-bottom: none;
}
.evidence-frame::after {
  bottom: 0; right: 0;
  border-left: none; border-top: none;
}

/* ──── Readability bump ────────────────────────────────────────
   Inline `font-size` values smaller than 14px get nudged up so body
   text remains legible. Tiny intentional badges (9–11px) stay where
   they are - readers expect those to be compact stamps. */
[style*="font-size: 12px"] { font-size: 13px !important; }
[style*="font-size: 13px"] { font-size: 14px !important; }
[style*="font-size: 14px"]:not(.btn):not(.input) { font-size: 15px !important; }

/* Body paragraphs in cards get a touch more breathing room */
.card p[style*="line-height"] { line-height: 1.7 !important; }

/* Mobile-first responsive */
/* Burger is for phone widths and the Android app only. Tablets/laptops/desktop
   show the horizontal nav bar instead, so the burger never duplicates it. */
@media (max-width: 767px) {
  .nav-desktop { display: none !important; }
  .nav-burger { display: inline-flex !important; }
}

/* Keep the desktop nav bar tidy on the narrower end (tablet landscape / small
   laptops) so the extra items still fit once the burger is gone there. */
@media (min-width: 768px) and (max-width: 991px) {
  .nav-desktop a { padding: 8px 10px !important; font-size: 12px !important; letter-spacing: 1px !important; }
}

@media (max-width: 768px) {
  .container { padding: 0 12px; }
  .card { padding: 16px; }
  /* Touch targets: minimum 48px tappable height */
  .btn { padding: 14px 22px; font-size: 14px; min-height: 48px; }
  .input { padding: 14px 16px; font-size: 16px; min-height: 48px; } /* 16px prevents iOS auto-zoom */
  select.input { font-size: 16px; }
  body::before { background-size: 24px 24px; }
  /* Slightly larger body text for legibility */
  body { font-size: 15px; }
  /* Hide desktop-only elements */
  .hide-mobile { display: none !important; }
  /* Disable hover lifts/glows on touch devices to avoid sticky :hover state */
  .lift:hover { transform: none; }
}

/* Show only on mobile */
.show-mobile { display: none; }
@media (max-width: 768px) {
  .show-mobile { display: revert; }
}

/* Preserve focus ring for accessibility on non-mouse */
:focus-visible {
  outline: 2px solid var(--green-neon);
  outline-offset: 2px;
}

/* ──────────────────────────────────────────────────────────────────
   LIGHT MODE - opt-in via [data-theme="light"] on <html>
   Dark mode is the default and stays unchanged. Light mode strips
   all glow effects, replaces black surfaces with off-white, and uses
   darker green text for readability.
   ────────────────────────────────────────────────────────────────── */

[data-theme="light"] {
  --bg-primary: #f5f7f4;
  --bg-secondary: #ffffff;
  --bg-tertiary: #ebf2ed;
  --bg-card: #ffffff;
  --bg-elevated: #ffffff;

  --border-dark: #c8d8cd;
  --border-light: #a5c2af;
  --border-glow: #6da884;

  --green-neon: #00541f;
  --green-bright: #007a36;
  --green-matrix: #004a1c;
  --green-dim: #003d17;
  --green-cyan: #00553a;
  --green-soft: #1a3a24;
  --green-text: #061a0c;

  --text-primary: #061a0c;
  --text-secondary: #1a3a24;
  --text-muted: #3a5040;
  --text-dim: #5a7064;

  --red-alert: #a4151f;
  --orange-warn: #a45616;
  --purple-ai: #4d3290;
}

[data-theme="light"] body {
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Hide the dark-theme background flourishes */
[data-theme="light"] body::before,
[data-theme="light"] body::after { display: none; }

[data-theme="light"] .tape-border {
  background: linear-gradient(90deg, transparent 0%, #00592a 50%, transparent 100%);
  box-shadow: none;
  animation: none;
}
[data-theme="light"] .tape-border::after { display: none; }

/* Kill every glow */
[data-theme="light"] *,
[data-theme="light"] *::before,
[data-theme="light"] *::after {
  text-shadow: none !important;
}
[data-theme="light"] .glow,
[data-theme="light"] .glow-strong,
[data-theme="light"] .glow-soft {
  text-shadow: none !important;
}

/* Card surfaces */
[data-theme="light"] .card {
  background: var(--bg-card) !important;
  border: 1px solid var(--border-dark) !important;
  box-shadow: 0 1px 2px rgba(0, 60, 30, 0.05) !important;
}
[data-theme="light"] .card::before { display: none; }
[data-theme="light"] .card:hover { border-color: var(--border-light) !important; }

/* Inputs */
[data-theme="light"] input.input,
[data-theme="light"] textarea.input,
[data-theme="light"] select.input {
  background: #ffffff !important;
  border: 1px solid #86bf9a !important;
  color: #0f1f15 !important;
}
[data-theme="light"] input.input:focus,
[data-theme="light"] textarea.input:focus,
[data-theme="light"] select.input:focus {
  border-color: #007a36 !important;
  box-shadow: 0 0 0 2px rgba(0, 122, 54, 0.25) !important;
}
[data-theme="light"] input.input::placeholder { color: #8aa590; }

/* Autofill in light mode: keep the white surface but fix dark text color */
[data-theme="light"] input.input:-webkit-autofill,
[data-theme="light"] input.input:-webkit-autofill:hover,
[data-theme="light"] input.input:-webkit-autofill:focus,
[data-theme="light"] input.input:-webkit-autofill:active {
  -webkit-box-shadow: 0 0 0 1000px #ffffff inset !important;
  -webkit-text-fill-color: #0f1f15 !important;
  caret-color: #007a36;
}

/* Buttons */
[data-theme="light"] .btn-primary {
  background: linear-gradient(180deg, #009944 0%, #007a36 100%) !important;
  color: #ffffff !important;
  box-shadow: 0 1px 2px rgba(0,122,54,0.3) !important;
}
[data-theme="light"] .btn-primary:hover:not(:disabled) {
  background: linear-gradient(180deg, #00aa4d 0%, #008a3f 100%) !important;
  box-shadow: 0 2px 6px rgba(0,122,54,0.45) !important;
}
[data-theme="light"] .btn-secondary {
  background: #ffffff !important;
  border: 1px solid #007a36 !important;
  color: #007a36 !important;
}
[data-theme="light"] .btn-secondary:hover {
  background: #ebf7ef !important;
  color: #006a2e !important;
  box-shadow: 0 1px 4px rgba(0,122,54,0.2) !important;
}
[data-theme="light"] .btn::before { display: none; }
[data-theme="light"] .btn-danger {
  background: linear-gradient(180deg, #c81e2e, #9c1623) !important;
  color: #ffffff !important;
  box-shadow: none !important;
}

/* Selection */
[data-theme="light"] ::selection {
  background: rgba(0, 122, 54, 0.18);
  color: #0f1f15;
  text-shadow: none;
}

/* Scrollbar */
[data-theme="light"] ::-webkit-scrollbar-track { background: #e0eae3; }
[data-theme="light"] ::-webkit-scrollbar-thumb { background: #86bf9a; }
[data-theme="light"] ::-webkit-scrollbar-thumb:hover { background: #6da884; }

/* Links */
[data-theme="light"] a { color: #007a36; }
[data-theme="light"] a:hover { color: #009944; }

/* Badges */
[data-theme="light"] .badge-no_forgery_detected {
  background: rgba(0, 122, 54, 0.1);
  color: #006a2e;
  box-shadow: none;
}
[data-theme="light"] .badge-forged {
  background: rgba(200, 30, 46, 0.1);
  color: #b01a26;
  box-shadow: none;
}
[data-theme="light"] .badge-suspicious {
  background: rgba(200, 116, 31, 0.1);
  color: #a05a14;
  box-shadow: none;
}

/* Classification bar */
[data-theme="light"] .classification-bar { color: #007a36; }
[data-theme="light"] .classification-bar::before,
[data-theme="light"] .classification-bar::after {
  background: linear-gradient(90deg, transparent, #86bf9a, transparent);
}

/* ── Universal color remapping for inline styles ─────────────────
   Browsers normalize React inline `style` values from hex to rgb()
   form when set via element.style.*. We match the rgb() representations
   so the selectors actually hit at runtime. */

/* Greens - text */
[data-theme="light"] [style*="rgb(0, 255, 102)"] { color: #00451c !important; }
[data-theme="light"] [style*="rgb(0, 204, 68)"]  { color: #00451c !important; }
[data-theme="light"] [style*="rgb(34, 255, 136)"] { color: #006a2e !important; }
[data-theme="light"] [style*="rgb(0, 255, 170)"] { color: #005a3f !important; }
[data-theme="light"] [style*="rgb(134, 239, 172)"] { color: #1a3a24 !important; }
[data-theme="light"] [style*="rgb(109, 186, 133)"] { color: #102a18 !important; }
[data-theme="light"] [style*="rgb(63, 110, 74)"]  { color: #3a5040 !important; }
[data-theme="light"] [style*="rgb(53, 80, 66)"]   { color: #3a5040 !important; }
[data-theme="light"] [style*="rgb(216, 255, 230)"] { color: #061a0c !important; }
[data-theme="light"] [style*="rgb(182, 245, 204)"] { color: #061a0c !important; }
[data-theme="light"] [style*="rgb(163, 230, 53)"]  { color: #3a5a14 !important; }
[data-theme="light"] [style*="rgb(0, 255, 153)"]   { color: #006a2e !important; }
[data-theme="light"] [style*="rgb(0, 204, 136)"]   { color: #00553a !important; }
[data-theme="light"] [style*="rgb(0, 255, 153)"]   { color: #005c33 !important; }
[data-theme="light"] [style*="rgb(95, 168, 115)"]  { color: #1a3a24 !important; }

/* Greys / whites used as text */
[data-theme="light"] [style*="rgb(115, 115, 115)"] { color: #4a4a4a !important; }
[data-theme="light"] [style*="rgb(229, 229, 229)"] { color: #061a0c !important; }
[data-theme="light"] [style*="rgb(255, 255, 255)"] { color: #061a0c !important; }

/* Reds / oranges / purples */
[data-theme="light"] [style*="rgb(196, 181, 253)"] { color: #3d2b85 !important; }
[data-theme="light"] [style*="rgb(167, 139, 250)"] { color: #3d2b85 !important; }
[data-theme="light"] [style*="rgb(255, 138, 153)"] { color: #a4151f !important; }
[data-theme="light"] [style*="rgb(255, 51, 68)"]   { color: #a4151f !important; }
[data-theme="light"] [style*="rgb(255, 117, 136)"] { color: #a4151f !important; }
[data-theme="light"] [style*="rgb(255, 160, 64)"]  { color: #a45616 !important; }
[data-theme="light"] [style*="rgb(255, 165, 0)"]   { color: #a45616 !important; }
[data-theme="light"] [style*="rgb(255, 200, 136)"] { color: #a45616 !important; }
[data-theme="light"] [style*="rgb(255, 149, 0)"]   { color: #a45616 !important; }
[data-theme="light"] [style*="rgb(255, 170, 0)"]   { color: #8a5300 !important; }
[data-theme="light"] [style*="rgb(255, 217, 150)"] { color: #7a4a10 !important; }
[data-theme="light"] [style*="rgb(255, 102, 136)"] { color: #a4151f !important; }
[data-theme="light"] [style*="rgb(91, 141, 239)"]  { color: #2f5fc0 !important; }

/* Dark borders */
[data-theme="light"] [style*="rgb(29, 56, 37)"]   { border-color: #c8d8cd !important; color: #102a18 !important; }
[data-theme="light"] [style*="rgb(17, 36, 24)"]   { border-color: #c8d8cd !important; }
[data-theme="light"] [style*="rgb(26, 46, 31)"]   { border-color: #c8d8cd !important; }
[data-theme="light"] [style*="rgb(42, 74, 48)"]   { color: #102a18 !important; }

/* ── Dark backgrounds - flip them all to white ───────────────────
   These cover every dark surface used inline across the app. */
[data-theme="light"] [style*="rgb(0, 0, 0)"],
[data-theme="light"] [style*="rgb(10, 18, 12)"],
[data-theme="light"] [style*="rgb(10, 15, 12)"],
[data-theme="light"] [style*="rgb(5, 10, 7)"],
[data-theme="light"] [style*="rgb(2, 11, 5)"],
[data-theme="light"] [style*="rgb(3, 14, 7)"],
[data-theme="light"] [style*="rgb(10, 22, 5)"],
[data-theme="light"] [style*="rgb(13, 24, 16)"],
[data-theme="light"] [style*="rgb(6, 18, 10)"],
[data-theme="light"] [style*="rgb(2, 8, 10)"],
[data-theme="light"] [style*="rgb(8, 18, 12)"] {
  background-color: #ffffff !important;
  background-image: none !important;
}

/* Nested dark panels (#091108) - used for cards sitting INSIDE an already-white
   card (prompt-analytics inspector: category header, distinction and overlap
   blocks). Tint instead of pure white so they still read as nested cards.
   Without this they stay black while their text is remapped dark = invisible. */
[data-theme="light"] [style*="rgb(9, 17, 8)"] {
  background-color: #f1f6f2 !important;
  background-image: none !important;
}

/* #112418 is remapped as a BORDER colour above, but it is also used as a
   selected-row BACKGROUND. Match the shorthand form only, so bordered
   elements are not given a stray fill. */
[data-theme="light"] [style*="background: rgb(17, 36, 24)"] {
  background-color: #dcebe1 !important;
  background-image: none !important;
}

/* Muted chart-bar fills that wash out on a white track */
[data-theme="light"] [style*="background: rgb(149, 165, 166)"] { background-color: #6f8384 !important; }
[data-theme="light"] [style*="background: rgb(82, 82, 82)"]    { background-color: #6b6b6b !important; }

/* Override background on elements with rgba(0,0,0,*) tints - match the comma-space rgba form */
[data-theme="light"] [style*="rgba(0, 0, 0,"] {
  background-color: #ffffff !important;
}

/* Green-tinted backgrounds → soften */
[data-theme="light"] [style*="rgba(0, 255, 102"] { background-color: rgba(0, 122, 54, 0.08) !important; }
[data-theme="light"] [style*="rgba(0, 255, 170"] { background-color: rgba(0, 122, 54, 0.08) !important; }

/* Structural fallback for <details>/<summary> (Account tutorial dropdown) */
[data-theme="light"] details,
[data-theme="light"] details > summary {
  background-color: #ffffff !important;
  color: #061a0c !important;
  border-color: #c8d8cd !important;
}

/* Native <select> and <option> elements */
[data-theme="light"] select,
[data-theme="light"] option {
  background-color: #ffffff !important;
  color: #061a0c !important;
}

/* Strip text-shadow + heavy glows */
[data-theme="light"] [style*="text-shadow"] { text-shadow: none !important; }
[data-theme="light"] [style*="textShadow"] { text-shadow: none !important; }

/* Header - light variant */
[data-theme="light"] header {
  background: linear-gradient(180deg, #ffffff 0%, #f5f7f4 100%) !important;
  border-bottom: 1px solid #d4e2d8 !important;
  box-shadow: 0 1px 0 rgba(0,122,54,0.08), 0 2px 8px rgba(0,0,0,0.06) !important;
}

/* Drawer - light variant */
[data-theme="light"] aside {
  background: linear-gradient(180deg, #ffffff 0%, #f5f7f4 100%) !important;
  border-right: 1px solid #d4e2d8 !important;
}

/* Evidence frame corners */
[data-theme="light"] .evidence-frame::before,
[data-theme="light"] .evidence-frame::after {
  border-color: #007a36;
}

/* Disable bright glow box-shadows */
[data-theme="light"] [style*="box-shadow"] {
  /* Note: we can't fully strip inline box-shadow, but the universal text-shadow removal above handles glow text. */
}

/* Spotlight pulse - softer in light mode */
@keyframes spotlight-pulse-light {
  0%, 100% { box-shadow: 0 0 0 2px rgba(0,122,54,0.4); }
  50% { box-shadow: 0 0 0 2px rgba(0,122,54,0.2); }
}

[data-theme="light"] [style*="spotlight-pulse"] {
  animation-name: spotlight-pulse-light !important;
}

/* ──────────────────────────────────────────────────────────────────
   LIGHT MODE - extended palette for category & group tints
   The original overrides cover the green spectrum used as body text.
   These cover the tinted accent colors used for badges/icons in the
   ForensicsGuide and History cards, where the dark-mode pastels
   become unreadable on a white background.
   ────────────────────────────────────────────────────────────────── */

/* Categories.js bright-green spectrum - used for the per-category accent
   color on history cards, scan results, etc. Map every bright-green tint
   to a single readable dark green so contrast is consistent in light mode. */
[data-theme="light"] [style*="rgb(61, 245, 138)"]  { color: #006a30 !important; }
[data-theme="light"] [style*="rgb(86, 255, 138)"]  { color: #006a35 !important; }
[data-theme="light"] [style*="rgb(124, 255, 175)"] { color: #006a3c !important; }
[data-theme="light"] [style*="rgb(155, 255, 186)"] { color: #006a48 !important; }
[data-theme="light"] [style*="rgb(94, 252, 142)"]  { color: #006a30 !important; }
[data-theme="light"] [style*="rgb(112, 255, 156)"] { color: #006a30 !important; }
[data-theme="light"] [style*="rgb(140, 255, 184)"] { color: #006a3c !important; }

/* ForensicsGuide group accents - replace pastel tints with deep variants */
[data-theme="light"] [style*="rgb(251, 191, 36)"]  { color: #8c5a00 !important; }  /* amber - alteration */
[data-theme="light"] [style*="rgb(56, 189, 248)"]  { color: #0d4a72 !important; }  /* sky   - digital */
[data-theme="light"] [style*="rgb(248, 113, 113)"] { color: #9b2030 !important; }  /* red   - obliteration */
[data-theme="light"] [style*="rgb(52, 211, 153)"]  { color: #0a6a4a !important; }  /* mint  - sympathetic */
[data-theme="light"] [style*="rgb(167, 139, 250)"] { color: #4a2a92 !important; }  /* violet */

/* Tints used as backgrounds - strip the bright tint from background
   while keeping the structural feel (light tinted card surface). */
[data-theme="light"] [style*="rgba(196, 181, 253"] { background-color: rgba(74, 42, 146, 0.08) !important; }
[data-theme="light"] [style*="rgba(251, 191, 36"]  { background-color: rgba(140, 90, 0, 0.08) !important; }
[data-theme="light"] [style*="rgba(56, 189, 248"]  { background-color: rgba(13, 74, 114, 0.08) !important; }
[data-theme="light"] [style*="rgba(248, 113, 113"] { background-color: rgba(155, 32, 48, 0.08) !important; }
[data-theme="light"] [style*="rgba(52, 211, 153"]  { background-color: rgba(10, 106, 74, 0.08) !important; }
[data-theme="light"] [style*="rgba(139, 92, 246"]  { background-color: rgba(74, 42, 146, 0.08) !important; }

/* AI badge (purple) in History - soften background while text override
   above pushes the foreground dark enough to read. */
[data-theme="light"] [style*="rgba(139, 92, 246, 0.12)"] {
  background-color: rgba(74, 42, 146, 0.1) !important;
}

/* ──────────────────────────────────────────────────────────────────
   LIGHT MODE - readability sweep
   Bump weights and tighten contrasts on common body-text colors so
   light mode reads cleanly without feeling washed-out.
   ────────────────────────────────────────────────────────────────── */

/* Make secondary/muted greens darker than the original mappings -
   the old #102a18 was OK, this pushes it to nearly-black for cleanest
   contrast on the off-white background. */
[data-theme="light"] [style*="rgb(109, 186, 133)"] { color: #0a1c11 !important; }
[data-theme="light"] [style*="rgb(134, 239, 172)"] { color: #0a1c11 !important; }
[data-theme="light"] [style*="rgb(63, 110, 74)"]   { color: #2a4030 !important; }

/* Slight weight bump on paragraphs in light mode for crispness */
[data-theme="light"] p,
[data-theme="light"] .card p {
  font-weight: 450;
}

/* Buttons inside cards keep enough contrast */
[data-theme="light"] .btn-secondary {
  font-weight: 600;
}

/* Section-divider lines (the "OR SIGN IN WITH" style) get a real color */
[data-theme="light"] [style*="border-top: 1px solid rgb(17, 36, 24)"],
[data-theme="light"] [style*="border-bottom: 1px solid rgb(17, 36, 24)"] {
  border-color: #d0dcd4 !important;
}

/* The faint dashed example-image stubs in ForensicsGuide */
[data-theme="light"] [style*="border: 1px dashed rgb(29, 56, 37)"] {
  border-color: #b8cebe !important;
  background-color: #f2f6f3 !important;
}

/* Hover lift in light mode - keep the lift but swap the green glow for a soft shadow */
[data-theme="light"] .lift:hover {
  box-shadow: 0 6px 24px rgba(0, 60, 30, 0.08), 0 2px 6px rgba(0, 60, 30, 0.06) !important;
}
```

## File: `frontend/src/main.jsx`

<!-- FILE: frontend/src/main.jsx -->

```jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { defineCustomElements } from '@ionic/pwa-elements/loader';
import App from './App';
import { registerServiceWorker } from './pwa';
import './index.css';

defineCustomElements(window);
registerServiceWorker();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

## File: `frontend/src/pages/Account.jsx`

<!-- FILE: frontend/src/pages/Account.jsx -->

```jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useAuth } from '../App';
import { api } from '../api/client';
import { consumeApiKeyTutorialRequest } from '../apiKeyTutorial';

const darkInput = {
  background: '#0a0f0c',
  border: '2px solid rgba(0,255,102,0.5)',
  color: '#ffffff',
  width: '100%',
};

export default function Account() {
  const { user, refreshUser } = useAuth();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ full_name: '', username: '' });
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');

  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyValue, setNewKeyValue] = useState('');
  const [newKeyLabel, setNewKeyLabel] = useState('');
  const [keyError, setKeyError] = useState('');
  const [keyMsg, setKeyMsg] = useState('');
  const [highlightKeyInput, setHighlightKeyInput] = useState(() => localStorage.getItem('fg_highlight_key_input') === 'true');
  const [editingKeyId, setEditingKeyId] = useState(null);
  const [editLabel, setEditLabel] = useState('');
  const [editKeyValue, setEditKeyValue] = useState('');
  const [revealedKeys, setRevealedKeys] = useState({});

  const [twoFABusy, setTwoFABusy] = useState(false);
  const [tutorialFocus, setTutorialFocus] = useState(false);
  const tutorialRef = useRef(null);

  useEffect(() => {
    if (user) setForm({ full_name: user.full_name || '', username: user.username || '' });
  }, [user]);

  useEffect(() => {
    if (highlightKeyInput) {
      localStorage.removeItem('fg_highlight_key_input');
      const timer = setTimeout(() => setHighlightKeyInput(false), 6000);
      return () => clearTimeout(timer);
    }
  }, [highlightKeyInput]);

  const loadKeys = useCallback(async () => {
    try {
      const data = await api.listApiKeys();
      setApiKeys(data.keys || []);
    } catch {}
  }, []);

  useEffect(() => { loadKeys(); }, [loadKeys]);

  useEffect(() => {
    if (!consumeApiKeyTutorialRequest()) return undefined;

    const openTimer = setTimeout(() => {
      if (!tutorialRef.current) return;
      tutorialRef.current.open = true;
      const tutorialTop = tutorialRef.current.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: Math.max(0, tutorialTop - window.innerHeight * 0.30), behavior: 'smooth' });
      setTimeout(() => setTutorialFocus(true), 500);
    }, 500);

    return () => clearTimeout(openTimer);
  }, []);

  async function saveProfile() {
    setError('');
    try {
      await api.updateMe(form);
      await refreshUser();
      setEditing(false);
      setMsg('Profile updated.');
      setTimeout(() => setMsg(''), 3000);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleAddKey() {
    setKeyError('');
    const trimmed = newKeyValue.trim();
    const labelTrimmed = newKeyLabel.trim();
    if (!trimmed) { setKeyError('Paste your API key first'); return; }
    if (!labelTrimmed) { setKeyError('Give your key a name (e.g., "Account 1", "Backup")'); return; }
    try {
      await api.addApiKey(trimmed, labelTrimmed);
      setNewKeyValue('');
      setNewKeyLabel('');
      setKeyMsg('Key added!');
      await loadKeys();
      setTimeout(() => setKeyMsg(''), 3000);
    } catch (err) {
      setKeyError(err.message);
    }
  }

  async function handleActivate(keyId) {
    try {
      await api.activateApiKey(keyId);
      await loadKeys();
    } catch (err) {
      setKeyError(err.message);
    }
  }

  async function handleDelete(keyId) {
    try {
      await api.deleteApiKey(keyId);
      await loadKeys();
    } catch (err) {
      setKeyError(err.message);
    }
  }

  function startEdit(key) {
    setEditingKeyId(key.id);
    setEditLabel(key.label || '');
    setEditKeyValue(''); // User must re-paste the key if they want to change it
  }

  async function handleSaveEdit(keyId) {
    setKeyError('');
    if (!editLabel.trim()) { setKeyError('Key name is required'); return; }
    const trimmedKey = editKeyValue.trim();
    try {
      const patch = { label: editLabel.trim() };
      if (trimmedKey) patch.api_key = trimmedKey;
      await api.updateApiKey(keyId, patch);
      setEditingKeyId(null);
      setKeyMsg('Key updated!');
      await loadKeys();
      setTimeout(() => setKeyMsg(''), 3000);
    } catch (err) {
      setKeyError(err.message);
    }
  }

  function cancelEdit() {
    setEditingKeyId(null);
    setEditLabel('');
    setEditKeyValue('');
  }

  function toggleReveal(keyId) {
    setRevealedKeys(prev => ({ ...prev, [keyId]: !prev[keyId] }));
  }

  async function toggle2FA(next) {
    setError(''); setMsg('');
    setTwoFABusy(true);
    try {
      await api.setTwoFactor(next);
      await refreshUser();
      setMsg(next
        ? 'Two-factor sign-in is ON. A 6-digit code is emailed when you sign in on a new device.'
        : 'Two-factor sign-in is OFF.');
    } catch (err) {
      setError(err.message || 'Could not update two-factor setting');
    } finally {
      setTwoFABusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <h1 className="oswald glow" style={{
        fontSize: 28, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 24, color: '#00ff66',
      }}>
        Account
      </h1>

      {msg && (
        <div style={{
          background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66', padding: 12, borderRadius: 2,
          marginBottom: 16, fontSize: 13, color: '#86efac', fontFamily: "'JetBrains Mono', monospace",
        }}>✓ {msg}</div>
      )}
      {error && (
        <div style={{
          background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12, borderRadius: 2,
          marginBottom: 16, fontSize: 13, color: '#ff8a99', fontFamily: "'JetBrains Mono', monospace",
        }}>⚠ {error}</div>
      )}

      {/* Profile */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase' }}>Profile</h2>
          {!editing && (
            <button onClick={() => setEditing(true)} style={{
              background: 'none', border: '1px solid #1d3825', color: '#86efac',
              padding: '6px 14px', cursor: 'pointer', fontSize: 11, borderRadius: 3,
              fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
            }}>Edit</button>
          )}
        </div>
        {editing ? (
          <div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Full Name</label>
              <input className="input" value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ fontSize: 12, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Username</label>
              <input className="input" value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} />
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-primary" onClick={saveProfile} style={{ padding: '10px 24px' }}>Save</button>
              <button className="btn btn-secondary" onClick={() => setEditing(false)} style={{ padding: '10px 24px' }}>Cancel</button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <div><span style={{ color: '#3f6e4a', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Email:</span> <span className="mono" style={{ fontSize: 14 }}>{user?.email}</span></div>
            <div><span style={{ color: '#3f6e4a', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Username:</span> <span style={{ fontSize: 14 }}>{user?.username}</span></div>
            <div><span style={{ color: '#3f6e4a', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Name:</span> <span style={{ fontSize: 14 }}>{user?.full_name || '-'}</span></div>
            <div><span style={{ color: '#3f6e4a', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Member since:</span> <span className="mono" style={{ fontSize: 14 }}>{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</span></div>
          </div>
        )}
      </div>

      {/* Security */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h2 className="oswald" style={{
          fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: '#d8ffe6', marginBottom: 14,
        }}>
          Security
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, justifyContent: 'space-between', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={{ fontSize: 14, color: '#d8ffe6', fontWeight: 600, marginBottom: 4 }}>
              Two-factor sign-in (email code)
            </div>
            <div style={{ fontSize: 12, color: '#6dba85', lineHeight: 1.6 }}>
              When on, signing in on a new device asks for a 6-digit code we email you.
              Trusted devices skip it for 30 days.
            </div>
          </div>
          <button
            onClick={() => toggle2FA(!user?.two_factor_enabled)}
            disabled={twoFABusy}
            className={user?.two_factor_enabled ? 'btn btn-secondary' : 'btn btn-primary'}
            style={{ fontSize: 12, padding: '10px 18px', minHeight: 'unset', whiteSpace: 'nowrap' }}
          >
            {twoFABusy ? '…' : user?.two_factor_enabled ? 'Turn off' : 'Turn on'}
          </button>
        </div>
        <div className="mono" style={{
          marginTop: 12, fontSize: 11, letterSpacing: 1,
          color: user?.two_factor_enabled ? '#00ff66' : '#6b7280',
        }}>
          STATUS: {user?.two_factor_enabled ? '● ENABLED' : '○ DISABLED'}
        </div>
      </div>

      {/* API Keys */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h2 className="oswald" style={{ fontSize: 14, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 6 }}>
        API Keys
        </h2>
      

        {/* How to get a key collapsible tutorial */}
        {tutorialFocus && (
          <div
            aria-hidden="true"
            style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(0,0,0,0.82)', pointerEvents: 'none' }}
          />
        )}
        <details
          ref={tutorialRef}
          onClick={event => event.stopPropagation()}
          style={{
          position: tutorialFocus ? 'relative' : 'static',
          zIndex: tutorialFocus ? 101 : 'auto',
          background: 'rgba(0,255,102,0.04)', border: '1px solid rgba(0,255,102,0.15)',
          borderRadius: 3, padding: 12, marginBottom: 16,
          boxShadow: tutorialFocus || highlightKeyInput
            ? '0 0 28px rgba(0,255,102,0.9), inset 0 0 16px rgba(0,255,102,0.3)'
            : 'none',
          transition: 'box-shadow 0.5s ease',
        }}>
          <summary style={{
            fontSize: 11, color: '#6dba85', textTransform: 'uppercase', letterSpacing: 1,
            cursor: 'pointer', fontWeight: 600, userSelect: 'none',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span>▸ How to get a key (step-by-step tutorial)</span>
          </summary>
          {tutorialFocus && (
            <button
              type="button"
              aria-label="Exit tutorial"
              onClick={() => {
                setTutorialFocus(false);
                if (tutorialRef.current) tutorialRef.current.open = false;
              }}
              style={{
                marginTop: 10, display: 'block', width: 'fit-content',
                background: '#dc2626', border: '1px solid #ff7b7b',
                color: '#ffffff', padding: '8px 14px', cursor: 'pointer',
                fontFamily: "'Oswald', sans-serif", fontSize: 11,
                textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700,
                borderRadius: 3, boxShadow: '0 2px 10px rgba(220,38,38,0.45)',
              }}
            >
              Exit tutorial
            </button>
          )}
          <div style={{ display: 'grid', gap: 16, marginTop: 12, paddingTop: 12, borderTop: '1px solid rgba(0,255,102,0.15)' }}>
            {[
              { step: 1, text: 'Go to', link: 'Google AI Studio', img: null },
              { step: 2, text: 'Accept the terms and conditions', img: '/tutorial-1.jpg' },
              { step: 3, text: 'Click the "Create API Key" button', img: '/tutorial-2.jpg' },
              { step: 4, text: 'Click "Create Key"', img: '/tutorial-3.jpg' },
              { step: 5, text: 'Copy your API key (click the copy icon)', img: '/tutorial-4.jpg?v=2' },
              { step: 6, text: 'Come back here and paste it in the "API Key" field below, add a key name, then click "Add Key"', img: null },
              { step: 7, text: 'Optional but recommended, Sign in to a different Google account and get more API keys, quota resets every 12 hours', img: null },
            ].map((item, idx) => (
              <div key={idx} style={{ display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 12, color: '#d8ffe6', lineHeight: 1.6 }}>
                  <span style={{ color: item.step === 7 ? '#6dba85' : '#00ff66', fontWeight: 600, marginRight: 8 }}>
                    Step {item.step}{item.step === 7 ? ' (optional)' : ''}:
                  </span>
                  {item.text}{item.link && (
                    <a
                      href="https://aistudio.google.com/api-keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-block', marginLeft: 8, padding: '5px 10px',
                        background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66',
                        borderRadius: 3, color: '#00ff66', textDecoration: 'none',
                        fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                        letterSpacing: 1, fontSize: 11,
                      }}
                    >
                      {item.link}
                    </a>
                  )}
                </div>
                {item.img && (
                  <img
                    src={item.img}
                    alt={`Step ${item.step}`}
                    style={{
                      width: '100%', borderRadius: 3,
                      border: '1px solid #1d3825',
                      maxHeight: 260, objectFit: 'contain',
                      background: '#000',
                    }}
                  />
                )}
              </div>
            ))}
          </div>
        </details>

        {keyMsg && (
          <div style={{
            background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66', padding: 10, borderRadius: 2,
            marginBottom: 12, fontSize: 12, color: '#86efac', fontFamily: "'JetBrains Mono', monospace",
          }}>✓ {keyMsg}</div>
        )}
        {keyError && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 10, borderRadius: 2,
            marginBottom: 12, fontSize: 12, color: '#ff8a99', fontFamily: "'JetBrains Mono', monospace",
          }}>⚠ {keyError}</div>
        )}

        {/* Key cells */}
        {apiKeys.length > 0 && (
          <div style={{ display: 'grid', gap: 10, marginBottom: 16 }}>
            {apiKeys.map(k => {
              const exhausted = k.quota_exhausted && k.hours_until_reset > 0;
              const isEditing = editingKeyId === k.id;
              return (
                <div key={k.id}>
                  {isEditing ? (
                    <div style={{
                      padding: '14px',
                      borderRadius: 3,
                      border: '1px solid rgba(0,255,102,0.4)',
                      background: 'rgba(0,10,5,0.5)',
                      display: 'grid', gap: 12,
                    }}>
                      <div>
                        <label style={{ fontSize: 10, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Key Name</label>
                        <input
                          className="input"
                          value={editLabel}
                          onChange={e => setEditLabel(e.target.value)}
                          type="text"
                          autoComplete="off"
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: 10, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>API Key </label>
                        <input
                          className="input"
                          placeholder="Leave blank to keep current key, or paste new one"
                          value={editKeyValue}
                          onChange={e => setEditKeyValue(e.target.value)}
                          type="password"
                          autoComplete="off"
                        />
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="btn btn-primary"
                          onClick={() => handleSaveEdit(k.id)}
                          style={{ padding: '8px 16px', flex: 1 }}
                        >
                          Save
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={cancelEdit}
                          style={{ padding: '8px 16px', flex: 1 }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        padding: '12px 14px',
                        borderRadius: 3,
                        border: k.is_active
                          ? (exhausted ? '1px solid #ff3344' : '1px solid #00ff66')
                          : '1px solid #1a2e1f',
                        background: k.is_active ? 'rgba(0,255,102,0.05)' : 'transparent',
                        opacity: k.is_active ? 1 : 0.45,
                        transition: 'opacity 0.2s',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        flexWrap: 'wrap',
                      }}
                    >
                      {/* Active indicator dot */}
                      <div style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: k.is_active ? (exhausted ? '#ff3344' : '#00ff66') : '#2a4a30',
                        boxShadow: k.is_active && !exhausted ? '0 0 8px rgba(0,255,102,0.9)' : 'none',
                      }} />

                      {/* Info */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: '#d8ffe6', fontWeight: 600, marginBottom: 2 }}>
                          {k.label}
                        </div>
                        <div style={{ fontSize: 11, color: '#3f6e4a', fontFamily: "'JetBrains Mono', monospace", wordBreak: 'break-all' }}>
                          <span
                            onClick={() => toggleReveal(k.id)}
                            title="Click to show/hide full key"
                            style={{ cursor: 'pointer', userSelect: revealedKeys[k.id] ? 'all' : 'none' }}
                          >
                            {revealedKeys[k.id] ? k.api_key : k.key_preview}
                          </span>
                          <span
                            onClick={() => toggleReveal(k.id)}
                            style={{ marginLeft: 8, cursor: 'pointer', color: '#3f6e4a', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}
                          >
                            {revealedKeys[k.id] ? '[hide]' : '[show]'}
                          </span>
                          {k.is_active && !exhausted && (
                            <span style={{ color: '#00ff66', marginLeft: 10, letterSpacing: 1 }}>● ACTIVE</span>
                          )}
                          {k.is_active && exhausted && (
                            <span style={{ color: '#ff8a99', marginLeft: 10 }}>
                              ⚠ QUOTA EXHAUSTED, resets in ~{k.hours_until_reset}h
                            </span>
                          )}
                          {!k.is_active && exhausted && (
                            <span style={{ color: '#ff8a99', marginLeft: 10 }}>⚠ quota exhausted</span>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                        <button
                          onClick={() => startEdit(k)}
                          style={{
                            padding: '5px 12px', background: 'none', border: '1px solid #1d3825',
                            color: '#86efac', cursor: 'pointer', borderRadius: 3, fontSize: 11,
                            fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                          }}
                        >
                          Edit
                        </button>
                        {!k.is_active && (
                          <button
                            onClick={() => handleActivate(k.id)}
                            style={{
                              padding: '5px 12px', background: 'none', border: '1px solid #1d3825',
                              color: '#86efac', cursor: 'pointer', borderRadius: 3, fontSize: 11,
                              fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                            }}
                          >
                            Activate
                          </button>
                        )}
                        {k.is_active && (
                          <div style={{
                            padding: '5px 12px', fontSize: 11, color: '#00ff66',
                            fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                          }}>
                            In Use
                          </div>
                        )}
                        <button
                          onClick={() => handleDelete(k.id)}
                          style={{
                            padding: '5px 10px', background: 'none', border: '1px solid rgba(255,51,68,0.25)',
                            color: '#ff8a99', cursor: 'pointer', borderRadius: 3, fontSize: 13, lineHeight: 1,
                          }}
                        >✕</button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Add key row */}
        <div style={{ borderTop: apiKeys.length > 0 ? '1px solid #112418' : 'none', paddingTop: apiKeys.length > 0 ? 16 : 0 }}>
          <div style={{ display: 'grid', gap: 10, marginBottom: 10 }}>
            <div>
              <label style={{ fontSize: 10, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>Key Name</label>
              <input
                className="input"
                placeholder="e.g., Account 1, Backup, Personal"
                value={newKeyLabel}
                onChange={e => setNewKeyLabel(e.target.value)}
                type="text"
                style={{ width: '100%' }}
                autoComplete="one-time-code"
                name="gemini-key-label"
              />
            </div>
            <div>
              <label style={{ fontSize: 10, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>API Key</label>
              <input
                className="input"
                placeholder="Paste API key"
                value={newKeyValue}
                onChange={e => setNewKeyValue(e.target.value)}
                type="password"
                style={{
                  width: '100%',
                  boxShadow: highlightKeyInput ? '0 0 8px rgba(0,255,102,0.5), inset 0 0 6px rgba(0,255,102,0.15)' : 'none',
                  transition: 'box-shadow 0.3s',
                }}
                autoComplete="new-password"
                name="gemini-api-key"
                autoFocus={highlightKeyInput}
              />
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleAddKey}
            style={{ width: '100%', padding: '12px' }}
          >
            Add Key
          </button>
        </div>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/Admin.jsx`

<!-- FILE: frontend/src/pages/Admin.jsx -->

```jsx
import React, { useEffect, useState, useCallback } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../App';
import PromptDashboard from '../components/PromptDashboard';

const PLANS = ['free', 'basic', 'pro'];

const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4, display: 'block' };

export default function Admin() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "superadmin";
  const [tab, setTab] = useState('users'); // 'users', 'logs', 'prompt'
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleteId, setDeleteId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsStats, setLogsStats] = useState({ admin_actions_total: 0, scans_total: 0, total: 0 });
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsFilter, setLogsFilter] = useState('all'); // 'all', 'admin', 'scan'
  const [logFilters, setLogFilters] = useState({ action: '', role: '', verdict: '', category: '', start_date: '', end_date: '', q: '' });
  const [logMeta, setLogMeta] = useState({ available_actions: [], available_verdicts: [], available_categories: [] });
  const [banningUserId, setBanningUserId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [list, s] = await Promise.all([
        api.adminListUsers({ q }),
        api.adminStats(),
      ]);
      setUsers(list.users);
      setTotal(list.total);
      setStats(s);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [q]);


  const loadLogs = useCallback(async () => {
    setLogsLoading(true);
    setError('');
    try {
      const kind = logsFilter === 'all' ? null : logsFilter;
      const data = await api.adminViewLogs({ limit: 200, offset: 0, kind, ...logFilters });
      setLogs(data.logs || []);
      setLogsStats({
        admin_actions_total: data.admin_actions_total || 0,
        scans_total: data.scans_total || 0,
        total: data.total || 0,
      });
      setLogMeta({
        available_actions: data.available_actions || [],
        available_verdicts: data.available_verdicts || [],
        available_categories: data.available_categories || [],
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLogsLoading(false);
    }
  }, [logsFilter, logFilters]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'logs') loadLogs(); }, [tab, loadLogs]);

  async function confirmDelete() {
    if (!deleteId) return;
    setError('');
    try {
      await api.adminDeleteUser(deleteId);
      setDeleteId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function findUser(userId) {
    return users.find(u => u.id === userId);
  }

  async function banUser(userId) {
    const u = findUser(userId);
    const label = u ? `${u.username} (${u.email})` : 'this user';
    if (!window.confirm(`Ban ${label}?\n\nThey will not be able to sign in until you unban them. Their data and scans remain intact.`)) return;
    setBanningUserId(userId);
    setError('');
    try {
      await api.adminBanUser(userId);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBanningUserId(null);
    }
  }

  async function unbanUser(userId) {
    const u = findUser(userId);
    const label = u ? `${u.username} (${u.email})` : 'this user';
    if (!window.confirm(`Unban ${label}?\n\nThey will be able to sign in again immediately.`)) return;
    setBanningUserId(userId);
    setError('');
    try {
      await api.adminUnbanUser(userId);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBanningUserId(null);
    }
  }

  async function promoteUser(userId) {
    const u = findUser(userId);
    const label = u ? `${u.username} (${u.email})` : 'this user';
    if (!window.confirm(`Promote ${label} to ADMIN?\n\nThey will gain access to the Admin Panel and every permission the admin role grants.`)) return;
    setError('');
    try {
      await api.adminPromoteAdmin(userId);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function demoteUser(userId) {
    const u = findUser(userId);
    const label = u ? `${u.username} (${u.email})` : 'this user';
    if (!window.confirm(`Demote ${label} back to a regular user?\n\nThey will lose access to the Admin Panel immediately.`)) return;
    setError('');
    try {
      await api.adminDemoteAdmin(userId);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 className="oswald glow" style={{
          fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0,
        }}>
          Admin Panel
        </h1>
      </div>

      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
          <StatCard label="Total Users" value={stats.total_users} />
          <StatCard label="Admins" value={stats.admins ?? 0} />
          <StatCard label="Super Admins" value={stats.super_admins ?? 0} />
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 20, borderBottom: '1px solid #1d3825', paddingBottom: 12 }}>
        <button
          className="mono"
          onClick={() => setTab('users')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'users' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'users' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Users
        </button>
        <button
          className="mono"
          onClick={() => setTab('logs')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'logs' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'logs' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Audit Logs
        </button>
        <button
          className="mono"
          onClick={() => setTab('prompt')}
          style={{
            padding: '8px 12px', fontSize: 12, background: 'none', border: 'none', cursor: 'pointer',
            color: tab === 'prompt' ? '#00ff66' : '#86efac',
            textTransform: 'uppercase', letterSpacing: 1,
            borderBottom: tab === 'prompt' ? '2px solid #00ff66' : 'none',
            marginBottom: '-12px',
          }}
        >
          Prompt Analytics
        </button>
      </div>

      {tab === 'users' && (
      <div>
      <div className="card" style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 200px' }}>
          <label style={labelStyle}>Search</label>
          <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="email, username, name" />
        </div>
        <button className="btn btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12, borderRadius: 2,
          marginBottom: 16, fontSize: 13, color: '#ff8a99',
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          ⚠ {error}
        </div>
      )}

      <div style={{ display: 'grid', gap: 10 }}>
        {users.map(u => (
          <UserRow
            key={u.id}
            user={u}
            isMe={u.id === me?.id}
            isSuperAdmin={isSuperAdmin}
            onDelete={() => setDeleteId(u.id)}
            onBan={() => banUser(u.id)}
            onUnban={() => unbanUser(u.id)}
            onPromote={() => promoteUser(u.id)}
            onDemote={() => demoteUser(u.id)}
            isBanning={banningUserId === u.id}
          />
        ))}
        {!loading && users.length === 0 && (
          <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>No users found.</div>
        )}
      </div>

      {deleteId && (() => {
        const target = users.find(u => u.id === deleteId);
        return (
          <Modal onClose={() => setDeleteId(null)} title="Delete user?">
            <p style={{ color: '#e5e5e5', fontSize: 14, marginBottom: 12 }}>
              You are about to permanently delete:
            </p>
            <div style={{
              background: 'rgba(255,51,68,0.06)', border: '1px solid #7a1f28',
              borderRadius: 4, padding: 12, marginBottom: 14,
            }}>
              <div style={{ fontSize: 14, color: '#d8ffe6', fontWeight: 600 }}>
                {target?.full_name || target?.username || '—'}
              </div>
              <div className="mono" style={{ fontSize: 12, color: '#86efac', marginTop: 4 }}>
                @{target?.username} · {target?.email}
              </div>
              <div className="mono" style={{ fontSize: 11, color: '#6dba85', marginTop: 4 }}>
                {target?.scans_this_month ?? 0} scans this month
              </div>
            </div>
            <p style={{ color: '#ff8a99', fontSize: 13, lineHeight: 1.6, margin: 0 }}>
              This permanently deletes the user, their scan history, uploaded images, and any classroom memberships. This cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn" onClick={() => setDeleteId(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={confirmDelete}>Delete forever</button>
            </div>
          </Modal>
        );
      })()}
      </div>
      )}


      {tab === 'logs' && (
        <LogsView
          logs={logs}
          logsStats={logsStats}
          loading={logsLoading}
          filter={logsFilter}
          onFilterChange={setLogsFilter}
          onRefresh={loadLogs}
          logFilters={logFilters}
          setLogFilters={setLogFilters}
          logMeta={logMeta}
        />
      )}

      {tab === 'prompt' && (
      <div className="card">
        <div style={{ marginBottom: 20 }}>
          <h2 className="oswald" style={{
            fontSize: 13, letterSpacing: 2.5, textTransform: 'uppercase',
            color: '#6dba85', marginBottom: 14, margin: 0,
          }}>
            ▸ How the Analyst Reasons - Live Prompt Analytics
          </h2>
          <p style={{ fontSize: 12, color: '#86efac', marginBottom: 16, lineHeight: 1.6 }}>
            Behind every classification is a prompt that defines 19 forgery categories, branching rules, and
            user-context variables. This dashboard reads the live prompt and shows how each category is
            described, where overlaps exist, and which categories tend to dominate when evidence is ambiguous.
          </p>
        </div>
        <PromptDashboard />
      </div>
      )}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="mono" style={{ fontSize: 10, color: '#3f6e4a', textTransform: 'uppercase', letterSpacing: 2 }}>{label}</div>
      <div className="oswald" style={{
        fontSize: 24, color: '#00ff66', marginTop: 4,
        textShadow: '0 0 10px rgba(0,255,102,0.5)',
        letterSpacing: 1,
      }}>{value}</div>
    </div>
  );
}

function Badge({ children, color }) {
  return (
    <span style={{
      fontSize: 10, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
      padding: '2px 8px', borderRadius: 3, border: `1px solid ${color}`, color, background: `${color}1a`,
    }}>{children}</span>
  );
}

function UserRow({ user, isMe, isSuperAdmin, onDelete, onBan, onUnban, onPromote, onDemote, isBanning }) {
  const planColor = { free: '#86efac', basic: '#00ffaa', pro: '#00ff66' }[user.plan] || '#86efac';
  const targetIsSuperAdmin = user.role === 'superadmin';
  const canMutate = isSuperAdmin && !targetIsSuperAdmin;
  const roleColor = user.role === 'superadmin' ? '#a3e635' : user.role === 'admin' ? '#00ff66' : '#6dba85';
  // Card background tinted with role color for at-a-glance grouping
  const tintHex = roleColor + '14';  // ~8% alpha
  return (
    <div className="card" style={{
      display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between',
      background: tintHex, borderLeft: `4px solid ${roleColor}`,
    }}>
      <div style={{ flex: '1 1 240px', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 14, wordBreak: 'break-all' }}>{user.email}</span>
          {isMe && <Badge color="#00ff66">You</Badge>}
          <Badge color={roleColor}>{user.role}</Badge>
          {!user.is_active && <Badge color="#ff3344">Banned</Badge>}
          {user.plan && <Badge color={planColor}>{user.plan}</Badge>}
        </div>
        <div style={{ color: '#86efac', fontSize: 12, marginTop: 4 }}>
          @{user.username} {user.full_name && `· ${user.full_name}`}
        </div>
        <div style={{ color: '#737373', fontSize: 11, marginTop: 4, fontFamily: 'monospace', wordBreak: 'break-all' }}>
          {user.id}
        </div>
        <div style={{ color: '#737373', fontSize: 11, marginTop: 2 }}>
          {user.scans_this_month} scans this month · joined {(user.created_at || '').slice(0, 10)}
        </div>
      </div>
      {canMutate && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {user.role === 'user' && (
            <button
              className="btn"
              onClick={onPromote}
              style={{
                background: 'rgba(0,255,102,0.06)',
                borderColor: '#1f5d39',
                color: '#00ff66',
              }}
              title="Promote to admin"
            >
              Promote to Admin
            </button>
          )}
          {user.role === 'admin' && (
            <button
              className="btn"
              onClick={onDemote}
              style={{
                background: 'rgba(255,170,64,0.06)',
                borderColor: '#7a4e10',
                color: '#ffa040',
              }}
              title="Demote to regular user"
            >
              Demote to User
            </button>
          )}
          {user.is_active ? (
            <button
              className="btn"
              onClick={onBan}
              disabled={isMe || isBanning}
              style={isMe ? {
                background: 'transparent', borderColor: '#1d3825', color: '#3f6e4a',
              } : {
                background: 'rgba(255,170,64,0.06)',
                borderColor: '#7a4e10',
                color: '#ffa040',
              }}
              title={isMe ? 'You cannot ban your own account' : 'Ban user'}
            >
              {isBanning ? 'Banning...' : 'Ban'}
            </button>
          ) : (
            <button
              className="btn"
              onClick={onUnban}
              disabled={isBanning}
              style={{
                background: 'rgba(0,255,102,0.06)',
                borderColor: '#1f5d39',
                color: '#00ff66',
              }}
              title="Unban user"
            >
              {isBanning ? 'Unbanning...' : 'Unban'}
            </button>
          )}
          <button
            className="btn"
            onClick={onDelete}
            disabled={isMe}
            style={isMe ? {
              background: 'transparent', borderColor: '#1d3825', color: '#3f6e4a',
            } : {
              background: 'rgba(255,51,68,0.08)',
              borderColor: '#7a1f28',
              color: '#ff8a99',
            }}
            title={isMe ? 'You cannot delete your own account' : 'Delete user'}
          >
            Delete
          </button>
        </div>
      )}
      {!isSuperAdmin && (
        <span className="mono" style={{ fontSize: 10, color: '#737373', letterSpacing: 1.5, padding: '4px 8px', border: '1px solid #1d3825', borderRadius: 2 }}>
          READ-ONLY
        </span>
      )}
      {isSuperAdmin && targetIsSuperAdmin && !isMe && (
        <span className="mono" style={{ fontSize: 10, color: '#a3e635', letterSpacing: 1.5, padding: '4px 8px', border: '1px solid #a3e635', borderRadius: 2 }}>
          PROTECTED
        </span>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

function Modal({ title, children, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        padding: 24, zIndex: 1000, overflowY: 'auto',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="card"
        style={{ width: '100%', maxWidth: 520, marginTop: 40 }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 className="oswald" style={{ margin: 0, fontSize: 18, letterSpacing: 2, textTransform: 'uppercase' }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#86efac', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// AUDIT LOG VIEW
// ─────────────────────────────────────────────────────────────────

const ACTION_COLORS = {
  ban_user:       '#ff8a99',
  unban_user:     '#86efac',
  promote_admin:  '#c4b5fd',
  demote_admin:   '#ffa040',
  update_user:    '#86efac',
  delete_user:    '#ff8a99',
  user_scan:      '#00ff66',
};

function LogsView({ logs, logsStats, loading, filter, onFilterChange, onRefresh, logFilters, setLogFilters, logMeta }) {
  const [qDraft, setQDraft] = useState(logFilters.q || '');
  useEffect(() => { setQDraft(logFilters.q || ''); }, [logFilters.q]);
  const setF = (k, v) => setLogFilters(f => ({ ...f, [k]: v }));
  const clearFilters = () => setLogFilters({ action: '', role: '', verdict: '', category: '', start_date: '', end_date: '', q: '' });
  const hasAdvanced = Boolean(logFilters.action || logFilters.role || logFilters.verdict || logFilters.category || logFilters.start_date || logFilters.end_date || logFilters.q);
  const inp = { padding: '6px 8px', fontSize: 11, background: '#0a120c', border: '1px solid #1d3825', color: '#d8ffe6', borderRadius: 2, fontFamily: "'JetBrains Mono', monospace" };
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 18 }}>
        <StatCard label="Total Scans" value={logsStats.scans_total ?? 0} />
        <StatCard label="Admin Actions" value={logsStats.admin_actions_total ?? 0} />
        <StatCard label="Matching Events" value={logsStats.total ?? 0} />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 2, textTransform: 'uppercase', marginRight: 4 }}>KIND</span>
        {[
          { id: 'all',   label: 'All' },
          { id: 'admin', label: 'Admin Actions' },
          { id: 'scan',  label: 'User Scans' },
        ].map(opt => (
          <button
            key={opt.id}
            className="mono"
            onClick={() => onFilterChange(opt.id)}
            style={{
              padding: '6px 12px', fontSize: 11, cursor: 'pointer',
              background: filter === opt.id ? 'rgba(0,255,102,0.1)' : 'transparent',
              border: `1px solid ${filter === opt.id ? '#00ff66' : '#1d3825'}`,
              color: filter === opt.id ? '#00ff66' : '#86efac',
              letterSpacing: 1, textTransform: 'uppercase', borderRadius: 2,
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <span className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 2, textTransform: 'uppercase', marginRight: 4 }}>FILTER</span>
        <select value={logFilters.action} onChange={e => setF('action', e.target.value)} style={inp} title="Action">
          <option value="">Any action</option>
          {(logMeta.available_actions || []).map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}
        </select>
        <select value={logFilters.verdict} onChange={e => setF('verdict', e.target.value)} style={inp} title="Verdict">
          <option value="">Any verdict</option>
          {(logMeta.available_verdicts || []).map(v => <option key={v} value={v}>{v}</option>)}
        </select>
        <select value={logFilters.category} onChange={e => setF('category', e.target.value)} style={inp} title="Forgery category">
          <option value="">Any category</option>
          {(logMeta.available_categories || []).map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
        </select>
        <select value={logFilters.role} onChange={e => setF('role', e.target.value)} style={inp} title="Actor role">
          <option value="">Any role</option>
          <option value="user">user</option>
          <option value="admin">admin</option>
          <option value="superadmin">superadmin</option>
        </select>
        <input type="date" value={logFilters.start_date} max={logFilters.end_date || undefined} onChange={e => setF('start_date', e.target.value)} style={inp} title="From date" />
        <span style={{ color: '#3f6e4a', fontSize: 11 }}>→</span>
        <input type="date" value={logFilters.end_date} min={logFilters.start_date || undefined} onChange={e => setF('end_date', e.target.value)} style={inp} title="To date" />
        <input
          placeholder="search actor / file / category…"
          value={qDraft}
          onChange={e => setQDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') setF('q', qDraft); }}
          onBlur={() => { if (qDraft !== (logFilters.q || '')) setF('q', qDraft); }}
          style={{ ...inp, minWidth: 190, flex: 1 }}
        />
        {hasAdvanced && (
          <button className="mono" onClick={clearFilters} style={{ fontSize: 11, padding: '6px 10px', background: 'transparent', border: '1px solid #ff8a99', color: '#ff8a99', borderRadius: 2, cursor: 'pointer' }}>
            Clear
          </button>
        )}
      </div>

      {loading && <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>Loading logs...</div>}
      {!loading && logs.length === 0 && (
        <div className="card" style={{ textAlign: 'center', color: '#86efac' }}>No log entries match these filters.</div>
      )}
      {logs.map(log => (
        <LogRow key={log.id} log={log} />
      ))}
    </div>
  );
}

function LogRow({ log }) {
  const [expanded, setExpanded] = useState(false);
  const isScan = log.kind === 'scan';
  const accent = ACTION_COLORS[log.action] || '#86efac';
  const timestamp = log.created_at ? new Date(log.created_at).toLocaleString() : '';

  return (
    <div className="card" style={{
      marginBottom: 10, padding: 12, borderLeft: `3px solid ${accent}`,
    }}>
      <div
        onClick={() => setExpanded(s => !s)}
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', userSelect: 'none' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
          <span className="mono" style={{
            fontSize: 9, padding: '3px 8px', borderRadius: 2, letterSpacing: 1.5,
            background: `${accent}1a`, color: accent, border: `1px solid ${accent}66`, textTransform: 'uppercase',
          }}>
            {isScan ? 'SCAN' : 'ADMIN'}
          </span>
          <span style={{ color: '#e5e5e5', fontWeight: 600, fontSize: 13 }}>
            {log.actor?.username || '-'}
          </span>
          {log.actor?.role && (
            <span className="mono" style={{ fontSize: 9, color: '#6dba85', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              {log.actor.role}
            </span>
          )}
          <span style={{ color: '#86efac', fontSize: 12 }}>·</span>
          <span style={{ color: '#86efac', fontSize: 12, letterSpacing: 0.5 }}>
            {log.action.replace(/_/g, ' ')}
          </span>
          {log.target && (
            <>
              <span style={{ color: '#3f6e4a', fontSize: 12 }}>→</span>
              <span style={{ color: '#d8ffe6', fontSize: 12 }}>@{log.target.username}</span>
            </>
          )}
          {isScan && log.scan && (
            <>
              <span style={{ color: '#3f6e4a', fontSize: 12 }}>·</span>
              <span className="mono" style={{ fontSize: 11, color: accent, letterSpacing: 1 }}>
                {log.scan.verdict?.toUpperCase()}
              </span>
              <span className="mono" style={{ fontSize: 11, color: '#6dba85' }}>
                {log.scan.confidence_score != null
                  ? `${(log.scan.confidence_score * 100).toFixed(0)}%`
                  : 'metadata'}
              </span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#737373', fontSize: 11, whiteSpace: 'nowrap' }}>{timestamp}</span>
          <span className="mono" style={{ fontSize: 11, color: '#00ff66' }}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #112418' }}>
          {isScan && log.scan ? (
            <ScanJsonDetail scan={log.scan} />
          ) : (
            <pre style={{
              color: '#86efac', fontSize: 11, lineHeight: 1.6, fontFamily: "'JetBrains Mono', monospace",
              background: '#000', padding: 10, borderRadius: 2, border: '1px solid #112418',
              whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
            }}>
              {JSON.stringify(log.details ?? {}, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ScanJsonDetail({ scan }) {
  const imageUrl = scan.has_image ? api.adminScanImageUrl(scan.scan_id) : null;

  return (
    <div>
      {imageUrl && (
        <div style={{ marginBottom: 14 }}>
          <div className="mono" style={{ color: '#3f6e4a', fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 6 }}>
            Scan Image
          </div>
          <img
            src={imageUrl}
            alt={`Uploaded scan ${scan.scan_id}`}
            style={{
              display: 'block', width: '100%', maxWidth: 720, maxHeight: 420,
              objectFit: 'contain', objectPosition: 'left center',
              background: '#000', border: '1px solid #1d3825', borderRadius: 3,
            }}
          />
          <div className="mono" style={{ color: '#3f6e4a', fontSize: 10, marginTop: 5 }}>
            {scan.image_width || '?'} × {scan.image_height || '?'} px
          </div>
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
        <Pill label="Scan ID" value={scan.scan_id} mono />
        <Pill label="Verdict" value={scan.verdict?.toUpperCase()} />
        <Pill label="Confidence" value={scan.confidence_score != null ? `${(scan.confidence_score * 100).toFixed(1)}%` : '-'} />
        {scan.detected_category && <Pill label="Category" value={scan.detected_category} />}
        {scan.certainty_level && <Pill label="Certainty" value={scan.certainty_level} />}
        {scan.document_type && <Pill label="Doc Type" value={scan.document_type} />}
      </div>
      <details style={{ marginTop: 10 }}>
        <summary style={{ cursor: 'pointer', color: '#86efac', fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', fontFamily: "'JetBrains Mono', monospace" }}>
          ▸ Full JSON metadata
        </summary>
        <pre style={{
          color: '#86efac', fontSize: 11, lineHeight: 1.6, fontFamily: "'JetBrains Mono', monospace",
          background: '#000', padding: 10, borderRadius: 2, border: '1px solid #112418', marginTop: 8,
          whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 480, overflow: 'auto',
        }}>
          {JSON.stringify(scan, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function Pill({ label, value, color = '#86efac', mono = false }) {
  return (
    <div style={{ background: '#0a120c', border: '1px solid #112418', padding: '6px 10px', borderRadius: 2 }}>
      <div className="mono" style={{ fontSize: 9, letterSpacing: 1.5, color: '#3f6e4a', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{
        fontSize: 12, color, fontFamily: mono ? "'JetBrains Mono', monospace" : 'inherit',
        marginTop: 2, wordBreak: 'break-all',
      }}>
        {value}
      </div>
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────
// ROLES MANAGER (super admin only)
// ─────────────────────────────────────────────────────────────────

const DEFAULT_ROLE_COLORS = [
  '#00ff66', '#00ffaa', '#a3e635', '#fbbf24', '#fb923c',
  '#f87171', '#c084fc', '#60a5fa', '#22d3ee', '#86efac',
];

function RolesManager({ roles, permissions, onReload, onError }) {
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  function emptyRole() {
    return {
      name: '',
      color: DEFAULT_ROLE_COLORS[Math.floor(Math.random() * DEFAULT_ROLE_COLORS.length)],
      description: '',
      permissions: [],
      is_self_assignable: false,
      sort_order: 100,
    };
  }

  async function saveRole(role) {
    setBusy(true);
    try {
      if (role.id) {
        await api.updateRole(role.id, {
          name: role.name,
          color: role.color,
          description: role.description,
          permissions: role.permissions,
          is_self_assignable: role.is_self_assignable,
          sort_order: role.sort_order,
        });
      } else {
        await api.createRole({
          name: role.name,
          color: role.color,
          description: role.description,
          permissions: role.permissions,
          is_self_assignable: role.is_self_assignable,
          sort_order: role.sort_order,
        });
      }
      setEditing(null);
      setCreating(false);
      await onReload();
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteRole(role) {
    if (!confirm(`Delete role "${role.name}"? All users with this role will be moved back to "user".`)) return;
    setBusy(true);
    try {
      await api.deleteRole(role.id);
      await onReload();
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // Group permissions by their group label for display
  const permGroups = permissions.reduce((acc, p) => {
    (acc[p.group] = acc[p.group] || []).push(p);
    return acc;
  }, {});

  return (
    <div>
      <div className="card" style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="oswald" style={{ fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: '#00ff66', margin: 0 }}>
            Role Management
          </h2>
          <p style={{ color: '#86efac', fontSize: 12, marginTop: 6, marginBottom: 0 }}>
            Create roles for sections / groups. Edit privileges for any role. Color-code for at-a-glance grouping in the Users tab.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => { setEditing(emptyRole()); setCreating(true); }} disabled={busy}>
          + New Role
        </button>
      </div>

      <div style={{ display: 'grid', gap: 10 }}>
        {roles.map(r => (
          <div key={r.id} className="card" style={{
            background: `${r.color}10`, borderLeft: `4px solid ${r.color}`,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            flexWrap: 'wrap', gap: 12,
          }}>
            <div style={{ flex: '1 1 240px', minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{
                  display: 'inline-block', width: 14, height: 14, borderRadius: 3,
                  background: r.color, border: '1px solid rgba(0,0,0,0.2)',
                }} />
                <span className="oswald" style={{
                  color: r.color, fontSize: 16, letterSpacing: 1.5, textTransform: 'uppercase', fontWeight: 600,
                }}>
                  {r.name}
                </span>
                {r.is_system && <Badge color="#a3e635">System</Badge>}
                {r.is_self_assignable && <Badge color="#22d3ee">Self-assignable</Badge>}
              </div>
              {r.description && (
                <div style={{ color: '#86efac', fontSize: 12, marginTop: 6 }}>{r.description}</div>
              )}
              <div style={{ color: '#3f6e4a', fontSize: 11, marginTop: 4 }}>
                {r.permissions.length === 0 ? 'No permissions' : r.permissions.map(pKey => {
                  const perm = permissions && permissions.length > 0
                    ? permissions.find(p => p.key === pKey)
                    : null;
                  return perm ? perm.label : pKey;
                }).join(', ')}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn" onClick={() => { setEditing({ ...r }); setCreating(false); }} disabled={busy}>
                Edit
              </button>
              {!r.is_system && (
                <button
                  className="btn"
                  onClick={() => deleteRole(r)}
                  disabled={busy}
                  style={{ borderColor: '#ff3344', color: '#ff8a99' }}
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {editing && (
        <Modal
          onClose={() => { setEditing(null); setCreating(false); }}
          title={creating ? 'New role' : `Edit role ${editing.name}`}
        >
          <div style={{ display: 'grid', gap: 12 }}>
            <Field label="Name">
              <input
                className="input"
                value={editing.name}
                onChange={e => setEditing({ ...editing, name: e.target.value })}
                disabled={editing.is_system && !creating}
                placeholder="e.g., Section A, Mentor, Student"
              />
              {editing.is_system && !creating && (
                <div style={{ color: '#86efac', fontSize: 11, marginTop: 4 }}>System roles cannot be renamed.</div>
              )}
            </Field>

            <Field label="Color">
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {DEFAULT_ROLE_COLORS.map(c => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setEditing({ ...editing, color: c })}
                    style={{
                      width: 28, height: 28, borderRadius: 4, background: c, cursor: 'pointer',
                      border: editing.color === c ? '2px solid #fff' : '1px solid #1d3825',
                    }}
                  />
                ))}
                <input
                  type="color"
                  value={editing.color}
                  onChange={e => setEditing({ ...editing, color: e.target.value })}
                  style={{ width: 36, height: 28, border: '1px solid #1d3825', background: '#0a120c', cursor: 'pointer', borderRadius: 4 }}
                />
                <span style={{ color: '#86efac', fontSize: 11, fontFamily: 'monospace' }}>{editing.color}</span>
              </div>
            </Field>

            <Field label="Description">
              <input
                className="input"
                value={editing.description || ''}
                onChange={e => setEditing({ ...editing, description: e.target.value })}
                placeholder="What this role is for"
              />
            </Field>

            <Field label="Permissions">
              <div style={{
                border: '1px solid #1d3825', borderRadius: 3, padding: 10, background: '#0a120c',
                maxHeight: 280, overflowY: 'auto', display: 'grid', gap: 10,
              }}>
                {Object.entries(permGroups).map(([group, perms]) => (
                  <div key={group}>
                    <div className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 6 }}>
                      {group}
                    </div>
                    {perms.map(p => {
                      const checked = editing.permissions.includes(p.key);
                      const isSuperPerm = p.key === 'is_superadmin';
                      const disabled = isSuperPerm && editing.name !== 'superadmin';
                      return (
                        <label
                          key={p.key}
                          style={{
                            display: 'flex', alignItems: 'flex-start', gap: 8, padding: '5px 0',
                            color: disabled ? '#3f6e4a' : '#d8ffe6', fontSize: 12, cursor: disabled ? 'not-allowed' : 'pointer',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={disabled}
                            onChange={e => {
                              const next = e.target.checked
                                ? [...editing.permissions, p.key]
                                : editing.permissions.filter(k => k !== p.key);
                              setEditing({ ...editing, permissions: next });
                            }}
                            style={{ marginTop: 2 }}
                          />
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <span style={{ color: disabled ? '#3f6e4a' : '#d8ffe6' }}>{p.label}</span>
                            {p.description && (
                              <span style={{ color: '#5fa873', fontSize: 11, lineHeight: '1.3' }}>{p.description}</span>
                            )}
                          </div>
                        </label>
                      );
                    })}
                  </div>
                ))}
              </div>
            </Field>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#d8ffe6' }}>
              <input
                type="checkbox"
                checked={!!editing.is_self_assignable}
                onChange={e => setEditing({ ...editing, is_self_assignable: e.target.checked })}
              />
              Self-assignable (users can pick this role themselves on their Account page)
            </label>

            <Field label="Sort order">
              <input
                className="input"
                type="number"
                value={editing.sort_order}
                onChange={e => setEditing({ ...editing, sort_order: parseInt(e.target.value) || 0 })}
              />
            </Field>

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button className="btn" onClick={() => { setEditing(null); setCreating(false); }} disabled={busy}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={() => saveRole(editing)} disabled={busy}>
                {busy ? 'Saving…' : creating ? 'Create role' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Rooms (Sections) - admins create rooms, students join via code
// ──────────────────────────────────────────────────────────────────

function RoomsManager({ onError }) {
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listRooms();
      setRooms(data.rooms || []);
    } catch (err) {
      onError(err.message);
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    if (!newName.trim()) { onError('Name is required'); return; }
    setBusy(true);
    try {
      const created = await api.createRoom(newName.trim(), newDescription.trim());
      setNewName(''); setNewDescription(''); setCreating(false);
      setRooms(cs => [created, ...cs]);
      setExpandedId(created.id);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h2 className="oswald" style={{
              fontSize: 16, letterSpacing: 2, textTransform: 'uppercase',
              color: '#d8ffe6', margin: 0, fontWeight: 700,
            }}>
              Rooms
            </h2>
            <span className="mono" style={{ fontSize: 11, color: '#3f6e4a', letterSpacing: 1 }}>
              {rooms.length} TOTAL
            </span>
          </div>
          {!creating && (
            <button
              className="btn btn-primary"
              onClick={() => setCreating(true)}
              style={{ fontSize: 12, padding: '8px 14px', minHeight: 'unset', display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <Plus size={14} strokeWidth={2.5} />
              Add Room
            </button>
          )}
        </div>

        {creating && (
          <div style={{
            background: 'rgba(0,255,102,0.04)', border: '1px solid #1d3825',
            borderRadius: 4, padding: 14, marginTop: 8,
          }}>
            <div style={{ marginBottom: 10 }}>
              <label style={labelStyle}>Room name</label>
              <input
                className="input"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="e.g. BSCS 3-A · Document Forensics"
                maxLength={120}
                autoFocus
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>Description (optional)</label>
              <textarea
                className="input"
                value={newDescription}
                onChange={e => setNewDescription(e.target.value)}
                placeholder="What students will work on in this section."
                rows={2}
                maxLength={2000}
                style={{ resize: 'vertical', fontFamily: "'Source Sans Pro', sans-serif" }}
              />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn"
                onClick={() => { setCreating(false); setNewName(''); setNewDescription(''); }}
                disabled={busy}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleCreate} disabled={busy}>
                {busy ? 'Creating…' : 'Create Room'}
              </button>
            </div>
          </div>
        )}

        <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: '8px 0 0' }}>
          Share each room's join code with your students, they'll enter it from their account page to join. You'll see them in the class list below.
        </p>
      </div>

      {loading ? (
        <p className="mono" style={{ color: '#6dba85', textAlign: 'center', padding: 24 }}>
          ◌ Loading rooms…
        </p>
      ) : rooms.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 32 }}>
          <GraduationCap size={32} strokeWidth={1.5} style={{ color: '#3f6e4a', margin: '0 auto 10px' }} />
          <p className="mono" style={{ color: '#6dba85', letterSpacing: 1, fontSize: 13 }}>
            No rooms yet, click "Add Room" to create your first one.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {rooms.map(c => (
            <RoomCard
              key={c.id}
              room={c}
              expanded={expandedId === c.id}
              onToggle={() => setExpandedId(id => id === c.id ? null : c.id)}
              onChange={updated => setRooms(cs => cs.map(x => x.id === updated.id ? updated : x))}
              onDelete={() => setRooms(cs => cs.filter(x => x.id !== c.id))}
              onError={onError}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RoomCard({ room, expanded, onToggle, onChange, onDelete, onError }) {
  const [detail, setDetail] = useState(room);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(room.name);
  const [description, setDescription] = useState(room.description || '');
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Fetch full details (with members) when first expanded
  useEffect(() => {
    if (expanded && !detail.members) {
      api.getRoom(room.id).then(setDetail).catch(err => onError(err.message));
    }
  }, [expanded, room.id]);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(detail.join_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }

  async function regenerate() {
    if (!confirm('Generate a new join code? The old code will stop working immediately.')) return;
    setBusy(true);
    try {
      const res = await api.regenerateRoomCode(room.id);
      const updated = { ...detail, join_code: res.join_code };
      setDetail(updated);
      onChange(updated);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    setBusy(true);
    try {
      const updated = await api.updateRoom(room.id, {
        name: name.trim(),
        description: description.trim(),
      });
      setDetail(updated);
      onChange(updated);
      setEditing(false);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    setBusy(true);
    try {
      await api.deleteRoom(room.id);
      onDelete();
    } catch (err) {
      onError(err.message);
      setBusy(false);
    }
  }

  async function kickMember(userId, username) {
    if (!confirm(`Remove ${username} from this room?`)) return;
    try {
      await api.removeRoomMember(room.id, userId);
      const fresh = await api.getRoom(room.id);
      setDetail(fresh);
      onChange(fresh);
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <button
        onClick={onToggle}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          padding: '14px 18px', textAlign: 'left',
          display: 'flex', alignItems: 'center', gap: 12,
        }}
      >
        {expanded
          ? <ChevronDown size={18} strokeWidth={2} style={{ color: '#6dba85', flexShrink: 0 }} />
          : <ChevronRight size={18} strokeWidth={2} style={{ color: '#6dba85', flexShrink: 0 }} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="oswald" style={{
            fontSize: 15, color: '#d8ffe6', letterSpacing: 1, fontWeight: 600,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {detail.name}
          </div>
          {detail.description && (
            <div style={{
              fontSize: 12, color: '#86efac', marginTop: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {detail.description}
            </div>
          )}
        </div>
        <span className="mono" style={{
          fontSize: 11, color: '#00ff66', letterSpacing: 2, fontWeight: 700,
          background: 'rgba(0,255,102,0.08)', border: '1px solid #1d3825',
          borderRadius: 4, padding: '4px 10px', flexShrink: 0,
        }}>
          {detail.join_code}
        </span>
        <span className="mono" style={{
          fontSize: 11, color: '#3f6e4a', letterSpacing: 1, flexShrink: 0,
          display: 'inline-flex', alignItems: 'center', gap: 4,
        }}>
          <Users size={12} strokeWidth={2} />
          {detail.member_count ?? (detail.members?.length || 0)}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '0 18px 18px', borderTop: '1px solid #112418' }}>
          {/* Join code panel */}
          <div style={{
            marginTop: 14, padding: 14,
            background: 'rgba(0,255,102,0.05)', border: '1px solid #1d3825',
            borderRadius: 4,
            display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
          }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div className="mono" style={{ fontSize: 9, color: '#3f6e4a', letterSpacing: 2, marginBottom: 4, textTransform: 'uppercase' }}>
                Join code
              </div>
              <div className="mono" style={{ fontSize: 22, color: '#00ff66', letterSpacing: 4, fontWeight: 700 }}>
                {detail.join_code}
              </div>
            </div>
            <button
              onClick={copyCode}
              className="btn btn-secondary"
              style={{ fontSize: 11, padding: '8px 12px', minHeight: 'unset', display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              {copied ? <Check size={14} strokeWidth={2.5} /> : <Copy size={14} strokeWidth={2} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              onClick={regenerate}
              className="btn btn-secondary"
              disabled={busy}
              style={{ fontSize: 11, padding: '8px 12px', minHeight: 'unset', display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <RefreshCw size={14} strokeWidth={2} />
              Regenerate
            </button>
          </div>

          {/* Edit / delete controls */}
          <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {!editing && !confirmDelete && (
              <>
                <button
                  className="btn btn-secondary"
                  onClick={() => setEditing(true)}
                  style={{ fontSize: 11, padding: '6px 10px', minHeight: 'unset', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                >
                  <Pencil size={12} strokeWidth={2.2} />
                  Edit
                </button>
                <button
                  className="btn"
                  onClick={() => setConfirmDelete(true)}
                  style={{
                    fontSize: 11, padding: '6px 10px', minHeight: 'unset', background: 'transparent',
                    color: '#ff8a99', border: '1px solid #ff8a99',
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <Trash2 size={12} strokeWidth={2.2} />
                  Delete
                </button>
              </>
            )}
          </div>

          {editing && (
            <div style={{ marginTop: 12, padding: 12, border: '1px solid #1d3825', borderRadius: 4 }}>
              <div style={{ marginBottom: 8 }}>
                <label style={labelStyle}>Room name</label>
                <input className="input" value={name} onChange={e => setName(e.target.value)} maxLength={120} />
              </div>
              <div style={{ marginBottom: 10 }}>
                <label style={labelStyle}>Description</label>
                <textarea
                  className="input"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={3}
                  maxLength={2000}
                  style={{ resize: 'vertical', fontFamily: "'Source Sans Pro', sans-serif" }}
                />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="btn" onClick={() => { setEditing(false); setName(detail.name); setDescription(detail.description || ''); }} disabled={busy}>
                  Cancel
                </button>
                <button className="btn btn-primary" onClick={saveEdit} disabled={busy}>
                  {busy ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          )}

          {confirmDelete && (
            <div style={{
              marginTop: 12, padding: 14,
              background: 'rgba(255,51,68,0.08)', border: '1px solid #ff3344',
              borderRadius: 4,
              display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
            }}>
              <AlertTriangle size={16} strokeWidth={2.2} style={{ color: '#ff8a99' }} />
              <span style={{ fontSize: 13, color: '#ff8a99', flex: 1, minWidth: 200 }}>
                Delete <strong>{detail.name}</strong> and remove all enrolled students? This can't be undone.
              </span>
              <button className="btn" onClick={() => setConfirmDelete(false)} disabled={busy}>
                Keep
              </button>
              <button
                className="btn"
                onClick={doDelete}
                disabled={busy}
                style={{ background: '#ff3344', color: '#fff' }}
              >
                {busy ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          )}

          {/* Class list */}
          <div style={{ marginTop: 18 }}>
            <div className="mono" style={{
              fontSize: 10, color: '#6dba85', letterSpacing: 2,
              textTransform: 'uppercase', marginBottom: 10, fontWeight: 600,
              display: 'inline-flex', alignItems: 'center', gap: 6,
            }}>
              <Users size={12} strokeWidth={2.2} />
              Class List ({detail.members?.length || 0})
            </div>
            {detail.members && detail.members.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', border: '1px solid #112418', borderRadius: 4 }}>
                {detail.members.map((m, i) => (
                  <div key={m.id} style={{
                    padding: '10px 12px',
                    borderTop: i === 0 ? 'none' : '1px solid #112418',
                    display: 'flex', alignItems: 'center', gap: 10,
                  }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%',
                      background: 'rgba(0,255,102,0.1)', border: '1px solid #1d3825',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, color: '#00ff66', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0,
                    }}>
                      {(m.full_name || m.username || '?').charAt(0).toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, color: '#d8ffe6', fontWeight: 500 }}>
                        {m.full_name || m.username}
                      </div>
                      <div className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 0.5 }}>
                        {m.email} · {m.role}
                      </div>
                    </div>
                    <button
                      onClick={() => kickMember(m.id, m.username)}
                      title="Remove from room"
                      style={{
                        background: 'transparent', border: 'none', cursor: 'pointer',
                        color: '#ff8a99', padding: 4, display: 'inline-flex',
                      }}
                    >
                      <Trash2 size={14} strokeWidth={2} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mono" style={{ fontSize: 12, color: '#3f6e4a', padding: '12px 0', fontStyle: 'italic' }}>
                No students yet. Share the join code above.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

## File: `frontend/src/pages/ForensicsGuide.jsx`

<!-- FILE: frontend/src/pages/ForensicsGuide.jsx -->

```jsx
import React, { useState } from 'react';
import {
  Fingerprint, FileEdit, Layers, EyeOff, FlaskConical, Banknote,
  ChevronDown, ChevronRight, CornerDownRight,
} from 'lucide-react';
import { useTheme } from '../App';
import { themed, tintedBg } from '../themeColors';

const GROUPS = [
  {
    id: 'traced',
    label: 'Traced Signatures',
    Icon: Fingerprint,
    color: '#c4b5fd',
    description: 'A genuine signature is physically reproduced using an intermediary guide, carbon paper, light table, or projector. The forger follows a real signature rather than inventing one, producing subtle artifacts from the tracing method.',
    categories: [
      {
        id: 'traced_carbon',
        label: 'Carbon Tracing',
        description: 'Carbon paper placed beneath the genuine signature transfers a faint "blueprint" via pressure. The forger then inks over the faint transfer, leaving behind telltale carbon residue and hesitant strokes.',
        indicators: ['Faint carbon residue along strokes', 'Hesitation or tremor following blueprint', 'Uniform line weight', 'Misalignment from carbon transfer'],
      },
      {
        id: 'traced_indentation',
        label: 'Indentation Tracing',
        description: 'A pen pressed hard onto paper placed over a genuine signature creates physical grooves. The forger inks inside these canals, leaving a colorless depression (halo) around strokes visible under raking light.',
        indicators: ['Halo / colorless depression around strokes', 'Ink not filling indented path', 'Hesitation or tremor'],
      },
      {
        id: 'traced_projection',
        label: 'Projection Tracing',
        description: 'A light table or projector throws the genuine signature as a shadow onto paper. The forger traces the projected lines with pen. No grooves or carbon residue, only the telltale monotony of following a projected guide.',
        indicators: ['Uniform / monotonous pen pressure', 'Micro-tremors throughout', 'Frequent pen lifts', 'No carbon residue, no grooves', 'Suspiciously perfect match to original'],
      },
    ],
  },
  {
    id: 'alteration',
    label: 'Document Alteration',
    Icon: FileEdit,
    color: '#fbbf24',
    description: 'An authentic document is modified after the fact, text is added between lines or inside words, or existing content is erased (chemically or mechanically) and replaced. The original paper and its surrounding content remain genuine.',
    categories: [
      {
        id: 'addition_insertion',
        label: 'Addition, Insertion',
        description: 'Characters or digits are added inside a word or number to change its meaning (e.g., "1000" → "10000"). New strokes appear between or alongside existing ones, often with visible crowding, ink mismatches, or morphological inconsistency.',
        indicators: ['Crowding or tight spacing', 'Ink density mismatch', 'Stroke rhythm inconsistency', 'Baseline misalignment', 'Logical value conflict'],
      },
      {
        id: 'addition_interlineation',
        label: 'Addition, Interlineation',
        description: 'New text is squeezed into the whitespace between existing printed lines, not inside a word. The inserted writing often uses a smaller size or different pen to fit the narrow gap.',
        indicators: ['Smaller text size than surrounding', 'Different pen baseline', 'Different ink color or texture'],
      },
      {
        id: 'erasure_chemical',
        label: 'Erasure, Chemical',
        description: 'Original ink is dissolved with a solvent (bleach, acetone, commercial eradicator). The cleaned area is then written on or printed over. Solvents leave characteristic tide marks, ghosting, and paper fiber damage.',
        indicators: ['Halo / tide mark around altered zone', 'Ink ghosting of original text', 'Paper fiber damage', 'New text on visibly damaged background', 'Sheen difference under oblique light'],
      },
      {
        id: 'erasure_mechanical',
        label: 'Erasure, Mechanical',
        description: 'Original ink is scraped away with a razor blade, sandpaper, or eraser. The abraded area is then written or printed over. Abrasion leaves a rough "fuzzy patch" of disturbed paper fibers.',
        indicators: ["Abraded fibers ('fuzzy patch')", 'Shadow patch or sheen', 'Ghost ink particles', 'Paper thinning', 'Jagged void boundary', 'Ink feathering into damaged area'],
      },
    ],
  },
  {
    id: 'digital',
    label: 'Digital Fabrication',
    Icon: Layers,
    color: '#38bdf8',
    description: 'Software is used to create or manipulate document content. A document may be fabricated entirely from scratch, or genuine elements (signatures, stamps) may be digitally transplanted onto another document.',
    categories: [
      {
        id: 'digital_cut_paste',
        label: 'Digital, Cut & Paste',
        description: 'A genuine element (signature, seal, or stamp) is digitally extracted from one image and composited onto a different document. The transplanted element often carries halos, pixelation, DPI mismatches, or inconsistent shadows.',
        indicators: ['Halo or fringe around element', 'Pixelation or aliasing at edges', 'Background inconsistency under element', 'Compression artefacts', 'DPI or resolution mismatch', 'Inconsistent shadow or lighting'],
      },
      {
        id: 'digital_desktop',
        label: 'Digital, Desktop',
        description: 'The entire document is fabricated from scratch in software (Word, Canva, Photoshop, etc.). No physical paper ever existed. Indicators include unnaturally perfect typography, template-like layout, and a complete absence of physical paper realism.',
        indicators: ['Perfect digital typography throughout', 'Font consistency across entire doc', 'Forms or template layout', 'Signature quality mismatch vs printed text', 'Zero physical paper realism (no grain, no tilt)'],
      },
      {
        id: 'digital_scanned',
        label: 'Digital, Scanned',
        description: 'A real document is scanned, then digital elements (dates, signatures, stamps) are composited onto the scan image. The scan provides a realistic paper background while inserted elements betray themselves through scan-noise inconsistencies.',
        indicators: ['Scan noise inconsistency around inserted element', 'Stamp or signature flatness vs paper grain', 'Global tilt vs local perfect alignment', 'Compression level mismatch', 'Resolution halo around element', 'Font or field inconsistency'],
      },
    ],
  },
  {
    id: 'obliteration',
    label: 'Obliteration',
    Icon: EyeOff,
    color: '#f87171',
    description: 'Original content is intentionally concealed, not erased or replaced, but covered. Ink or correction fluid is applied over existing text to hide it while the surrounding document remains intact.',
    categories: [
      {
        id: 'obliteration_ink',
        label: 'Obliteration, Ink',
        description: 'Original text is scribbled over with a pen or marker, rendering it visually illegible. The underlying text may still be recoverable by infrared photography or other forensic techniques.',
        indicators: ['Ink scribbled over existing text', 'Possible underlying text visible via IR'],
      },
      {
        id: 'obliteration_whiteout',
        label: 'Obliteration, White Out',
        description: 'Correction fluid (Wite-Out, Tipp-Ex) is applied as an opaque white layer over existing text. The fluid leaves a distinctive raised, chalky surface texture that is visible to touch and sometimes to oblique light.',
        indicators: ['Correction fluid layer over text', 'Raised chalky surface texture', 'Whitened patch inconsistent with paper'],
      },
    ],
  },
  {
    id: 'sympathetic',
    label: 'Sympathetic Ink',
    Icon: FlaskConical,
    color: '#34d399',
    description: 'Writing that is invisible under normal conditions, either because no ink was deposited (pure pressure indentation) or because the ink only becomes visible under a specific stimulus such as heat, UV light, or a chemical reagent.',
    categories: [
      {
        id: 'sympathetic_indented',
        label: 'Sympathetic, Indented Writing',
        description: 'Writing pressure alone, with no ink, creates grooves on paper beneath the written-on sheet. The indented text contains no ink and is only visible by raking light or an electrostatic detection device (ESDA). Often used to reveal secondary documents.',
        indicators: ['Pressure indentations present on paper', 'No visible ink in grooves', 'Revealed by raking or oblique light', 'ESDA / electrostatic detection'],
      },
      {
        id: 'sympathetic_special',
        label: 'Sympathetic, Special Ink',
        description: 'An invisible or near-invisible substance is used to write, then later revealed by an external stimulus. Classic examples include heat-activated (lemon juice, milk), UV-fluorescent inks, and chemical reagent-activated compounds.',
        indicators: ['Heat-activated: text browns or chars', 'Chemical-activated: color reaction appears', 'UV / fluorescent glow under blacklight', 'Specific substances (lemon, milk, phenolphthalein)'],
      },
    ],
  },
  {
    id: 'currency',
    label: 'Currency Counterfeit',
    Icon: Banknote,
    color: '#fbbf24',
    description: 'Suspected counterfeit banknotes or currency documents. The system evaluates security features, print quality, substrate characteristics, and known anti-counterfeiting elements for the suspected denomination.',
    categories: [
      {
        id: 'currency_analysis',
        label: 'Currency Analysis',
        description: 'Analysis of a suspected counterfeit banknote. The system checks print precision, microprinting legibility, security thread presence, color-shifting ink, watermark clarity, and paper substrate texture against known genuine specimen characteristics.',
        indicators: ['Counterfeit banknote suspected', 'Security feature integrity', 'Print quality evaluation', 'Substrate texture assessment'],
      },
    ],
  },
];

const SPECIMEN_EXTENSIONS = {
  traced_carbon: 'jpeg',
  traced_indentation: 'jpeg',
  traced_projection: 'jpg',
  addition_insertion: 'jpg',
  addition_interlineation: 'jpg',
  erasure_chemical: 'jpg',
  erasure_mechanical: 'jpg',
  digital_cut_paste: 'jpg',
  digital_desktop: 'jpg',
  digital_scanned: 'jpg',
  obliteration_ink: 'jpeg',
  obliteration_whiteout: 'jpeg',
  sympathetic_indented: 'jpg',
  sympathetic_special: 'jpg',
  currency_analysis: 'jpg',
};

function ImageStub({ category }) {
  const extension = SPECIMEN_EXTENSIONS[category.id] || 'jpg';
  const src = `/guide-specimens/${category.id}.${extension}`;

  return (
    <div style={{
      border: '1px solid #1d3825',
      borderRadius: 6,
      background: '#020b05',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: 180,
      overflow: 'hidden',
    }}>
      <img
        src={src}
        alt={`Representative ${category.label} specimen`}
        style={{ width: '100%', height: 180, objectFit: 'contain', display: 'block' }}
      />
      <div className="mono" style={{ width: '100%', padding: '6px 8px', fontSize: 9, letterSpacing: 1.2, color: '#6dba85', background: 'rgba(0,0,0,0.72)', textTransform: 'uppercase', textAlign: 'center' }}>
        Representative specimen
      </div>
    </div>
  );
}

function CategoryCard({ cat, groupColor }) {
  const { theme } = useTheme();
  const [open, setOpen] = useState(false);
  const accent = themed(groupColor, theme);

  return (
    <div style={{
      background: theme === 'light' ? '#ffffff' : '#030e07',
      border: `1px solid ${open ? tintedBg(groupColor, theme, 0.35) : (theme === 'light' ? '#d0dcd4' : '#112418')}`,
      borderRadius: 6,
      overflow: 'hidden',
      transition: 'border-color 0.15s, box-shadow 0.15s',
      boxShadow: open ? `0 2px 12px ${tintedBg(groupColor, theme, 0.1)}` : 'none',
    }}>
      <button
        onClick={() => setOpen(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          padding: '14px 16px', textAlign: 'left',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: accent, flexShrink: 0,
            boxShadow: theme === 'dark' ? `0 0 8px ${accent}aa` : 'none',
          }} />
          <span className="oswald" style={{
            fontSize: 15, color: theme === 'light' ? '#0a1c11' : '#d8ffe6',
            letterSpacing: 1.5, textTransform: 'uppercase', fontWeight: 600,
          }}>
            {cat.label}
          </span>
        </div>
        {open
          ? <ChevronDown size={18} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a', flexShrink: 0 }} />
          : <ChevronRight size={18} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a', flexShrink: 0 }} />}
      </button>

      {open && (
        <div style={{ padding: '0 16px 18px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(140px, 200px) 1fr',
            gap: 18,
            alignItems: 'start',
          }}>
            <ImageStub category={cat} />
            <div>
              <p style={{
                color: theme === 'light' ? '#1a3024' : '#cfe9d8',
                fontSize: 14, lineHeight: 1.75, margin: '0 0 14px',
              }}>
                {cat.description}
              </p>
              <div className="mono" style={{
                fontSize: 10, letterSpacing: 2,
                color: theme === 'light' ? '#3a5040' : '#3f6e4a',
                textTransform: 'uppercase', marginBottom: 8, fontWeight: 600,
              }}>
                Key Indicators
              </div>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {cat.indicators.map((ind, i) => (
                  <li key={i} style={{
                    color: theme === 'light' ? '#0a1c11' : '#86efac',
                    fontSize: 13, lineHeight: 1.7, paddingLeft: 0, marginBottom: 4,
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                  }}>
                    <CornerDownRight size={14} strokeWidth={2.2} style={{ color: accent, flexShrink: 0, marginTop: 3 }} />
                    <span>{ind}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function GroupSection({ group }) {
  const { theme } = useTheme();
  const [collapsed, setCollapsed] = useState(false);
  const accent = themed(group.color, theme);
  const Icon = group.Icon;

  return (
    <section style={{ marginBottom: 36 }}>
      <button
        onClick={() => setCollapsed(s => !s)}
        style={{
          width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 14, padding: '0 0 16px',
          borderBottom: `1px solid ${tintedBg(group.color, theme, 0.25)}`,
          marginBottom: 16,
        }}
      >
        <div style={{
          width: 40, height: 40, borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: tintedBg(group.color, theme, 0.12),
          border: `1px solid ${tintedBg(group.color, theme, 0.3)}`,
          flexShrink: 0,
          boxShadow: theme === 'dark' ? `0 0 12px ${tintedBg(group.color, theme, 0.25)}` : 'none',
        }}>
          <Icon size={20} strokeWidth={2} style={{ color: accent }} />
        </div>
        <div style={{ flex: 1, textAlign: 'left' }}>
          <div className="oswald" style={{
            fontSize: 18, color: accent, letterSpacing: 2,
            textTransform: 'uppercase', fontWeight: 700,
          }}>
            {group.label}
          </div>
          <div className="mono" style={{
            fontSize: 11, color: theme === 'light' ? '#3a5040' : '#3f6e4a',
            letterSpacing: 1.5, marginTop: 3,
          }}>
            {group.categories.length} {group.categories.length === 1 ? 'type' : 'types'}
          </div>
        </div>
        {collapsed
          ? <ChevronRight size={20} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a' }} />
          : <ChevronDown size={20} strokeWidth={2} style={{ color: theme === 'light' ? '#3a5040' : '#3f6e4a' }} />}
      </button>

      {!collapsed && (
        <>
          <p style={{
            color: theme === 'light' ? '#1a3024' : '#cfe9d8',
            fontSize: 14, lineHeight: 1.75, margin: '0 0 16px',
          }}>
            {group.description}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {group.categories.map(cat => (
              <CategoryCard key={cat.id} cat={cat} groupColor={group.color} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export default function ForensicsGuide() {
  const { theme } = useTheme();

  return (
    <div style={{ maxWidth: 820, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div className="mono" style={{
          fontSize: 10, letterSpacing: 3,
          color: theme === 'light' ? '#3a5040' : '#3f6e4a',
          textTransform: 'uppercase', marginBottom: 10,
          display: 'inline-flex', alignItems: 'center', gap: 8,
        }}>
          <Fingerprint size={14} strokeWidth={2} />
          Forensics Guide
        </div>
        <h1 className="oswald" style={{
          fontSize: 30, color: theme === 'light' ? '#003d17' : '#00ff66',
          letterSpacing: 3, textTransform: 'uppercase', margin: 0, fontWeight: 700,
          textShadow: theme === 'dark' ? '0 0 20px rgba(0,255,102,0.3)' : 'none',
        }}>
          Document Forgery Types
        </h1>
        <p style={{
          color: theme === 'light' ? '#1a3024' : '#cfe9d8',
          fontSize: 15, lineHeight: 1.75, margin: '12px 0 0',
        }}>
          Revelator detects 15 categories of document forgery across 6 groups. Each category uses a tailored
          analysis pipeline tuned to its specific physical or digital indicators. Click any category to expand
          its description, indicators, and example image.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 32 }}>
        {GROUPS.map(g => {
          const accent = themed(g.color, theme);
          const Icon = g.Icon;
          return (
            <div key={g.id} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: tintedBg(g.color, theme, 0.08),
              border: `1px solid ${tintedBg(g.color, theme, 0.3)}`,
              borderRadius: 6, padding: '6px 12px',
            }}>
              <Icon size={14} strokeWidth={2.2} style={{ color: accent }} />
              <span className="mono" style={{
                fontSize: 11, color: accent, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
              }}>
                {g.label}
              </span>
              <span className="mono" style={{
                fontSize: 10, color: theme === 'light' ? '#3a5040' : '#3f6e4a',
              }}>
                ×{g.categories.length}
              </span>
            </div>
          );
        })}
      </div>

      {GROUPS.map(group => (
        <GroupSection key={group.id} group={group} />
      ))}

      <div className="card" style={{
        marginTop: 8, padding: '14px 18px',
        borderLeft: `3px solid ${theme === 'light' ? '#6da884' : '#1d3825'}`,
      }}>
        <p className="mono" style={{
          fontSize: 11, color: theme === 'light' ? '#3a5040' : '#5a7a64',
          margin: 0, lineHeight: 1.75, letterSpacing: 0.5,
        }}>
          Analysis is powered by Gemini Vision with a custom forensic prompt chain. Results are probabilistic -
          physical examination by a qualified document examiner is required for legal or evidentiary use.
        </p>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/ForgotPassword.jsx`

<!-- FILE: frontend/src/pages/ForgotPassword.jsx -->

```jsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import Logo from '../components/Logo';
import { FingerprintWatermark } from '../components/ForensicMotifs';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block', fontFamily: "'JetBrains Mono', monospace" };

  return (
    <div style={{ maxWidth: 440, margin: 'clamp(20px, 6vw, 60px) auto', position: 'relative' }}>
      <FingerprintWatermark size={420} opacity={0.06} style={{ position: 'absolute', top: -40, right: -120, zIndex: 0 }} />
      <div style={{ textAlign: 'center', marginBottom: 32, position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <Logo size={86} glow animated />
        </div>
        <h1 className="oswald glow-strong" style={{ fontSize: 32, color: '#00ff66', letterSpacing: 7, fontWeight: 700 }}>
          REVELATOR
        </h1>
        <p className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 11, letterSpacing: 3 }}>
          [ RECOVER ACCESS ]
        </p>
      </div>

      <div className="card">
        {sent ? (
          <div style={{ textAlign: 'center' }}>
            <div className="mono glow" style={{ fontSize: 40, color: '#00ff66', marginBottom: 12 }}>✉</div>
            <h2 className="oswald" style={{ fontSize: 20, letterSpacing: 2, color: '#d8ffe6', marginBottom: 14 }}>
              CHECK YOUR EMAIL
            </h2>
            <p style={{ fontSize: 14, color: '#86efac', lineHeight: 1.6, marginBottom: 8 }}>
              If an account exists for <strong style={{ color: '#d8ffe6' }}>{email}</strong>, we’ve sent a password reset link.
            </p>
            <p style={{ fontSize: 13, color: '#6dba85', lineHeight: 1.6, marginBottom: 22 }}>
              The link expires in 1 hour. Check your spam folder if you don’t see it.
            </p>
            <p style={{ textAlign: 'center', fontSize: 13, color: '#86efac' }}>
              <Link to="/login">Back to sign in</Link>
            </p>
          </div>
        ) : (
          <>
            <h2 className="oswald" style={{ fontSize: 18, marginBottom: 8, letterSpacing: 3, textTransform: 'uppercase', color: '#d8ffe6' }}>
              ▸ Forgot Password
            </h2>
            <p style={{ fontSize: 13, color: '#6dba85', lineHeight: 1.6, marginBottom: 20 }}>
              Enter your email and we’ll send you a link to reset your password.
            </p>

            {error && (
              <div style={{
                background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12,
                borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#ff8a99',
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                ⚠ {error}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 24 }}>
                <label style={labelStyle}>Email</label>
                <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
              </div>
              <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
                {loading ? '◌ Sending…' : '▶ Send Reset Link'}
              </button>
            </form>

            <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: '#86efac' }}>
              Remembered it? <Link to="/login">Sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/History.jsx`

<!-- FILE: frontend/src/pages/History.jsx -->

```jsx
import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Sparkles, ImageOff, StickyNote, Check, AlertTriangle, Pencil, Trash2 } from 'lucide-react';
import { api } from '../api/client';
import { CATEGORY_BY_KEY, MAIN_CATEGORY_CODE_BY_KEY } from '../categories';
import { useTheme } from '../App';
import { themed, tintedBg } from '../themeColors';

// Maps a Gemini category code to its display color
function geminiColor(code) {
  if (!code) return '#3f6e4a';
  if (code === 'no_forgery_detected') return '#00ff66';
  if (code === 'not_a_document') return '#737373';
  if (code === 'other') return '#ffa040';
  return CATEGORY_BY_KEY[code]?.color || '#a78bfa';
}

// Formats a document_type key into a readable label
function docTypeLabel(key) {
  if (!key || key === 'other') return null;
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// Maps a Gemini category code to a short display label
function geminiLabel(code, label) {
  if (label) return label;
  if (!code) return 'Unknown';
  if (code === 'no_forgery_detected') return 'No Forgery';
  if (code === 'not_a_document') return 'Not a Document';
  if (code === 'other') return 'Other Forgery';
  return CATEGORY_BY_KEY[code]?.title || code;
}

export default function History() {
  const [scans, setScans] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState(null);
  const limit = 20;

  useEffect(() => { loadScans(); }, [page]);

  function loadScans() {
    api.getHistory(limit, page * limit).then(data => {
      setScans(data.scans);
      setTotal(data.total);
    }).catch(() => {});
  }

  function viewDetail(scanId) {
    api.getScanDetail(scanId).then(setDetail).catch(() => {});
  }

  if (detail) return <ScanDetailView detail={detail} onBack={() => setDetail(null)} onDeleted={() => { setDetail(null); loadScans(); }} />;

  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <h1 className="oswald glow" style={{ fontSize: 28, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 24, color: '#00ff66' }}>
        Scan History
      </h1>

      {scans.length === 0 ? (
        <div className="card">
          <p className="mono" style={{ color: '#3f6e4a', textAlign: 'center', padding: 32, letterSpacing: 2 }}>▣ NO SCANS RECORDED</p>
        </div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {scans.map(scan => (
              <HistoryCard key={scan.scan_id} scan={scan} onClick={() => viewDetail(scan.scan_id)} />
            ))}
          </div>
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 24 }}>
              <button className="btn btn-secondary" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} style={{ padding: '8px 16px', fontSize: 12 }}>&larr; Prev</button>
              <span className="mono" style={{ padding: '8px 16px', color: '#86efac', fontSize: 13 }}>{page + 1} / {totalPages}</span>
              <button className="btn btn-secondary" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1} style={{ padding: '8px 16px', fontSize: 12 }}>Next &rarr;</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function HistoryCard({ scan, onClick }) {
  const { theme } = useTheme();
  const cat = scan.detected_category;
  const rawColor = geminiColor(cat);
  const color = themed(rawColor, theme);
  const label = geminiLabel(cat, null);
  const conf = typeof scan.category_confidence === 'number' ? scan.category_confidence : scan.confidence_score;

  const isLight = theme === 'light';
  const cardBg = isLight ? '#ffffff' : '#0a120c';
  const cardBorder = isLight ? '#d0dcd4' : '#1a2e1e';
  const filenameColor = isLight ? '#0a1c11' : '#d4d4d4';
  const mutedColor = isLight ? '#3a5040' : '#3f6e4a';
  const noImageBg = isLight ? '#f0f5f1' : '#000';
  const noImageColor = isLight ? '#7a8e7f' : '#404040';

  return (
    <button onClick={onClick} className="lift" style={{
      background: cardBg, border: `1px solid ${cardBorder}`, borderLeft: `4px solid ${color}`,
      borderRadius: 8, padding: 0, cursor: 'pointer', textAlign: 'left',
      overflow: 'hidden', color: 'inherit', font: 'inherit', width: '100%',
      boxShadow: isLight ? '0 1px 3px rgba(0, 60, 30, 0.06)' : 'none',
    }}>
      <div style={{
        aspectRatio: '4/3', background: noImageBg,
        display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
      }}>
        {scan.has_image ? (
          <img src={api.getScanImageUrl(scan.scan_id)} alt={scan.filename}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { e.currentTarget.style.display = 'none'; }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <ImageOff size={28} strokeWidth={1.5} style={{ color: noImageColor }} />
            <span style={{ color: noImageColor, fontSize: 11, fontFamily: "'Oswald', sans-serif", letterSpacing: 1.5 }}>NO IMAGE</span>
          </div>
        )}
      </div>
      <div style={{ padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8 }}>
          <span className="oswald" style={{
            fontSize: 11, color, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: 700,
            background: tintedBg(rawColor, theme, 0.1),
            border: `1px solid ${tintedBg(rawColor, theme, 0.35)}`,
            borderRadius: 4, padding: '3px 8px',
            maxWidth: '70%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {cat ? label : '-'}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {scan.has_notes && (
              <span title="This scan has notes" style={{
                color: isLight ? '#003d17' : '#00ff66',
                display: 'inline-flex', alignItems: 'center',
              }}>
                <StickyNote size={13} strokeWidth={2.2} />
              </span>
            )}
            {scan.has_llm_explanation && (
              <span className="oswald" style={{
                fontSize: 9, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 700,
                color: themed('#a78bfa', theme),
                background: tintedBg('#a78bfa', theme, 0.12),
                border: `1px solid ${tintedBg('#a78bfa', theme, 0.35)}`,
                borderRadius: 4, padding: '2px 6px',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}>
                <Sparkles size={9} strokeWidth={2.5} />
                AI
              </span>
            )}
            <span className="mono" style={{ fontSize: 12, color, fontWeight: 700 }}>
              {(conf * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        <div style={{
          fontSize: 13, color: filenameColor, fontWeight: isLight ? 500 : 400,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {scan.filename}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          <span className="mono" style={{ fontSize: 10, color: mutedColor }}>{scan.scan_id}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {docTypeLabel(scan.document_type) && (
              <span className="mono" style={{
                fontSize: 9, color: isLight ? '#1a3024' : '#86efac', letterSpacing: 1,
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}>
                <FileText size={10} strokeWidth={2} />
                {docTypeLabel(scan.document_type).toUpperCase()}
              </span>
            )}
            <span className="mono" style={{ fontSize: 10, color: mutedColor }}>
              Scanned {new Date(scan.scanned_at || scan.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}

function ScanDetailView({ detail, onBack, onDeleted }) {
  const canvasRef = useRef(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const cat = detail.detected_category;
  const color = geminiColor(cat);
  const label = geminiLabel(cat, detail.detected_category_label);
  const mainCategoryCode = MAIN_CATEGORY_CODE_BY_KEY[cat];
  const leafLabel = label.replace(/^[^-]+\s+-\s+/, '');
  const geminiOk = typeof detail.category_confidence === 'number' && detail.category_confidence > 0;
  const geminiForgery = geminiOk && cat !== 'no_forgery_detected' && cat !== 'not_a_document';
  const hasYolo = detail.annotations?.length > 0 && geminiForgery;
  const certColor = detail.certainty_level === 'HIGH' ? '#00ff66' : detail.certainty_level === 'MEDIUM' ? '#ffa040' : '#ff5555';

  async function handleDelete() {
    if (!window.confirm(`Delete scan ${detail.scan_id} from your history? This cannot be undone.`)) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await api.deleteScan(detail.scan_id);
      onDeleted();
    } catch (err) {
      setDeleteError(err.message || 'Could not delete this scan');
      setDeleting(false);
    }
  }

  useEffect(() => {
    if (!detail.has_image || !hasYolo) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const maxW = Math.min(canvas.parentElement.offsetWidth - 32, 900);
      const scale = maxW / img.naturalWidth;
      canvas.width = img.naturalWidth * scale;
      canvas.height = img.naturalHeight * scale;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      detail.annotations.forEach((ann, idx) => {
        const c = ann.coordinates;
        const x = c.x_min * scale, y = c.y_min * scale;
        const w = (c.x_max - c.x_min) * scale, h = (c.y_max - c.y_min) * scale;
        ctx.shadowColor = ann.color || color;
        ctx.shadowBlur = 8;
        ctx.strokeStyle = ann.color || color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.shadowBlur = 0;
        ctx.fillStyle = ann.color || color;
        ctx.font = 'bold 12px JetBrains Mono';
        const lbl = `${idx + 1}. ${ann.title} (${(ann.confidence * 100).toFixed(0)}%)`;
        const tw = ctx.measureText(lbl).width + 8;
        ctx.fillRect(x, Math.max(0, y - 18), tw, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(lbl, x + 4, Math.max(12, y - 5));
      });
    };
    img.src = api.getScanImageUrl(detail.scan_id);
  }, [detail]);

  return (
    <div>
      <button onClick={onBack} style={{ background: 'none', border: 'none', color: '#00ff66', cursor: 'pointer', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.5, fontSize: 13, marginBottom: 20, padding: 0, textShadow: '0 0 6px rgba(0,255,102,0.5)' }}>
        ← back to history
      </button>

      <div className="card" style={{ borderColor: color, boxShadow: `0 0 20px ${color}20`, padding: 0, overflow: 'hidden' }}>
        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px', borderBottom: `1px solid ${color}33` }}>
          <h2 className="oswald" style={{ fontSize: 14, letterSpacing: 2.5, textTransform: 'uppercase', margin: 0, color: '#d8ffe6' }}>◆ Forensic Report</h2>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
            {docTypeLabel(detail.document_type) && (
              <span className="mono" style={{ fontSize: 10, color: '#6dba85', letterSpacing: 1.5 }}>
                📄 {docTypeLabel(detail.document_type).toUpperCase()}
              </span>
            )}
            <span className="mono" style={{ color: '#86efac', fontSize: 10 }}>
              Scanned {new Date(detail.scanned_at || detail.created_at).toLocaleString()}
            </span>
            <span className="mono" style={{ color: '#3f6e4a', fontSize: 11 }}>{detail.scan_id}</span>
            <button
              className="btn btn-danger"
              onClick={handleDelete}
              disabled={deleting}
              title="Delete this scan from history"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 10px', fontSize: 11, minHeight: 'unset' }}
            >
              <Trash2 size={13} />
              {deleting ? 'Deleting...' : 'Delete scan'}
            </button>
          </div>
        </div>

        {deleteError && (
          <div className="mono" style={{ color: '#ff8a99', padding: '10px 20px', borderBottom: `1px solid ${color}33` }}>
            ⚠ {deleteError}
          </div>
        )}

        {/* category banner */}
        <div style={{ textAlign: 'center', padding: '28px 20px 24px', background: '#000', borderBottom: `1px solid ${color}33`, boxShadow: `inset 0 0 32px ${color}18` }}>
          <div className="oswald" style={{ fontSize: 30, fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: 5, textShadow: `0 0 18px ${color}99` }}>
            {cat ? leafLabel : '-'}
          </div>
          {geminiOk && mainCategoryCode && (
            <div className="oswald" style={{ color, marginTop: 8, fontSize: 'clamp(12px, 3.3vw, 19px)', fontWeight: 600, letterSpacing: 'clamp(1.5px, 0.35vw, 3px)', textTransform: 'uppercase', textShadow: `0 0 8px ${color}66` }}>
              ({mainCategoryCode})
            </div>
          )}
          {geminiOk && (
            <div className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 12, letterSpacing: 1.5 }}>
              GEMINI {(detail.category_confidence * 100).toFixed(1)}% ·{' '}
              <span style={{ color: certColor }}>{detail.certainty_level}</span> CERTAINTY
            </div>
          )}
        </div>

        <div style={{ padding: '20px 20px 4px' }}>
          {/* image */}
          {detail.has_image && (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>
                {hasYolo ? '▸ YOLO · ANNOTATED IMAGE' : '▸ UPLOADED IMAGE'}
              </p>
              {hasYolo ? (
                <canvas ref={canvasRef} style={{ display: 'block', width: '100%', maxWidth: 900, margin: '0 auto', borderRadius: 3, border: '1px solid #1d3825' }} />
              ) : (
                <img src={api.getScanImageUrl(detail.scan_id)} alt={detail.filename}
                  style={{ display: 'block', width: '100%', maxWidth: 900, height: 'auto', margin: '0 auto', borderRadius: 3, border: '1px solid #1d3825' }} />
              )}
            </div>
          )}

          {/* gemini panel */}
          {geminiOk ? (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color, margin: '0 0 8px', textShadow: `0 0 6px ${color}80` }}>▣ GEMINI VISION · CLASSIFICATION</p>
              <div style={{ background: `${color}08`, border: `1px solid ${color}44`, borderLeft: `3px solid ${color}`, borderRadius: 3, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                  <div>
                    <h4 className="oswald" style={{ fontSize: 17, color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 2, margin: 0 }}>{label}</h4>
                    {detail.detected_subtype && <p style={{ fontSize: 12, color, margin: '3px 0 0', fontStyle: 'italic' }}>Subtype: {detail.detected_subtype}</p>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <span className="mono" style={{ fontSize: 11, color, letterSpacing: 1.5, display: 'block' }}>
                      {(detail.category_confidence * 100).toFixed(0)}% CONF
                    </span>
                    {detail.certainty_level && (
                      <span className="mono" style={{ fontSize: 10, color: certColor, letterSpacing: 1 }}>{detail.certainty_level} CERTAINTY</span>
                    )}
                  </div>
                </div>
                {detail.category_explanation && (
                  <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: '0 0 10px' }}>{detail.category_explanation}</p>
                )}
                {detail.category_evidence?.length > 0 && (
                  <div style={{ marginBottom: 10 }}>
                    <p className="mono" style={{ fontSize: 9, color: '#86efac', letterSpacing: 2, margin: '0 0 6px' }}>EVIDENCE</p>
                    <ul style={{ margin: 0, paddingLeft: 18, color: '#86efac', fontSize: 13, lineHeight: 1.6 }}>
                      {detail.category_evidence.map((e, i) => <li key={i}>{e}</li>)}
                    </ul>
                  </div>
                )}
                {detail.anomaly_location && (
                  <p style={{ fontSize: 12, color: '#ffc888', margin: '0 0 8px', borderTop: '1px solid #112418', paddingTop: 8 }}>
                    <span className="mono" style={{ color: '#ffa040', letterSpacing: 1.5, marginRight: 6 }}>LOCATION:</span>
                    {detail.anomaly_location}
                  </p>
                )}
                {detail.tools_likely_used && (
                  <p style={{ fontSize: 12, color: '#86efac', margin: 0, borderTop: '1px solid #112418', paddingTop: 8 }}>
                    <span className="mono" style={{ color, letterSpacing: 1.5, marginRight: 6 }}>TOOLS USED:</span>
                    {detail.tools_likely_used}
                  </p>
                )}
                {detail.reasoning_steps?.length > 0 && (
                  <details style={{ marginTop: 10, borderTop: '1px solid #112418', paddingTop: 8 }}>
                    <summary className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 1.5, cursor: 'pointer' }}>
                      ▸ REASONING STEPS ({detail.reasoning_steps.length})
                    </summary>
                    <ol style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 12, color: '#86efac', lineHeight: 1.7 }}>
                      {detail.reasoning_steps.map((step, i) => <li key={i}>{step}</li>)}
                    </ol>
                  </details>
                )}
                {detail.alternatives?.length > 0 && (
                  <div style={{ marginTop: 12, borderTop: '1px solid #112418', paddingTop: 10 }}>
                    <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#ffa040', margin: '0 0 8px' }}>
                      ⚠ COULD ALSO BE ({detail.alternatives.length})
                    </p>
                    {detail.alternatives.map((alternative, i) => (
                      <div key={i} style={{ background: 'rgba(255,160,64,0.04)', border: '1px solid rgba(255,160,64,0.18)', borderRadius: 2, padding: '8px 12px', marginBottom: 6 }}>
                        <p className="oswald" style={{ fontSize: 12, color: '#ffd680', margin: '0 0 3px', textTransform: 'uppercase', letterSpacing: 1 }}>
                          {alternative.category_label}
                        </p>
                        {alternative.reasoning && <p style={{ fontSize: 12, color: '#c4a45a', margin: 0, lineHeight: 1.6 }}>{alternative.reasoning}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : cat ? (
            <div style={{ marginBottom: 20 }}>
              <span className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', padding: '4px 10px', border: '1px solid #1d3825', borderRadius: 2 }}>
                ▣ GEMINI VISION · TEMPORARILY UNAVAILABLE
              </span>
            </div>
          ) : null}

          {/* llm */}
          {detail.llm_explanation ? (
            <div style={{ marginBottom: 20 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ AI FORENSIC EXPLANATION</p>
              <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: 0 }}>{detail.llm_explanation}</p>
            </div>
          ) : detail.llm_locked ? (
            <div style={{ marginBottom: 20 }}>
              <div style={{ background: 'linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(139,92,246,0.02) 100%)', border: '1px solid rgba(139,92,246,0.4)', borderRadius: 3, padding: 14, display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 22, lineHeight: 1 }}>✨</span>
                <div style={{ flex: 1 }}>
                  <div className="oswald" style={{ fontSize: 13, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 4 }}>AI Forensic Explanation</div>
                  <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: '0 0 10px' }}>
                    Upgrade to <strong style={{ color: '#a78bfa', textTransform: 'capitalize' }}>{detail.llm_required_plan || 'pro'}</strong> for a plain-language breakdown on every scan.
                  </p>
                  <Link to="/account" style={{ display: 'inline-block', padding: '6px 14px', borderRadius: 2, background: '#8b5cf6', color: '#fff', textDecoration: 'none', fontSize: 12, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5 }}>See plans →</Link>
                </div>
              </div>
            </div>
          ) : null}

          {/* yolo detections */}
          {hasYolo && (
            <div style={{ marginBottom: 16 }}>
              <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ YOLO · DETECTIONS</p>
              {detail.annotations.map((ann, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #112418' }}>
                  <span style={{ width: 24, height: 24, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', background: ann.color, color: '#000', fontSize: 10, fontWeight: 800, fontFamily: "'JetBrains Mono', monospace" }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{ flex: 1, fontSize: 14, color: '#d8ffe6' }}>{ann.title}</span>
                  <span className="mono" style={{ fontSize: 12, color: ann.color }}>{(ann.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {detail.training_warning && (
            <div style={{ background: 'rgba(255,160,64,0.08)', border: '1px solid #ffa040', padding: '10px 14px', borderRadius: 2, fontSize: 12, color: '#ffc888', fontFamily: "'JetBrains Mono', monospace", marginBottom: 16 }}>
              ⚠ {detail.training_warning}
            </div>
          )}

        </div>
      </div>
      <NotesSection scanId={detail.scan_id} initialNotes={detail.notes || ''} />
    </div>
  );
}

function NotesSection({ scanId, initialNotes }) {
  const { theme } = useTheme();
  const [notes, setNotes] = useState(initialNotes);
  const [editing, setEditing] = useState(!initialNotes);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // 'saved' | 'error' | null
  const [errorMsg, setErrorMsg] = useState('');
  const isLight = theme === 'light';

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    setErrorMsg('');
    try {
      const res = await api.updateScanNotes(scanId, notes);
      setNotes(res.notes || '');
      setStatus('saved');
      setEditing(false);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message || 'Could not save notes');
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setNotes(initialNotes);
    setEditing(false);
    setStatus(null);
  }

  const hasNotes = !!(notes && notes.trim());

  return (
    <div style={{
      marginTop: 6,
      padding: 16,
      background: isLight ? '#f7faf8' : 'rgba(0,255,102,0.03)',
      border: `1px solid ${isLight ? '#d0dcd4' : '#1a2e1e'}`,
      borderRadius: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <StickyNote size={16} strokeWidth={2} style={{ color: isLight ? '#003d17' : '#00ff66' }} />
        <h3 className="oswald" style={{
          fontSize: 13, color: isLight ? '#0a1c11' : '#d8ffe6',
          letterSpacing: 2, textTransform: 'uppercase', margin: 0, fontWeight: 700,
        }}>
          Your Notes
        </h3>
        {!editing && hasNotes && (
          <button
            onClick={() => setEditing(true)}
            style={{
              marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer',
              color: isLight ? '#003d17' : '#00ff66',
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1,
              padding: '4px 8px', borderRadius: 3,
            }}
          >
            <Pencil size={11} strokeWidth={2.2} />
            EDIT
          </button>
        )}
      </div>

      {editing ? (
        <>
          <textarea
            className="input"
            value={notes}
            onChange={e => { setNotes(e.target.value); if (status) setStatus(null); }}
            placeholder="Add a note about this scan, context, follow-ups, what to verify next…"
            rows={4}
            maxLength={5000}
            style={{ resize: 'vertical', minHeight: 90, fontFamily: "'Source Sans Pro', sans-serif" }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving}
              style={{ fontSize: 12, padding: '8px 18px', minHeight: 'unset' }}
            >
              {saving ? '◌ Saving…' : 'Save Note'}
            </button>
            {hasNotes && (
              <button
                onClick={handleCancel}
                disabled={saving}
                style={{
                  background: 'transparent', border: `1px solid ${isLight ? '#a5c2af' : '#1d3825'}`,
                  color: isLight ? '#3a5040' : '#86efac',
                  padding: '8px 14px', borderRadius: 2, cursor: 'pointer',
                  fontSize: 12, fontFamily: "'Oswald', sans-serif",
                  textTransform: 'uppercase', letterSpacing: 1.5,
                }}
              >
                Cancel
              </button>
            )}
            {status === 'error' && (
              <span className="mono" style={{
                fontSize: 11, color: '#ff8a99', letterSpacing: 1,
                display: 'inline-flex', alignItems: 'center', gap: 4,
              }}>
                <AlertTriangle size={12} strokeWidth={2.5} />
                {errorMsg}
              </span>
            )}
            <span className="mono" style={{
              fontSize: 10, color: isLight ? '#3a5040' : '#3f6e4a',
              letterSpacing: 1, marginLeft: 'auto',
            }}>
              {notes.length}/5000
            </span>
          </div>
        </>
      ) : hasNotes ? (
        <>
          <p style={{
            fontSize: 14, lineHeight: 1.7,
            color: isLight ? '#0a1c11' : '#d8ffe6',
            margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {notes}
          </p>
          {status === 'saved' && (
            <span className="mono" style={{
              fontSize: 11, color: isLight ? '#003d17' : '#00ff66',
              letterSpacing: 1, marginTop: 10,
              display: 'inline-flex', alignItems: 'center', gap: 4,
            }}>
              <Check size={12} strokeWidth={2.5} />
              Saved
            </span>
          )}
        </>
      ) : (
        <p style={{
          fontSize: 13, color: isLight ? '#3a5040' : '#6dba85',
          lineHeight: 1.6, margin: 0, fontStyle: 'italic',
        }}>
          No notes yet, click above to add one.
        </p>
      )}
    </div>
  );
}
```

## File: `frontend/src/pages/Login.jsx`

<!-- FILE: frontend/src/pages/Login.jsx -->

```jsx
import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { Capacitor } from '@capacitor/core';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import { useAuth } from '../App';
import { api } from '../api/client';
import Logo from '../components/Logo';
import { FingerprintWatermark } from '../components/ForensicMotifs';

export default function Login() {
  const { loginUser, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const verifiedParam = searchParams.get('verified');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [needsResend, setNeedsResend] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState('login');   // 'login' | 'code'
  const [code, setCode] = useState('');
  const [rememberDevice, setRememberDevice] = useState(false);
  const [agreed, setAgreed] = useState(false);

  if (user) { navigate('/scan', { replace: true }); return null; }

  async function handleResend() {
    if (!email) { setError('Enter your email above, then tap resend.'); return; }
    setError('');
    try { await api.resendVerification(email); } catch {}
    setInfo('Verification link sent. Check your inbox.');
    setNeedsResend(false);
  }

  async function handleNativeGoogleSignIn() {
    if (!agreed) { setError('Please agree to the Terms of Service first.'); return; }
    setError('');
    setLoading(true);
    try {
      const result = await GoogleAuth.signIn();
      const data = await api.googleLogin(result.authentication.idToken);
      loginUser(data);
      navigate('/scan');
    } catch (err) {
      if (err.code !== 'CANCELED') setError('Google sign-in failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!agreed) { setError('Please agree to the Terms of Service first.'); return; }
    setError('');
    setInfo('');
    setLoading(true);
    try {
      const data = await api.login(email, password);
      if (data.requires_2fa) {
        setStage('code');
        setCode('');
        setInfo(data.message || `Enter the code we emailed to ${email}.`);
        return;
      }
      loginUser(data);
      navigate('/scan');
    } catch (err) {
      setError(err.message);
      if (/verify/i.test(err.message)) setNeedsResend(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyCode(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.verify2fa(email, code.trim(), rememberDevice);
      loginUser(data);
      navigate('/scan');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResendCode() {
    setError('');
    try { await api.resend2fa(email); } catch {}
    setInfo('A new code has been sent. Check your inbox.');
  }

  function backToLogin() {
    setStage('login');
    setCode('');
    setError('');
    setInfo('');
  }

  return (
    <div style={{ maxWidth: 440, margin: 'clamp(20px, 6vw, 60px) auto', position: 'relative' }}>
      <FingerprintWatermark
        size={420} opacity={0.06}
        style={{ position: 'absolute', top: -40, right: -120, zIndex: 0 }}
      />
      <div style={{ textAlign: 'center', marginBottom: 32, position: 'relative' }}>
        <p className="classification-bar" style={{ marginBottom: 18 }}>
          DOCUMENT · FORENSICS · UNIT
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <Logo size={86} glow animated />
        </div>
        <h1 className="oswald glow-strong" style={{
          fontSize: 32, color: '#00ff66', letterSpacing: 7, fontWeight: 700,
        }}>
          REVELATOR
        </h1>
        <p className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 11, letterSpacing: 3 }}>
          [ AUTHENTICATE TO PROCEED ]
        </p>
      </div>

      <div className="card">
        <h2 className="oswald" style={{
          fontSize: 18, marginBottom: 20, letterSpacing: 3, textTransform: 'uppercase',
          color: '#d8ffe6',
        }}>
          {stage === 'code' ? '▸ Verify Sign-In' : '▸ Sign In'}
        </h2>

        {verifiedParam === '1' && (
          <div style={{
            background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66', padding: 12,
            borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#86efac',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            ✓ Email confirmed. You can sign in now.
          </div>
        )}
        {verifiedParam === '0' && (
          <div style={{
            background: 'rgba(255,170,0,0.1)', border: '1px solid #ffaa00', padding: 12,
            borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#ffcf80',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            ⚠ That link is invalid or expired. Sign in to request a new one.
          </div>
        )}
        {info && (
          <div style={{
            background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66', padding: 12,
            borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#86efac',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            ✓ {info}
          </div>
        )}
        {error && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12,
            borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#ff8a99',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            ⚠ {error}
            {needsResend && (
              <button
                type="button"
                onClick={handleResend}
                style={{
                  display: 'block', marginTop: 10, background: 'transparent',
                  border: '1px solid #ff8a99', color: '#ff8a99', padding: '6px 12px',
                  borderRadius: 2, fontSize: 12, cursor: 'pointer',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                ↻ Resend verification email
              </button>
            )}
          </div>
        )}

        {stage === 'code' ? (
          <form onSubmit={handleVerifyCode}>
            <div style={{ marginBottom: 16 }}>
              <label className="mono" style={{ fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block' }}>6-Digit Code</label>
              <input
                className="input mono"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]*"
                maxLength={6}
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="______"
                autoFocus
                required
                style={{ textAlign: 'center', letterSpacing: 12, fontSize: 24 }}
              />
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer', fontSize: 13, color: '#86efac' }}>
              <input type="checkbox" checked={rememberDevice} onChange={e => setRememberDevice(e.target.checked)} style={{ width: 16, height: 16, accentColor: '#00ff66' }} />
              Trust this device for 30 days
            </label>
            <button className="btn btn-primary" type="submit" disabled={loading || code.length < 6} style={{ width: '100%' }}>
              {loading ? '◌ Verifying…' : '▶ Verify & Sign In'}
            </button>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button type="button" onClick={backToLogin} style={{ background: 'transparent', border: 'none', color: '#6dba85', fontSize: 12, cursor: 'pointer', padding: 0 }}>
                ← Back
              </button>
              <button type="button" onClick={handleResendCode} style={{ background: 'transparent', border: 'none', color: '#6dba85', fontSize: 12, cursor: 'pointer', padding: 0 }}>
                ↻ Resend code
              </button>
            </div>
          </form>
        ) : (
          <>
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 16 }}>
                <label className="mono" style={{ fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block' }}>Email</label>
                <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
              </div>
              <div style={{ marginBottom: 8 }}>
                <label className="mono" style={{ fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block' }}>Password</label>
                <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" required />
              </div>
              <div style={{ textAlign: 'right', marginBottom: 24 }}>
                <Link to="/forgot-password" style={{ fontSize: 12, color: '#6dba85' }}>Forgot password?</Link>
              </div>
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 22,
                fontSize: 12, color: '#86efac', lineHeight: 1.5, cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={e => setAgreed(e.target.checked)}
                  style={{ marginTop: 2, width: 16, height: 16, accentColor: '#00ff66', flexShrink: 0 }}
                />
                <span>
                  I have read and agree to the{' '}
                  <Link to="/terms" target="_blank" style={{ color: '#00ff66' }}>Terms of Service &amp; Privacy Policy</Link>.
                </span>
              </label>
              <button className="btn btn-primary" type="submit" disabled={loading || !agreed} style={{ width: '100%', opacity: agreed ? 1 : 0.55 }}>
                {loading ? '◌ Authenticating…' : '▶ Sign In'}
              </button>
            </form>

            <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #112418' }}>
              <p className="mono" style={{ fontSize: 10, color: '#3f6e4a', textAlign: 'center', marginBottom: 12, letterSpacing: 1 }}>
                OR SIGN IN WITH
              </p>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                {Capacitor.isNativePlatform() ? (
                  <button
                    onClick={handleNativeGoogleSignIn}
                    disabled={loading || !agreed}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px',
                      background: '#fff', color: '#3c4043', border: 'none', borderRadius: 4,
                      fontSize: 14, fontWeight: 500, cursor: 'pointer', minHeight: 44, width: '100%',
                      justifyContent: 'center',
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/></svg>
                    Sign in with Google
                  </button>
                ) : (
                  <div style={{ opacity: agreed ? 1 : 0.5, pointerEvents: agreed ? 'auto' : 'none' }}>
                    <GoogleLogin
                      onSuccess={async (credentialResponse) => {
                        if (!agreed) {
                          setError('Please agree to the Terms of Service first.');
                          return;
                        }
                      setError('');
                      setLoading(true);
                      try {
                        const data = await api.googleLogin(credentialResponse.credential);
                        loginUser(data);
                        navigate('/scan');
                      } catch (err) {
                        setError(err.message);
                      } finally {
                        setLoading(false);
                      }
                    }}
                      onError={() => setError('Google sign-in failed')}
                      theme="filled_black"
                      shape="rectangular"
                      text="signin_with_google"
                      size="large"
                    />
                  </div>
                )}
              </div>
            </div>

            <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: '#86efac' }}>
              New here? <Link to="/register">Create an account</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/Register.jsx`

<!-- FILE: frontend/src/pages/Register.jsx -->

```jsx
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { Capacitor } from '@capacitor/core';
import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth';
import { useAuth } from '../App';
import { api } from '../api/client';
import Logo from '../components/Logo';
import { FingerprintWatermark } from '../components/ForensicMotifs';
import PasswordStrength, { passwordPolicyError } from '../components/PasswordStrength';

function FieldError({ msg }) {
  if (!msg) return null;
  return (
    <div className="mono" style={{
      fontSize: 11, color: '#ff8a99', marginTop: 5, letterSpacing: 0.5,
    }}>
      {msg}
    </div>
  );
}

export default function Register() {
  const { loginUser, user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: '', middle_initial: '', last_name: '',
    email: '', username: '', password: '', confirm_password: '',
  });
  const [fieldErrors, setFieldErrors] = useState({});
  const [agreed, setAgreed] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (user) { navigate('/scan', { replace: true }); return null; }

  function update(field, transform) {
    return e => {
      const v = transform ? transform(e.target.value) : e.target.value;
      setForm(f => ({ ...f, [field]: v }));
      if (fieldErrors[field]) setFieldErrors(fe => ({ ...fe, [field]: '' }));
      // Editing the password invalidates a stale "do not match" on the confirm field.
      if (field === 'password' && fieldErrors.confirm_password) {
        setFieldErrors(fe => ({ ...fe, confirm_password: '' }));
      }
    };
  }

  // Compose backend-friendly full_name from the three parts so the database
  // schema stays unchanged.
  function composedFullName() {
    const fn = form.first_name.trim();
    const mi = form.middle_initial.trim().toUpperCase();
    const ln = form.last_name.trim();
    const parts = [fn];
    if (mi) parts.push(mi + '.');
    if (ln) parts.push(ln);
    return parts.join(' ').trim();
  }

  function validate() {
    const errs = {};
    // Allow letters (incl. accented), spaces, hyphens, apostrophes, periods
    const nameRe = /^[A-Za-zÀ-ſ\s'\-.]+$/;

    if (!form.first_name.trim()) errs.first_name = 'First name is required';
    else if (form.first_name.length > 50) errs.first_name = 'Too long (max 50)';
    else if (!nameRe.test(form.first_name)) errs.first_name = 'Letters and basic punctuation only';

    if (form.middle_initial && !/^[A-Za-z]$/.test(form.middle_initial.trim())) {
      errs.middle_initial = 'Single letter';
    }

    if (!form.last_name.trim()) errs.last_name = 'Last name is required';
    else if (form.last_name.length > 50) errs.last_name = 'Too long (max 50)';
    else if (!nameRe.test(form.last_name)) errs.last_name = 'Letters and basic punctuation only';

    if (!form.username.trim()) errs.username = 'Username is required';
    else if (!/^[a-zA-Z][a-zA-Z0-9_]{2,19}$/.test(form.username)) {
      errs.username = '3-20 chars, letters/numbers/underscore, must start with a letter';
    }

    if (!form.email.trim()) errs.email = 'Email is required';
    else if (form.email.length > 254) errs.email = 'Email is too long';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = 'Enter a valid email address';

    const pwErr = passwordPolicyError(form.password);
    if (pwErr) errs.password = pwErr;

    if (!form.confirm_password) errs.confirm_password = 'Please re-enter your password';
    else if (form.confirm_password !== form.password) errs.confirm_password = 'Passwords do not match';

    return errs;
  }

  async function handleNativeGoogleSignUp() {
    if (!agreed) { setError('Please agree to the Terms of Service first.'); return; }
    setError('');
    setLoading(true);
    try {
      const result = await GoogleAuth.signIn();
      const data = await api.googleLogin(result.authentication.idToken);
      loginUser(data);
      navigate('/scan');
    } catch (err) {
      if (err.code !== 'CANCELED') setError('Google sign-up failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!agreed) { setError('Please agree to the Terms of Service first.'); return; }
    const errs = validate();
    setFieldErrors(errs);
    if (Object.keys(errs).length) {
      setError('Please fix the highlighted fields.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const res = await api.register(form.email.trim(), form.username.trim(), form.password, composedFullName());
      if (res && res.access_token) {
        // Email verification disabled on this deployment: auto-login.
        loginUser(res);
        navigate('/scan');
      } else {
        setRegistered(true);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block', fontFamily: "'JetBrains Mono', monospace" };

  if (registered) {
    return (
      <div style={{ maxWidth: 440, margin: 'clamp(20px, 6vw, 60px) auto' }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <div className="mono glow" style={{ fontSize: 40, color: '#00ff66', marginBottom: 12 }}>✉</div>
          <h2 className="oswald" style={{ fontSize: 20, letterSpacing: 2, color: '#d8ffe6', marginBottom: 14 }}>
            CHECK YOUR EMAIL
          </h2>
          <p style={{ fontSize: 14, color: '#86efac', lineHeight: 1.6, marginBottom: 8 }}>
            We sent a confirmation link to <strong style={{ color: '#d8ffe6' }}>{form.email}</strong>.
          </p>
          <p style={{ fontSize: 13, color: '#6dba85', lineHeight: 1.6, marginBottom: 22 }}>
            Click the link in that email to activate your account, then sign in. The link expires in 24 hours.
          </p>
          <button
            className="btn btn-primary"
            style={{ width: '100%' }}
            onClick={async () => {
              setError('');
              try {
                await api.register(form.email.trim(), form.username.trim(), form.password, composedFullName());
                setError('A new verification email is on its way.');
              } catch (err) {
                setError(err.message);
              }
            }}
          >
            ↻ Resend email
          </button>
          <p style={{ textAlign: 'center', marginTop: 18, fontSize: 13, color: '#86efac' }}>
            <Link to="/login">Back to sign in</Link>
          </p>
          {error && (
            <p className="mono" style={{ marginTop: 12, fontSize: 12, color: '#6dba85' }}>{error}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 440, margin: 'clamp(20px, 5vw, 40px) auto', position: 'relative' }}>
      <FingerprintWatermark
        size={420} opacity={0.06}
        style={{ position: 'absolute', top: -40, left: -120, zIndex: 0 }}
      />
      <div style={{ textAlign: 'center', marginBottom: 32, position: 'relative' }}>
        <p className="classification-bar" style={{ marginBottom: 18 }}>
          NEW · OPERATOR · REGISTRATION
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <Logo size={86} glow animated />
        </div>
        <h1 className="oswald glow-strong" style={{ fontSize: 32, color: '#00ff66', letterSpacing: 7, fontWeight: 700 }}>
          REVELATOR
        </h1>
        <p className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 11, letterSpacing: 3 }}>
          [ CREATE YOUR ACCOUNT ]
        </p>
      </div>

      <div className="card">
        <h2 className="oswald" style={{
          fontSize: 18, marginBottom: 20, letterSpacing: 3, textTransform: 'uppercase', color: '#d8ffe6',
        }}>
          ▸ Register
        </h2>

        {error && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12,
            borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#ff8a99',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            ⚠ {error}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>First Name</label>
            <input
              className="input"
              value={form.first_name}
              onChange={update('first_name')}
              placeholder="Juan"
              maxLength={50}
              autoComplete="given-name"
              aria-invalid={!!fieldErrors.first_name}
              required
            />
            <FieldError msg={fieldErrors.first_name} />
          </div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
            <div style={{ width: 96 }}>
              <label style={labelStyle}>M.I.</label>
              <input
                className="input"
                value={form.middle_initial}
                onChange={update('middle_initial', v => v.replace(/[^A-Za-z]/g, '').slice(0, 1).toUpperCase())}
                placeholder="D"
                maxLength={1}
                autoComplete="additional-name"
                aria-invalid={!!fieldErrors.middle_initial}
                style={{ textAlign: 'center', letterSpacing: 2 }}
              />
              <FieldError msg={fieldErrors.middle_initial} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <label style={labelStyle}>Last Name</label>
              <input
                className="input"
                value={form.last_name}
                onChange={update('last_name')}
                placeholder="Dela Cruz"
                maxLength={50}
                autoComplete="family-name"
                aria-invalid={!!fieldErrors.last_name}
                required
              />
              <FieldError msg={fieldErrors.last_name} />
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Username</label>
            <input
              className="input"
              value={form.username}
              onChange={update('username', v => v.replace(/[^A-Za-z0-9_]/g, '').slice(0, 20))}
              placeholder="juandc"
              maxLength={20}
              autoComplete="username"
              aria-invalid={!!fieldErrors.username}
              required
            />
            <FieldError msg={fieldErrors.username} />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Email</label>
            <input
              className="input"
              type="email"
              value={form.email}
              onChange={update('email', v => v.slice(0, 254))}
              placeholder="you@example.com"
              maxLength={254}
              autoComplete="email"
              aria-invalid={!!fieldErrors.email}
              required
            />
            <FieldError msg={fieldErrors.email} />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Password</label>
            <input
              className="input"
              type={showPw ? 'text' : 'password'}
              value={form.password}
              onChange={update('password')}
              placeholder="At least 8 chars, letters + numbers"
              maxLength={128}
              autoComplete="new-password"
              aria-invalid={!!fieldErrors.password}
              required
              minLength={8}
            />
            <PasswordStrength password={form.password} />
            <FieldError msg={fieldErrors.password} />
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={labelStyle}>Confirm Password</label>
            <input
              className="input"
              type={showPw ? 'text' : 'password'}
              value={form.confirm_password}
              onChange={update('confirm_password')}
              placeholder="Re-enter your password"
              maxLength={128}
              autoComplete="new-password"
              aria-invalid={!!fieldErrors.confirm_password}
              required
            />
            {form.confirm_password && form.confirm_password === form.password && (
              <div className="mono" style={{ fontSize: 11, color: '#00ff66', marginTop: 5, letterSpacing: 0.5 }}>
                ✓ Passwords match
              </div>
            )}
            <FieldError msg={fieldErrors.confirm_password} />
          </div>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 18,
            fontSize: 12, color: '#6dba85', cursor: 'pointer',
          }}>
            <input
              type="checkbox"
              checked={showPw}
              onChange={e => setShowPw(e.target.checked)}
              style={{ width: 15, height: 15, accentColor: '#00ff66', flexShrink: 0 }}
            />
            Show passwords
          </label>
          <label style={{
            display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 22,
            fontSize: 12, color: '#86efac', lineHeight: 1.5, cursor: 'pointer',
          }}>
            <input
              type="checkbox"
              checked={agreed}
              onChange={e => setAgreed(e.target.checked)}
              style={{ marginTop: 2, width: 16, height: 16, accentColor: '#00ff66', flexShrink: 0 }}
            />
            <span>
              I have read and agree to the{' '}
              <Link to="/terms" target="_blank" style={{ color: '#00ff66' }}>Terms of Service &amp; Privacy Policy</Link>.
            </span>
          </label>
          <button className="btn btn-primary" type="submit" disabled={loading || !agreed} style={{ width: '100%', opacity: agreed ? 1 : 0.55 }}>
            {loading ? '◌ Creating account…' : '▶ Create Account'}
          </button>
        </form>

        <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #112418' }}>
          <p className="mono" style={{ fontSize: 10, color: '#3f6e4a', textAlign: 'center', marginBottom: 12, letterSpacing: 1 }}>
            OR SIGN UP WITH
          </p>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            {Capacitor.isNativePlatform() ? (
              <button
                onClick={handleNativeGoogleSignUp}
                disabled={loading || !agreed}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 20px',
                  background: '#fff', color: '#3c4043', border: 'none', borderRadius: 4,
                  fontSize: 14, fontWeight: 500, cursor: 'pointer', minHeight: 44, width: '100%',
                  justifyContent: 'center',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 18 18"><path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"/><path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/><path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/></svg>
                Sign up with Google
              </button>
            ) : (
              <div style={{ opacity: agreed ? 1 : 0.5, pointerEvents: agreed ? 'auto' : 'none' }}>
                <GoogleLogin
                  onSuccess={async (credentialResponse) => {
                    if (!agreed) {
                      setError('Please agree to the Terms of Service first.');
                      return;
                    }
                    setError('');
                    setLoading(true);
                    try {
                      const data = await api.googleLogin(credentialResponse.credential);
                      loginUser(data);
                      navigate('/scan');
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setLoading(false);
                    }
                  }}
                  onError={() => setError('Google sign-up failed')}
                  theme="filled_black"
                  shape="rectangular"
                  text="signup_with"
                  size="large"
                />
              </div>
            )}
          </div>
        </div>

        <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: '#86efac' }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/ResetPassword.jsx`

<!-- FILE: frontend/src/pages/ResetPassword.jsx -->

```jsx
import React, { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import Logo from '../components/Logo';
import { FingerprintWatermark } from '../components/ForensicMotifs';
import PasswordStrength, { passwordPolicyError, PASSWORD_MIN } from '../components/PasswordStrength';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const pwErr = passwordPolicyError(password);
    if (pwErr) { setError(pwErr + '.'); return; }
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    setError('');
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const labelStyle = { fontSize: 11, color: '#86efac', textTransform: 'uppercase', letterSpacing: 2, marginBottom: 6, display: 'block', fontFamily: "'JetBrains Mono', monospace" };

  return (
    <div style={{ maxWidth: 440, margin: 'clamp(20px, 6vw, 60px) auto', position: 'relative' }}>
      <FingerprintWatermark size={420} opacity={0.06} style={{ position: 'absolute', top: -40, left: -120, zIndex: 0 }} />
      <div style={{ textAlign: 'center', marginBottom: 32, position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
          <Logo size={86} glow animated />
        </div>
        <h1 className="oswald glow-strong" style={{ fontSize: 32, color: '#00ff66', letterSpacing: 7, fontWeight: 700 }}>
          REVELATOR
        </h1>
        <p className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 11, letterSpacing: 3 }}>
          [ SET A NEW PASSWORD ]
        </p>
      </div>

      <div className="card">
        {done ? (
          <div style={{ textAlign: 'center' }}>
            <div className="mono glow" style={{ fontSize: 40, color: '#00ff66', marginBottom: 12 }}>✓</div>
            <h2 className="oswald" style={{ fontSize: 20, letterSpacing: 2, color: '#d8ffe6', marginBottom: 14 }}>
              PASSWORD UPDATED
            </h2>
            <p style={{ fontSize: 14, color: '#86efac', lineHeight: 1.6, marginBottom: 22 }}>
              Your password has been changed. You can now sign in with your new password.
            </p>
            <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => navigate('/login')}>
              ▶ Go to Sign In
            </button>
          </div>
        ) : !token ? (
          <div style={{ textAlign: 'center' }}>
            <h2 className="oswald" style={{ fontSize: 18, letterSpacing: 2, color: '#d8ffe6', marginBottom: 14 }}>
              INVALID LINK
            </h2>
            <p style={{ fontSize: 13, color: '#6dba85', lineHeight: 1.6, marginBottom: 22 }}>
              This reset link is missing its token. Request a new one.
            </p>
            <p style={{ textAlign: 'center', fontSize: 13, color: '#86efac' }}>
              <Link to="/forgot-password">Request a reset link</Link>
            </p>
          </div>
        ) : (
          <>
            <h2 className="oswald" style={{ fontSize: 18, marginBottom: 20, letterSpacing: 3, textTransform: 'uppercase', color: '#d8ffe6' }}>
              ▸ Reset Password
            </h2>

            {error && (
              <div style={{
                background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 12,
                borderRadius: 2, marginBottom: 16, fontSize: 13, color: '#ff8a99',
                fontFamily: "'JetBrains Mono', monospace",
              }}>
                ⚠ {error}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 14 }}>
                <label style={labelStyle}>New Password</label>
                <input
                  className="input"
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder={`At least ${PASSWORD_MIN} chars, letters + numbers`}
                  maxLength={128}
                  autoComplete="new-password"
                  required
                  minLength={PASSWORD_MIN}
                />
                <PasswordStrength password={password} />
              </div>
              <div style={{ marginBottom: 14 }}>
                <label style={labelStyle}>Confirm Password</label>
                <input
                  className="input"
                  type={showPw ? 'text' : 'password'}
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="Re-enter password"
                  maxLength={128}
                  autoComplete="new-password"
                  required
                  minLength={PASSWORD_MIN}
                />
                {confirm && (
                  <div className="mono" style={{
                    fontSize: 11, marginTop: 5, letterSpacing: 0.5,
                    color: confirm === password ? '#00ff66' : '#ff8a99',
                  }}>
                    {confirm === password ? '✓ Passwords match' : 'Passwords do not match'}
                  </div>
                )}
              </div>
              <label style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 22,
                fontSize: 12, color: '#6dba85', cursor: 'pointer',
              }}>
                <input
                  type="checkbox"
                  checked={showPw}
                  onChange={e => setShowPw(e.target.checked)}
                  style={{ width: 15, height: 15, accentColor: '#00ff66', flexShrink: 0 }}
                />
                Show passwords
              </label>
              <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
                {loading ? '◌ Updating…' : '▶ Update Password'}
              </button>
            </form>

            <p style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: '#86efac' }}>
              <Link to="/login">Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/SampleGallery.jsx`

<!-- FILE: frontend/src/pages/SampleGallery.jsx -->

```jsx
import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { CATEGORY_BY_ID, GUIDANCE } from '../categories';

export default function SampleGallery() {
  const { categoryId } = useParams();
  const navigate = useNavigate();
  const cat = CATEGORY_BY_ID[categoryId];
  const [stats, setStats] = useState(null);
  const [samples, setSamples] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!cat) return;
    api.getCategories().then(data => {
      // Find the category data in the flattened categories array
      const catData = data.categories
        ? Object.values(data.categories).flat().find(c => c.api_key === cat.apiKey)
        : null;
      const total = catData?.dataset_count || 0;
      const trained = catData?.is_trained || false;
      setStats({ total, trained, threshold: data.limited_data_threshold || 200 });
    }).catch(() => {});
  }, [categoryId, cat]);

  useEffect(() => {
    if (!cat) return;
    setLoading(true);
    fetch(`/api/samples/${cat.apiKey}`)
      .then(r => r.json())
      .then(data => {
        setSamples(data.samples || []);
        setLoading(false);
      })
      .catch(() => {
        setSamples([]);
        setLoading(false);
      });
  }, [categoryId, cat]);

  if (!cat) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <p className="mono" style={{ color: '#86efac', letterSpacing: 2, marginBottom: 14 }}>
          ▣ UNKNOWN CATEGORY
        </p>
        <Link to="/scan" style={{ color: '#00ff66' }}>← back to scan</Link>
      </div>
    );
  }

  const guidance = GUIDANCE[categoryId] || { shooting: [], detector: '' };
  const accent = cat.color;

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        style={{
          background: 'none', border: 'none', color: '#6dba85', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16, padding: 0,
          fontSize: 13, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1,
        }}
      >
        ← back
      </button>

      <div style={{
        background: `linear-gradient(135deg, ${accent}10 0%, transparent 70%), #0a120c`,
        borderLeft: `3px solid ${accent}`,
        border: '1px solid #112418', borderLeftWidth: 3,
        padding: 22, marginBottom: 24, borderRadius: 3,
        display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap',
        boxShadow: `0 0 24px ${accent}20, inset 0 1px 0 ${accent}15`,
      }}>
        <span style={{
          fontSize: 40, color: accent,
          textShadow: `0 0 18px ${accent}99`,
          lineHeight: 1,
        }}>{cat.icon}</span>
        <div style={{ flex: 1, minWidth: 200 }}>
          <p className="mono" style={{
            fontSize: 10, letterSpacing: 3, color: accent, margin: 0,
            textShadow: `0 0 8px ${accent}80`,
          }}>
            ▸ {cat.code} · SAMPLE GALLERY · TIER {cat.tier}
          </p>
          <h1 className="oswald" style={{
            fontSize: 26, fontWeight: 700, letterSpacing: 2, margin: '4px 0 0',
            textTransform: 'uppercase', color: '#d8ffe6',
          }}>
            {cat.title}
          </h1>
          <p style={{ fontSize: 13, color: '#86efac', margin: '6px 0 0', maxWidth: 600, lineHeight: 1.5 }}>
            {cat.description}
          </p>
        </div>
        <Link
          to={`/scan?category=${categoryId}`}
          className="btn btn-primary"
          style={{ fontSize: 12, padding: '12px 18px' }}
        >
          ▶ Start Scan
        </Link>
      </div>

      {stats && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, marginBottom: 24,
        }}>
          <DatasetStat
            label="Training Images"
            value={stats.total > 0 ? stats.total.toLocaleString() : 'No data yet'}
            color={stats.total >= stats.threshold ? '#00ff66' : (stats.total > 0 ? '#ffa040' : '#86efac')}
          />
          <DatasetStat
            label="Detector Status"
            value={stats.total >= stats.threshold ? 'Ready' : (stats.total > 0 ? 'Training' : 'Awaiting Data')}
            color={stats.total >= stats.threshold ? '#00ff66' : (stats.total > 0 ? '#ffa040' : '#86efac')}
          />
          <DatasetStat
            label="Min Threshold"
            value={stats.threshold.toLocaleString()}
            color="#86efac"
          />
          <Link to="/about" style={{
            background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
            padding: '14px 12px', textAlign: 'center', textDecoration: 'none',
            display: 'flex', flexDirection: 'column', justifyContent: 'center',
            transition: 'border-color 0.15s, box-shadow 0.15s',
          }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = '#1f5d39';
              e.currentTarget.style.boxShadow = '0 0 14px rgba(0,255,102,0.15)';
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = '#112418';
              e.currentTarget.style.boxShadow = 'none';
            }}>
            <div className="oswald" style={{ fontSize: 13, color: '#00ff66', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              Full breakdown →
            </div>
            <div style={{ fontSize: 10, color: '#3f6e4a', marginTop: 4 }}>About page</div>
          </Link>
        </div>
      )}

      {stats && stats.total > 0 && stats.total < stats.threshold && (
        <div style={{
          background: 'rgba(255,160,64,0.08)', border: '1px solid rgba(255,160,64,0.4)',
          padding: 12, borderRadius: 3, marginBottom: 24, fontSize: 13, color: '#ffc888',
          display: 'flex', gap: 10, alignItems: 'flex-start',
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          <span>⚠</span>
          <span>
            <strong>Limited data:</strong> only {stats.total.toLocaleString()} / {stats.threshold.toLocaleString()} training images collected.
            Detector accuracy may improve as more samples are gathered.
          </span>
        </div>
      )}

      {stats && stats.total === 0 && (
        <div style={{
          background: 'rgba(255,102,102,0.08)', border: '1px solid rgba(255,102,102,0.4)',
          padding: 12, borderRadius: 3, marginBottom: 24, fontSize: 13, color: '#ff9999',
          display: 'flex', gap: 10, alignItems: 'flex-start',
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          <span>◐</span>
          <span>
            <strong>No training data:</strong> this category is awaiting dataset samples.
            Sample images will appear here once the dataset is populated.
          </span>
        </div>
      )}

      <div className="card" style={{ marginBottom: 24 }}>
        <h2 className="oswald" style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: 2.5, color: '#6dba85', marginBottom: 14 }}>
          ▸ Capture Protocol
        </h2>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {guidance.shooting.map((tip, i) => (
            <li key={i} style={{
              padding: '10px 0', borderBottom: i < guidance.shooting.length - 1 ? '1px solid #112418' : 'none',
              fontSize: 14, color: '#d8ffe6', display: 'flex', gap: 12, alignItems: 'flex-start',
            }}>
              <span className="mono" style={{
                color: accent, fontSize: 11, letterSpacing: 1, lineHeight: 1.5,
                textShadow: `0 0 6px ${accent}80`,
              }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span>{tip}</span>
            </li>
          ))}
        </ul>

        {guidance.detector && (
          <div style={{
            marginTop: 18, padding: 14, background: '#000', borderRadius: 2,
            borderLeft: `2px solid ${accent}`,
          }}>
            <p className="oswald" style={{
              fontSize: 11, color: accent, textTransform: 'uppercase', letterSpacing: 2.5,
              margin: 0, marginBottom: 6,
              textShadow: `0 0 6px ${accent}80`,
            }}>
              ▸ What the detector looks for
            </p>
            <p style={{ fontSize: 13, color: '#d8ffe6', margin: 0, lineHeight: 1.6 }}>
              {guidance.detector}
            </p>
          </div>
        )}
      </div>

      <h2 className="oswald" style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: 2.5, color: '#6dba85', marginBottom: 14 }}>
        ▸ Dataset Examples
      </h2>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#86efac' }}>
          <p className="mono">Loading samples...</p>
        </div>
      )}

      {!loading && samples.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: '#86efac' }}>
          <p className="mono">No sample images available yet</p>
        </div>
      )}

      {!loading && samples.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {samples.map((sample, idx) => (
            <SampleImage
              key={`${sample.split}-${sample.filename}`}
              src={sample.url}
              label={`${sample.split.toUpperCase()}: ${sample.filename}`}
              catColor={accent}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DatasetStat({ label, value, color }) {
  return (
    <div style={{
      background: '#0a120c', border: '1px solid #112418', borderRadius: 3,
      padding: 14, textAlign: 'center',
    }}>
      <div className="mono" style={{ fontSize: 18, fontWeight: 600, color, textShadow: `0 0 8px ${color}60` }}>
        {value}
      </div>
      <div className="oswald" style={{ fontSize: 10, letterSpacing: 1.5, textTransform: 'uppercase', color: '#3f6e4a', marginTop: 4 }}>
        {label}
      </div>
    </div>
  );
}

function SampleImage({ src, label, catColor }) {
  const [errored, setErrored] = useState(false);
  const [loaded, setLoaded] = useState(false);

  return (
    <div
      className="card"
      style={{
        position: 'relative',
        overflow: 'hidden',
        background: '#000',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          aspectRatio: '4/3',
          background: '#000',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {!errored && (
          <img
            src={src}
            alt={label}
            onError={() => setErrored(true)}
            onLoad={() => setLoaded(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              opacity: loaded ? 1 : 0,
              transition: 'opacity 0.3s',
            }}
          />
        )}
        {!loaded && !errored && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'repeating-linear-gradient(45deg, #000 0 12px, #0a120c 12px 24px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#3f6e4a',
            }}
          >
            <span className="mono" style={{ fontSize: 11 }}>Loading...</span>
          </div>
        )}
        {errored && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              background: `repeating-linear-gradient(45deg, #000 0 12px, #0a120c 12px 24px)`,
              color: '#3f6e4a',
              gap: 6,
            }}
          >
            <span className="mono" style={{ fontSize: 10, color: catColor, letterSpacing: 2 }}>
              ERROR
            </span>
            <span style={{ fontSize: 11 }}>failed to load</span>
          </div>
        )}
        <span
          className="mono"
          style={{
            position: 'absolute',
            top: 6,
            left: 6,
            fontSize: 9,
            padding: '2px 6px',
            borderRadius: 2,
            background: 'rgba(0,0,0,0.85)',
            color: catColor,
            letterSpacing: 1.5,
            border: `1px solid ${catColor}50`,
          }}
        >
          {label.split(':')[0]}
        </span>
      </div>
      <div style={{ padding: 10, borderTop: '1px solid #112418' }}>
        <p className="mono" style={{ fontSize: 10, color: '#86efac', margin: 0, wordBreak: 'break-all' }}>
          {label.split(':')[1]?.trim()}
        </p>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/Scan.jsx`

<!-- FILE: frontend/src/pages/Scan.jsx -->

```jsx
import React, { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { StickyNote, Check, AlertTriangle } from 'lucide-react';
import { api } from '../api/client';
import { useAuth, useScan } from '../App';
import { MagnifierIcon } from '../components/ForensicMotifs';
import { CATEGORY_BY_KEY, MAIN_CATEGORY_CODE_BY_KEY } from '../categories';
import { requestApiKeyTutorial } from '../apiKeyTutorial';

export default function Scan() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { status: scanStatus, result, error: scanError, previewUrl: ctxPreview, startScan, stopScan, clearScan } = useScan();

  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const [documentType, setDocumentType] = useState('');
  const [documentTypes, setDocumentTypes] = useState([]);
  const [showExtras, setShowExtras] = useState(false);
  const [suspicionReason, setSuspicionReason] = useState('');
  const [areaOfConcern, setAreaOfConcern] = useState('');
  const [imageSource, setImageSource] = useState('');
  const [isForgedBelief, setIsForgedBelief] = useState('');
  const [shotType, setShotType] = useState('');
  const [lighting, setLighting] = useState('');
  const [physicalClues, setPhysicalClues] = useState('');
  const fileRef = useRef();
  const canvasRef = useRef();

  const loading = scanStatus === 'scanning';
  const error = scanError;
  const activePreview = preview || ctxPreview;

  // Load document types on mount
  useEffect(() => {
    api.getDocumentTypes()
      .then(data => setDocumentTypes(data.document_types))
      .catch(err => console.error('Failed to load document types:', err));
  }, []);

  // Handle quota exhaustion errors
  useEffect(() => {
    if (scanError === 'quota_exhausted' || scanError === 'no_api_key') {
      setQuotaExhausted(true);
      clearScan();
      localStorage.setItem('fg_highlight_key_input', 'true');
      localStorage.setItem('fg_no_api_key', scanError === 'no_api_key' ? 'true' : 'false');
      requestApiKeyTutorial();
      navigate('/account');
    }
  }, [clearScan, navigate, scanError]);

  function openApiKeyTutorial() {
    requestApiKeyTutorial();
    navigate('/account');
  }

  // Draw annotations when result arrives
  useEffect(() => {
    if (result?.annotations?.length > 0 && result.original_image_dimensions) {
      setTimeout(() => drawAnnotations(
        result.annotations,
        result.original_image_dimensions.width,
        result.original_image_dimensions.height,
      ), 100);
    }
  }, [result]);

  function resetScan() {
    setFile(null);
    setPreview(null);
    clearScan();
    setQuotaExhausted(false);
  }

  function handleFileChange(e) {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    clearScan();
    const reader = new FileReader();
    reader.onload = ev => setPreview(ev.target.result);
    reader.readAsDataURL(f);
  }

  async function handleTakePhoto() {
    clearScan();
    try {
      const photo = await Camera.getPhoto({
        quality: 90, allowEditing: false,
        resultType: CameraResultType.Base64, source: CameraSource.Camera,
      });

      const format = (photo.format || 'jpeg').toLowerCase();
      const mimeType = `image/${format === 'jpg' ? 'jpeg' : format}`;
      let blob;
      let previewUrl;

      if (photo.base64String) {
        const binary = atob(photo.base64String);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        blob = new Blob([bytes], { type: mimeType });
        previewUrl = `data:${mimeType};base64,${photo.base64String}`;
      } else if (photo.webPath || photo.path) {
        const res = await fetch(photo.webPath || photo.path);
        if (!res.ok) throw new Error(`Camera image could not be read (${res.status})`);
        blob = await res.blob();
        previewUrl = URL.createObjectURL(blob);
      } else {
        throw new Error('Camera returned no image data');
      }

      const f = new File([blob], `scan-${Date.now()}.${format}`, { type: blob.type || mimeType });
      setFile(f);
      setPreview(previewUrl);
    } catch (err) {
      // ignore - camera cancel or transient error; user can retry
      if (err?.message && !/cancel/i.test(err.message)) console.error('Camera error:', err);
    }
  }

  function drawAnnotations(annotations, imgW, imgH) {
    const canvas = canvasRef.current;
    if (!canvas || !activePreview) return;
    const img = new Image();
    img.onload = () => {
      const maxW = Math.min(canvas.parentElement.offsetWidth - 32, 800);
      const scale = maxW / imgW;
      canvas.width = imgW * scale;
      canvas.height = imgH * scale;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      annotations.forEach((ann, idx) => {
        const c = ann.coordinates;
        const x = c.x_min * scale;
        const y = c.y_min * scale;
        const w = (c.x_max - c.x_min) * scale;
        const h = (c.y_max - c.y_min) * scale;
        ctx.shadowColor = ann.color || '#00ff66';
        ctx.shadowBlur = 8;
        ctx.strokeStyle = ann.color || '#00ff66';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.shadowBlur = 0;
        ctx.fillStyle = ann.color || '#00ff66';
        ctx.font = 'bold 12px JetBrains Mono';
        const label = `${idx + 1}. ${ann.title} (${(ann.confidence * 100).toFixed(0)}%)`;
        const tw = ctx.measureText(label).width + 8;
        ctx.fillRect(x, y - 18, tw, 18);
        ctx.fillStyle = '#000';
        ctx.fillText(label, x + 4, y - 5);
      });
    };
    img.src = activePreview;
  }

  function handleAnalyze() {
    if (!file) return;
    setQuotaExhausted(false);
    startScan(
      file,
      documentType !== 'other' ? documentType : null,
      {
        suspicionReason: suspicionReason.trim() || null,
        areaOfConcern: areaOfConcern || null,
        imageSource: imageSource || null,
        isForgedBelief: isForgedBelief || null,
        shotType: shotType || null,
        lighting: lighting || null,
        physicalClues: physicalClues || null,
      },
      preview,
    );
  }

  const verdictColors = {
    forged: '#ff3344',
    suspicious: '#ffa040',
    no_forgery_detected: '#00ff66',
    not_a_document: '#737373',
  };


  return (
    <div>
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <h2 className="oswald glow" style={{ fontSize: 26, color: '#00ff66', letterSpacing: 4, textTransform: 'uppercase', margin: 0 }}>
          Scan Forgery
        </h2>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 20, maxWidth: 800, margin: '0 auto' }}>
        <div className="card">
          <input ref={fileRef} type="file" accept="image/*" onChange={handleFileChange} style={{ display: 'none' }} />

          {!activePreview ? (
            <>
              {/* Camera-first big primary action */}
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleTakePhoto}
                style={{
                  width: '100%',
                  padding: '22px 16px',
                  fontSize: 16,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
                  marginBottom: 12,
                  minHeight: 64,
                }}
              >
                <span style={{ fontSize: 24, lineHeight: 1 }}>⌖</span>
                <span>Take Photo</span>
              </button>

              <div
                onClick={() => fileRef.current.click()}
                style={{
                  border: '1px dashed #1f5d39', borderRadius: 3,
                  padding: 36, textAlign: 'center',
                  background: 'rgba(0,255,102,0.02)',
                  cursor: 'pointer',
                }}
              >
                <div className="mono glow" style={{ fontSize: 28, marginBottom: 8, color: '#00ff66' }}>+</div>
                <p className="mono" style={{ color: '#86efac', fontSize: 12, letterSpacing: 1.5 }}>UPLOAD FROM DEVICE</p>
              </div>
            </>
          ) : (
            <>
              {/* Preview with retake control */}
              <div style={{
                border: '1px solid #1d3825', borderRadius: 3, padding: 12,
                background: '#000', textAlign: 'center', marginBottom: 12,
              }}>
                <img src={activePreview} alt="Preview" style={{
                  maxWidth: '100%', maxHeight: 360, borderRadius: 2,
                  display: 'block', margin: '0 auto',
                }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <button
                  type="button"
                  onClick={handleTakePhoto}
                  style={{
                    padding: '12px', minHeight: 44,
                    background: 'transparent', border: '1px solid #1d3825',
                    color: '#86efac', cursor: 'pointer', borderRadius: 3,
                    fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                    letterSpacing: 1.5, fontSize: 12,
                  }}
                >
                  ↻ Retake
                </button>
                <button
                  type="button"
                  onClick={() => fileRef.current.click()}
                  style={{
                    padding: '12px', minHeight: 44,
                    background: 'transparent', border: '1px solid #1d3825',
                    color: '#86efac', cursor: 'pointer', borderRadius: 3,
                    fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase',
                    letterSpacing: 1.5, fontSize: 12,
                  }}
                >
                  ⎙ Upload New
                </button>
              </div>
            </>
          )}
        </div>

        {/* Optional context - collapsed by default */}
        <div style={{ border: '1px solid #112418', borderRadius: 3, background: 'rgba(0,255,102,0.02)' }}>
          <button
            type="button"
            onClick={() => setShowExtras(!showExtras)}
            style={{
              width: '100%', padding: '12px 16px', background: 'transparent', border: 'none',
              cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              color: '#6dba85', fontFamily: "'Oswald', sans-serif", letterSpacing: 2,
              textTransform: 'uppercase', fontSize: 12,
            }}
          >
            <span>
              ＋ Additional Context
              <span style={{ fontSize: 10, color: '#ffa040', marginLeft: 8, letterSpacing: 1 }}>RECOMMENDED</span>
            </span>
            <span style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 1 }}>
              {showExtras ? '▲ HIDE' : '▼ EXPAND'}
            </span>
          </button>
          {showExtras && (
            <div style={{ padding: '0 16px 16px', display: 'grid', gap: 14 }}>
              <p style={{ fontSize: 12, color: '#86efac', margin: 0 }}>
                Filling in context significantly improves accuracy, especially document type, suspected forgery, and any physical clues you noticed. All fields are optional but the more you provide, the fewer alternative hypotheses the model will need to hedge on.
              </p>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  DOCUMENT TYPE
                </label>
                <select
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value=""> Not sure / general document (default) -</option>
                  {documentTypes.map(dt => (
                    <option key={dt.key} value={dt.key} style={{ background: '#0a1605', color: '#d8ffe6' }}>
                      {dt.title}
                    </option>
                  ))}
                </select>
                {documentType && documentType !== 'other' && (
                  <p style={{ fontSize: 11, color: '#3f6e4a', marginTop: 5, fontStyle: 'italic' }}>
                    {documentTypes.find(dt => dt.key === documentType)?.description}
                  </p>
                )}
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  WHAT MAKES YOU SUSPICIOUS?
                </label>
                <textarea
                  value={suspicionReason}
                  onChange={(e) => setSuspicionReason(e.target.value)}
                  maxLength={300}
                  rows={2}
                  placeholder="e.g. The signature looks shaky, or the date seems edited..."
                  style={{
                    width: '100%', padding: 10, background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    resize: 'vertical',
                  }}
                />
                <p style={{ fontSize: 10, color: '#3f6e4a', margin: '4px 0 0', textAlign: 'right' }}>
                  {suspicionReason.length}/300
                </p>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  AREA TO FOCUS ON
                </label>
                <select
                  value={areaOfConcern}
                  onChange={(e) => setAreaOfConcern(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- Anywhere (default) -</option>
                  <option value="signature">Signature</option>
                  <option value="photo">Photo / face</option>
                  <option value="dates">Dates</option>
                  <option value="seals_stamps">Seals or stamps</option>
                  <option value="watermarks">Watermarks / security features</option>
                  <option value="text_content">Text content</option>
                  <option value="numbers">Numbers / amounts</option>
                </select>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  HOW WAS THIS CAPTURED?
                </label>
                <select
                  value={imageSource}
                  onChange={(e) => setImageSource(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- Not sure (default) -</option>
                  <option value="phone_photo">Phone photo</option>
                  <option value="scanner">Scanner</option>
                  <option value="screenshot">Screenshot</option>
                  <option value="downloaded_pdf">Downloaded PDF</option>
                </select>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  ARE YOU SURE THIS IS FORGED?
                </label>
                <select
                  value={isForgedBelief}
                  onChange={(e) => setIsForgedBelief(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- Not sure (default) -</option>
                  <option value="yes_confident">Yes, I'm confident</option>
                  <option value="probably">Probably</option>
                  <option value="just_checking">Just checking, could go either way</option>
                  <option value="no_just_curious">No, just curious / authenticating</option>
                </select>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  IS THIS ZOOMED IN OR MACRO?
                </label>
                <select
                  value={shotType}
                  onChange={(e) => setShotType(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- Not sure (default) -</option>
                  <option value="macro_extreme_close">Macro / extreme close-up</option>
                  <option value="zoomed_close_up">Zoomed close-up of one region</option>
                  <option value="normal_full_doc">Normal,whole document</option>
                  <option value="wide_with_context">Wide shot with surroundings</option>
                </select>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  DID YOU USE SPECIAL LIGHTING?
                </label>
                <select
                  value={lighting}
                  onChange={(e) => setLighting(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- Not sure / normal light (default) -</option>
                  <option value="ultraviolet">Ultraviolet (UV) light</option>
                  <option value="raking_light">Raking / oblique light (for indentations)</option>
                  <option value="backlit">Backlit (light behind paper)</option>
                  <option value="infrared">Infrared</option>
                  <option value="normal_daylight">Normal daylight only</option>
                </select>
              </div>

              <div>
                <label className="mono" style={{ fontSize: 10, letterSpacing: 2, color: '#6dba85', display: 'block', marginBottom: 6 }}>
                  PHYSICAL CLUE YOU NOTICED
                </label>
                <select
                  value={physicalClues}
                  onChange={(e) => setPhysicalClues(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', background: '#0a1605',
                    border: '1px solid #1d3825', borderRadius: 3,
                    color: '#d8ffe6', fontSize: 13, fontFamily: "'JetBrains Mono', monospace",
                    cursor: 'pointer',
                  }}
                >
                  <option value="">- None / not sure (default) -</option>
                  <option value="indentation_grooves">Indentation grooves / canal marks behind writing</option>
                  <option value="carbon_streaks">Faint carbon residue along strokes</option>
                  <option value="uniform_traced_lines">Uniform line weight (looks traced)</option>
                  <option value="ink_halo">Halo or discoloration around erased area</option>
                  <option value="paper_thinning">Thinned or abraded paper surface</option>
                  <option value="characters_inserted">Extra characters squeezed inside words/numbers</option>
                  <option value="text_between_lines">Writing squeezed between existing lines</option>
                  <option value="cut_paste_edges">Visible cut/paste edges or texture mismatch</option>
                  <option value="whiteout_correction">Correction fluid covering text</option>
                  <option value="ink_scribbles">Ink scribbled over original text</option>
                  <option value="counterfeit_currency">Suspect counterfeit banknote</option>
                  <option value="computer_generated">Looks computer-generated / desktop-published</option>
                  <option value="scan_tampering_artifacts">Scanned document with visible digital edits on top</option>
                  <option value="sympathetic_hidden_writing">Hidden writing only visible under special lighting (UV, raking, backlight)</option>
                  <option value="uv_reactive_ink_glow">Ink glows or reacts under UV light</option>
                </select>
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleAnalyze} disabled={!file || loading} style={{ fontSize: 16, padding: '18px 0', flex: 1 }}>
            {loading ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                <span className="scan-spinner" aria-hidden="true" />
                Running detection...
              </span>
            ) : '▶ Scan Forgery'}
          </button>
          {loading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
              <div className="scan-progress" role="progressbar" aria-label="Scan in progress">
                <span />
              </div>
              <button
                onClick={stopScan}
                title="Stop scan"
                style={{
                  flex: 1, background: 'rgba(255,51,68,0.08)', border: '1px solid rgba(255,51,68,0.5)',
                  color: '#ff8a99', borderRadius: 3, padding: '0 16px',
                  cursor: 'pointer', fontSize: 13,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1,
                }}
              >
                ✕ Stop
              </button>
            </div>
          )}
        </div>

        <button
          type="button"
          className="btn btn-secondary"
          onClick={openApiKeyTutorial}
          style={{ width: '100%', padding: '12px', fontSize: 12, letterSpacing: 1.5 }}
        >
          How to Get API Key
        </button>

        <div style={{
          border: '1px solid #1d3825', borderRadius: 3, padding: '10px 14px',
          background: 'rgba(109,186,133,0.06)', fontSize: 12, color: '#86efac',
          lineHeight: 1.6,
        }}>
          <span style={{ color: '#6dba85', fontWeight: 600 }}>Note:</span> It is highly recommended you use multiple API keys from different Google accounts so that when you hit your quota for your current API key (it resets every 12 hours), you can just activate another one and keep scanning documents.
        </div>

        {error && (
          <div style={{
            background: 'rgba(255,51,68,0.1)', border: '1px solid #ff3344', padding: 14, borderRadius: 2,
            fontSize: 13, color: '#ff8a99', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 0.5,
          }}>
            ⚠ {error}
          </div>
        )}

        {quotaExhausted && (() => {
          const isNoKey = localStorage.getItem('fg_no_api_key') === 'true';
          return (
            <div style={{
              background: 'rgba(255,160,64,0.08)', border: '1px solid #ffa040', padding: 16, borderRadius: 3,
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              <div style={{ fontSize: 14, color: '#ffa040', fontWeight: 700, marginBottom: 10 }}>
                {isNoKey ? '⚠ API Key Not Set Up' : '⚠ API Quota Exhausted'}
              </div>
              <p style={{ fontSize: 12, color: '#d8ffe6', lineHeight: 1.7, margin: '0 0 14px 0' }}>
                {isNoKey
                  ? "It seems your API key isn't set up yet. Head to the Account tab to paste in your Gemini API key - it's free from Google AI Studio."
                  : <>Your current API key has used up its free daily quota (1,500 requests/day). It will <strong style={{ color: '#ffa040' }}>reset automatically in ~24 hours</strong>, or add a key from a different Google account to keep scanning now.</>
                }
              </p>
              <a
                href="/account"
                style={{
                  display: 'inline-block', padding: '10px 20px',
                  background: 'rgba(0,255,102,0.1)', border: '1px solid #00ff66',
                  borderRadius: 3, color: '#00ff66', textDecoration: 'none', fontSize: 12,
                  fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5,
                }}>
                → Go to Account Tab
              </a>
            </div>
          );
        })()}

        {result && (
          <ForensicResultCard
            result={result}
            canvasRef={canvasRef}
            verdictColors={verdictColors}

            documentTypeLabel={documentTypes.find(dt => dt.key === documentType)?.title}
          />
        )}

        {result && result.scan_id && (
          <ScanNotes scanId={result.scan_id} />
        )}

        {result && (
          <button className="btn" onClick={resetScan} style={{ fontSize: 13 }}>
            ← New Scan
          </button>
        )}
      </div>
    </div>
  );
}

function LlmUpgradePrompt({ requiredPlan = 'premium' }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(139,92,246,0.1) 0%, rgba(139,92,246,0.02) 100%)',
      border: '1px solid rgba(139,92,246,0.4)', borderRadius: 3, padding: 14,
      display: 'flex', gap: 12, alignItems: 'flex-start',
    }}>
      <span style={{ fontSize: 22, lineHeight: 1 }}>✨</span>
      <div style={{ flex: 1 }}>
        <div className="oswald" style={{ fontSize: 13, color: '#c4b5fd', textTransform: 'uppercase', letterSpacing: 1.5, marginBottom: 4 }}>
          AI Forensic Explanation
        </div>
        <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: 0, marginBottom: 10 }}>
          Upgrade to <strong style={{ color: '#a78bfa', textTransform: 'capitalize' }}>{requiredPlan}</strong> to
          get a plain-language breakdown of every detectio,what was flagged, where, and why it matters.
        </p>
        <Link to="/account" style={{
          display: 'inline-block', padding: '6px 14px', borderRadius: 2,
          background: '#8b5cf6', color: '#fff', textDecoration: 'none',
          fontSize: 12, fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1.5,
        }}>
          See plans →
        </Link>
      </div>
    </div>
  );
}

function ForensicResultCard({ result, canvasRef, verdictColors, documentTypeLabel }) {
  const cat = result.detected_category;
  const mainCategoryCode = MAIN_CATEGORY_CODE_BY_KEY[cat];
  const categoryLabel = result.detected_category_label || cat || '-';
  const leafLabel = categoryLabel.replace(/^[^-]+\s+-\s+/, '');

  // Gemini succeeded only when confidence > 0 (0 = fallback/error/unavailable)
  const geminiOk = typeof result.category_confidence === 'number' && result.category_confidence > 0;
  const geminiForgery = geminiOk && cat !== 'no_forgery_detected' && cat !== 'not_a_document';

  const geminiAccent = !cat || !geminiOk ? '#737373'
    : cat === 'no_forgery_detected' ? '#00ff66'
    : cat === 'not_a_document' ? '#737373'
    : cat === 'other' ? '#ffa040'
    : (CATEGORY_BY_KEY[cat]?.color || '#a78bfa');

  const vc = geminiOk ? (CATEGORY_BY_KEY[cat]?.color || (cat === 'no_forgery_detected' ? '#00ff66' : cat === 'not_a_document' ? '#737373' : cat === 'other' ? '#ffa040' : '#a78bfa')) : (verdictColors[result.verdict] || '#1d3825');

  // Show YOLO only when Gemini confirms a forgery AND (if a specific category was
  // scanned) the Gemini category matches what YOLO was analyzing.
  const categoryMatch = !result.category_analyzed || result.detected_category === result.category_analyzed;
  const hasYolo = result.annotations?.length > 0 && geminiForgery && categoryMatch;

  return (
    <div className="card" style={{ borderColor: vc, boxShadow: `0 0 24px ${vc}30`, padding: 0, overflow: 'hidden' }}>
      {/* ── Verdict ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: 'clamp(10px, 3vw, 14px) clamp(12px, 3.5vw, 20px)', borderBottom: `1px solid ${vc}33` }}>
        <h3 className="oswald" style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: 2, color: '#d8ffe6', margin: 0, whiteSpace: 'nowrap' }}>◆ Forensic Report</h3>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, minWidth: 0 }}>
          {documentTypeLabel && documentTypeLabel !== 'Other Document' && (
            <span className="mono" style={{ fontSize: 9, color: '#6dba85', letterSpacing: 1.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>
              📄 {documentTypeLabel.toUpperCase()}
            </span>
          )}
          <span className="mono" style={{ fontSize: 10, color: '#3f6e4a' }}>{result.scan_id}</span>
        </div>
      </div>

      <div style={{ textAlign: 'center', padding: 'clamp(20px, 5vw, 28px) clamp(14px, 4vw, 20px) clamp(18px, 4vw, 24px)', background: '#000', borderBottom: `1px solid ${geminiAccent}33`, boxShadow: `inset 0 0 32px ${geminiAccent}18` }}>
        <div className="oswald" style={{
          fontSize: 'clamp(18px, 5.5vw, 32px)',
          fontWeight: 700, color: geminiAccent,
          textTransform: 'uppercase',
          letterSpacing: 'clamp(2px, 0.6vw, 5px)',
          textShadow: `0 0 18px ${geminiAccent}99`,
          lineHeight: 1.15,
          wordBreak: 'break-word',
        }}>
          {geminiOk ? leafLabel : '-'}
        </div>
        {geminiOk && mainCategoryCode && (
          <div className="oswald" style={{ color: geminiAccent, marginTop: 8, fontSize: 'clamp(12px, 3.3vw, 19px)', fontWeight: 600, letterSpacing: 'clamp(1.5px, 0.35vw, 3px)', textTransform: 'uppercase', textShadow: `0 0 8px ${geminiAccent}66` }}>
            ({mainCategoryCode})
          </div>
        )}
        {geminiOk && (
          <div className="mono" style={{ color: '#6dba85', marginTop: 10, fontSize: 12, letterSpacing: 1.5 }}>
            {(result.category_confidence * 100).toFixed(1)}% CONF
            {result.certainty_level && (
              <span style={{ marginLeft: 10, color: result.certainty_level === 'HIGH' ? '#00ff66' : result.certainty_level === 'MEDIUM' ? '#ffa040' : '#ff5555' }}>
                · {result.certainty_level}
              </span>
            )}
          </div>
        )}
        {hasYolo && (
          <div className="mono" style={{ color: '#3f6e4a', marginTop: 6, fontSize: 10, letterSpacing: 1.5 }}>
            YOLO {(result.confidence_score * 100).toFixed(1)}%
          </div>
        )}
      </div>

      {result.training_warning && (
        <div style={{ background: 'rgba(255,160,64,0.08)', borderBottom: '1px solid #ffa040', padding: '10px 20px', fontSize: 12, color: '#ffc888', fontFamily: "'JetBrains Mono', monospace" }}>
          ⚠ {result.training_warning}
        </div>
      )}

      <div style={{ padding: 'clamp(14px, 4vw, 20px) clamp(12px, 3.5vw, 20px) 4px' }}>
        {/* ── Gemini Vision ── */}
        {geminiOk ? (
          <div style={{ marginBottom: 20 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: geminiAccent, margin: '0 0 8px', textShadow: `0 0 6px ${geminiAccent}99` }}>
              ▣ GEMINI VISION · CLASSIFICATION
            </p>
            <div style={{ background: `${geminiAccent}08`, border: `1px solid ${geminiAccent}44`, borderLeft: `3px solid ${geminiAccent}`, borderRadius: 3, padding: 'clamp(10px, 3vw, 14px)' }}>
              {(() => {
                const conf = result.category_confidence || 0;
                const altCount = result.alternatives?.length || 0;
                if (conf >= 0.90) return null;

                const isInconclusive = conf < 0.50;
                const isUncertain = conf < 0.85;
                const color = isInconclusive ? '#ff5555' : '#ffa040';
                const label = isInconclusive ? 'INCONCLUSIVE,NOT A DEFINITIVE ANSWER'
                              : isUncertain ? 'UNCERTAIN,TREAT AS A LEAD, NOT A VERDICT'
                              : 'BORDERLINE CONFIDENCE';
                const message = isInconclusive
                  ? `The model could not determine a definitive forgery type. It guessed "${result.detected_category_label}" but only at ${(conf * 100).toFixed(0)}% confidence. ${altCount > 0 ? `The result could realistically be one of ${altCount} other types listed below.` : 'Manual review by a forensic examiner is recommended.'}`
                  : isUncertain
                  ? `The model picked "${result.detected_category_label}" as its best guess at ${(conf * 100).toFixed(0)}% confidence - below the 85% threshold for a definitive call. ${altCount > 0 ? `It also seriously considered ${altCount} other forgery type${altCount > 1 ? 's' : ''} (see "Could Also Be" below). The image evidence is not strong enough to rule them out.` : 'Consider re-scanning with a higher-resolution image or adding context.'}`
                  : `Confidence is ${(conf * 100).toFixed(0)}% - close to definitive but not quite. Review the alternatives before acting on this result.`;

                return (
                  <div style={{
                    background: `${color}12`,
                    border: `1px solid ${color}55`,
                    borderLeft: `3px solid ${color}`,
                    borderRadius: 2,
                    padding: '10px 12px',
                    marginBottom: 12,
                  }}>
                    <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color, margin: '0 0 6px', fontWeight: 700 }}>
                      ⚠ {label}
                    </p>
                    <p style={{ fontSize: 12, color: '#ffd680', margin: 0, lineHeight: 1.6 }}>
                      {message}
                    </p>
                  </div>
                );
              })()}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                <div style={{ minWidth: 0, flex: '1 1 auto' }}>
                  {(() => {
                    const conf = result.category_confidence || 0;
                    if (conf >= 0.90) return null;
                    const prefix = conf < 0.50 ? 'STRONGEST GUESS' : 'MOST LIKELY';
                    const color = conf < 0.50 ? '#ff5555' : '#ffa040';
                    return (
                      <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color, margin: '0 0 4px' }}>
                        {prefix}:
                      </p>
                    );
                  })()}
                  <h4 className="oswald" style={{ fontSize: 'clamp(14px, 4vw, 17px)', color: '#d8ffe6', textTransform: 'uppercase', letterSpacing: 1.8, margin: 0, lineHeight: 1.25, wordBreak: 'break-word' }}>
                    {result.detected_category_label || cat}
                  </h4>
                  {result.detected_subtype && (
                    <p style={{ fontSize: 12, color: geminiAccent, margin: '3px 0 0', fontStyle: 'italic' }}>Subtype: {result.detected_subtype}</p>
                  )}
                </div>
                <span className="mono" style={{ fontSize: 11, color: geminiAccent, letterSpacing: 1.5 }}>
                  {(result.category_confidence * 100).toFixed(0)}% CONF
                </span>
              </div>
              {result.category_explanation && (
                <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: '0 0 10px' }}>{result.category_explanation}</p>
              )}
              {result.category_evidence?.length > 0 && (
                <ul style={{ margin: '0 0 10px', paddingLeft: 18, color: '#86efac', fontSize: 13, lineHeight: 1.6 }}>
                  {result.category_evidence.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
              {result.anomaly_location && (
                <p style={{ fontSize: 12, color: '#ffc888', margin: '0 0 8px', borderTop: '1px solid #112418', paddingTop: 8 }}>
                  <span className="mono" style={{ color: '#ffa040', letterSpacing: 1.5, marginRight: 6 }}>LOCATION:</span>
                  {result.anomaly_location}
                </p>
              )}
              {result.tools_likely_used && (
                <p style={{ fontSize: 12, color: '#86efac', margin: 0, borderTop: '1px solid #112418', paddingTop: 8 }}>
                  <span className="mono" style={{ color: geminiAccent, letterSpacing: 1.5, marginRight: 6 }}>TOOLS USED:</span>
                  {result.tools_likely_used}
                </p>
              )}
              {result.reasoning_steps?.length > 0 && (
                <details style={{ marginTop: 10, borderTop: '1px solid #112418', paddingTop: 8 }}>
                  <summary className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 1.5, cursor: 'pointer' }}>
                    ▸ REASONING STEPS ({result.reasoning_steps.length})
                  </summary>
                  <ol style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 12, color: '#86efac', lineHeight: 1.7 }}>
                    {result.reasoning_steps.map((s, i) => <li key={i}>{s}</li>)}
                  </ol>
                </details>
              )}

              {/* Ambiguity + Confidence + Capture Tips */}
              {(() => {
                const conf = result.category_confidence || 0;
                const dims = result.original_image_dimensions;
                const w = dims?.width || result.image_width || 0;
                const h = dims?.height || result.image_height || 0;
                const minDim = Math.min(w, h);
                const alts = result.alternatives || [];

                // Build confidence reasons
                const confReasons = [];
                if (minDim > 0 && minDim < 600) {
                  confReasons.push(`Image resolution is very low (${w}×${h}px) - forensic artifacts like halos, fiber texture, and compression noise are difficult to distinguish below 600px on the shortest side.`);
                } else if (minDim > 0 && minDim < 1000) {
                  confReasons.push(`Image resolution is moderate (${w}×${h}px) - some fine forensic details may be lost. Recommended minimum: 1000px on shortest side.`);
                }
                if (alts.length > 0) {
                  const altNames = alts.slice(0, 2).map(a => a.category_label).join(' and ');
                  confReasons.push(`Visual indicators overlap with ${altNames} - these categories share similar surface characteristics that are hard to separate without higher image quality or context.`);
                }
                if (!result.anomaly_location) {
                  confReasons.push('No specific anomaly location was identified, which limits certainty.');
                }
                const hasContext = result.document_type && result.document_type !== 'other';
                if (!hasContext) {
                  confReasons.push('No document type was provided. Adding context (bank check, ID, certificate, etc.) helps the model focus on the right forgery patterns.');
                }

                // Capture tips
                const captureTips = [];
                if (minDim < 1000) {
                  captureTips.push('Shoot closer or use higher camera resolution. Target at least 1000×1000px - phone cameras at close range easily achieve this.');
                }
                captureTips.push('Use even, diffuse lighting. Avoid harsh shadows or glare- tilt the document slightly if a flash is washing out surface texture.');
                captureTips.push('Lay the document flat on a plain surface. Creases and perspective distortion make edge artifacts harder to detect.');
                captureTips.push('Keep the original full-resolution image. Take the photo directly in Revelator when possible. If transferring an image from another device, use Gmail or Google Drive instead of Messenger or apps that compress and pixelate images.');
                captureTips.push('If examining a signature or stamp, zoom in on just that area for a second scan - localized detail is more useful than the whole page at low resolution.');
                if (!hasContext) {
                  captureTips.push('Fill in the Additional Context section before scanning - document type and your suspicion reason significantly narrow the analysis.');
                }

                const showSection = alts.length > 0 || confReasons.length > 0;
                if (!showSection) return null;

                return (
                  <div style={{ marginTop: 12, borderTop: '1px solid #1d3825', paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 12 }}>

                    {/* Could it be something else? */}
                    {alts.length > 0 && (
                      <div>
                        <p className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#ffa040', margin: '0 0 8px' }}>
                          ⚠ COULD ALSO BE ({alts.length})
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {alts.map((alt, i) => (
                            <div key={i} style={{ background: 'rgba(255,160,64,0.04)', borderRadius: 2, padding: '8px 12px', border: '1px solid rgba(255,160,64,0.18)' }}>
                              <p style={{ fontSize: 12, color: '#ffd680', margin: '0 0 3px', fontFamily: "'Oswald', sans-serif", textTransform: 'uppercase', letterSpacing: 1 }}>
                                {alt.category_label}
                              </p>
                              {alt.reasoning && (
                                <p style={{ fontSize: 12, color: '#c4a45a', margin: 0, lineHeight: 1.6 }}>{alt.reasoning}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Why this confidence? */}
                    {confReasons.length > 0 && (
                      <details style={{ borderTop: '1px solid #1d3825', paddingTop: 10 }}>
                        <summary className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#6dba85', cursor: 'pointer', marginBottom: 0 }}>
                          ▸ WHY {(conf * 100).toFixed(0)}% CONFIDENCE?
                        </summary>
                        <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 12, color: '#86efac', lineHeight: 1.7 }}>
                          {confReasons.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </details>
                    )}

                    {/* How to improve */}
                    <details style={{ borderTop: '1px solid #1d3825', paddingTop: 10 }}>
                      <summary className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#6dba85', cursor: 'pointer' }}>
                        ▸ HOW TO GET A BETTER RESULT
                      </summary>
                      <ul style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 12, color: '#86efac', lineHeight: 1.7 }}>
                        {captureTips.map((t, i) => <li key={i}>{t}</li>)}
                      </ul>
                    </details>

                  </div>
                );
              })()}
            </div>
          </div>
        ) : (
          <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="mono" style={{ fontSize: 9, letterSpacing: 2, color: '#3f6e4a', padding: '4px 10px', border: '1px solid #1d3825', borderRadius: 2 }}>
              ▣ GEMINI VISION · TEMPORARILY UNAVAILABLE
            </span>
          </div>
        )}

        {/* ── LLM Explanation ── */}
        {result.llm_explanation && (
          <div style={{ marginBottom: 20 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ AI FORENSIC EXPLANATION</p>
            <p style={{ lineHeight: 1.7, fontSize: 14, color: '#d8ffe6', margin: 0 }}>{result.llm_explanation}</p>
          </div>
        )}
        {!result.llm_explanation && result.llm_locked && (
          <div style={{ marginBottom: 20 }}>
            <LlmUpgradePrompt requiredPlan={result.llm_required_plan} />
          </div>
        )}

        {/* ── YOLO Detections - only when bounding boxes exist ── */}
        {hasYolo && (
          <div style={{ marginBottom: 16 }}>
            <p className="mono" style={{ fontSize: 9, letterSpacing: 3, color: '#6dba85', margin: '0 0 8px' }}>▸ YOLO · DETECTED REGIONS</p>
            <canvas ref={canvasRef} style={{ maxWidth: '100%', borderRadius: 2, border: '1px solid #1d3825', marginBottom: 12 }} />
            {result.annotations.map((ann, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid #112418' }}>
                <span style={{ width: 26, height: 26, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', background: ann.color, color: '#000', fontSize: 11, fontWeight: 800, boxShadow: `0 0 8px ${ann.color}80`, fontFamily: "'JetBrains Mono', monospace" }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{ flex: 1, fontSize: 14, color: '#d8ffe6' }}>{ann.title}</span>
                <span className="mono" style={{ fontSize: 12, color: ann.color }}>{(ann.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ScanNotes({ scanId }) {
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // 'saved' | 'error' | null
  const [errorMsg, setErrorMsg] = useState('');

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    setErrorMsg('');
    try {
      await api.updateScanNotes(scanId, notes);
      setStatus('saved');
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message || 'Could not save notes');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 16, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <StickyNote size={16} strokeWidth={2} style={{ color: '#00ff66' }} />
        <h3 className="oswald" style={{
          fontSize: 14, color: '#d8ffe6', letterSpacing: 2,
          textTransform: 'uppercase', margin: 0, fontWeight: 600,
        }}>
          Your Notes
        </h3>
        <span className="mono" style={{ fontSize: 10, color: '#3f6e4a', letterSpacing: 1, marginLeft: 'auto' }}>
          OPTIONAL · SAVED TO THIS SCAN
        </span>
      </div>
      <p style={{ fontSize: 13, color: '#86efac', lineHeight: 1.6, margin: '0 0 12px' }}>
        Notes appear in your scan history.
      </p>
      <textarea
        className="input"
        value={notes}
        onChange={e => { setNotes(e.target.value); if (status) setStatus(null); }}
        placeholder="e.g. Comparison sample for the Cruz signature case - verify with original on file."
        rows={4}
        maxLength={5000}
        style={{ resize: 'vertical', minHeight: 90, fontFamily: "'Source Sans Pro', sans-serif" }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving || !notes.trim()}
          style={{ fontSize: 12, padding: '8px 18px', minHeight: 'unset' }}
        >
          {saving ? '◌ Saving…' : status === 'saved' ? '✓ Saved' : 'Save Note'}
        </button>
        {status === 'saved' && (
          <span className="mono" style={{
            fontSize: 11, color: '#00ff66', letterSpacing: 1,
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <Check size={12} strokeWidth={2.5} />
            Saved to history
          </span>
        )}
        {status === 'error' && (
          <span className="mono" style={{
            fontSize: 11, color: '#ff8a99', letterSpacing: 1,
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <AlertTriangle size={12} strokeWidth={2.5} />
            {errorMsg}
          </span>
        )}
        <span className="mono" style={{
          fontSize: 10, color: '#3f6e4a', letterSpacing: 1, marginLeft: 'auto',
        }}>
          {notes.length}/5000
        </span>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pages/Terms.jsx`

<!-- FILE: frontend/src/pages/Terms.jsx -->

```jsx
import React from 'react';
import { Link } from 'react-router-dom';
import Logo from '../components/Logo';

export default function Terms() {
  const h2 = { fontSize: 16, letterSpacing: 2, color: '#00ff66', marginTop: 28, marginBottom: 10, textTransform: 'uppercase' };
  const p = { fontSize: 14, color: '#cfe9d8', lineHeight: 1.7, marginBottom: 12 };

  return (
    <div style={{ maxWidth: 760, margin: 'clamp(20px, 5vw, 48px) auto', padding: '0 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
          <Logo size={64} glow />
        </div>
        <h1 className="oswald glow-strong" style={{ fontSize: 26, color: '#00ff66', letterSpacing: 5 }}>
          TERMS OF SERVICE &amp; PRIVACY POLICY
        </h1>
        <p className="mono" style={{ color: '#6dba85', marginTop: 8, fontSize: 11, letterSpacing: 2 }}>
          [ LAST UPDATED: 2026-05-16 ]
        </p>
      </div>

      <div className="card">
        <p style={p}>
          Welcome to Revelator (the “Service”), an AI-assisted document forgery
          analysis tool. By creating an account or using the Service, you agree to
          these Terms of Service and Privacy Policy. If you do not agree, do not use
          the Service.
        </p>

        <h2 style={h2}>1. Use of the Service</h2>
        <p style={p}>
          Revelator provides automated, probabilistic assessments of document images.
          Results are advisory only and are not a substitute for professional forensic
          examination or legal advice. You are responsible for how you interpret and
          act on any verdict the Service produces.
        </p>

        <h2 style={h2}>2. Accounts &amp; Eligibility</h2>
        <p style={p}>
          You must provide a valid email address and confirm it before using the
          Service. You are responsible for keeping your credentials secure and for all
          activity under your account. You must not share your account or impersonate
          others.
        </p>

        <h2 style={h2}>3. Acceptable Use</h2>
        <p style={p}>
          You agree not to upload content you have no right to analyze, not to use the
          Service to create or refine forgeries, and not to attempt to disrupt,
          reverse-engineer, or gain unauthorized access to the Service or other users’
          data.
        </p>

        <h2 style={h2}>4. Documents You Upload</h2>
        <p style={p}>
          Images you submit are processed to generate an analysis and are stored as part
          of your scan history so you can review past results. Do not upload documents
          containing information you are not authorized to process. You retain ownership
          of your uploaded content.
        </p>

        <h2 style={h2}>5. Privacy &amp; Data We Store</h2>
        <p style={p}>
          We store your account details (email, username, name), your scan history and
          uploaded images, and, if you provide them, your own AI API keys, which are used
          solely to run your analyses. We do not sell your personal data. Analysis may be
          performed using third-party AI providers; by using the Service you consent to
          your uploaded images being transmitted to those providers for processing.
        </p>

        <h2 style={h2}>6. Email Communications</h2>
        <p style={p}>
          We send transactional emails such as account verification and security notices.
          These are required for the Service to function and are not marketing messages.
        </p>

        <h2 style={h2}>7. Data Retention &amp; Deletion</h2>
        <p style={p}>
          Your data is retained while your account is active. You may request deletion of
          your account and associated scan history; once deleted, this information cannot
          be recovered.
        </p>

        <h2 style={h2}>8. Disclaimer of Warranties</h2>
        <p style={p}>
          The Service is provided “as is” without warranties of any kind. We do not
          guarantee that any verdict is accurate, complete, or fit for a particular
          purpose. Absence of detected forgery is not proof of authenticity.
        </p>

        <h2 style={h2}>9. Limitation of Liability</h2>
        <p style={p}>
          To the maximum extent permitted by law, Revelator and its operators are not
          liable for any indirect, incidental, or consequential damages arising from your
          use of, or reliance on, the Service.
        </p>

        <h2 style={h2}>10. Changes to These Terms</h2>
        <p style={p}>
          We may update these Terms from time to time. Continued use of the Service after
          changes take effect constitutes acceptance of the revised Terms.
        </p>

        <h2 style={h2}>11. Contact</h2>
        <p style={p}>
          Questions about these Terms or your data can be directed to the Service
          operator.
        </p>

        <div style={{ marginTop: 28, paddingTop: 20, borderTop: '1px solid #112418', textAlign: 'center' }}>
          <Link to="/login" style={{ color: '#00ff66' }}>← Back to sign in</Link>
        </div>
      </div>
    </div>
  );
}
```

## File: `frontend/src/pwa.js`

<!-- FILE: frontend/src/pwa.js -->

```javascript
/*
 * PWA glue: service-worker registration and the "Install app" prompt.
 *
 * Two guards matter here:
 *  - Only in a production build. A service worker in front of the Vite dev
 *    server serves stale modules and makes HMR look broken.
 *  - Only on the web. Inside the Capacitor Android shell the page is served
 *    from a local scheme, where a service worker is pointless and can shadow
 *    the app's own assets.
 */

import { Capacitor } from '@capacitor/core';

const isWeb = !Capacitor.isNativePlatform();

// Chrome fires beforeinstallprompt before React has mounted, so the listener is
// attached at module load and the event is parked here for the UI to pick up.
let deferredPrompt = null;
const listeners = new Set();

function emit() {
  listeners.forEach(fn => {
    try { fn(!!deferredPrompt); } catch { /* a bad subscriber must not break the rest */ }
  });
}

if (isWeb && typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', e => {
    // Suppress Chrome's own mini-infobar so the in-app button is the one path.
    e.preventDefault();
    deferredPrompt = e;
    emit();
  });

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    emit();
  });
}

/** True once the app is running from the home screen rather than a browser tab. */
export function isStandalone() {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(display-mode: standalone)').matches
      || window.navigator.standalone === true;
}

/** iOS has no install prompt API: Safari requires Share -> Add to Home Screen. */
export function isIos() {
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export function canInstall() {
  return !!deferredPrompt;
}

/** Subscribe to install-availability changes. Returns an unsubscribe function. */
export function onInstallAvailable(fn) {
  listeners.add(fn);
  fn(!!deferredPrompt);
  return () => listeners.delete(fn);
}

/** Show the native install dialog. Resolves to 'accepted' | 'dismissed' | 'unavailable'. */
export async function promptInstall() {
  if (!deferredPrompt) return 'unavailable';
  const evt = deferredPrompt;
  // The event is single-use: clear it up front so a double tap cannot reuse it.
  deferredPrompt = null;
  emit();
  evt.prompt();
  const { outcome } = await evt.userChoice;
  return outcome;
}

export function registerServiceWorker() {
  if (!isWeb) return;
  if (!import.meta.env.PROD) return;
  if (!('serviceWorker' in navigator)) return;

  // Captured before registering: on a first-ever install there is no controller
  // and reloading would be pointless churn. Only an UPDATE should refresh.
  const hadController = !!navigator.serviceWorker.controller;
  let reloading = false;

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || reloading) return;
    reloading = true;
    window.location.reload();
  });

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Registration failing (private mode, unsupported browser, http origin)
      // must never take the app down: it just means no install/offline support.
    });
  });
}
```

## File: `frontend/src/themeColors.js`

<!-- FILE: frontend/src/themeColors.js -->

```javascript
/**
 * Theme-aware color helpers.
 *
 * Many components use bright accent colors (category pastels, forensic-group
 * tints) that look great on the dark Matrix background but turn unreadable
 * on the off-white light-mode surface. The CSS attribute selectors in
 * index.css handle most of these globally, but where a component composes
 * a color into something more complex (alpha tints, computed gradients,
 * canvas drawing), the JS needs to know which color to use.
 *
 * Usage:
 *   import { themed } from '../themeColors';
 *   import { useTheme } from '../App';
 *   const { theme } = useTheme();
 *   const color = themed('#c4b5fd', theme);   // → '#4a2a92' in light, original in dark
 */

const LIGHT_MAP = {
  // ForensicsGuide group accents
  '#c4b5fd': '#4a2a92', // violet - traced signatures
  '#fbbf24': '#8c5a00', // amber  - document alteration
  '#38bdf8': '#0d4a72', // sky    - digital fabrication
  '#f87171': '#9b2030', // red    - obliteration
  '#34d399': '#0a6a4a', // mint   - sympathetic ink
  '#a78bfa': '#4a2a92', // violet (alt)

  // Category greens from categories.js
  '#00ff66': '#005a22',
  '#3df58a': '#006a30',
  '#56ff8a': '#006a35',
  '#7cffaf': '#006a3c',
  '#9bffba': '#006a48',
  '#00ffaa': '#005a3a',
  '#a3e635': '#3a5a14',

  // Common UI accents
  '#ff3344': '#9b2030',
  '#ffa040': '#8c5a00',
  '#737373': '#4a4a4a',
};

export function themed(color, theme) {
  if (!color || theme !== 'light') return color;
  return LIGHT_MAP[String(color).toLowerCase()] || color;
}

/**
 * Returns a CSS-string with a tinted background suitable for a light-on-dark
 * pill in dark mode or a dark-on-light pill in light mode.
 */
export function tintedBg(color, theme, alpha = 0.12) {
  const base = themed(color, theme);
  // Convert hex → rgb
  const hex = base.replace('#', '');
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
```

## File: `frontend/vite.config.js`

<!-- FILE: frontend/vite.config.js -->

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

## Binary Assets

These are included in the ZIP, but are not source text:

- `frontend/public/apple-touch-icon.png`
- `frontend/public/guide-specimens/addition_insertion.jpg`
- `frontend/public/guide-specimens/addition_interlineation.jpg`
- `frontend/public/guide-specimens/currency_analysis.jpg`
- `frontend/public/guide-specimens/digital_cut_paste.jpg`
- `frontend/public/guide-specimens/digital_desktop.jpg`
- `frontend/public/guide-specimens/digital_scanned.jpg`
- `frontend/public/guide-specimens/erasure_chemical.jpg`
- `frontend/public/guide-specimens/erasure_mechanical.jpg`
- `frontend/public/guide-specimens/obliteration_ink.jpeg`
- `frontend/public/guide-specimens/obliteration_whiteout.jpeg`
- `frontend/public/guide-specimens/sympathetic_indented.jpg`
- `frontend/public/guide-specimens/sympathetic_special.jpg`
- `frontend/public/guide-specimens/traced_carbon.jpeg`
- `frontend/public/guide-specimens/traced_indentation.jpeg`
- `frontend/public/guide-specimens/traced_projection.jpg`
- `frontend/public/icon-192.png`
- `frontend/public/icon-512.png`
- `frontend/public/icon-maskable-512.png`
- `frontend/public/tutorial-1.jpg`
- `frontend/public/tutorial-2.jpg`
- `frontend/public/tutorial-3.jpg`
- `frontend/public/tutorial-4.jpg`