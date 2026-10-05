from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AuthUser
from app.database.models import UserProfile


def ensure_profile(db: Session, user: AuthUser) -> UserProfile:
    """
    ``resumes.user_id`` is a foreign key to ``profiles.id``. If the profile
    row has not been created yet (e.g. no signup trigger on auth.users),
    the first resume upload used to fail with a foreign-key error.
    """

    profile = db.query(UserProfile).filter(UserProfile.id == user.id).first()

    if profile:
        return profile

    profile = UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
    )

    db.add(profile)

    try:
        db.commit()
    except IntegrityError:          # created concurrently by a trigger
        db.rollback()
        profile = (
            db.query(UserProfile).filter(UserProfile.id == user.id).first()
        )

    return profile
