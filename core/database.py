"""
Database session management
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


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
