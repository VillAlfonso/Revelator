"""
Room routes - Google-Room-style grouping of students.

Admins/superadmins create rooms with a short join code; students enter
that code to enroll. The class list view shows every enrolled student. This
sits on top of the existing user model - every room member is just a
user with a row in ``room_members``.
"""

import secrets
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_admin, user_has_permission
from ..database import get_db
from ..models import Room, RoomMember, User

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


# Letters + digits, no 0/O/1/I/L to make codes phone-friendly to type.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_join_code(db: Session, length: int = 6) -> str:
    """Return a join code that is not currently in use."""
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
        if not db.query(Room).filter(Room.join_code == code).first():
            return code


def _can_manage(user: User, room: Room, db: Session) -> bool:
    """Owners of a room + superadmins can edit/delete it. Admins can also
    manage rooms they own, but a teacher's rooms aren't editable by
    other admins. Superadmins have full access."""
    if user.role == "superadmin":
        return True
    if room.owner_id == user.id:
        return True
    return False


def _room_to_dict(c: Room, db: Session, include_members: bool = False) -> dict:
    owner = db.query(User).filter(User.id == c.owner_id).first()
    member_count = db.query(RoomMember).filter(RoomMember.room_id == c.id).count()
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
            db.query(RoomMember, User)
            .join(User, RoomMember.user_id == User.id)
            .filter(RoomMember.room_id == c.id)
            .order_by(RoomMember.joined_at.asc())
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

class RoomCreate(BaseModel):
    name: str
    description: str = ""

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class JoinRequest(BaseModel):
    code: str


# ── Admin / teacher endpoints ───────────────────────────

@router.get("")
def list_rooms(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List every room (superadmin) or just the ones owned by this admin."""
    q = db.query(Room)
    if current_user.role != "superadmin":
        q = q.filter(Room.owner_id == current_user.id)
    rows = q.order_by(Room.created_at.desc()).all()
    return {"rooms": [_room_to_dict(c, db) for c in rows]}


@router.post("")
def create_room(
    body: RoomCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Room name is required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Name is too long (max 120 characters)")

    room = Room(
        name=name,
        description=(body.description or "").strip()[:2000],
        join_code=_generate_join_code(db),
        owner_id=current_user.id,
        is_active=True,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return _room_to_dict(room, db, include_members=True)


@router.get("/{room_id}")
def get_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Allowed viewers: owner, superadmin, any other admin, or an enrolled member.
    is_member = bool(
        db.query(RoomMember).filter(
            RoomMember.room_id == room_id,
            RoomMember.user_id == current_user.id,
        ).first()
    )
    is_admin_like = user_has_permission(current_user, "view_users", db) or current_user.role == "superadmin"
    if not (is_member or is_admin_like or room.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="You don't have access to this room")

    return _room_to_dict(room, db, include_members=True)


@router.put("/{room_id}")
def update_room(
    room_id: str,
    body: RoomUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not _can_manage(current_user, room, db):
        raise HTTPException(status_code=403, detail="Only the room owner or a superadmin can edit this")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        if len(name) > 120:
            raise HTTPException(status_code=400, detail="Name is too long")
        room.name = name
    if body.description is not None:
        room.description = body.description.strip()[:2000]
    if body.is_active is not None:
        room.is_active = bool(body.is_active)

    db.commit()
    db.refresh(room)
    return _room_to_dict(room, db, include_members=True)


@router.delete("/{room_id}")
def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not _can_manage(current_user, room, db):
        raise HTTPException(status_code=403, detail="Only the room owner or a superadmin can delete this")
    db.delete(room)
    db.commit()
    return {"success": True}


@router.post("/{room_id}/regenerate-code")
def regenerate_code(
    room_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if not _can_manage(current_user, room, db):
        raise HTTPException(status_code=403, detail="Only the room owner or a superadmin can regenerate the code")
    room.join_code = _generate_join_code(db)
    db.commit()
    db.refresh(room)
    return {"join_code": room.join_code}


@router.delete("/{room_id}/members/{user_id}")
def remove_member(
    room_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner/superadmin kicks a student, or a student leaves on their own."""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Allowed: room owner, superadmin, or the student removing themself.
    if not (_can_manage(current_user, room, db) or current_user.id == user_id):
        raise HTTPException(status_code=403, detail="Not allowed")

    member = db.query(RoomMember).filter(
        RoomMember.room_id == room_id,
        RoomMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
    return {"success": True}


# ── Student endpoints ───────────────────────────────────

@router.get("/mine/list")
def my_rooms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List every room the current user has joined."""
    rows = (
        db.query(Room, RoomMember)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .filter(RoomMember.user_id == current_user.id)
        .order_by(RoomMember.joined_at.desc())
        .all()
    )
    return {"rooms": [_room_to_dict(c, db) for c, _ in rows]}


@router.post("/join")
def join_room(
    body: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    code = (body.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="A join code is required")

    room = db.query(Room).filter(Room.join_code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="No room matches that code")
    if not room.is_active:
        raise HTTPException(status_code=400, detail="This room is archived")

    existing = db.query(RoomMember).filter(
        RoomMember.room_id == room.id,
        RoomMember.user_id == current_user.id,
    ).first()
    if existing:
        # Already a member - just return the room so the UI can navigate to it.
        return _room_to_dict(room, db)

    member = RoomMember(room_id=room.id, user_id=current_user.id)
    db.add(member)
    db.commit()
    return _room_to_dict(room, db)
