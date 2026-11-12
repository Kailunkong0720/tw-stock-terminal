from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from pipeline.core.config import get_settings
from pipeline.models import Base

config = context.config
target_metadata = Base.metadata

# 命令列直接執行 alembic 時（alembic.ini 裡是佔位字串），使用管線設定的資料庫位置。
# 由 pipeline.core.db.migrate() 呼叫時連線字串已經填好，不要覆蓋。
if config.get_main_option("sqlalchemy.url", "") == "pipeline-default":
    settings = get_settings()
    settings.ensure_dirs()
    config.set_main_option("sqlalchemy.url", settings.db_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
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
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
