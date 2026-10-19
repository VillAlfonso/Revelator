"""Account archival and permanent history."""
import json
from datetime import datetime
from fastapi import HTTPException
from .models import UserSession, AuthChallenge, AccountArchiveEvent


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
