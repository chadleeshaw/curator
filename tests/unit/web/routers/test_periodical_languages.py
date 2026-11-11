"""Language counts treat a blank language as English."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Periodical
from web.routers.auth import get_verify_token
from web.routers.periodicals import _shared

import web.routers.periodicals.crud  # noqa: F401


@pytest.fixture
def test_db():
    """Create a file-based SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name
    try:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def test_client(test_db):
    """Client for the periodicals router with auth bypassed."""
    _, session_factory = test_db
    _shared.set_dependencies(session_factory=session_factory, library_base_dir=None)
    app = FastAPI()
    app.include_router(_shared.router)
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    with TestClient(app) as client:
        yield client


def _add_periodical(session, title, language, file_path):
    session.add(
        Periodical(
            title=title,
            language=language,
            file_path=file_path,
            issue_date=datetime(2024, 1, 1),
            user_id=1,
        )
    )


def test_blank_language_counts_as_english(test_client, test_db):
    """NULL, empty, and whitespace languages fold into English."""
    _, session_factory = test_db
    session = session_factory()
    rows = [
        ("Field Notes", None, "/tmp/field-notes.pdf"),
        ("Field Notes", "", "/tmp/field-notes-blank.pdf"),
        ("City Paper", "   ", "/tmp/city-paper.pdf"),
        ("Weekly Review", "English", "/tmp/weekly-review.pdf"),
        ("Harbor News", "English", "/tmp/harbor-news.pdf"),
        ("Town Gazette", " German ", "/tmp/town-gazette-padded.pdf"),
        ("Town Gazette", "German", "/tmp/town-gazette.pdf"),
        ("Revue", "French", "/tmp/revue.pdf"),
    ]
    for title, language, file_path in rows:
        _add_periodical(session, title, language, file_path)
    session.commit()
    session.close()

    response = test_client.get("/api/periodicals/languages")

    assert response.status_code == 200
    languages = {row["language"]: row["count"] for row in response.json()["languages"]}
    assert languages == {"English": 5, "French": 1, "German": 2}
    assert "" not in languages
    assert "   " not in languages
    assert " German " not in languages
