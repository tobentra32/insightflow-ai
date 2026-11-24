
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from dotenv import load_dotenv

from app.database import engine
from app.routes import datasets, sheets, auth


load_dotenv()

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
app.include_router(datasets.router)
app.include_router(sheets.router)


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
