from pydantic import BaseModel, Field


class TargetRoleCreate(BaseModel):
    role_title: str = Field(min_length=1, max_length=255)


class TargetRoleResponse(BaseModel):
    id: int
    role_title: str
    is_active: bool
