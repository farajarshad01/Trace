from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.database.connection import get_db
from app.database.models import TargetRole
from app.schemas.role import (
    TargetRoleCreate,
    TargetRoleResponse,
)


router = APIRouter(
    prefix="/api/roles",
    tags=["Target Roles"],
)


@router.get(
    "",
    response_model=list[TargetRoleResponse],
)
def get_roles(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    roles = (
        db.query(TargetRole)
        .filter(
            TargetRole.user_id == user_id,
            TargetRole.is_active.is_(True),
        )
        .order_by(
            TargetRole.created_at.desc()
        )
        .all()
    )

    return roles


@router.post(
    "",
    response_model=TargetRoleResponse,
)
def create_role(
    payload: TargetRoleCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    role_title = payload.role_title.strip()

    if not role_title:
        raise HTTPException(
            status_code=400,
            detail="Role title cannot be empty.",
        )

    existing = (
        db.query(TargetRole)
        .filter(
            TargetRole.user_id == user_id,
            TargetRole.role_title.ilike(
                role_title
            ),
            TargetRole.is_active.is_(True),
        )
        .first()
    )

    if existing:
        return existing

    role = TargetRole(
        user_id=user_id,
        role_title=role_title,
        is_active=True,
    )

    db.add(role)
    db.commit()
    db.refresh(role)

    return role


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    role = (
        db.query(TargetRole)
        .filter(
            TargetRole.id == role_id,
            TargetRole.user_id == user_id,
        )
        .first()
    )

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role not found.",
        )

    role.is_active = False

    db.commit()

    return {
        "message": "Role removed."
    }