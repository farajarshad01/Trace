import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.ai.resume_analyzer import analyze_resume
from app.core.config import settings
from app.core.security import (
    AuthUser,
    get_current_user,
    get_current_user_id,
    get_supabase_client,
)
from app.database.connection import get_db
from app.database.models import Resume
from app.schemas.resume import ResumeResponse
from app.services.resume_service import extract_resume_text
from app.services.user_service import ensure_profile


router = APIRouter(
    prefix="/api/resumes",
    tags=["Resumes"],
)


# A real resume has far more text than this. Anything shorter is almost
# always a scanned image PDF, and sending it to Gemini would waste a call.
MIN_RESUME_CHARS = 80


def _safe_filename(name: str) -> str:
    """Supabase Storage rejects keys with spaces/unicode/special chars."""

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "resume"

    return stem[-100:]


def _to_response(resume: Resume) -> ResumeResponse:
    return ResumeResponse(
        id=resume.id,
        file_name=resume.file_name,
        structured_profile=resume.structured_profile,
        created_at=resume.created_at.isoformat(),
    )


# NOTE: this is a plain ``def`` on purpose. It does blocking work (PDF
# parsing, a Gemini call that may take several seconds or retry, a storage
# upload, database writes). As ``async def`` all of that ran on the event
# loop and froze every other request on the server while Gemini was busy.
# FastAPI runs sync endpoints in its threadpool.
@router.post(
    "/upload",
    response_model=ResumeResponse,
)
def upload_resume(
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user.id

    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is missing.")

    extension = file.filename.lower().rsplit(".", 1)[-1]

    if extension not in {"pdf", "docx"}:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported.",
        )

    file_bytes = file.file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(file_bytes) > settings.MAX_RESUME_BYTES:
        limit_mb = settings.MAX_RESUME_BYTES // (1024 * 1024)

        raise HTTPException(
            status_code=413,
            detail=f"Resume is too large (limit {limit_mb} MB).",
        )

    try:
        extracted_text = extract_resume_text(file.filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Could not read this file. Is it a valid PDF or DOCX?",
        ) from exc

    if len(extracted_text.strip()) < MIN_RESUME_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                "We couldn't find readable text in this file. If it's a "
                "scanned document, export a text-based PDF and try again."
            ),
        )

    ensure_profile(db, user)

    # Re-uploading the same resume should not spend another Gemini call.
    # ("total_years_experience" marks profiles made by the current schema.)
    previous = (
        db.query(Resume)
        .filter(
            Resume.user_id == user_id,
            Resume.extracted_text == extracted_text,
            Resume.structured_profile.isnot(None),
        )
        .order_by(Resume.created_at.desc())
        .first()
    )

    if previous and "total_years_experience" in (previous.structured_profile or {}):
        structured_profile = previous.structured_profile
    else:
        # AIServiceError propagates to the app-level handler, which returns
        # 429/503 with a friendly message and a Retry-After header.
        structured_profile = analyze_resume(extracted_text, interactive=True)

    storage_path = (
        f"{user_id}/"
        f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}-"
        f"{_safe_filename(file.filename)}"
    )

    try:
        get_supabase_client().storage.from_("resumes").upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": file.content_type
                or "application/octet-stream",
                "upsert": "true",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Resume storage upload failed: {exc}",
        ) from exc

    db.query(Resume).filter(Resume.user_id == user_id).update(
        {Resume.is_active: False}
    )

    resume = Resume(
        user_id=user_id,
        file_name=file.filename,
        storage_path=storage_path,
        extracted_text=extracted_text,
        structured_profile=structured_profile,
        is_active=True,
    )

    db.add(resume)
    db.commit()
    db.refresh(resume)

    return _to_response(resume)


@router.get(
    "/current",
    response_model=ResumeResponse | None,
)
def get_current_resume(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    resume = (
        db.query(Resume)
        .filter(
            Resume.user_id == user_id,
            Resume.is_active.is_(True),
        )
        .order_by(Resume.created_at.desc())
        .first()
    )

    if not resume:
        return None

    return _to_response(resume)
