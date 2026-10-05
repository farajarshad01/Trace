from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    profile_exists: bool = True