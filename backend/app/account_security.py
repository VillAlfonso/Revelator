"""Authenticator challenges, recovery codes, and account archival."""
import base64
import io
import json
import secrets
import time
from datetime import datetime, timedelta
import pyotp
import qrcode
from fastapi import HTTPException
from sqlalchemy import func
from .models import User, UserSession, AuthChallenge, RecoveryCode, AccountArchiveEvent
from .auth import hash_token
from .key_storage import encrypt_api_key, decrypt_api_key


def begin_auth(user, db):
    if not user.is_active or user.archived_at:
        raise HTTPException(403, "Account is archived or banned")
    secret = pyotp.random_base32() if not user.totp_secret else None
    token = secrets.token_urlsafe(32)
    db.query(AuthChallenge).filter((AuthChallenge.user_id == user.id) | (AuthChallenge.expires_at < datetime.utcnow())).delete(synchronize_session=False)
    db.add(AuthChallenge(id=hash_token(token), user_id=user.id, auth_version=user.auth_version,
        secret=encrypt_api_key(secret), expires_at=datetime.utcnow() + timedelta(minutes=10)))
    db.commit()
    result = {"challenge_token": token, "requires_2fa": True, "setup_required": bool(secret), "email": user.email}
    if secret:
        uri = pyotp.TOTP(secret).provisioning_uri(user.email, issuer_name="Revelator")
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        result.update(setup_key=secret, qr_image="data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode())
    return result


def consume_recovery(user, code, db):
    return db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id,
        RecoveryCode.code_hash == hash_token(code.strip().upper())).delete(synchronize_session=False) == 1


def finish_auth(token, code, db):
    challenge = db.query(AuthChallenge).filter(AuthChallenge.id == hash_token(token)).first()
    if not challenge or challenge.expires_at <= datetime.utcnow() or challenge.attempts >= 5:
        raise HTTPException(401, "Verification expired or locked. Sign in again.")
    user = db.get(User, challenge.user_id)
    if not user or not user.is_active or user.archived_at or user.auth_version != challenge.auth_version:
        raise HTTPException(401, "Account or verification is no longer available")
    claimed = db.query(AuthChallenge).filter(AuthChallenge.id == challenge.id, AuthChallenge.attempts < 5).update(
        {AuthChallenge.attempts: AuthChallenge.attempts + 1}, synchronize_session=False)
    if not claimed:
        db.rollback()
        raise HTTPException(401, "Verification locked. Sign in again.")
    secret = decrypt_api_key(challenge.secret or user.totp_secret)
    step = int(time.time()) // 30
    match = next((n for n in (step - 1, step, step + 1)
                  if pyotp.utils.strings_equal(pyotp.TOTP(secret).at(n * 30), code.strip())), None)
    valid = False
    if match is not None:
        conditions = [User.id == user.id, User.totp_last_step < match]
        if challenge.secret:
            conditions.append(User.totp_secret.is_(None))
        values = {User.totp_last_step: match}
        if challenge.secret:
            values[User.totp_secret] = challenge.secret
        valid = db.query(User).filter(*conditions).update(values, synchronize_session=False) == 1
    elif not challenge.secret:
        valid = consume_recovery(user, code, db)
    if not valid:
        db.commit()
        raise HTTPException(401, "Incorrect or already used code. Try the next Authenticator code or a recovery code.")
    used = db.query(AuthChallenge).filter(AuthChallenge.id == challenge.id).delete(synchronize_session=False)
    if not used:
        db.rollback()
        raise HTTPException(401, "Verification already used")
    recovery = []
    if challenge.secret:
        db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete()
        recovery = [secrets.token_hex(10).upper() for _ in range(10)]
        db.add_all([RecoveryCode(user_id=user.id, code_hash=hash_token(c)) for c in recovery])
    db.commit()
    db.refresh(user)
    return user, recovery


def archive_event(user, action, db, actor_id=None):
    db.add(AccountArchiveEvent(user_id=user.id, email=user.email, action=action, actor_id=actor_id,
        snapshot=json.dumps({"email": user.email, "username": user.username, "full_name": user.full_name,
                             "role": user.role, "created_at": str(user.created_at)})))


def archive_account(user, db, actor_id=None):
    # An existing ban remains a ban and cannot be converted into re-registration eligibility.
    if not user.is_active and not user.archived_at:
        raise HTTPException(400, "Banned accounts must remain banned")
    if user.archived_at:
        return
    archive_event(user, "archived", db, actor_id)
    user.archived_at = datetime.utcnow()
    user.is_active = False
    user.auth_version += 1
    db.query(UserSession).filter(UserSession.user_id == user.id).update({UserSession.revoked_at: datetime.utcnow()})
    db.query(AuthChallenge).filter(AuthChallenge.user_id == user.id).delete()
    db.commit()


def release_archived_identity(user, db):
    archive_event(user, "registered_again", db)
    # Preserve old account data under its archived ID; the new account starts fresh.
    user.email = f"archived-{user.id}@archive.invalid"
    user.username = f"archived-{user.id}"
    user.google_id = None
    db.flush()
