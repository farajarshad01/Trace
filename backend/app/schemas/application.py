from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.database.models import ApplicationStatus


def _enum_value(value):
    return getattr(value, "value", value)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus
    notes: str | None = None


class ApplicationJob(BaseModel):
    """The slice of a job the Applications page needs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    title: str
    location: str | None = None
    original_url: str
    status: str

    @field_validator("status", mode="before")
    @classmethod
    def _status_value(cls, value):
        return _enum_value(value)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    status: str
    notes: str | None = None
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    job: ApplicationJob | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status_value(cls, value):
        return _enum_value(value)
