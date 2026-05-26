"""
Classroom routes — Google-Classroom-style grouping of students.

Admins/superadmins create classrooms with a short join code; students enter
that code to enroll. The class list view shows every enrolled student. This
sits on top of the existing user model — every classroom member is just a
user with a row in ``classroom_members``.
"""

import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_admin, user_has_permission
from ..database import get_db
from ..models import Classroom, ClassroomMember, User

router = APIRouter(prefix="/api/classrooms", tags=["classrooms"])


# Letters + digits, no 0/O/1/I/L to make codes phone-friendly to type.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_join_code(db: Session, length: int = 6) -> str:
    """Return a join code that is not currently in use."""
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
        if not db.query(Classroom).filter(Classroom.join_code == code).first():
            return code


def _can_manage(user: User, classroom: Classroom, db: Session) -> bool:
    """Owners of a classroom + superadmins can edit/delete it. Admins can also
    manage classrooms they own, but a teacher's classrooms aren't editable by
    other admins. Superadmins have full access."""
    if user.role == "superadmin":
        return True
    if classroom.owner_id == user.id:
        return True
    return False


def _classroom_to_dict(c: Classroom, db: Session, include_members: bool = False) -> dict:
    owner = db.query(User).filter(User.id == c.owner_id).first()
    member_count = db.query(ClassroomMember).filter(ClassroomMember.classroom_id == c.id).count()
    data = {
        "id": c.id,
        "name": c.name,
        "description": c.description or "",
        "join_code": c.join_code,
        "owner_id": c.owner_id,
        "owner_username": owner.username if owner else None,
        "owner_full_name": (owner.full_name if owner else "") or (owner.username if owner else ""),
        "member_count": member_count,
        "is_active": bool(c.is_active),
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
    }
    if include_members:
        rows = (
            db.query(ClassroomMember, User)
            .join(User, ClassroomMember.user_id == User.id)
            .filter(ClassroomMember.classroom_id == c.id)
            .order_by(ClassroomMember.joined_at.asc())
            .all()
        )
        data["members"] = [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "full_name": u.full_name or "",
                "role": u.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else "",
            }
            for m, u in rows
        ]
    return data


# ── Schemas ─────────────────────────────────────────────

class ClassroomCreate(BaseModel):
    name: str
    description: str = ""

class ClassroomUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class JoinRequest(BaseModel):
    code: str


# ── Admin / teacher endpoints ───────────────────────────

@router.get("")
def list_classrooms(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List every classroom (superadmin) or just the ones owned by this admin."""
    q = db.query(Classroom)
    if current_user.role != "superadmin":
        q = q.filter(Classroom.owner_id == current_user.id)
    rows = q.order_by(Classroom.created_at.desc()).all()
    return {"classrooms": [_classroom_to_dict(c, db) for c in rows]}


@router.post("")
def create_classroom(
    body: ClassroomCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Classroom name is required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Name is too long (max 120 characters)")

    classroom = Classroom(
        name=name,
        description=(body.description or "").strip()[:2000],
        join_code=_generate_join_code(db),
        owner_id=current_user.id,
        is_active=True,
    )
    db.add(classroom)
    db.commit()
    db.refresh(classroom)
    return _classroom_to_dict(classroom, db, include_members=True)


@router.get("/{classroom_id}")
def get_classroom(
    classroom_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # Allowed viewers: owner, superadmin, any other admin, or an enrolled member.
    is_member = bool(
        db.query(ClassroomMember).filter(
            ClassroomMember.classroom_id == classroom_id,
            ClassroomMember.user_id == current_user.id,
        ).first()
    )
    is_admin_like = user_has_permission(current_user, "view_users", db) or current_user.role == "superadmin"
    if not (is_member or is_admin_like or classroom.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this classroom")

    return _classroom_to_dict(classroom, db, include_members=True)


@router.put("/{classroom_id}")
def update_classroom(
    classroom_id: str,
    body: ClassroomUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not _can_manage(current_user, classroom, db):
        raise HTTPException(status_code=403, detail="Only the classroom owner or a superadmin can edit this")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        if len(name) > 120:
            raise HTTPException(status_code=400, detail="Name is too long")
        classroom.name = name
    if body.description is not None:
        classroom.description = body.description.strip()[:2000]
    if body.is_active is not None:
        classroom.is_active = bool(body.is_active)

    db.commit()
    db.refresh(classroom)
    return _classroom_to_dict(classroom, db, include_members=True)


@router.delete("/{classroom_id}")
def delete_classroom(
    classroom_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not _can_manage(current_user, classroom, db):
        raise HTTPException(status_code=403, detail="Only the classroom owner or a superadmin can delete this")
    db.delete(classroom)
    db.commit()
    return {"success": True}


@router.post("/{classroom_id}/regenerate-code")
def regenerate_code(
    classroom_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    if not _can_manage(current_user, classroom, db):
        raise HTTPException(status_code=403, detail="Only the classroom owner or a superadmin can regenerate the code")
    classroom.join_code = _generate_join_code(db)
    db.commit()
    db.refresh(classroom)
    return {"join_code": classroom.join_code}


@router.delete("/{classroom_id}/members/{user_id}")
def remove_member(
    classroom_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner/superadmin kicks a student, or a student leaves on their own."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # Allowed: classroom owner, superadmin, or the student removing themself.
    if not (_can_manage(current_user, classroom, db) or current_user.id == user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    member = db.query(ClassroomMember).filter(
        ClassroomMember.classroom_id == classroom_id,
        ClassroomMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
    return {"success": True}


# ── Student endpoints ───────────────────────────────────

@router.get("/mine/list")
def my_classrooms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List every classroom the current user has joined."""
    rows = (
        db.query(Classroom, ClassroomMember)
        .join(ClassroomMember, ClassroomMember.classroom_id == Classroom.id)
        .filter(ClassroomMember.user_id == current_user.id)
        .order_by(ClassroomMember.joined_at.desc())
        .all()
    )
    return {"classrooms": [_classroom_to_dict(c, db) for c, _ in rows]}


@router.post("/join")
def join_classroom(
    body: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = (body.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="A join code is required")

    classroom = db.query(Classroom).filter(Classroom.join_code == code).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="No classroom matches that code")
    if not classroom.is_active:
        raise HTTPException(status_code=400, detail="This classroom is archived")

    existing = db.query(ClassroomMember).filter(
        ClassroomMember.classroom_id == classroom.id,
        ClassroomMember.user_id == current_user.id,
    ).first()
    if existing:
        # Already a member — just return the classroom so the UI can navigate to it.
        return _classroom_to_dict(classroom, db)

    member = ClassroomMember(classroom_id=classroom.id, user_id=current_user.id)
    db.add(member)
    db.commit()
    return _classroom_to_dict(classroom, db)
