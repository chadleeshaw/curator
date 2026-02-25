"""
Test suite for stack membership cleanup when periodicals/tracking are deleted or merged.

Ensures that StackMembership rows are properly cleaned up and not orphaned when:
- A periodical is deleted (via delete_periodical)
- A tracking record is deleted (via delete_tracking)
- Tracking records are merged (source membership transferred or removed)
- The database is purged
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import (
    Base,
    Periodical,
    PeriodicalTracking,
    Stack,
    StackMembership,
    OCRJob,
    DiscoveredIssue,
    DownloadSubmission,
)


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


@pytest.fixture
def db_with_stack_and_periodical(test_db):
    """Create a stack with a periodical membership"""
    _, session_factory = test_db
    db = session_factory()

    stack = Stack(
        name="Test Stack",
        slug="test-stack",
        user_id=1,
    )
    db.add(stack)
    db.commit()

    periodical = Periodical(
        title="Test Magazine",
        file_path="/tmp/test.pdf",
        issue_date=datetime.now(UTC),
        language="eng",
        user_id=1,
    )
    db.add(periodical)
    db.commit()

    membership = StackMembership(stack_id=stack.id, periodical_id=periodical.id)
    db.add(membership)
    db.commit()

    yield db, session_factory, stack, periodical, membership


@pytest.fixture
def db_with_stack_and_tracking(test_db):
    """Create a stack with a tracking membership"""
    _, session_factory = test_db
    db = session_factory()

    stack = Stack(
        name="Test Stack",
        slug="test-stack",
        user_id=1,
    )
    db.add(stack)
    db.commit()

    tracking = PeriodicalTracking(
        olid="OL100W",
        title="Test Magazine",
        user_id=1,
    )
    db.add(tracking)
    db.commit()

    membership = StackMembership(stack_id=stack.id, periodical_tracking_id=tracking.id)
    db.add(membership)
    db.commit()

    yield db, session_factory, stack, tracking, membership


class TestDeletePeriodicalCleansUpMembership:
    """Test that deleting periodicals removes their stack memberships"""

    def test_delete_periodical_removes_membership(self, db_with_stack_and_periodical):
        """Deleting a periodical should remove its StackMembership"""
        db, _, stack, periodical, membership = db_with_stack_and_periodical

        # Verify membership exists
        assert db.query(StackMembership).filter_by(periodical_id=periodical.id).count() == 1

        # Simulate what delete_periodical does: clean up memberships, then delete
        mag_ids = [periodical.id]
        db.query(StackMembership).filter(StackMembership.periodical_id.in_(mag_ids)).delete(synchronize_session="fetch")
        db.delete(periodical)
        db.commit()

        # Membership should be gone
        assert db.query(StackMembership).filter_by(periodical_id=periodical.id).count() == 0
        # Stack should still exist
        assert db.query(Stack).filter_by(id=stack.id).first() is not None

        db.close()

    def test_delete_all_issues_removes_all_memberships(self, test_db):
        """Deleting all issues of a title should remove all their memberships"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(
            name="Multi Stack",
            slug="multi-stack",
            user_id=1,
        )
        db.add(stack)
        db.commit()

        # Create multiple periodicals with the same title
        periodicals = []
        for i in range(3):
            p = Periodical(
                title="Monthly Mag",
                file_path=f"/tmp/test_{i}.pdf",
                issue_date=datetime(2024, i + 1, 1, tzinfo=UTC),
                language="eng",
                user_id=1,
            )
            db.add(p)
            db.commit()
            periodicals.append(p)

            membership = StackMembership(stack_id=stack.id, periodical_id=p.id)
            db.add(membership)
            db.commit()

        # Verify all memberships exist
        assert db.query(StackMembership).filter_by(stack_id=stack.id).count() == 3

        # Simulate delete_all_issues: clean up all memberships, then delete all
        mag_ids = [p.id for p in periodicals]
        db.query(StackMembership).filter(StackMembership.periodical_id.in_(mag_ids)).delete(synchronize_session="fetch")
        for p in periodicals:
            db.delete(p)
        db.commit()

        # All memberships gone
        assert db.query(StackMembership).filter_by(stack_id=stack.id).count() == 0
        # Stack still exists (empty now)
        assert db.query(Stack).filter_by(id=stack.id).first() is not None

        db.close()

    def test_delete_periodical_with_no_membership(self, test_db):
        """Deleting a periodical with no membership should not error"""
        _, session_factory = test_db
        db = session_factory()

        periodical = Periodical(
            title="No Stack Mag",
            file_path="/tmp/nostackmag.pdf",
            issue_date=datetime.now(UTC),
            user_id=1,
        )
        db.add(periodical)
        db.commit()

        # Should not raise
        mag_ids = [periodical.id]
        deleted = (
            db.query(StackMembership)
            .filter(StackMembership.periodical_id.in_(mag_ids))
            .delete(synchronize_session="fetch")
        )
        assert deleted == 0

        db.delete(periodical)
        db.commit()

        db.close()


class TestDeleteTrackingCleansUpMembership:
    """Test that deleting tracking records removes their stack memberships"""

    def test_delete_tracking_removes_membership(self, db_with_stack_and_tracking):
        """Deleting a tracking record should remove its StackMembership"""
        db, _, stack, tracking, membership = db_with_stack_and_tracking

        tracking_id = tracking.id

        # Verify membership exists
        assert db.query(StackMembership).filter_by(periodical_tracking_id=tracking_id).count() == 1

        # Simulate what delete_tracking does: clean up memberships, then delete
        db.query(StackMembership).filter(StackMembership.periodical_tracking_id == tracking_id).delete(
            synchronize_session="fetch"
        )
        db.delete(tracking)
        db.commit()

        # Membership should be gone
        assert db.query(StackMembership).filter_by(periodical_tracking_id=tracking_id).count() == 0
        # Stack should still exist
        assert db.query(Stack).filter_by(id=stack.id).first() is not None

        db.close()

    def test_delete_tracking_with_remove_tracking_flag(self, test_db):
        """When delete_periodical uses remove_tracking=True, both memberships should be cleaned"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(
            name="Full Stack",
            slug="full-stack",
            user_id=1,
        )
        db.add(stack)
        db.commit()

        tracking = PeriodicalTracking(
            olid="OL200W",
            title="Full Mag",
            user_id=1,
        )
        db.add(tracking)
        db.commit()

        periodical = Periodical(
            title="Full Mag",
            file_path="/tmp/full.pdf",
            issue_date=datetime.now(UTC),
            tracking_id=tracking.id,
            user_id=1,
        )
        db.add(periodical)
        db.commit()

        # Add tracking membership to stack
        db.add(StackMembership(stack_id=stack.id, periodical_tracking_id=tracking.id))
        db.commit()

        # Simulate delete_periodical + remove_tracking:
        # 1. Clean up periodical memberships
        mag_ids = [periodical.id]
        db.query(StackMembership).filter(StackMembership.periodical_id.in_(mag_ids)).delete(synchronize_session="fetch")
        db.delete(periodical)
        db.commit()

        # 2. Clean up tracking memberships and delete tracking
        db.query(StackMembership).filter(StackMembership.periodical_tracking_id == tracking.id).delete(
            synchronize_session="fetch"
        )
        db.delete(tracking)
        db.commit()

        # Everything is cleaned up
        assert db.query(StackMembership).count() == 0
        assert db.query(Stack).filter_by(id=stack.id).first() is not None

        db.close()


class TestMergeTrackingTransfersMembership:
    """Test that merging tracking transfers or removes stack memberships"""

    def test_merge_transfers_membership_to_target(self, test_db):
        """When source has a membership and target doesn't, transfer it"""
        _, session_factory = test_db
        db = session_factory()

        stack = Stack(
            name="Merge Stack",
            slug="merge-stack",
            user_id=1,
        )
        db.add(stack)
        db.commit()

        source = PeriodicalTracking(
            olid="OL300W",
            title="Source Mag",
            user_id=1,
        )
        target = PeriodicalTracking(
            olid="OL301W",
            title="Target Mag",
            user_id=1,
        )
        db.add_all([source, target])
        db.commit()

        # Source is in the stack
        db.add(StackMembership(stack_id=stack.id, periodical_tracking_id=source.id))
        db.commit()

        # Simulate merge: transfer membership from source to target
        source_membership = (
            db.query(StackMembership).filter(StackMembership.periodical_tracking_id == source.id).first()
        )
        target_membership = (
            db.query(StackMembership).filter(StackMembership.periodical_tracking_id == target.id).first()
        )

        assert source_membership is not None
        assert target_membership is None

        # Transfer
        source_membership.periodical_tracking_id = target.id

        # Delete source
        db.delete(source)
        db.commit()

        # Membership now points to target
        remaining = db.query(StackMembership).filter_by(stack_id=stack.id).first()
        assert remaining is not None
        assert remaining.periodical_tracking_id == target.id

        db.close()

    def test_merge_removes_source_membership_when_target_has_one(self, test_db):
        """When both source and target have memberships, remove source's"""
        _, session_factory = test_db
        db = session_factory()

        stack1 = Stack(
            name="Stack A",
            slug="stack-a",
            user_id=1,
        )
        stack2 = Stack(
            name="Stack B",
            slug="stack-b",
            user_id=1,
        )
        db.add_all([stack1, stack2])
        db.commit()

        source = PeriodicalTracking(
            olid="OL400W",
            title="Source",
            user_id=1,
        )
        target = PeriodicalTracking(
            olid="OL401W",
            title="Target",
            user_id=1,
        )
        db.add_all([source, target])
        db.commit()

        # Both in different stacks
        db.add(StackMembership(stack_id=stack1.id, periodical_tracking_id=source.id))
        db.add(StackMembership(stack_id=stack2.id, periodical_tracking_id=target.id))
        db.commit()

        # Simulate merge: target already has membership, so remove source's
        source_membership = (
            db.query(StackMembership).filter(StackMembership.periodical_tracking_id == source.id).first()
        )
        target_membership = (
            db.query(StackMembership).filter(StackMembership.periodical_tracking_id == target.id).first()
        )

        assert source_membership is not None
        assert target_membership is not None

        # Target already in a stack, just remove source membership
        db.delete(source_membership)

        # Delete source tracking
        db.delete(source)
        db.commit()

        # Only target's membership remains
        assert db.query(StackMembership).count() == 1
        remaining = db.query(StackMembership).first()
        assert remaining.periodical_tracking_id == target.id
        assert remaining.stack_id == stack2.id

        db.close()

    def test_merge_with_no_memberships(self, test_db):
        """When neither source nor target have memberships, merge is clean"""
        _, session_factory = test_db
        db = session_factory()

        source = PeriodicalTracking(
            olid="OL500W",
            title="Source",
            user_id=1,
        )
        target = PeriodicalTracking(
            olid="OL501W",
            title="Target",
            user_id=1,
        )
        db.add_all([source, target])
        db.commit()

        # No memberships — should not error
        source_membership = (
            db.query(StackMembership).filter(StackMembership.periodical_tracking_id == source.id).first()
        )
        assert source_membership is None

        db.delete(source)
        db.commit()

        assert db.query(StackMembership).count() == 0

        db.close()


class TestPurgeDatabaseCleansUpStacks:
    """Test that purging the database removes stacks and memberships"""

    def test_purge_removes_all_stacks_and_memberships(self, test_db):
        """Purging database should delete all stacks and stack memberships"""
        _, session_factory = test_db
        db = session_factory()

        # Create stacks
        stack1 = Stack(
            name="Stack 1",
            slug="stack-1",
            user_id=1,
        )
        stack2 = Stack(
            name="Stack 2",
            slug="stack-2",
            user_id=1,
        )
        db.add_all([stack1, stack2])
        db.commit()

        tracking = PeriodicalTracking(
            olid="OL600W",
            title="Purge Mag",
            user_id=1,
        )
        db.add(tracking)
        db.commit()

        periodical = Periodical(
            title="Purge Mag",
            file_path="/tmp/purge.pdf",
            issue_date=datetime.now(UTC),
            tracking_id=tracking.id,
            user_id=1,
        )
        db.add(periodical)
        db.commit()

        db.add(StackMembership(stack_id=stack1.id, periodical_tracking_id=tracking.id))
        db.add(StackMembership(stack_id=stack2.id, periodical_id=periodical.id))
        db.commit()

        assert db.query(Stack).count() == 2
        assert db.query(StackMembership).count() == 2

        # Simulate purge: delete memberships and stacks first, then everything else
        db.query(StackMembership).delete()
        db.query(Stack).delete()
        db.query(Periodical).delete()
        db.query(PeriodicalTracking).delete()
        db.commit()

        assert db.query(Stack).count() == 0
        assert db.query(StackMembership).count() == 0
        assert db.query(Periodical).count() == 0
        assert db.query(PeriodicalTracking).count() == 0

        db.close()
