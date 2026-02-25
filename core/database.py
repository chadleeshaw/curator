"""
Database session management
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.constants.app import DB_LOCK_TIMEOUT

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and session lifecycle"""

    def __init__(self, db_url: str):
        connect_args = {
            "check_same_thread": False,
            "timeout": DB_LOCK_TIMEOUT,
        }

        is_memory_db = ":memory:" in db_url
        poolclass = StaticPool if is_memory_db else None

        self.engine = create_engine(
            db_url,
            echo=False,
            connect_args=connect_args,
            poolclass=poolclass,
            pool_pre_ping=True,
        )
        self._db_url = db_url

        if "sqlite" in db_url and not is_memory_db:

            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute(f"PRAGMA busy_timeout={int(DB_LOCK_TIMEOUT * 1000)}")
                cursor.close()

        self.session_factory = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all database tables — used for in-memory test databases only."""
        from models.database import Base

        Base.metadata.create_all(self.engine)

    def run_migrations(self):
        """
        Run Alembic database migrations to ensure schema is up to date.

        Strategy:
          - If the database has tables but no alembic_version table (existing pre-Alembic DB):
            stamp the database at the current head revision so Alembic knows it's already current.
          - If the database is empty (new install): run 'upgrade head' to create the full schema.
          - If alembic_version already exists: run 'upgrade head' to apply any new migrations.
        """
        # In-memory databases are set up with create_tables(), not Alembic.
        if ":memory:" in self._db_url:
            logger.debug("In-memory database: skipping Alembic, using create_tables()")
            self.create_tables()
            return

        from alembic import command
        from alembic.config import Config

        alembic_cfg = self._build_alembic_config()

        inspector = inspect(self.engine)
        existing_tables = set(inspector.get_table_names())

        if existing_tables and "alembic_version" not in existing_tables:
            # Pre-Alembic database: the schema matches revision 001 (no user_id columns).
            # Stamp at 001 so Alembic knows the baseline, then run upgrade to apply
            # any subsequent migrations (e.g. 002 adds user_id columns).
            logger.info("Existing pre-Alembic database detected. " "Stamping at revision 001, then upgrading to head.")
            command.stamp(alembic_cfg, "001")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database upgraded to Alembic head revision.")
        else:
            # Fresh database or already managed by Alembic: apply any pending migrations.
            logger.debug("Running Alembic upgrade to head")
            command.upgrade(alembic_cfg, "head")

    def _build_alembic_config(self):
        """Build an Alembic Config object pointing at this database."""
        from alembic.config import Config

        # Locate alembic.ini relative to this file's package root.
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(here)
        ini_path = os.path.join(project_root, "alembic.ini")

        cfg = Config(ini_path)
        # Override the URL with the live engine URL (handles all path/env-var scenarios).
        cfg.set_main_option("sqlalchemy.url", str(self.engine.url))
        return cfg

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic commit/rollback.

        Usage:
            with db_manager.get_session() as session:
                session.add(obj)
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session_dependency(self) -> Generator[Session, None, None]:
        """
        Dependency for FastAPI route injection.

        Usage:
            @app.get("/items")
            def get_items(session: Session = Depends(db_manager.get_session_dependency)):
                return session.query(Item).all()
        """
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
