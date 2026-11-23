
from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app import models


app = FastAPI(
    title="InsightFlow AI API",
    description="AI-powered Business Intelligence and Data Operations Platform",
    version="1.0.0",
)


@app.get("/")
def home():
    return {
        "message": "InsightFlow AI backend running",
        "status": "healthy",
    }


@app.get("/health/database")
def database_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "status": "healthy",
        }

    except SQLAlchemyError:
        return {
            "database": "disconnected",
            "status": "unhealthy",
        }
