"""
Admin CRUD routes — all endpoints require is_admin=True.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from ..auth import get_current_admin, hash_password
from ..database import get_db
from ..models import User, Scan

router = APIRouter(prefix="/api/admin", tags=["admin"])


VALID_PLANS = {"free", "basic", "pro"}


class UserUpdate(BaseModel):
    plan: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # optional reset


def _user_row(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "username": u.username,
        "full_name": u.full_name or "",
        "plan": u.plan,
        "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active),
        "is_verified": bool(u.is_verified),
        "scans_this_month": u.scans_this_month,
        "stripe_customer_id": u.stripe_customer_id,
        "stripe_subscription_id": u.stripe_subscription_id,
        "created_at": u.created_at.isoformat() if u.created_at else "",
        "updated_at": u.updated_at.isoformat() if u.updated_at else "",
    }


@router.get("/stats")
def stats(_: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_scans = db.query(func.count(Scan.id)).scalar() or 0
    plan_counts = dict(db.query(User.plan, func.count(User.id)).group_by(User.plan).all())
    admin_count = db.query(func.count(User.id)).filter(User.is_admin == True).scalar() or 0
    return {
        "total_users": total_users,
        "total_scans": total_scans,
        "admins": admin_count,
        "plans": {p: plan_counts.get(p, 0) for p in ("free", "basic", "pro")},
    }


@router.get("/users")
def list_users(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    plan: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.email.ilike(like), User.username.ilike(like), User.full_name.ilike(like)))
    if plan:
        query = query.filter(User.plan == plan)

    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {"users": [_user_row(u) for u in rows], "total": total}


@router.get("/users/{user_id}")
def get_user(user_id: str, _: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    scan_count = db.query(func.count(Scan.id)).filter(Scan.user_id == user_id).scalar() or 0
    data = _user_row(user)
    data["total_scans"] = scan_count
    return data


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    body: UserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.plan is not None:
        if body.plan not in VALID_PLANS:
            raise HTTPException(status_code=400, detail=f"Invalid plan. Options: {sorted(VALID_PLANS)}")
        user.plan = body.plan

    if body.is_admin is not None:
        if user.id == admin.id and body.is_admin is False:
            raise HTTPException(status_code=400, detail="You cannot remove your own admin role")
        user.is_admin = body.is_admin

    if body.is_active is not None:
        if user.id == admin.id and body.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        user.is_active = body.is_active

    if body.full_name is not None:
        user.full_name = body.full_name

    if body.username is not None and body.username != user.username:
        if db.query(User).filter(User.username == body.username, User.id != user.id).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        user.username = body.username

    if body.email is not None and body.email != user.email:
        if db.query(User).filter(User.email == body.email, User.id != user.id).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = body.email

    if body.password is not None:
        if len(body.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        user.hashed_password = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return _user_row(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"deleted": user_id}
