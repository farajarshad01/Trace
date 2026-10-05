from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai.errors import AIServiceError
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.resumes import router as resume_router
from app.api.roles import router as roles_router
from app.api.sources import router as sources_router
from app.api.jobs import router as jobs_router
from app.api.applications import (
    router as applications_router,
)
from app.core.config import settings
from app.database import models  # noqa: F401  (registers the tables)


app = FastAPI(
    title="Trace API",
    description=(
        "AI-powered personalized "
        "job tracking platform"
    ),
    version="1.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request: Request, exc: AIServiceError):
    """
    Turn Gemini failures into a clean response the UI can show:
    429 for rate/quota limits, 500 for a misconfigured key, else 503 -
    plus a Retry-After header when the API told us how long to wait.
    """

    status = exc.status_code if exc.status_code in (429, 500) else 503

    headers = {}

    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after) + 1)

    return JSONResponse(
        status_code=status,
        content={"detail": str(exc)},
        headers=headers,
    )


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(resume_router)
app.include_router(roles_router)
app.include_router(sources_router)
app.include_router(jobs_router)
app.include_router(applications_router)


@app.get("/")
def root():
    return {
        "message": "Trace API is running"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "trace-api",
        "ai_configured": bool(settings.GOOGLE_API_KEY),
        "ai_model": settings.GEMINI_MODEL,
    }
