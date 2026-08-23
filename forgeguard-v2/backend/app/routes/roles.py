"""
Role management routes - dynamic role + permission system.

Superadmin can create, edit, and delete roles; can edit privileges of any role
(except superadmin itself, which is always godmode). Users self-assign roles
flagged as `is_self_assignable` (e.g., room sections).
"""

import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_super_admin, user_has_permission
from ..database import get_db
from ..models import Role, User

router = APIRouter(prefix="/api/roles", tags=["roles"])


# Canonical permission catalog - what superadmin can grant/revoke on each role.
AVAILABLE_PERMISSIONS = [
    {"key": "view_users", "label": "View users panel", "description": "Access the Users tab to view all user accounts, profiles, and account status information. Allows filtering and searching across user database.", "group": "Users"},
    {"key": "edit_users", "label": "Edit user accounts", "description": "Modify user profile fields including name, email, username, password, and account status. Changes are logged in audit trails.", "group": "Users"},
    {"key": "ban_users", "label": "Ban or unban users", "description": "Temporarily disable or re-enable user accounts. Banned users cannot log in, but their data and history remain intact.", "group": "Users"},
    {"key": "delete_users", "label": "Delete user accounts", "description": "Permanently remove user accounts from the system along with their associated data. This action cannot be undone.", "group": "Users"},
    {"key": "assign_roles", "label": "Assign roles to users", "description": "Change which role a user belongs to, controlling their access level and permissions. Cannot assign admin or superadmin roles without higher permissions.", "group": "Roles"},
    {"key": "manage_roles", "label": "Create, edit, and delete roles", "description": "Full role management: create new roles, modify existing role properties, permissions, and descriptions. Can also delete custom roles and reassign users.", "group": "Roles"},
    {"key": "view_logs", "label": "View audit logs", "description": "Access the audit logs panel to review admin actions, user activity, scan history, and system events for compliance and troubleshooting.", "group": "System"},
    {"key": "view_admin_panel", "label": "Access admin panel", "description": "General access to the admin dashboard and related administrative features. Required as a base permission for most admin functions.", "group": "Panels"},
    {"key": "view_users_panel", "label": "View users panel", "description": "Access to the users management interface where administrators can view, filter, and manage user accounts and their properties.", "group": "Panels"},
    {"key": "view_roles_panel", "label": "View roles panel", "description": "Access to the role management interface where administrators can view existing roles, their permissions, and properties.", "group": "Panels"},
    {"key": "view_prompt_analytics", "label": "View prompt analytics", "description": "Access detailed analytics about forgery detection prompts, AI model usage, and analysis results across the system.", "group": "System"},
    {"key": "is_superadmin", "label": "Super Administrator", "description": "Grants complete system access and all permissions without restrictions. Super Administrators can manage all users, roles, and system settings. This permission should be reserved only for trusted administrators.", "group": "Special"},
]


# ── Schemas ──────────────────────────────────────────────

class RoleCreate(BaseModel):
    name: str
    color: str = "#6dba85"
    description: str = ""
    permissions: List[str] = []
    is_self_assignable: bool = False
    sort_order: int = 100


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    is_self_assignable: Optional[bool] = None
    sort_order: Optional[int] = None


class AssignRoleRequest(BaseModel):
    role: str


# ── Helpers ──────────────────────────────────────────────

def _role_dict(r: Role) -> dict:
    try:
        perms = json.loads(r.permissions or "[]")
    except (ValueError, TypeError):
        perms = []
    return {
        "id": r.id,
        "name": r.name,
        "color": r.color,
        "description": r.description or "",
        "permissions": perms,
        "is_system": bool(r.is_system),
        "is_self_assignable": bool(r.is_self_assignable),
        "sort_order": r.sort_order,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


def _validate_permissions(perms: list) -> list:
    """Filter out unknown permission keys."""
    valid = {p["key"] for p in AVAILABLE_PERMISSIONS}
    return [p for p in perms if p in valid]


# ── Endpoints ────────────────────────────────────────────

@router.get("")
def list_roles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all roles. Available to any authenticated user (for self-assign + filter UI)."""
    rows = db.query(Role).order_by(Role.sort_order, Role.name).all()
    return {"roles": [_role_dict(r) for r in rows], "permissions": AVAILABLE_PERMISSIONS}


@router.post("")
def create_role(
    body: RoleCreate,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Role name is required")
    if db.query(Role).filter(Role.name == name).first():
        raise HTTPException(status_code=400, detail="Role name already exists")

    # Block creating new "is_superadmin" - only the seeded superadmin gets god mode.
    perms = _validate_permissions(body.permissions)
    if "is_superadmin" in perms:
        raise HTTPException(status_code=400, detail="Only the built-in superadmin role can hold is_superadmin")

    role = Role(
        name=name,
        color=body.color or "#6dba85",
        description=body.description or "",
        permissions=json.dumps(perms),
        is_system=False,
        is_self_assignable=bool(body.is_self_assignable),
        sort_order=body.sort_order,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return _role_dict(role)


@router.put("/{role_id}")
def update_role(
    role_id: str,
    body: RoleUpdate,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # superadmin role: name and is_superadmin permission are immutable.
    if role.name == "superadmin":
        if body.name is not None and body.name != "superadmin":
            raise HTTPException(status_code=400, detail="Cannot rename the superadmin role")
        if body.permissions is not None:
            perms = _validate_permissions(body.permissions)
            if "is_superadmin" not in perms:
                raise HTTPException(status_code=400, detail="superadmin role must keep is_superadmin")

    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Role name cannot be empty")
        if new_name != role.name:
            if role.is_system:
                raise HTTPException(status_code=400, detail="System roles cannot be renamed")
            existing = db.query(Role).filter(Role.name == new_name).first()
            if existing and existing.id != role.id:
                raise HTTPException(status_code=400, detail="Role name already exists")
            # Cascade: update all users with the old role name
            db.query(User).filter(User.role == role.name).update({"role": new_name})
            role.name = new_name

    if body.color is not None:
        role.color = body.color
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        perms = _validate_permissions(body.permissions)
        # Don't allow adding is_superadmin to any role other than superadmin
        if "is_superadmin" in perms and role.name != "superadmin":
            raise HTTPException(status_code=400, detail="is_superadmin is reserved for the superadmin role")
        role.permissions = json.dumps(perms)
    if body.is_self_assignable is not None:
        role.is_self_assignable = bool(body.is_self_assignable)
    if body.sort_order is not None:
        role.sort_order = body.sort_order

    db.commit()
    db.refresh(role)
    return _role_dict(role)


@router.delete("/{role_id}")
def delete_role(
    role_id: str,
    admin: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system role")

    # Reassign all users with this role back to "user"
    db.query(User).filter(User.role == role.name).update({"role": "user"})
    db.delete(role)
    db.commit()
    return {"deleted": role_id}


@router.put("/users/{user_id}/role")
def assign_role_to_user(
    user_id: str,
    body: AssignRoleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assign a role to a user.

    - Superadmin can assign any role.
    - Users with assign_roles permission can assign any non-elevated role.
    - Any user can self-assign a role flagged is_self_assignable=True.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    new_role = db.query(Role).filter(Role.name == body.role).first()
    if not new_role:
        raise HTTPException(status_code=404, detail="Role not found")

    is_self = target.id == current_user.id
    is_super = current_user.role == "superadmin"
    can_assign = user_has_permission(current_user, "assign_roles", db)

    if is_super:
        pass  # superadmin can do anything
    elif is_self and new_role.is_self_assignable:
        pass  # user self-assigning an open role
    elif can_assign and new_role.name not in ("admin", "superadmin"):
        pass  # assign_roles users can grant non-elevated roles
    else:
        raise HTTPException(status_code=403, detail="Not allowed to assign this role")

    # Prevent demoting the last superadmin
    if target.role == "superadmin" and new_role.name != "superadmin":
        super_count = db.query(User).filter(User.role == "superadmin").count()
        if super_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last superadmin")

    target.role = new_role.name
    db.commit()
    db.refresh(target)
    return {
        "user_id": target.id,
        "role": target.role,
        "role_color": new_role.color,
    }
