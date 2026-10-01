import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


# The migration that matches the tables created before Alembic was added
BASELINE_REVISION = "0001"


def init_database() -> None:
    from alembic import command
    from alembic.config import Config

    # pgvector must be enabled before tables with vector columns are created.
    # IF NOT EXISTS makes this safe to run on every start.
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    config.attributes["configure_logger"] = False

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = inspect(connection).get_table_names()

        # A database made with create_all() before migrations existed already has
        # the baseline tables: mark the baseline as done instead of creating them again
        if "users" in tables and "alembic_version" not in tables:
            command.stamp(config, BASELINE_REVISION)

        # Apply every migration that hasn't run yet (nothing happens if up to date)
        command.upgrade(config, "head")
