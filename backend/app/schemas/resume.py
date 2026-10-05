from pydantic import BaseModel


class ResumeResponse(BaseModel):
    id: int
    file_name: str
    structured_profile: dict | None = None
    created_at: str