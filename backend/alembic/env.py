
import os
from pathlib import Path
from logging.config import fileConfig

from dotenv import load_dotenv
from alembic import context
from sqlalchemy import pool

backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=backend_dir / ".env")

from app.database import (
    Base,
    create_database_engine,
    normalize_database_url,
)
from app import models


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


database_url = (
    os.getenv("ALEMBIC_DATABASE_URL")
    or os.getenv("DATABASE_URL")
)

if not database_url:
    raise RuntimeError(
        "Neither ALEMBIC_DATABASE_URL nor DATABASE_URL is configured."
    )


normalized_url = normalize_database_url(database_url)

config.set_main_option(
    "sqlalchemy.url",
    normalized_url.render_as_string(
        hide_password=False
    ).replace("%", "%%"),
)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_database_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
