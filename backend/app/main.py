
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

from app.database import engine
from app.routes import admin, auth, datasets, projects, sheets


app = FastAPI(
    title="InsightFlow AI API",
    description="AI-powered BI and Data Operations Platform",
    version="1.0.0",
)


FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Return safe validation errors without echoing rejected input.

    Pydantic validation errors can contain non-finite values such as NaN
    in their input/context fields. Those values cannot be serialized as
    strict JSON, so only expose the location, message, and error type.
    """
    safe_errors = []

    for error in exc.errors():
        safe_errors.append(
            {
                "loc": list(error.get("loc", ())),
                "msg": str(error.get("msg", "Invalid request.")),
                "type": str(error.get("type", "value_error")),
            }
        )

    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def validate_browser_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")

        if origin and origin not in FRONTEND_ORIGINS:
            return JSONResponse(
                status_code=403,
                content={"detail": "Untrusted request origin."},
            )

    return await call_next(request)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(datasets.router)
app.include_router(sheets.router)
app.include_router(projects.router)


@app.get("/")
def root():
    return {
        "message": "InsightFlow AI API is running.",
        "status": "healthy",
    }


@app.get("/health/database")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "status": "healthy",
        }

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "database": "disconnected",
                "status": "unhealthy",
            },
        )
