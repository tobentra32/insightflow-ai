
import os
import ssl

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


load_dotenv()


def normalize_database_url(database_url: str):
    """
    Configure PostgreSQL URLs to use the pure-Python pg8000 driver.

    Psycopg-specific query parameters are removed because pg8000
    uses a Python SSLContext for encrypted connections.
    """
    url = make_url(database_url)

    query = dict(url.query)
    query.pop("sslmode", None)
    query.pop("channel_binding", None)

    return url.set(
        drivername="postgresql+pg8000",
        query=query,
    )


def create_database_engine(database_url: str, **engine_options):
    """
    Create a PostgreSQL engine using pg8000 and verified TLS.
    """
    connect_args = dict(engine_options.pop("connect_args", {}) or {})

    connect_args.setdefault(
        "ssl_context",
        ssl.create_default_context(),
    )

    return create_engine(
        normalize_database_url(database_url),
        connect_args=connect_args,
        **engine_options,
    )


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing from .env")


engine = create_database_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
