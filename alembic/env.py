"""Alembic environment — wired to the app's SQLAlchemy engine and models."""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Pull in the app's engine config and models ──────────────────────────────
from app.config import get_settings
from app.database import Base

# Ensure all models are registered on Base.metadata before autogenerate runs
import app.models  # noqa: F401  (side-effect import)

# This is the Alembic Config object (gives access to alembic.ini values)
config = context.config

# Override sqlalchemy.url with the value from our Settings
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Provide the metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (uses a live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
