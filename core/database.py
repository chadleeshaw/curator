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
        """Run database migrations to ensure schema is up to date"""
        inspector = inspect(self.engine)
        
        # Define expected schema for each table
        expected_schemas = {
            "periodical_tracking": [
                ("delete_from_client_on_completion", "BOOLEAN DEFAULT 0"),
            ],
            "download_submissions": [
                # Add any future columns here
            ],
            "search_results": [
                # Add any future columns here
            ],
            "magazines": [
                # Add any future columns here
            ],
        }
        
        migrations_applied = 0
        
        for table_name, columns_to_add in expected_schemas.items():
            # Check if table exists
            if not inspector.has_table(table_name):
                logger.debug(f"Table {table_name} doesn't exist yet, skipping migration check")
                continue
            
            # Get existing columns
            existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
            
            # Check and add missing columns
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    logger.info(f"Adding missing column '{column_name}' to {table_name}")
                    try:
                        with self.engine.connect() as conn:
                            conn.execute(
                                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
                            )
                            conn.commit()
                        migrations_applied += 1
                        logger.info(f"✓ Added column {table_name}.{column_name}")
                    except Exception as e:
                        logger.error(f"Failed to add column {table_name}.{column_name}: {e}")
        
        if migrations_applied > 0:
            logger.info(f"Schema migrations complete: {migrations_applied} column(s) added")
        else:
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
