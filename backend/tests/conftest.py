
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=backend_dir / ".env")

from app.database import (
    create_database_engine,
    get_db,
)
import app.models
from app.main import app


@pytest.fixture(scope="session")
def test_engine():
    test_database_url = os.getenv("TEST_DATABASE_URL")
    main_database_url = os.getenv("DATABASE_URL")

    if not test_database_url or not main_database_url:
        raise RuntimeError(
            "Both TEST_DATABASE_URL and DATABASE_URL must be configured."
        )

    test_url = make_url(test_database_url)
    main_url = make_url(main_database_url)

    same_database = (
        test_url.host == main_url.host
        and test_url.port == main_url.port
        and test_url.database == main_url.database
    )

    if same_database:
        raise RuntimeError(
            "TEST_DATABASE_URL points to the main database."
        )

    previous_alembic_url = os.environ.get(
        "ALEMBIC_DATABASE_URL"
    )

    os.environ["ALEMBIC_DATABASE_URL"] = test_database_url

    try:
        alembic_config = Config(
            str(backend_dir / "alembic.ini")
        )

        alembic_config.set_main_option(
            "script_location",
            str(backend_dir / "alembic"),
        )

        command.upgrade(alembic_config, "head")

    finally:
        if previous_alembic_url is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous_alembic_url

    engine = create_database_engine(
        test_database_url,
        pool_pre_ping=True,
    )

    yield engine

    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()

    testing_session_local = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    session = testing_session_local()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
