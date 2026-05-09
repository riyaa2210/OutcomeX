"""
RBAC — Role-Based Access Control
==================================
Roles (least → most privileged):
  viewer   — read-only access to own meetings
  employee — create meetings, manage own action items
  manager  — view team meetings, manage team tasks, access analytics
  admin    — full access, user management, security dashboard

Permission matrix:
  Resource              viewer  employee  manager  admin
  ─────────────────────────────────────────────────────
  own meetings          R       CRUD      CRUD     CRUD
  team meetings         —       R         CRUD     CRUD
  all meetings          —       —         R        CRUD
  action items (own)    R       CRUD      CRUD     CRUD
  action items (team)   —       —         CRUD     CRUD
  analytics             —       R         R        CRUD
  user management       —       —         —        CRUD
  security dashboard    —       —         —        R
  integrations          —       R         R        CRUD
  LLM admin             —       —         —        R
  eval dashboard        —       R         R        CRUD
  webhook config        —       —         —        CRUD
"""

import enum
import logging
from functools import wraps
from typing import Optional

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)


# ── Role hierarchy ────────────────────────────────────────────────────────────

class Role(str, enum.Enum):
    VIEWER   = "viewer"
    EMPLOYEE = "employee"
    MANAGER  = "manager"
    ADMIN    = "admin"


ROLE_HIERARCHY: dict[Role, int] = {
    Role.VIEWER:   0,
    Role.EMPLOYEE: 1,
    Role.MANAGER:  2,
    Role.ADMIN:    3,
}


def role_level(role: str) -> int:
    """Return numeric level for a role string."""
    try:
        return ROLE_HIERARCHY[Role(role)]
    except (ValueError, KeyError):
        return 0  # unknown role → lowest privilege


def has_role(user_role: str, required_role: Role) -> bool:
    """True if user_role is at least as privileged as required_role."""
    return role_level(user_role) >= ROLE_HIERARCHY[required_role]


# ── Permission definitions ────────────────────────────────────────────────────

class Permission(str, enum.Enum):
    # Meetings
    READ_OWN_MEETINGS    = "read:own_meetings"
    WRITE_OWN_MEETINGS   = "write:own_meetings"
    READ_TEAM_MEETINGS   = "read:team_meetings"
    WRITE_TEAM_MEETINGS  = "write:team_meetings"
    READ_ALL_MEETINGS    = "read:all_meetings"
    DELETE_ANY_MEETING   = "delete:any_meeting"

    # Action items
    READ_OWN_ACTIONS     = "read:own_actions"
    WRITE_OWN_ACTIONS    = "write:own_actions"
    WRITE_TEAM_ACTIONS   = "write:team_actions"

    # Analytics
    READ_ANALYTICS       = "read:analytics"
    WRITE_ANALYTICS      = "write:analytics"

    # Users
    READ_USERS           = "read:users"
    WRITE_USERS          = "write:users"
    DELETE_USERS         = "delete:users"

    # Security
    READ_SECURITY        = "read:security"
    WRITE_SECURITY       = "write:security"

    # Admin
    READ_LLM_ADMIN       = "read:llm_admin"
    WRITE_LLM_ADMIN      = "write:llm_admin"
    READ_EVAL            = "read:eval"
    WRITE_EVAL           = "write:eval"

    # Integrations
    READ_INTEGRATIONS    = "read:integrations"
    WRITE_INTEGRATIONS   = "write:integrations"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.READ_OWN_MEETINGS,
        Permission.READ_OWN_ACTIONS,
    },
    Role.EMPLOYEE: {
        Permission.READ_OWN_MEETINGS,
        Permission.WRITE_OWN_MEETINGS,
        Permission.READ_OWN_ACTIONS,
        Permission.WRITE_OWN_ACTIONS,
        Permission.READ_ANALYTICS,
        Permission.READ_INTEGRATIONS,
        Permission.WRITE_INTEGRATIONS,
        Permission.READ_EVAL,
    },
    Role.MANAGER: {
        Permission.READ_OWN_MEETINGS,
        Permission.WRITE_OWN_MEETINGS,
        Permission.READ_TEAM_MEETINGS,
        Permission.WRITE_TEAM_MEETINGS,
        Permission.READ_ALL_MEETINGS,
        Permission.READ_OWN_ACTIONS,
        Permission.WRITE_OWN_ACTIONS,
        Permission.WRITE_TEAM_ACTIONS,
        Permission.READ_ANALYTICS,
        Permission.WRITE_ANALYTICS,
        Permission.READ_USERS,
        Permission.READ_INTEGRATIONS,
        Permission.WRITE_INTEGRATIONS,
        Permission.READ_EVAL,
        Permission.WRITE_EVAL,
    },
    Role.ADMIN: {p for p in Permission},  # all permissions
}


def get_permissions(role: str) -> set[Permission]:
    """Return the full permission set for a role."""
    try:
        r = Role(role)
    except ValueError:
        r = Role.VIEWER
    return ROLE_PERMISSIONS.get(r, set())


def check_permission(user_role: str, permission: Permission) -> bool:
    return permission in get_permissions(user_role)


# ── FastAPI dependency factories ──────────────────────────────────────────────

def require_role(minimum_role: Role):
    """
    FastAPI dependency: raises 403 if user doesn't have minimum_role.

    Usage:
        @router.get("/admin")
        def admin_only(current_user=Depends(require_role(Role.ADMIN))):
            ...
    """
    from backend.app.auth import get_current_user

    def _check(current_user=Depends(get_current_user)):
        if not has_role(current_user.role, minimum_role):
            logger.warning(
                f"[RBAC] Access denied: user={current_user.id} "
                f"role={current_user.role} required={minimum_role.value}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role.value} role or higher",
            )
        return current_user

    return _check


def require_permission(permission: Permission):
    """
    FastAPI dependency: raises 403 if user lacks a specific permission.
    """
    from backend.app.auth import get_current_user

    def _check(current_user=Depends(get_current_user)):
        if not check_permission(current_user.role, permission):
            logger.warning(
                f"[RBAC] Permission denied: user={current_user.id} "
                f"role={current_user.role} permission={permission.value}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission.value}",
            )
        return current_user

    return _check


# ── Resource ownership check ──────────────────────────────────────────────────

def assert_owns_or_admin(resource_user_id: int, current_user, allow_manager: bool = False) -> None:
    """
    Raise 403 if current_user doesn't own the resource and isn't admin/manager.
    """
    if current_user.id == resource_user_id:
        return
    if has_role(current_user.role, Role.ADMIN):
        return
    if allow_manager and has_role(current_user.role, Role.MANAGER):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this resource",
    )
