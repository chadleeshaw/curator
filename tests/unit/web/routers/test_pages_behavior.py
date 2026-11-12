"""Behavior tests for the HTML page routes in web/routers/pages.py."""

import html
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import (
    Base,
    Credentials,
    Periodical,
    PeriodicalTracking,
    Stack,
    StackMembership,
)
from web.routers import pages

REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch):
    """Templates are opened with paths relative to the repository root."""
    monkeypatch.chdir(REPO_ROOT)


@pytest.fixture
def test_db():
    """File-backed SQLite so the router's worker thread can see committed rows."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    try:
        yield engine, session_factory
    finally:
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def test_client(test_db):
    """Mount the pages router the same way the tasks router tests mount theirs."""
    _, session_factory = test_db
    pages.set_dependencies(session_factory)
    app = FastAPI()
    app.include_router(pages.router)
    with TestClient(app) as client:
        yield client


def _session(test_db):
    _, session_factory = test_db
    return session_factory()


def _add_user(session):
    session.add(Credentials(id=1, username="reader", password_hash="not-used"))


def _add_periodical(session, **overrides):
    values = {
        "user_id": 1,
        "title": "Wired",
        "issue_date": datetime(2024, 6, 1, tzinfo=UTC),
        "file_path": "/library/wired-2024-06.pdf",
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    return row


def _attr(body, name):
    match = re.search(rf'data-{name}="([^"]*)"', body)
    assert match, f"data-{name} attribute missing from response"
    return html.unescape(match.group(1))


def _data_attr(body, name):
    return json.loads(_attr(body, name))


def _issue_ids(years, specials):
    ids = [issue["id"] for year in years for issue in year["issues"]]
    ids.extend(item["id"] for item in specials)
    return ids


class TestStaticPages:
    """Routes that serve templates without reading the database."""

    def test_version_reports_build_fields(self, test_client):
        response = test_client.get("/api/version")

        assert response.status_code == 200
        data = response.json()
        assert set(data) == {"version", "is_dev", "build_hash"}
        assert isinstance(data["version"], str) and data["version"]
        assert isinstance(data["is_dev"], bool)
        assert isinstance(data["build_hash"], str) and data["build_hash"]

    def test_root_serves_library_page(self, test_client):
        response = test_client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Curator</title>" in response.text
        assert 'id="periodicals-grid"' in response.text

    def test_login_page(self, test_client):
        response = test_client.get("/login.html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Curator - Login</title>" in response.text
        assert 'id="loginForm"' in response.text

    @pytest.mark.parametrize(
        ("path", "title"),
        [
            ("/epub-reader?id=1", "EPUB Reader - Curator"),
            ("/comic-reader?id=4", "Comic Reader - Curator"),
            ("/pdf-reader?id=9", "PDF Reader - Curator"),
        ],
    )
    def test_reader_pages_serve_html_for_any_id(self, test_client, path, title):
        response = test_client.get(path)

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert f"<title>{title}</title>" in response.text

    @pytest.mark.parametrize("path", ["/epub-reader", "/comic-reader", "/pdf-reader", "/periodical"])
    def test_id_query_is_required(self, test_client, path):
        response = test_client.get(path)

        assert response.status_code == 422


class TestPeriodicalPages:
    """/periodical and /periodicals/{title} render issue groups from SQLite."""

    def test_periodical_by_id_missing(self, test_client):
        response = test_client.get("/periodical", params={"id": 99999})

        assert response.status_code == 404
        assert response.json()["detail"] == "Periodical with ID 99999 not found"

    def test_periodical_by_id_groups_issues_and_specials(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        june = _add_periodical(
            session,
            title="Wired",
            issue_date=datetime(2024, 6, 15, tzinfo=UTC),
            file_path="/library/wired-2024-06.pdf",
            cover_path="/covers/wired-2024-06.jpg",
        )
        january = _add_periodical(
            session,
            title="Wired",
            issue_date=datetime(2023, 1, 1, tzinfo=UTC),
            file_path="/library/wired-2023-01.pdf",
        )
        holiday = _add_periodical(
            session,
            title="Wired",
            issue_date=datetime(2022, 12, 1, tzinfo=UTC),
            file_path="/library/wired-holiday.pdf",
            derived_metadata={"is_special_edition": True, "special_edition_name": "Holiday"},
        )
        session.commit()
        june_id, january_id, holiday_id = june.id, january.id, holiday.id
        session.close()

        response = test_client.get("/periodical", params={"id": june_id})

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Wired - Curator</title>" in response.text
        years = _data_attr(response.text, "years")
        specials = _data_attr(response.text, "special-editions")
        assert [year["year"] for year in years] == [2024, 2023]
        assert years[0]["issues"][0]["id"] == june_id
        assert years[0]["issues"][0]["title"] == "Wired"
        assert years[0]["issues"][0]["issue_date"] == "2024-06-15"
        assert years[0]["issues"][0]["file_path"] == "/library/wired-2024-06.pdf"
        assert years[0]["issues"][0]["cover_url"] == f"/api/periodicals/{june_id}/cover"
        assert years[1]["issues"][0]["id"] == january_id
        assert years[1]["issues"][0]["issue_date"] == "2023-01-01"
        assert [item["id"] for item in specials] == [holiday_id]
        assert specials[0]["title"] == "Wired"
        assert specials[0]["issue_date"] == "2022-12-01"
        assert specials[0]["cover_url"] == f"/api/periodicals/{holiday_id}/cover"
        assert specials[0]["derived_metadata"]["special_edition_name"] == "Holiday"
        assert holiday_id not in _issue_ids(years, [])

    @pytest.mark.parametrize("by", ["id", "title"])
    def test_undated_issues_have_no_date_and_group_last(self, test_client, test_db, by):
        """The 1900 sentinel is not shown as a date, and its group sorts after every year."""
        session = _session(test_db)
        _add_user(session)
        dated = _add_periodical(session, issue_date=datetime(2024, 6, 1, tzinfo=UTC))
        undated = _add_periodical(
            session,
            issue_date=datetime(1900, 1, 1, tzinfo=UTC),
            file_path="/library/wired-vol-3.pdf",
            derived_metadata={"volume": {"value": 3}},
        )
        session.commit()
        dated_id, undated_id = dated.id, undated.id
        session.close()

        if by == "id":
            response = test_client.get("/periodical", params={"id": dated_id})
        else:
            response = test_client.get("/periodicals/Wired")

        assert response.status_code == 200
        years = _data_attr(response.text, "years")
        assert [year["year"] for year in years] == [2024, "Undated"]
        assert years[1]["issues"][0]["id"] == undated_id
        assert years[1]["issues"][0]["issue_date"] is None
        assert years[0]["issues"][0]["issue_date"] == "2024-06-01"

    def test_periodical_by_id_uses_tracking_title(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        tracking = PeriodicalTracking(user_id=1, olid="OLWIRED", title="Wired", language="English")
        session.add(tracking)
        session.flush()
        uk = _add_periodical(
            session,
            title="Wired UK",
            tracking_id=tracking.id,
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
            file_path="/library/wired-uk.pdf",
        )
        us = _add_periodical(
            session,
            title="Wired US",
            tracking_id=tracking.id,
            issue_date=datetime(2023, 5, 1, tzinfo=UTC),
            file_path="/library/wired-us.pdf",
        )
        session.commit()
        uk_id, us_id = uk.id, us.id
        session.close()

        response = test_client.get("/periodical", params={"id": uk_id})

        assert response.status_code == 200
        assert "<title>Wired - Curator</title>" in response.text
        assert "<title>Wired UK - Curator</title>" not in response.text
        years = _data_attr(response.text, "years")
        assert [year["year"] for year in years] == [2024, 2023]
        assert {issue["id"] for year in years for issue in year["issues"]} == {uk_id, us_id}
        assert years[0]["issues"][0]["title"] == "Wired UK"
        assert years[0]["issues"][0]["issue_date"] == "2024-06-01"

    def test_periodical_by_title_missing(self, test_client):
        response = test_client.get("/periodicals/Missing%20Title")

        assert response.status_code == 404
        assert response.json()["detail"] == "No periodicals found for 'Missing Title'"

    def test_periodical_by_title_renders_special_edition_name(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        _add_periodical(
            session,
            title="Economist",
            issue_date=datetime(2024, 3, 1, tzinfo=UTC),
            file_path="/library/economist-2024-03.pdf",
        )
        _add_periodical(
            session,
            title="Economist",
            issue_date=datetime(2021, 12, 20, tzinfo=UTC),
            file_path="/library/economist-holiday.pdf",
            derived_metadata={"is_special_edition": {"value": True}, "special_edition_name": "Holiday"},
        )
        session.commit()
        session.close()

        response = test_client.get("/periodicals/Economist")

        assert response.status_code == 200
        assert "<title>Economist - Curator</title>" in response.text
        years = _data_attr(response.text, "years")
        specials = _data_attr(response.text, "special-editions")
        assert [year["year"] for year in years] == [2024]
        assert years[0]["issues"][0]["issue_date"] == "2024-03-01"
        assert years[0]["issues"][0]["file_path"] == "/library/economist-2024-03.pdf"
        assert len(specials) == 1
        assert specials[0]["issue_date"] == "2021-12-20"
        assert specials[0]["special_edition_name"] == "Holiday"
        assert specials[0]["derived_metadata"]["is_special_edition"] == {"value": True}

    def test_periodical_by_title_language_filter(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        _add_periodical(
            session,
            title="Monde",
            language="English",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            file_path="/library/monde-en.pdf",
        )
        _add_periodical(
            session,
            title="Monde",
            language="French",
            issue_date=datetime(2024, 2, 1, tzinfo=UTC),
            file_path="/library/monde-fr.pdf",
        )
        session.commit()
        session.close()

        french = test_client.get("/periodicals/Monde", params={"language": "French"})
        missing = test_client.get("/periodicals/Monde", params={"language": "German"})

        assert french.status_code == 200
        years = _data_attr(french.text, "years")
        assert len(years) == 1
        assert len(years[0]["issues"]) == 1
        assert years[0]["issues"][0]["issue_date"] == "2024-02-01"
        assert years[0]["issues"][0]["file_path"] == "/library/monde-fr.pdf"
        assert missing.status_code == 404
        assert missing.json()["detail"] == "No periodicals found for 'Monde'"

    def test_periodical_by_title_tracking_id_query(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        tracking = PeriodicalTracking(
            user_id=1,
            olid="OLSCI",
            title="Scientific American",
            language="English",
        )
        session.add(tracking)
        session.flush()
        _add_periodical(
            session,
            title="SciAm",
            tracking_id=tracking.id,
            issue_date=datetime(2020, 4, 1, tzinfo=UTC),
            file_path="/library/sciam-2020-04.pdf",
        )
        session.commit()
        tracking_id = tracking.id
        session.close()

        found = test_client.get("/periodicals/Ignored", params={"tracking_id": tracking_id})
        missing = test_client.get("/periodicals/Ignored", params={"tracking_id": 99999})

        assert found.status_code == 200
        assert "<title>Scientific American - Curator</title>" in found.text
        years = _data_attr(found.text, "years")
        assert years[0]["year"] == 2020
        assert years[0]["issues"][0]["title"] == "SciAm"
        assert years[0]["issues"][0]["issue_date"] == "2020-04-01"
        assert years[0]["issues"][0]["file_path"] == "/library/sciam-2020-04.pdf"
        assert missing.status_code == 404
        assert missing.json()["detail"] == "No periodicals found for 'Ignored'"

    def test_periodical_by_issue_title_follows_tracking_record(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        tracking = PeriodicalTracking(user_id=1, olid="OLNY", title="New Yorker", language="English")
        session.add(tracking)
        session.flush()
        _add_periodical(
            session,
            title="New Yorker Weekly",
            tracking_id=tracking.id,
            issue_date=datetime(2019, 8, 1, tzinfo=UTC),
            file_path="/library/new-yorker-weekly.pdf",
        )
        _add_periodical(
            session,
            title="New Yorker Monthly",
            tracking_id=tracking.id,
            issue_date=datetime(2018, 8, 1, tzinfo=UTC),
            file_path="/library/new-yorker-monthly.pdf",
        )
        session.commit()
        session.close()

        response = test_client.get(f"/periodicals/{quote('New Yorker Weekly')}")

        assert response.status_code == 200
        assert "<title>New Yorker - Curator</title>" in response.text
        years = _data_attr(response.text, "years")
        assert [year["year"] for year in years] == [2019, 2018]
        titles = [issue["title"] for year in years for issue in year["issues"]]
        assert titles == ["New Yorker Weekly", "New Yorker Monthly"]


class TestStackPages:
    """/stacks/{slug} renders stack membership from SQLite."""

    def test_stack_missing(self, test_client):
        response = test_client.get("/stacks/missing-stack")

        assert response.status_code == 404
        assert response.json()["detail"] == "Stack 'missing-stack' not found"

    def test_empty_stack(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        session.add(Stack(user_id=1, name="Empty Stack", slug="empty-stack", description=None))
        session.commit()
        session.close()

        response = test_client.get("/stacks/empty-stack")

        assert response.status_code == 200
        assert "<title>Empty Stack - Curator</title>" in response.text
        assert _attr(response.text, "slug") == "empty-stack"
        assert _data_attr(response.text, "members") == []

    def test_stack_renders_tracking_and_periodical_members(self, test_client, test_db):
        session = _session(test_db)
        _add_user(session)
        tracking = PeriodicalTracking(
            user_id=1,
            olid="OLASTRO",
            title="Astronomy",
            language="English",
            category="Magazines",
            country="US",
            first_publish_year=1973,
        )
        session.add(tracking)
        session.flush()
        tracked = _add_periodical(
            session,
            title="Astronomy",
            tracking_id=tracking.id,
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
            file_path="/library/astronomy-2024-06.pdf",
            cover_path="/covers/astronomy.jpg",
            language="English",
        )
        standalone = _add_periodical(
            session,
            title="One-off Digest",
            issue_date=datetime(2024, 5, 1, tzinfo=UTC),
            file_path="/library/one-off.pdf",
            cover_path="/covers/one-off.jpg",
            language="French",
        )
        stack = Stack(
            user_id=1,
            name="Astronomy Stack",
            slug="astronomy-stack",
            description="Nightly science reading",
        )
        session.add(stack)
        session.flush()
        session.add(
            StackMembership(
                stack_id=stack.id,
                periodical_tracking_id=tracking.id,
                added_at=datetime(2024, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            StackMembership(
                stack_id=stack.id,
                periodical_id=standalone.id,
                added_at=datetime(2024, 2, 1, tzinfo=UTC),
            )
        )
        session.commit()
        tracking_id, tracked_id, standalone_id = tracking.id, tracked.id, standalone.id
        session.close()

        response = test_client.get("/stacks/astronomy-stack")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<title>Astronomy Stack - Curator</title>" in response.text
        assert "Nightly science reading" in response.text
        assert _attr(response.text, "slug") == "astronomy-stack"
        members = _data_attr(response.text, "members")
        assert [member["type"] for member in members] == ["tracking", "periodical"]
        assert members[0]["tracking_id"] == tracking_id
        assert members[0]["title"] == "Astronomy"
        assert members[0]["language"] == "English"
        assert members[0]["category"] == "Magazines"
        assert members[0]["country"] == "US"
        assert members[0]["first_publish_year"] == 1973
        assert members[0]["library_count"] == 1
        assert members[0]["cover_periodical_id"] == tracked_id
        assert members[1]["id"] == standalone_id
        assert members[1]["title"] == "One-off Digest"
        assert members[1]["language"] == "French"
        assert members[1]["category"] is None
        assert members[1]["cover_path"] == "/covers/one-off.jpg"
        assert members[1]["cover_periodical_id"] == standalone_id
        assert members[1]["issue_date"].startswith("2024-05-01")
