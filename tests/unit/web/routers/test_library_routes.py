"""HTTP coverage for stack CRUD and periodical library routes.

Stacks are exercised through the router with a sqlite session factory.
Periodical list, get, delete, and count stay on rows already in the database.
File routes are only called for missing files and wrong types, which return
before any PDF process pool starts.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, Periodical, PeriodicalTracking, Stack, StackMembership
from web.routers import stacks
from web.routers.auth import get_verify_token
from web.routers.periodicals import _shared

import web.routers.periodicals.crud  # noqa: F401
import web.routers.periodicals.files  # noqa: F401


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
    """Mount stack and periodical routers with auth bypassed."""
    _, session_factory = test_db
    stacks.set_dependencies(session_factory)
    _shared.set_dependencies(session_factory=session_factory, library_base_dir=None)
    app = FastAPI()
    app.include_router(stacks.router)
    app.include_router(_shared.router)
    app.dependency_overrides[get_verify_token] = lambda: "test_user"
    with TestClient(app) as client:
        yield client


def _session(test_db):
    _, session_factory = test_db
    return session_factory()


def _insert_periodical(test_db, **overrides):
    session = _session(test_db)
    values = {
        "user_id": 1,
        "title": "Wired",
        "language": "English",
        "category": "Magazines",
        "issue_date": datetime(2024, 6, 1, tzinfo=UTC),
        "file_path": "/library/wired-2024-06.pdf",
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    periodical_id = row.id
    session.close()
    return periodical_id


def _insert_tracking(test_db, **overrides):
    session = _session(test_db)
    values = {
        "user_id": 1,
        "olid": "OL1W",
        "title": "National Geographic",
        "language": "English",
        "category": "Magazines",
    }
    values.update(overrides)
    row = PeriodicalTracking(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    tracking_id = row.id
    session.close()
    return tracking_id


class TestStackRoutes:
    """CRUD, membership, and 404s for /api/stacks."""

    def test_create_list_get_and_update_round_trip(self, test_client, test_db):
        empty = test_client.get("/api/stacks")
        assert empty.status_code == 200
        assert empty.json() == {"success": True, "stacks": [], "total": 0}

        created = test_client.post(
            "/api/stacks",
            json={
                "name": "  Science Magazines  ",
                "description": "  shelf notes  ",
                "categories": ["Science", "Nature"],
            },
        )
        assert created.status_code == 200
        stack = created.json()["stack"]
        assert created.json()["success"] is True
        assert stack["name"] == "Science Magazines"
        assert stack["slug"] == "science-magazines"
        assert stack["description"] == "shelf notes"
        assert stack["categories"] == ["Science", "Nature"]
        assert stack["member_count"] == 0
        assert stack["preview_covers"] == []
        assert stack["sort_order"] == 0
        assert stack["id"]

        second = test_client.post("/api/stacks", json={"name": "Art Desk"})
        assert second.status_code == 200
        assert second.json()["stack"]["slug"] == "art-desk"
        assert second.json()["stack"]["sort_order"] == 1

        listed = test_client.get("/api/stacks")
        assert listed.status_code == 200
        assert listed.json()["total"] == 2
        assert [item["slug"] for item in listed.json()["stacks"]] == ["science-magazines", "art-desk"]
        assert listed.json()["stacks"][0]["member_count"] == 0

        fetched = test_client.get("/api/stacks/science-magazines")
        assert fetched.status_code == 200
        assert fetched.json()["stack"]["name"] == "Science Magazines"
        assert fetched.json()["stack"]["members"] == []

        updated = test_client.put(
            "/api/stacks/science-magazines",
            json={
                "name": "Nature Desk",
                "description": "",
                "categories": ["Nature"],
                "sort_order": 5,
            },
        )
        assert updated.status_code == 200
        updated_stack = updated.json()["stack"]
        assert updated_stack["name"] == "Nature Desk"
        assert updated_stack["slug"] == "nature-desk"
        assert updated_stack["description"] is None
        assert updated_stack["categories"] == ["Nature"]
        assert updated_stack["sort_order"] == 5

        assert test_client.get("/api/stacks/science-magazines").status_code == 404
        renamed = test_client.get("/api/stacks/nature-desk")
        assert renamed.status_code == 200
        assert renamed.json()["stack"]["name"] == "Nature Desk"

        session = _session(test_db)
        row = session.query(Stack).filter(Stack.slug == "nature-desk").one()
        assert row.name == "Nature Desk"
        assert row.description is None
        assert row.categories == ["Nature"]
        assert row.sort_order == 5
        assert session.query(Stack).count() == 2
        session.close()

        ordered = test_client.get("/api/stacks")
        assert [item["slug"] for item in ordered.json()["stacks"]] == ["art-desk", "nature-desk"]

    def test_duplicate_name_conflicts_and_slug_suffix(self, test_client, test_db):
        first = test_client.post("/api/stacks", json={"name": "Hello World!"})
        assert first.status_code == 200
        assert first.json()["stack"]["slug"] == "hello-world"

        duplicate = test_client.post("/api/stacks", json={"name": "Hello World!"})
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "A stack named 'Hello World!' already exists"

        suffixed = test_client.post("/api/stacks", json={"name": "Hello World"})
        assert suffixed.status_code == 200
        assert suffixed.json()["stack"]["name"] == "Hello World"
        assert suffixed.json()["stack"]["slug"] == "hello-world-1"

        conflict = test_client.put("/api/stacks/hello-world-1", json={"name": "Hello World!"})
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "A stack named 'Hello World!' already exists"

        session = _session(test_db)
        rows = {row.slug: row.name for row in session.query(Stack).all()}
        session.close()
        assert rows == {"hello-world": "Hello World!", "hello-world-1": "Hello World"}

    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("get", "/api/stacks/missing-stack", {}),
            ("put", "/api/stacks/missing-stack", {"json": {"name": "Nope"}}),
            ("delete", "/api/stacks/missing-stack", {}),
            ("post", "/api/stacks/missing-stack/members", {"json": {"periodical_ids": [1]}}),
            ("delete", "/api/stacks/missing-stack/members/1", {}),
            ("get", "/api/stacks/missing-stack/library", {}),
        ],
    )
    def test_missing_stack_returns_404(self, test_client, method, path, kwargs):
        response = getattr(test_client, method)(path, **kwargs)

        assert response.status_code == 404
        assert response.json()["detail"] == "Stack 'missing-stack' not found"

    def test_add_and_remove_members(self, test_client, test_db):
        created = test_client.post(
            "/api/stacks",
            json={"name": "Reading List", "description": "Current shelf"},
        )
        assert created.status_code == 200
        assert created.json()["stack"]["slug"] == "reading-list"

        tracking_id = _insert_tracking(test_db)
        geographic_id = _insert_periodical(
            test_db,
            title="National Geographic",
            file_path="/library/national-geographic-2024-06.pdf",
            issue_date=datetime(2024, 6, 15, tzinfo=UTC),
            cover_path="/covers/national-geographic.jpg",
            tracking_id=tracking_id,
        )
        lonely_id = _insert_periodical(
            test_db,
            title="Lonely Planet",
            file_path="/library/lonely-planet-2023-04.pdf",
            issue_date=datetime(2023, 4, 1, tzinfo=UTC),
            cover_path="/covers/lonely-planet.jpg",
            language="English",
            extra_metadata={"category": "Travel"},
        )

        added = test_client.post(
            "/api/stacks/reading-list/members",
            json={"tracking_ids": [tracking_id], "periodical_ids": [lonely_id]},
        )
        assert added.status_code == 200
        body = added.json()
        assert body["success"] is True
        assert body["added"] == 2
        assert body["errors"] is None
        assert body["stack"]["member_count"] == 2
        assert body["stack"]["slug"] == "reading-list"
        assert [cover["title"] for cover in body["stack"]["preview_covers"]] == [
            "National Geographic",
            "Lonely Planet",
        ]
        assert body["stack"]["preview_covers"][0]["periodical_id"] == geographic_id

        fetched = test_client.get("/api/stacks/reading-list")
        assert fetched.status_code == 200
        members = {member["type"]: member for member in fetched.json()["stack"]["members"]}
        assert set(members) == {"tracking", "periodical"}
        assert members["tracking"]["periodical_tracking_id"] == tracking_id
        assert members["tracking"]["title"] == "National Geographic"
        assert members["tracking"]["category"] == "Magazines"
        assert members["tracking"]["language"] == "English"
        assert members["tracking"]["library_count"] == 1
        assert members["tracking"]["cover_periodical_id"] == geographic_id
        assert members["periodical"]["periodical_id"] == lonely_id
        assert members["periodical"]["title"] == "Lonely Planet"
        assert members["periodical"]["category"] == "Travel"
        assert members["periodical"]["language"] == "English"
        assert members["periodical"]["issue_date"] == "2023-04-01T00:00:00+00:00"
        assert members["periodical"]["cover_periodical_id"] == lonely_id

        library = test_client.get("/api/stacks/reading-list/library")
        assert library.status_code == 200
        library_body = library.json()
        assert library_body["stack"]["slug"] == "reading-list"
        assert library_body["total"] == 2
        by_title = {item["title"]: item for item in library_body["periodicals"]}
        assert by_title["National Geographic"]["id"] == geographic_id
        assert by_title["National Geographic"]["tracking_id"] == tracking_id
        assert by_title["National Geographic"]["issue_count"] == 1
        assert by_title["National Geographic"]["issue_date"] == "2024-06-15"
        assert by_title["Lonely Planet"]["id"] == lonely_id
        assert by_title["Lonely Planet"]["issue_count"] == 1
        assert by_title["Lonely Planet"]["issue_date"] == "2023-04-01"

        listed = test_client.get("/api/stacks")
        reading = next(item for item in listed.json()["stacks"] if item["slug"] == "reading-list")
        assert reading["member_count"] == 2

        removed = test_client.delete(f"/api/stacks/reading-list/members/{members['periodical']['id']}")
        assert removed.status_code == 200
        assert removed.json() == {"success": True, "message": "Member removed from stack"}

        session = _session(test_db)
        remaining = session.query(StackMembership).all()
        assert len(remaining) == 1
        assert remaining[0].periodical_tracking_id == tracking_id
        assert remaining[0].periodical_id is None
        assert session.query(Periodical).count() == 2
        session.close()

        missing_member = test_client.delete(f"/api/stacks/reading-list/members/{members['periodical']['id']}")
        assert missing_member.status_code == 404
        assert missing_member.json()["detail"] == "Membership not found in this stack"

        again = test_client.post(
            "/api/stacks/reading-list/members",
            json={"tracking_ids": [tracking_id]},
        )
        assert again.status_code == 200
        assert again.json()["added"] == 0
        assert again.json()["errors"] == ["'National Geographic' is already in this stack"]

    def test_add_members_reports_missing_ids_and_other_stack(self, test_client, test_db):
        home = test_client.post("/api/stacks", json={"name": "Home"})
        travel = test_client.post("/api/stacks", json={"name": "Travel Shelf"})
        assert home.status_code == 200
        assert travel.status_code == 200

        lonely_id = _insert_periodical(
            test_db,
            title="Lonely Planet",
            file_path="/library/lonely-planet.pdf",
        )
        placed = test_client.post(
            "/api/stacks/travel-shelf/members",
            json={"periodical_ids": [lonely_id]},
        )
        assert placed.status_code == 200
        assert placed.json()["added"] == 1

        unknown = test_client.post(
            "/api/stacks/home/members",
            json={"tracking_ids": [99999], "periodical_ids": [lonely_id, 88888]},
        )
        assert unknown.status_code == 200
        assert unknown.json()["added"] == 0
        assert unknown.json()["stack"]["member_count"] == 0
        assert unknown.json()["errors"] == [
            "Tracking ID 99999 not found",
            "'Lonely Planet' is already in stack 'Travel Shelf'",
            "Periodical ID 88888 not found",
        ]

        noop = test_client.post("/api/stacks/home/members", json={})
        assert noop.status_code == 200
        assert noop.json()["added"] == 0
        assert noop.json()["errors"] is None

        session = _session(test_db)
        memberships = session.query(StackMembership).all()
        assert len(memberships) == 1
        assert memberships[0].periodical_id == lonely_id
        home_stack = session.query(Stack).filter(Stack.slug == "home").one()
        other_membership = session.query(StackMembership).filter(StackMembership.stack_id == home_stack.id).count()
        assert other_membership == 0
        travel_membership_id = memberships[0].id
        session.close()

        wrong_stack = test_client.delete(f"/api/stacks/home/members/{travel_membership_id}")
        assert wrong_stack.status_code == 404
        assert wrong_stack.json()["detail"] == "Membership not found in this stack"

        session = _session(test_db)
        assert session.query(StackMembership).count() == 1
        session.close()

    def test_delete_stack_removes_memberships_and_keeps_periodicals(self, test_client, test_db):
        created = test_client.post("/api/stacks", json={"name": "Short List"})
        assert created.status_code == 200
        periodical_id = _insert_periodical(test_db, file_path="/library/short-list.pdf", title="Monocle")
        added = test_client.post(
            "/api/stacks/short-list/members",
            json={"periodical_ids": [periodical_id]},
        )
        assert added.status_code == 200
        assert added.json()["added"] == 1

        deleted = test_client.delete("/api/stacks/short-list")
        assert deleted.status_code == 200
        assert deleted.json() == {"success": True, "message": "Stack 'Short List' deleted"}

        assert test_client.get("/api/stacks/short-list").status_code == 404
        remaining = test_client.get("/api/stacks")
        assert remaining.status_code == 200
        assert remaining.json()["stacks"] == []

        session = _session(test_db)
        assert session.query(Stack).count() == 0
        assert session.query(StackMembership).count() == 0
        kept = session.query(Periodical).one()
        assert kept.id == periodical_id
        assert kept.title == "Monocle"
        session.close()


class TestPeriodicalCrudRoutes:
    """List, get, delete, and count for library rows."""

    def test_list_empty(self, test_client):
        response = test_client.get("/api/periodicals")

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "periodicals": [],
            "total": 0,
            "skip": 0,
            "limit": 50,
        }

    def test_count_includes_every_issue(self, test_client, test_db):
        empty = test_client.get("/api/periodicals/stats/count")
        assert empty.status_code == 200
        assert empty.json() == {"total": 0}

        _insert_periodical(test_db, file_path="/library/one.pdf", title="One")
        _insert_periodical(test_db, file_path="/library/two.pdf", title="Two")

        counted = test_client.get("/api/periodicals/stats/count")
        assert counted.status_code == 200
        assert counted.json() == {"total": 2}

    def test_list_groups_tracked_issues_and_returns_fields(self, test_client, test_db):
        tracking_id = _insert_tracking(test_db, olid="OLATL", title="The Atlantic")
        session = _session(test_db)
        session.add(Stack(user_id=1, name="Favorites", slug="favorites", description="Kept titles"))
        session.commit()
        stack = session.query(Stack).filter(Stack.slug == "favorites").one()
        session.add(StackMembership(stack_id=stack.id, periodical_tracking_id=tracking_id))
        session.commit()
        stack_id = stack.id
        session.close()

        _insert_periodical(
            test_db,
            title="Atlantic Issue",
            file_path="/library/atlantic-2024-01.pdf",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
            tracking_id=tracking_id,
            content_hash="january-hash",
        )
        june_id = _insert_periodical(
            test_db,
            title="Atlantic Issue",
            file_path="/library/atlantic-2024-06.pdf",
            issue_date=datetime(2024, 6, 15, tzinfo=UTC),
            tracking_id=tracking_id,
            cover_path="/covers/atlantic-2024-06.jpg",
            content_hash="june-hash",
            extra_metadata={"category": "News"},
            derived_metadata={"source": "filename"},
            parsed_metadata={"raw": True},
        )
        wired_id = _insert_periodical(
            test_db,
            title="Wired",
            file_path="/library/wired-2023-03.pdf",
            issue_date=datetime(2023, 3, 1, tzinfo=UTC),
            content_hash="wired-hash",
        )

        response = test_client.get("/api/periodicals")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["total"] == 2
        assert body["skip"] == 0
        assert body["limit"] == 50
        assert [item["title"] for item in body["periodicals"]] == ["The Atlantic", "Wired"]

        atlantic = body["periodicals"][0]
        assert atlantic["id"] == june_id
        assert atlantic["language"] == "English"
        assert atlantic["issue_date"] == "2024-06-15"
        assert atlantic["file_path"] == "/library/atlantic-2024-06.pdf"
        assert atlantic["cover_path"] == "/covers/atlantic-2024-06.jpg"
        assert atlantic["content_hash"] == "june-hash"
        assert atlantic["tracking_id"] == tracking_id
        assert atlantic["metadata"] == {"category": "News"}
        assert atlantic["derived_metadata"] == {"source": "filename"}
        assert atlantic["issue_count"] == 2
        assert atlantic["stack_id"] == stack_id
        assert atlantic["stack_name"] == "Favorites"
        assert atlantic["stack_slug"] == "favorites"
        assert isinstance(atlantic["created_at"], str) and atlantic["created_at"]
        assert isinstance(atlantic["updated_at"], str) and atlantic["updated_at"]

        wired = body["periodicals"][1]
        assert wired["id"] == wired_id
        assert wired["title"] == "Wired"
        assert wired["issue_date"] == "2023-03-01"
        assert wired["issue_count"] == 1
        assert wired["tracking_id"] is None
        assert wired["stack_id"] is None
        assert wired["stack_name"] is None
        assert wired["stack_slug"] is None

        counted = test_client.get("/api/periodicals/stats/count")
        assert counted.json() == {"total": 3}

        page = test_client.get("/api/periodicals", params={"skip": 0, "limit": 1, "sort_by": "title"})
        assert page.status_code == 200
        assert page.json()["total"] == 2
        assert page.json()["skip"] == 0
        assert page.json()["limit"] == 1
        assert [item["title"] for item in page.json()["periodicals"]] == ["The Atlantic"]

        newest = test_client.get(
            "/api/periodicals",
            params={"sort_by": "issue_date", "sort_order": "desc"},
        )
        assert newest.status_code == 200
        assert [item["title"] for item in newest.json()["periodicals"]] == ["The Atlantic", "Wired"]
        assert newest.json()["periodicals"][0]["issue_date"] == "2024-06-15"

    def test_get_returns_json_fields(self, test_client, test_db):
        tracking_id = _insert_tracking(test_db, olid="OLGET", title="The Atlantic")
        periodical_id = _insert_periodical(
            test_db,
            title="Atlantic Issue",
            file_path="/library/atlantic-get.pdf",
            issue_date=datetime(2024, 6, 15, tzinfo=UTC),
            tracking_id=tracking_id,
            cover_path="/covers/atlantic.jpg",
            content_hash="abc123",
            category="Magazines",
            extra_metadata={"category": "News"},
            derived_metadata={"source": "filename"},
            parsed_metadata={"raw": True},
        )

        response = test_client.get(f"/api/periodicals/{periodical_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == periodical_id
        assert body["title"] == "Atlantic Issue"
        assert body["language"] == "English"
        assert body["category"] == "Magazines"
        assert body["issue_date"] == "2024-06-15T00:00:00+00:00"
        assert body["file_path"] == "/library/atlantic-get.pdf"
        assert body["cover_path"] == "/covers/atlantic.jpg"
        assert body["content_hash"] == "abc123"
        assert body["tracking_id"] == tracking_id
        assert body["metadata"] == {"category": "News"}
        assert body["extra_metadata"] == {"category": "News"}
        assert body["derived_metadata"] == {"source": "filename"}
        assert body["parsed_metadata"] == {"raw": True}
        assert isinstance(body["created_at"], str) and body["created_at"]
        assert isinstance(body["updated_at"], str) and body["updated_at"]

    def test_missing_periodical_get_and_delete_404(self, test_client, test_db):
        kept_id = _insert_periodical(test_db, file_path="/library/kept.pdf", title="Kept")

        missing_get = test_client.get("/api/periodicals/99999")
        assert missing_get.status_code == 404
        assert missing_get.json()["detail"] == "Magazine not found"

        missing_delete = test_client.delete("/api/periodicals/99999")
        assert missing_delete.status_code == 404
        assert missing_delete.json()["detail"] == "Magazine not found"

        session = _session(test_db)
        kept = session.query(Periodical).one()
        assert kept.id == kept_id
        assert kept.title == "Kept"
        session.close()
        assert test_client.get("/api/periodicals/stats/count").json() == {"total": 1}

    def test_delete_removes_row_and_keeps_file(self, test_client, test_db, tmp_path):
        pdf_path = tmp_path / "wired.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 not really")
        cover_path = tmp_path / "wired.jpg"
        cover_path.write_bytes(b"cover")
        periodical_id = _insert_periodical(
            test_db,
            title="Wired",
            file_path=str(pdf_path),
            cover_path=str(cover_path),
        )
        sibling_id = _insert_periodical(
            test_db,
            title="Wired",
            file_path=str(tmp_path / "wired-sibling.pdf"),
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
        )

        response = test_client.delete(f"/api/periodicals/{periodical_id}")

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "message": "Removed 'Wired' from library (files retained on disk)",
        }
        assert pdf_path.exists()
        assert cover_path.exists()

        session = _session(test_db)
        remaining = session.query(Periodical).all()
        assert [row.id for row in remaining] == [sibling_id]
        session.close()
        assert test_client.get("/api/periodicals/stats/count").json() == {"total": 1}
        assert test_client.get(f"/api/periodicals/{periodical_id}").status_code == 404

    def test_delete_all_issues_matches_title_and_language(self, test_client, test_db):
        june_id = _insert_periodical(
            test_db,
            title="Wired",
            language="English",
            file_path="/library/wired-june.pdf",
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
        )
        _insert_periodical(
            test_db,
            title="Wired",
            language="English",
            file_path="/library/wired-january.pdf",
            issue_date=datetime(2024, 1, 1, tzinfo=UTC),
        )
        french_id = _insert_periodical(
            test_db,
            title="Wired",
            language="French",
            file_path="/library/wired-french.pdf",
            issue_date=datetime(2024, 6, 1, tzinfo=UTC),
        )
        monocle_id = _insert_periodical(
            test_db,
            title="Monocle",
            language="English",
            file_path="/library/monocle.pdf",
        )

        response = test_client.delete(
            f"/api/periodicals/{june_id}",
            params={"delete_all_issues": True},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["message"] == ("Removed 2 issues of 'Wired' from library (files retained on disk)")

        session = _session(test_db)
        remaining = {(row.title, row.language, row.id) for row in session.query(Periodical).all()}
        session.close()
        assert remaining == {("Wired", "French", french_id), ("Monocle", "English", monocle_id)}
        assert test_client.get("/api/periodicals/stats/count").json() == {"total": 2}
        assert test_client.get(f"/api/periodicals/{june_id}").status_code == 404
        assert test_client.get(f"/api/periodicals/{french_id}").status_code == 200


class TestPeriodicalFileRoutes:
    """File routes that reject a missing file or the wrong type before rendering."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/periodicals/99999/pdf",
            "/api/periodicals/99999/pdf/metadata",
            "/api/periodicals/99999/pdf/page/0",
            "/api/periodicals/99999/pdf/page/0/thumbnail",
            "/api/periodicals/99999/epub/metadata",
            "/api/periodicals/99999/epub/chapter/0",
            "/api/periodicals/99999/epub/image/cover.jpg",
            "/api/periodicals/99999/comic/metadata",
            "/api/periodicals/99999/comic/page/0",
            "/api/periodicals/99999/comic/page/0/thumbnail",
        ],
    )
    def test_missing_periodical_returns_404(self, test_client, monkeypatch, path):
        monkeypatch.setattr(
            "web.routers.periodicals.files._render_in_process",
            _render_must_not_run,
        )

        response = test_client.get(path)

        assert response.status_code == 404
        assert response.json()["detail"] == "Magazine not found"

    @pytest.mark.parametrize(
        ("path_template", "filename", "create_file", "status_code", "detail"),
        [
            pytest.param(
                "/api/periodicals/{id}/pdf",
                "missing.pdf",
                False,
                404,
                "Periodical file not found",
                id="pdf-missing-file",
            ),
            pytest.param(
                "/api/periodicals/{id}/pdf/metadata",
                "missing.pdf",
                False,
                404,
                "Periodical file not found",
                id="pdf-metadata-missing-file",
            ),
            pytest.param(
                "/api/periodicals/{id}/epub/metadata",
                "missing.epub",
                False,
                404,
                "Periodical file not found",
                id="epub-metadata-missing-file",
            ),
            pytest.param(
                "/api/periodicals/{id}/comic/metadata",
                "missing.cbz",
                False,
                404,
                "Periodical file not found",
                id="comic-metadata-missing-file",
            ),
            pytest.param(
                "/api/periodicals/{id}/pdf/metadata",
                "issue.epub",
                True,
                400,
                "File is not a PDF",
                id="pdf-metadata-on-epub",
            ),
            pytest.param(
                "/api/periodicals/{id}/pdf/page/0",
                "issue.epub",
                True,
                400,
                "File is not a PDF",
                id="pdf-page-on-epub",
            ),
            pytest.param(
                "/api/periodicals/{id}/pdf/page/0/thumbnail",
                "issue.epub",
                True,
                400,
                "File is not a PDF",
                id="pdf-thumbnail-on-epub",
            ),
            pytest.param(
                "/api/periodicals/{id}/epub/metadata",
                "issue.pdf",
                True,
                400,
                "File is not an EPUB",
                id="epub-metadata-on-pdf",
            ),
            pytest.param(
                "/api/periodicals/{id}/epub/chapter/0",
                "issue.pdf",
                True,
                400,
                "File is not an EPUB",
                id="epub-chapter-on-pdf",
            ),
            pytest.param(
                "/api/periodicals/{id}/epub/image/cover.jpg",
                "issue.pdf",
                True,
                400,
                "File is not an EPUB",
                id="epub-image-on-pdf",
            ),
            pytest.param(
                "/api/periodicals/{id}/comic/metadata",
                "issue.pdf",
                True,
                400,
                "File is not a comic (CBZ/CBR)",
                id="comic-metadata-on-pdf",
            ),
            pytest.param(
                "/api/periodicals/{id}/comic/page/0",
                "issue.pdf",
                True,
                400,
                "File is not a comic (CBZ/CBR)",
                id="comic-page-on-pdf",
            ),
            pytest.param(
                "/api/periodicals/{id}/comic/page/0/thumbnail",
                "issue.pdf",
                True,
                400,
                "File is not a comic (CBZ/CBR)",
                id="comic-thumbnail-on-pdf",
            ),
        ],
    )
    def test_missing_file_or_wrong_type(
        self,
        test_client,
        test_db,
        tmp_path,
        monkeypatch,
        path_template,
        filename,
        create_file,
        status_code,
        detail,
    ):
        monkeypatch.setattr(
            "web.routers.periodicals.files._render_in_process",
            _render_must_not_run,
        )
        stored_path = tmp_path / filename
        if create_file:
            stored_path.write_bytes(b"not a rendered document")
        periodical_id = _insert_periodical(
            test_db,
            title=filename,
            file_path=str(stored_path),
        )

        response = test_client.get(path_template.format(id=periodical_id))

        assert response.status_code == status_code
        assert response.json()["detail"] == detail

    def test_move_to_tracking_404_for_missing_records(self, test_client, test_db):
        missing_issue = test_client.post(
            "/api/periodicals/99999/move-to-tracking",
            params={"target_tracking_id": 1},
        )
        assert missing_issue.status_code == 404
        assert missing_issue.json()["detail"] == "Magazine not found"

        periodical_id = _insert_periodical(test_db, file_path="/library/needs-a-home.pdf", title="Orphan")
        missing_tracking = test_client.post(
            f"/api/periodicals/{periodical_id}/move-to-tracking",
            params={"target_tracking_id": 99999},
        )
        assert missing_tracking.status_code == 404
        assert missing_tracking.json()["detail"] == "Target tracking record not found"

        missing_query = test_client.post(f"/api/periodicals/{periodical_id}/move-to-tracking")
        assert missing_query.status_code == 422

        session = _session(test_db)
        row = session.query(Periodical).one()
        assert row.id == periodical_id
        assert row.tracking_id is None
        assert row.title == "Orphan"
        session.close()


async def _render_must_not_run(*_args, **_kwargs):
    raise AssertionError("PDF render pool should not run for this request")
