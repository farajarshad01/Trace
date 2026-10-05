from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class CareerSourceCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    career_url: HttpUrl


class CareerSourceResponse(BaseModel):
    id: int
    company_name: str
    career_url: str
    platform: str | None = None
    is_active: bool
    last_checked_at: datetime | None = None
