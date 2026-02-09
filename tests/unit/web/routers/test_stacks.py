"""
Test suite for stacks feature - models, slug generation, and router helpers
"""

import tempfile
from datetime import datetime, UTC
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models.database import Base, Stack, StackMembership, PeriodicalTracking, Periodical
from web.routers.stacks import _generate_slug, _ensure_unique_slug


@pytest.fixture
def test_db():
    """Create file-based test database for thread-safe testing"""
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


class TestGenerateSlug:
    """Test slug generation from stack names"""

    def test_simple_name(self):
        """Test simple lowercase name"""
        assert _generate_slug("Science") == "science"

    def test_multi_word(self):
        """Test multi-word name becomes hyphenated"""
        assert _generate_slug("Science Magazines") == "science-magazines"

    def test_special_characters_removed(self):
        """Test special characters are stripped"""
        assert _generate_slug("Sci/Fi & Fantasy!") == "scifi-fantasy"

    def test_multiple_spaces_collapsed(self):
        """Test multiple spaces become single hyphens"""
        assert _generate_slug("My   Great   Stack") == "my-great-stack"

    def test_leading_trailing_whitespace(self):
        """Test leading/trailing whitespace is stripped"""
        assert _generate_slug("  padded  ") == "padded"

    def test_underscores_become_hyphens(self):
        """Test underscores are converted to hyphens"""
        assert _generate_slug("my_stack_name") == "my-stack-name"

    def test_multiple_hyphens_collapsed(self):
        """Test consecutive hyphens are collapsed"""
        assert _generate_slug("a---b---c") == "a-b-c"

    def test_empty_after_cleaning(self):
        """Test empty string after cleaning returns 'stack'"""
        assert _generate_slug("!!!") == "stack"

    def test_empty_string(self):
        """Test empty input returns 'stack'"""
        assert _generate_slug("") == "stack"

    def test_mixed_case(self):
        """Test mixed case is lowered"""
        assert _generate_slug("My AWESOME Stack") == "my-awesome-stack"

    def test_numeric_name(self):
        """Test numeric name passes through"""
        assert _generate_slug("2024 Issues") == "2024-issues"

    def test_hyphens_preserved(self):
        """Test existing hyphens pass through correctly"""
        assert _generate_slug("sci-fi magazines") == "sci-fi-magazines"


class TestEnsureUniqueSlug:
    """Test unique slug generation with database checks"""

    def test_unique_slug_unchanged(self, test_db):
        """Test unique slug is returned as-is"""
        _, session_factory = test_db
        db = session_factory()
        result = _ensure_unique_slug(db, "my-stack")
        assert result == "my-stack"
        db.close()

    def test_duplicate_slug_gets_suffix(self, test_db):
        """Test duplicate slug gets numeric suffix"""
        _, session_factory = test_db
        db = session_factory()

        # Create an existing stack with the slug
        stack = Stack(name="My Stack", slug="my-stack")
        db.add(stack)
        db.commit()

        result = _ensure_unique_slug(db, "my-stack")
        assert result == "my-stack-1"
        db.close()

    def test_multiple_duplicates_increment(self, test_db):
        """Test multiple duplicates increment the suffix"""
        _, session_factory = test_db
        db = session_factory()

        # Create stacks with slug and slug-1
        db.add(Stack(name="My Stack", slug="my-stack"))
        db.add(Stack(name="My Stack 1", slug="my-stack-1"))
        db.commit()

        result = _ensure_unique_slug(db, "my-stack")
        assert result == "my-stack-2"
        db.close()

    def test_exclude_id_allows_same_slug(self, test_db):
        """Test exclude_id allows the same slug for updates"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="My Stack", slug="my-stack")
        db.add(stack)
        db.commit()

        # When updating the same stack, its own slug should be valid
        result = _ensure_unique_slug(db, "my-stack", exclude_id=stack.id)
        assert result == "my-stack"
        db.close()


class TestStackModel:
    """Test Stack database model"""

    def test_create_stack(self, test_db):
        """Test creating a stack"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Science Magazines", slug="science-magazines", description="All science stuff")
        db.add(stack)
        db.commit()

        retrieved = db.query(Stack).filter_by(slug="science-magazines").first()
        assert retrieved is not None
        assert retrieved.name == "Science Magazines"
        assert retrieved.description == "All science stuff"
        assert retrieved.sort_order == 0
        assert retrieved.created_at is not None
        db.close()

    def test_stack_unique_name(self, test_db):
        """Test that stack names must be unique"""
        _, session_factory = test_db
        db = session_factory()

        db.add(Stack(name="Unique", slug="unique"))
        db.commit()

        db.add(Stack(name="Unique", slug="unique-2"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_stack_unique_slug(self, test_db):
        """Test that stack slugs must be unique"""
        _, session_factory = test_db
        db = session_factory()

        db.add(Stack(name="Stack A", slug="same-slug"))
        db.commit()

        db.add(Stack(name="Stack B", slug="same-slug"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_stack_to_dict(self, test_db):
        """Test stack serialization"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Test", slug="test", description="desc", sort_order=5)
        db.add(stack)
        db.commit()

        d = stack.to_dict()
        assert d["name"] == "Test"
        assert d["slug"] == "test"
        assert d["description"] == "desc"
        assert d["sort_order"] == 5
        assert d["id"] is not None
        assert d["created_at"] is not None
        db.close()

    def test_stack_default_values(self, test_db):
        """Test stack default field values"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Defaults", slug="defaults")
        db.add(stack)
        db.commit()

        assert stack.sort_order == 0
        assert stack.description is None
        assert stack.cover_override_path is None
        db.close()


class TestStackMembershipModel:
    """Test StackMembership database model"""

    def test_create_tracking_membership(self, test_db):
        """Test adding a tracking item to a stack"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Stack", slug="stack")
        db.add(stack)
        db.commit()

        tracking = PeriodicalTracking(olid="OL1W", title="Mag A")
        db.add(tracking)
        db.commit()

        membership = StackMembership(stack_id=stack.id, periodical_tracking_id=tracking.id)
        db.add(membership)
        db.commit()

        retrieved = db.query(StackMembership).filter_by(stack_id=stack.id).first()
        assert retrieved is not None
        assert retrieved.periodical_tracking_id == tracking.id
        assert retrieved.periodical_id is None
        assert retrieved.added_at is not None
        db.close()

    def test_create_periodical_membership(self, test_db):
        """Test adding a periodical (library item) to a stack"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Stack", slug="stack")
        db.add(stack)
        db.commit()

        periodical = Periodical(title="Mag B", file_path="/tmp/test.pdf", issue_date=datetime.now(UTC))
        db.add(periodical)
        db.commit()

        membership = StackMembership(stack_id=stack.id, periodical_id=periodical.id)
        db.add(membership)
        db.commit()

        retrieved = db.query(StackMembership).filter_by(periodical_id=periodical.id).first()
        assert retrieved is not None
        assert retrieved.stack_id == stack.id
        db.close()

    def test_one_stack_per_tracking_item(self, test_db):
        """Test that a tracking item can only belong to one stack (unique constraint)"""
        _, session_factory = test_db
        db = session_factory()

        stack1 = Stack(name="Stack 1", slug="stack-1")
        stack2 = Stack(name="Stack 2", slug="stack-2")
        db.add_all([stack1, stack2])
        db.commit()

        tracking = PeriodicalTracking(olid="OL2W", title="Mag C")
        db.add(tracking)
        db.commit()

        # First membership should succeed
        db.add(StackMembership(stack_id=stack1.id, periodical_tracking_id=tracking.id))
        db.commit()

        # Second membership to a different stack should fail (unique constraint)
        db.add(StackMembership(stack_id=stack2.id, periodical_tracking_id=tracking.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_one_stack_per_periodical(self, test_db):
        """Test that a periodical can only belong to one stack (unique constraint)"""
        _, session_factory = test_db
        db = session_factory()

        stack1 = Stack(name="Stack A", slug="stack-a")
        stack2 = Stack(name="Stack B", slug="stack-b")
        db.add_all([stack1, stack2])
        db.commit()

        periodical = Periodical(title="Mag D", file_path="/tmp/test2.pdf", issue_date=datetime.now(UTC))
        db.add(periodical)
        db.commit()

        db.add(StackMembership(stack_id=stack1.id, periodical_id=periodical.id))
        db.commit()

        db.add(StackMembership(stack_id=stack2.id, periodical_id=periodical.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.close()

    def test_multiple_members_in_same_stack(self, test_db):
        """Test that a stack can have multiple distinct members"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Multi", slug="multi")
        db.add(stack)
        db.commit()

        t1 = PeriodicalTracking(olid="OL3W", title="Mag E")
        t2 = PeriodicalTracking(olid="OL4W", title="Mag F")
        db.add_all([t1, t2])
        db.commit()

        db.add(StackMembership(stack_id=stack.id, periodical_tracking_id=t1.id))
        db.add(StackMembership(stack_id=stack.id, periodical_tracking_id=t2.id))
        db.commit()

        members = db.query(StackMembership).filter_by(stack_id=stack.id).all()
        assert len(members) == 2
        db.close()

    def test_membership_to_dict(self, test_db):
        """Test membership serialization"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Dict Test", slug="dict-test")
        db.add(stack)
        db.commit()

        tracking = PeriodicalTracking(olid="OL5W", title="Mag G")
        db.add(tracking)
        db.commit()

        membership = StackMembership(stack_id=stack.id, periodical_tracking_id=tracking.id)
        db.add(membership)
        db.commit()

        d = membership.to_dict()
        assert d["stack_id"] == stack.id
        assert d["periodical_tracking_id"] == tracking.id
        assert d["periodical_id"] is None
        assert d["added_at"] is not None
        db.close()

    def test_delete_stack_cascades_check(self, test_db):
        """Test that deleting a stack allows cleanup of memberships"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(name="Deletable", slug="deletable")
        db.add(stack)
        db.commit()

        tracking = PeriodicalTracking(olid="OL6W", title="Mag H")
        db.add(tracking)
        db.commit()

        db.add(StackMembership(stack_id=stack.id, periodical_tracking_id=tracking.id))
        db.commit()

        # Delete memberships first, then stack (as the router does)
        db.query(StackMembership).filter_by(stack_id=stack.id).delete()
        db.query(Stack).filter_by(id=stack.id).delete()
        db.commit()

        assert db.query(Stack).filter_by(slug="deletable").first() is None
        assert db.query(StackMembership).filter_by(stack_id=stack.id).count() == 0
        db.close()
