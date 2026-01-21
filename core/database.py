"""
Database session management
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and session lifecycle"""

    def __init__(self, db_url: str):
        """
        Initialize database manager

        Args:
            db_url: SQLAlchemy database URL
        """
        self.engine = create_engine(db_url, echo=False)
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

        # Define expected schema for column additions/migrations
        expected_schemas = {
            "credentials": [
                ("api_token", "VARCHAR(255)"),
            ],
            "periodical_tracking": [
                ("delete_from_client_on_completion", "BOOLEAN DEFAULT 1"),
                ("language", "VARCHAR(50) DEFAULT 'English'"),
                ("category", "VARCHAR(100)"),
                ("download_category", "VARCHAR(100)"),
                ("country", "VARCHAR(50)"),
                # Adaptive search scheduling fields
                ("last_searched", "DATETIME"),
                ("search_count", "INTEGER DEFAULT 0"),
                ("search_interval_hours", "INTEGER DEFAULT 6"),
                ("total_issues_discovered", "INTEGER DEFAULT 0"),
                ("last_discovery_count", "INTEGER DEFAULT 0"),
                ("last_discovery_date", "DATETIME"),
                ("searches_without_new_issues", "INTEGER DEFAULT 0"),
            ],
            "periodicals": [
                ("language", "VARCHAR(50) DEFAULT 'English'"),
                ("category", "VARCHAR(100) DEFAULT 'Magazine'"),
                ("tracking_id", "INTEGER"),
                ("content_hash", "VARCHAR(64)"),
                ("created_at", "DATETIME"),
                ("updated_at", "DATETIME"),
            ],
            "download_submissions": [
                ("extra_status", "VARCHAR(512)"),
            ],
        }

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

        # Column renames (SQLite requires recreating tables, so we handle it carefully)
        column_renames = {
            "ocr_jobs": [("magazine_id", "periodical_id")],
            "search_results": [("magazine_id", "periodical_id")],
            "discovered_issues": [("magazine_id", "periodical_id")],
            "download_submissions": [("magazine_id", "periodical_id")],
            "downloads": [("magazine_id", "periodical_id")],
        }

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
