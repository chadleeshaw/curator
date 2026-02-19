"""
Stacks router - CRUD operations for user-created periodical groupings
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import Periodical, PeriodicalTracking, Stack, StackMembership
from web.utils.responses import success_response


class CreateStackRequest(BaseModel):
    """Request body for creating a stack"""

    name: str
    description: Optional[str] = None
    categories: Optional[List[str]] = None


class UpdateStackRequest(BaseModel):
    """Request body for updating a stack"""

    name: Optional[str] = None
    description: Optional[str] = None
    categories: Optional[List[str]] = None
    sort_order: Optional[int] = None


router = APIRouter(prefix="/api", tags=["stacks"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None


def set_dependencies(session_factory: Callable) -> None:
    """Set dependencies from main app"""
    global _session_factory
    _session_factory = session_factory


def _generate_slug(name: str) -> str:
    """
    Generate a URL-safe slug from a stack name.

    Args:
        name: The stack name to slugify

    Returns:
        URL-safe slug string
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "stack"


def _ensure_unique_slug(db, slug: str, exclude_id: Optional[int] = None) -> str:
    """
    Ensure slug is unique by appending a numeric suffix if needed.

    Args:
        db: Database session
        slug: Base slug to check
        exclude_id: Stack ID to exclude from uniqueness check (for updates)

    Returns:
        Unique slug string
    """
    original_slug = slug
    counter = 1
    while True:
        query = db.query(Stack).filter(Stack.slug == slug)
        if exclude_id is not None:
            query = query.filter(Stack.id != exclude_id)
        if not query.first():
            return slug
        slug = f"{original_slug}-{counter}"
        counter += 1


def _get_stack_preview_covers(db, stack_id: int, limit: int = 4) -> List[Dict[str, Any]]:
    """
    Get preview cover data for a stack's first N members.

    Args:
        db: Database session
        stack_id: Stack ID
        limit: Maximum number of preview covers to return

    Returns:
        List of dicts with periodical_id and cover info for preview display
    """
    # Get tracking-based members first (they have the most items)
    tracking_members = (
        db.query(StackMembership)
        .filter(
            StackMembership.stack_id == stack_id,
            StackMembership.periodical_tracking_id.isnot(None),
        )
        .order_by(StackMembership.added_at.asc())
        .all()
    )

    preview_covers = []
    for member in tracking_members:
        if len(preview_covers) >= limit:
            break
        # Get the latest periodical with a cover for this tracking
        periodical = (
            db.query(Periodical)
            .filter(
                Periodical.tracking_id == member.periodical_tracking_id,
                Periodical.cover_path.isnot(None),
            )
            .order_by(Periodical.issue_date.desc())
            .first()
        )
        if periodical:
            preview_covers.append({"periodical_id": periodical.id, "title": periodical.title})

    # Also check direct periodical members
    if len(preview_covers) < limit:
        direct_members = (
            db.query(StackMembership)
            .filter(
                StackMembership.stack_id == stack_id,
                StackMembership.periodical_id.isnot(None),
            )
            .order_by(StackMembership.added_at.asc())
            .all()
        )

        for member in direct_members:
            if len(preview_covers) >= limit:
                break
            periodical = db.query(Periodical).filter(Periodical.id == member.periodical_id).first()
            if periodical and periodical.cover_path:
                preview_covers.append({"periodical_id": periodical.id, "title": periodical.title})

    return preview_covers


def _get_stack_member_count(db, stack_id: int) -> int:
    """Get total member count for a stack."""
    return db.query(StackMembership).filter(StackMembership.stack_id == stack_id).count()


@router.get("/stacks")
@handle_api_errors("List stacks", logger)
async def list_stacks() -> Dict[str, Any]:
    """
    List all stacks with member counts and preview covers.

    Returns:
        List of stacks with metadata for display
    """

    def operation(db):
        stacks = db.query(Stack).order_by(Stack.sort_order.asc(), Stack.name.asc()).all()

        stack_list = []
        for stack in stacks:
            stack_dict = stack.to_dict()
            stack_dict["member_count"] = _get_stack_member_count(db, stack.id)
            stack_dict["preview_covers"] = _get_stack_preview_covers(db, stack.id)
            stack_list.append(stack_dict)

        return success_response(stacks=stack_list, total=len(stack_list))

    return await with_db_session(_session_factory, operation)


@router.post("/stacks")
@handle_api_errors("Create stack", logger)
async def create_stack(
    body: CreateStackRequest,
) -> Dict[str, Any]:
    """
    Create a new stack.

    Args:
        body: Stack creation data (name, description, categories)

    Returns:
        Created stack data
    """

    def operation(db):
        name = body.name
        description = body.description
        categories = body.categories
        # Check for duplicate name
        existing = db.query(Stack).filter(Stack.name == name.strip()).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"A stack named '{name}' already exists")

        slug = _generate_slug(name)
        slug = _ensure_unique_slug(db, slug)

        # Get next sort order
        max_order = db.query(Stack.sort_order).order_by(Stack.sort_order.desc()).first()
        next_order = (max_order[0] + 1) if max_order and max_order[0] is not None else 0

        stack = Stack(
            name=name.strip(),
            slug=slug,
            description=description.strip() if description else None,
            categories=categories if categories else None,
            sort_order=next_order,
        )
        db.add(stack)
        db.commit()

        stack_dict = stack.to_dict()
        stack_dict["member_count"] = 0
        stack_dict["preview_covers"] = []

        return success_response(stack=stack_dict)

    return await with_db_session(_session_factory, operation)


@router.get("/stacks/{slug}")
@handle_api_errors("Get stack details", logger)
async def get_stack(slug: str) -> Dict[str, Any]:
    """
    Get stack details with full member list.

    Args:
        slug: Stack URL slug

    Returns:
        Stack data with members
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        stack_dict = stack.to_dict()
        stack_dict["member_count"] = _get_stack_member_count(db, stack.id)
        stack_dict["preview_covers"] = _get_stack_preview_covers(db, stack.id)

        # Get all members with their details
        memberships = (
            db.query(StackMembership)
            .filter(StackMembership.stack_id == stack.id)
            .order_by(StackMembership.added_at.asc())
            .all()
        )

        members = []
        for m in memberships:
            member_data = m.to_dict()
            if m.periodical_tracking_id:
                tracking = (
                    db.query(PeriodicalTracking).filter(PeriodicalTracking.id == m.periodical_tracking_id).first()
                )
                if tracking:
                    member_data["title"] = tracking.title
                    member_data["category"] = tracking.category
                    member_data["language"] = tracking.language
                    member_data["type"] = "tracking"
                    # Get library count and latest cover for this tracking
                    library_count = db.query(Periodical).filter(Periodical.tracking_id == tracking.id).count()
                    member_data["library_count"] = library_count
                    latest = (
                        db.query(Periodical)
                        .filter(Periodical.tracking_id == tracking.id, Periodical.cover_path.isnot(None))
                        .order_by(Periodical.issue_date.desc())
                        .first()
                    )
                    member_data["cover_periodical_id"] = latest.id if latest else None
            elif m.periodical_id:
                periodical = db.query(Periodical).filter(Periodical.id == m.periodical_id).first()
                if periodical:
                    member_data["title"] = periodical.title
                    member_data["category"] = (
                        periodical.extra_metadata.get("category") if periodical.extra_metadata else None
                    )
                    member_data["language"] = periodical.language
                    member_data["type"] = "periodical"
                    member_data["cover_periodical_id"] = periodical.id if periodical.cover_path else None
                    member_data["issue_date"] = periodical.issue_date.isoformat() if periodical.issue_date else None
            members.append(member_data)

        stack_dict["members"] = members

        return success_response(stack=stack_dict)

    return await with_db_session(_session_factory, operation)


@router.put("/stacks/{slug}")
@handle_api_errors("Update stack", logger)
async def update_stack(
    slug: str,
    body: UpdateStackRequest,
) -> Dict[str, Any]:
    """
    Update a stack's properties.

    Args:
        slug: Stack URL slug
        body: Stack update data (name, description, categories, sort_order)

    Returns:
        Updated stack data
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        if body.name is not None:
            stripped_name = body.name.strip()
            # Check for duplicate name (excluding current stack)
            existing = db.query(Stack).filter(Stack.name == stripped_name, Stack.id != stack.id).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"A stack named '{stripped_name}' already exists")
            stack.name = stripped_name
            stack.slug = _ensure_unique_slug(db, _generate_slug(stripped_name), exclude_id=stack.id)

        if body.description is not None:
            stack.description = body.description.strip() if body.description else None

        if body.categories is not None:
            stack.categories = body.categories if body.categories else None

        if body.sort_order is not None:
            stack.sort_order = body.sort_order

        db.commit()

        stack_dict = stack.to_dict()
        stack_dict["member_count"] = _get_stack_member_count(db, stack.id)
        stack_dict["preview_covers"] = _get_stack_preview_covers(db, stack.id)

        return success_response(stack=stack_dict)

    return await with_db_session(_session_factory, operation)


@router.delete("/stacks/{slug}")
@handle_api_errors("Delete stack", logger)
async def delete_stack(slug: str) -> Dict[str, Any]:
    """
    Delete a stack. Members become ungrouped (not deleted).

    Args:
        slug: Stack URL slug

    Returns:
        Success confirmation
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        # Delete all memberships first
        db.query(StackMembership).filter(StackMembership.stack_id == stack.id).delete()
        db.delete(stack)
        db.commit()

        return success_response(message=f"Stack '{stack.name}' deleted")

    return await with_db_session(_session_factory, operation)


class AddMembersRequest(BaseModel):
    """Request body for adding members to a stack"""

    tracking_ids: Optional[List[int]] = None
    periodical_ids: Optional[List[int]] = None


@router.post("/stacks/{slug}/members")
@handle_api_errors("Add stack members", logger)
async def add_members(
    slug: str,
    body: AddMembersRequest,
) -> Dict[str, Any]:
    """
    Add items to a stack.

    Args:
        slug: Stack URL slug
        tracking_ids: List of PeriodicalTracking IDs to add
        periodical_ids: List of Periodical IDs to add (for untracked items)

    Returns:
        Updated stack data with new member count
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        added = 0
        errors = []

        if body.tracking_ids:
            for tid in body.tracking_ids:
                # Check if tracking exists
                tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tid).first()
                if not tracking:
                    errors.append(f"Tracking ID {tid} not found")
                    continue

                # Check if already in a stack
                existing = db.query(StackMembership).filter(StackMembership.periodical_tracking_id == tid).first()
                if existing:
                    if existing.stack_id == stack.id:
                        errors.append(f"'{tracking.title}' is already in this stack")
                    else:
                        other_stack = db.query(Stack).filter(Stack.id == existing.stack_id).first()
                        errors.append(
                            f"'{tracking.title}' is already in stack '{other_stack.name if other_stack else 'unknown'}'"
                        )
                    continue

                membership = StackMembership(
                    stack_id=stack.id,
                    periodical_tracking_id=tid,
                )
                db.add(membership)
                added += 1

        if body.periodical_ids:
            for pid in body.periodical_ids:
                # Check if periodical exists
                periodical = db.query(Periodical).filter(Periodical.id == pid).first()
                if not periodical:
                    errors.append(f"Periodical ID {pid} not found")
                    continue

                # Check if already in a stack
                existing = db.query(StackMembership).filter(StackMembership.periodical_id == pid).first()
                if existing:
                    if existing.stack_id == stack.id:
                        errors.append(f"'{periodical.title}' is already in this stack")
                    else:
                        other_stack = db.query(Stack).filter(Stack.id == existing.stack_id).first()
                        errors.append(
                            f"'{periodical.title}' is already in stack '{other_stack.name if other_stack else 'unknown'}'"
                        )
                    continue

                membership = StackMembership(
                    stack_id=stack.id,
                    periodical_id=pid,
                )
                db.add(membership)
                added += 1

        db.commit()

        stack_dict = stack.to_dict()
        stack_dict["member_count"] = _get_stack_member_count(db, stack.id)
        stack_dict["preview_covers"] = _get_stack_preview_covers(db, stack.id)

        return success_response(
            stack=stack_dict,
            added=added,
            errors=errors if errors else None,
        )

    return await with_db_session(_session_factory, operation)


@router.delete("/stacks/{slug}/members/{membership_id}")
@handle_api_errors("Remove stack member", logger)
async def remove_member(slug: str, membership_id: int) -> Dict[str, Any]:
    """
    Remove an item from a stack.

    Args:
        slug: Stack URL slug
        membership_id: StackMembership ID to remove

    Returns:
        Success confirmation
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        membership = (
            db.query(StackMembership)
            .filter(StackMembership.id == membership_id, StackMembership.stack_id == stack.id)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Membership not found in this stack")

        db.delete(membership)
        db.commit()

        return success_response(message="Member removed from stack")

    return await with_db_session(_session_factory, operation)


@router.get("/stacks/{slug}/library")
@handle_api_errors("Get stack library items", logger)
async def get_stack_library(slug: str) -> Dict[str, Any]:
    """
    Get all library periodicals that belong to this stack (for the stack detail page).
    Returns periodicals grouped the same way as the main library endpoint.

    Args:
        slug: Stack URL slug

    Returns:
        List of periodicals in this stack
    """

    def operation(db):
        stack = db.query(Stack).filter(Stack.slug == slug).first()
        if not stack:
            raise HTTPException(status_code=404, detail=f"Stack '{slug}' not found")

        memberships = db.query(StackMembership).filter(StackMembership.stack_id == stack.id).all()

        periodicals_list = []
        for m in memberships:
            if m.periodical_tracking_id:
                # Get all periodicals for this tracking
                tracking = (
                    db.query(PeriodicalTracking).filter(PeriodicalTracking.id == m.periodical_tracking_id).first()
                )
                if not tracking:
                    continue
                latest = (
                    db.query(Periodical)
                    .filter(Periodical.tracking_id == tracking.id)
                    .order_by(Periodical.issue_date.desc())
                    .first()
                )
                if latest:
                    issue_count = db.query(Periodical).filter(Periodical.tracking_id == tracking.id).count()
                    periodicals_list.append(
                        {
                            "id": latest.id,
                            "title": tracking.title,
                            "language": latest.language or "English",
                            "issue_date": latest.issue_date.date().isoformat() if latest.issue_date else None,
                            "cover_path": latest.cover_path,
                            "tracking_id": tracking.id,
                            "issue_count": issue_count,
                            "metadata": latest.extra_metadata,
                        }
                    )
            elif m.periodical_id:
                p = db.query(Periodical).filter(Periodical.id == m.periodical_id).first()
                if p:
                    periodicals_list.append(
                        {
                            "id": p.id,
                            "title": p.title,
                            "language": p.language or "English",
                            "issue_date": p.issue_date.date().isoformat() if p.issue_date else None,
                            "cover_path": p.cover_path,
                            "tracking_id": p.tracking_id,
                            "issue_count": 1,
                            "metadata": p.extra_metadata,
                        }
                    )

        return success_response(
            stack=stack.to_dict(),
            periodicals=periodicals_list,
            total=len(periodicals_list),
        )

    return await with_db_session(_session_factory, operation)
