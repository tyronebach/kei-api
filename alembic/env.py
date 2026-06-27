from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import settings
from db.connection import Base
from db import models  # noqa: F401 - import models so metadata is populated

PAYMENT_METHOD_CONSTRAINT_REVISION = "e1f2a3b4c5d6"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def _guard_payment_method_constraint_downgrade(connection) -> None:
    if connection.dialect.name != "sqlite":
        return

    try:
        context.get_revision_argument()
    except KeyError:
        return

    migration_context = context.get_context()
    migration_fn = getattr(migration_context, "_migrations_fn", None)
    if migration_fn is None:
        return

    steps = list(migration_fn(migration_context.get_current_heads(), migration_context))
    for index, step in enumerate(steps):
        if not getattr(step, "is_downgrade", False):
            continue
        revision = getattr(getattr(step, "revision", None), "revision", None)
        if revision == PAYMENT_METHOD_CONSTRAINT_REVISION and index > 0:
            raise RuntimeError(
                "Downgrade across e1f2a3b4c5d6 is unsupported on SQLite: "
                "removing the payment_method CHECK constraint requires a deliberate "
                "table rebuild. Restore from backup, downgrade only to "
                "e1f2a3b4c5d6, or create a tested forward migration instead."
            )


def run_migrations_offline() -> None:
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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            _guard_payment_method_constraint_downgrade(connection)
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
