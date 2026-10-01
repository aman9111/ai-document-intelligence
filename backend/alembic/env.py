from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import models  # noqa: F401  (registers every table on Base.metadata)
from database import DATABASE_URL, Base

config = context.config

# The connection string comes from .env (via database.py), not from alembic.ini,
# so there's only one place to change it
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# When migrations run from the app on startup, keep the app's logging as it is
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# What the tables should look like: Alembic compares this with the real database
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The app passes its own connection when it migrates on startup
    connection = config.attributes.get("connection")

    if connection is not None:
        run_migrations(connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
