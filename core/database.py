"""
Database session management
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
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
        """Create all database tables"""
        from models.database import Base

        Base.metadata.create_all(self.engine)

    def run_migrations(self):
        """Run database migrations to ensure schema is up to date."""
        from models.database import Base

        inspector = inspect(self.engine)
        inspector = self._create_missing_tables(inspector, Base)
        migrations_applied = self._add_missing_columns(inspector)
        migrations_applied += self._rename_columns(inspector)
        self._run_data_migrations()
        migrations_applied += self._remove_deprecated_columns(inspector)

        if migrations_applied > 0:
            logger.info(f"Schema migrations complete: {migrations_applied} migration(s) applied")
        else:
            logger.debug("Schema is up to date, no migrations needed")

    def _create_missing_tables(self, inspector, Base):
        from models.database import Base as _Base

        existing_tables = set(inspector.get_table_names())
        metadata_tables = set(Base.metadata.tables.keys())
        missing_tables = metadata_tables - existing_tables

        if missing_tables:
            logger.info(f"Creating missing tables: {', '.join(sorted(missing_tables))}")
            Base.metadata.create_all(
                self.engine,
                tables=[Base.metadata.tables[name] for name in missing_tables],
            )
            logger.info(f"✓ Created {len(missing_tables)} missing table(s)")
            inspector = inspect(self.engine)

        return inspector

    def _add_missing_columns(self, inspector) -> int:
        from models.migrations import COLUMN_ADDITIONS

        migrations_applied = 0

        for table_name, columns_to_add in COLUMN_ADDITIONS.items():
            if not inspector.has_table(table_name):
                logger.warning(f"Table {table_name} still doesn't exist after migration attempt")
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    logger.info(f"Adding missing column '{column_name}' to {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Added column {table_name}.{column_name}")
                    except SQLAlchemyError as db_error:
                        logger.error(f"Failed to add column {table_name}.{column_name}: {db_error}")

        return migrations_applied

    def _rename_columns(self, inspector) -> int:
        from models.migrations import COLUMN_RENAMES

        migrations_applied = 0

        for table_name, renames in COLUMN_RENAMES.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for old_name, new_name in renames:
                if old_name in existing_columns and new_name not in existing_columns:
                    logger.info(f"Renaming column '{old_name}' to '{new_name}' in {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Renamed column {table_name}.{old_name} → {new_name}")
                    except Exception as rename_error:
                        logger.error(f"Failed to rename column {table_name}.{old_name}: {rename_error}")

        return migrations_applied

    def _run_data_migrations(self):
        from models.migrations import run_data_migrations

        session = self.session_factory()
        try:
            results = run_data_migrations(session)
            session.commit()

            total_migrated = sum(results.values())
            if total_migrated > 0:
                logger.info(f"Data migrations complete: {total_migrated} record(s) migrated")
                for migration_name, count in results.items():
                    if count > 0:
                        logger.debug(f"  {migration_name}: {count} record(s)")
        except Exception as migration_error:
            session.rollback()
            logger.error(f"Data migration failed: {migration_error}")
            raise
        finally:
            session.close()

    def _remove_deprecated_columns(self, inspector) -> int:
        from models.migrations import COLUMN_REMOVALS

        migrations_applied = 0

        for table_name, columns_to_remove in COLUMN_REMOVALS.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for column_name in columns_to_remove:
                if column_name in existing_columns:
                    logger.info(f"Removing deprecated column '{column_name}' from {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Removed column {table_name}.{column_name}")
                    except Exception as drop_error:
                        logger.warning(
                            f"Could not remove column {table_name}.{column_name}: {drop_error}. "
                            f"This column is deprecated and can be safely ignored."
                        )

        return migrations_applied

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
        finally:
            session.close()
