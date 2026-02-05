"""
Database session management
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.constants.app import DB_LOCK_TIMEOUT

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and session lifecycle"""

    def __init__(self, db_url: str):
        """
        Initialize database manager

        Args:
            db_url: SQLAlchemy database URL
        """
        # Configure SQLite for concurrent access
        # - check_same_thread: Allow connections across threads (FastAPI/uvicorn)
        # - timeout: Wait up to 30 seconds before raising OperationalError
        # - StaticPool: Reuse single connection across threads for in-memory DBs
        connect_args = {
            "check_same_thread": False,
            "timeout": DB_LOCK_TIMEOUT,  # Wait for locks to be released
        }

        # Use StaticPool for in-memory databases, otherwise use default pooling
        is_memory_db = ":memory:" in db_url
        poolclass = StaticPool if is_memory_db else None

        self.engine = create_engine(
            db_url,
            echo=False,
            connect_args=connect_args,
            poolclass=poolclass,
            pool_pre_ping=True,  # Verify connections before using
        )

        # Enable WAL mode for better concurrent access (SQLite 3.7.0+)
        # WAL allows multiple readers and one writer simultaneously
        if "sqlite" in db_url and not is_memory_db:

            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")  # Faster writes with WAL
                cursor.execute(f"PRAGMA busy_timeout={int(DB_LOCK_TIMEOUT * 1000)}")  # milliseconds
                cursor.close()

        self.session_factory = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all database tables"""
        from models.database import Base

        Base.metadata.create_all(self.engine)

    def run_migrations(self):
        """
        Run database migrations to ensure schema is up to date.
        Creates missing tables and adds missing columns.
        """
        from models.database import Base

        inspector = inspect(self.engine)
        existing_tables = set(inspector.get_table_names())

        # Get all tables defined in models
        metadata_tables = set(Base.metadata.tables.keys())

        # Check for missing tables
        missing_tables = metadata_tables - existing_tables
        if missing_tables:
            logger.info(f"Creating missing tables: {', '.join(sorted(missing_tables))}")
            # Create only the missing tables
            Base.metadata.create_all(
                self.engine,
                tables=[Base.metadata.tables[table_name] for table_name in missing_tables],
            )
            logger.info(f"✓ Created {len(missing_tables)} missing table(s)")
            # Refresh inspector after creating tables
            inspector = inspect(self.engine)

        # Import schema definitions from migrations package
        from models.migrations import COLUMN_ADDITIONS

        expected_schemas = COLUMN_ADDITIONS

        migrations_applied = 0

        for table_name, columns_to_add in expected_schemas.items():
            # Check if table exists (should exist now after create_all above)
            if not inspector.has_table(table_name):
                logger.warning(f"Table {table_name} still doesn't exist after migration attempt")
                continue

            # Get existing columns
            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            # Check and add missing columns
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    logger.info(f"Adding missing column '{column_name}' to {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Added column {table_name}.{column_name}")
                    except Exception as e:
                        logger.error(f"Failed to add column {table_name}.{column_name}: {e}")

        # Import column renames from migrations package
        from models.migrations import COLUMN_RENAMES

        column_renames = COLUMN_RENAMES

        for table_name, renames in column_renames.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for old_name, new_name in renames:
                if old_name in existing_columns and new_name not in existing_columns:
                    logger.info(f"Renaming column '{old_name}' to '{new_name}' in {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            # SQLite doesn't support ALTER TABLE RENAME COLUMN directly in older versions
                            # Use a safe approach that works across SQLite versions
                            conn.execute(text(f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Renamed column {table_name}.{old_name} → {new_name}")
                    except Exception as e:
                        logger.error(f"Failed to rename column {table_name}.{old_name}: {e}")

        # Run data migrations after schema changes but before column removals
        # This ensures data is migrated before old columns are removed
        from models.migrations import run_data_migrations

        session = self.session_factory()
        try:
            data_migration_results = run_data_migrations(session)
            session.commit()

            # Log data migration results
            total_data_migrations = sum(data_migration_results.values())
            if total_data_migrations > 0:
                logger.info(f"Data migrations complete: {total_data_migrations} record(s) migrated")
                for migration_name, count in data_migration_results.items():
                    if count > 0:
                        logger.debug(f"  {migration_name}: {count} record(s)")
        except Exception as e:
            session.rollback()
            logger.error(f"Data migration failed: {e}")
            raise
        finally:
            session.close()

        # Import column removals from migrations package
        # This happens AFTER data migrations to ensure data is migrated first
        from models.migrations import COLUMN_REMOVALS

        column_removals = COLUMN_REMOVALS

        for table_name, columns_to_remove in column_removals.items():
            if not inspector.has_table(table_name):
                continue

            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}

            for column_name in columns_to_remove:
                if column_name in existing_columns:
                    logger.info(f"Removing deprecated column '{column_name}' from {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            # SQLite requires recreating the table to drop columns
                            # Use ALTER TABLE DROP COLUMN (supported in SQLite 3.35.0+)
                            conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Removed column {table_name}.{column_name}")
                    except Exception as e:
                        # If DROP COLUMN fails (older SQLite), log a warning but don't fail
                        logger.warning(
                            f"Could not remove column {table_name}.{column_name}: {e}. "
                            f"This column is deprecated and can be safely ignored."
                        )

        if migrations_applied > 0:
            logger.info(f"Schema migrations complete: {migrations_applied} migration(s) applied")
        elif not missing_tables:
            logger.debug("Schema is up to date, no migrations needed")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions with automatic commit/rollback

        Usage:
            with db_manager.get_session() as session:
                session.add(obj)
                # session.commit() called automatically on success
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
        Dependency for FastAPI route injection

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
