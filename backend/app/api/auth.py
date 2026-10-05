from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.database.connection import get_db
from app.database.models import UserProfile


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.get("/me")
def get_me(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = (
        db.query(UserProfile)
        .filter(UserProfile.id == user_id)
        .first()
    )

    if not user:
        return {
            "id": str(user_id),
            "profile_exists": False,
        }


    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "profile_exists": True,
    }