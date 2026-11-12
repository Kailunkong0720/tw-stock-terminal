"""SQLite 連線與遷移。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from pipeline.core.config import PIPELINE_DIR, Settings, get_settings


def make_engine(settings: Settings) -> Engine:
    settings.ensure_dirs()
    engine = create_engine(settings.db_url, future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


@lru_cache(maxsize=4)
def _engine_for(settings: Settings) -> Engine:
    return make_engine(settings)


def get_engine(settings: Settings | None = None) -> Engine:
    return _engine_for(settings or get_settings())


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(settings), future=True)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate(settings: Settings | None = None) -> None:
    """把資料庫升級到最新結構（alembic upgrade head）。"""
    from alembic import command
    from alembic.config import Config

    s = settings or get_settings()
    s.ensure_dirs()
    cfg = Config(str(PIPELINE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(PIPELINE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", s.db_url)
    command.upgrade(cfg, "head")
