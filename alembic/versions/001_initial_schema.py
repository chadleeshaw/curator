"""Initial schema — full current database state.

This revision represents the complete schema as of the Alembic migration system
adoption. Existing databases that already have this schema are stamped at this
revision on first startup without re-running these DDL statements.

Revision ID: 001
Revises:
Create Date: 2026-02-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("username", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("api_token", sa.String(255), nullable=True, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "periodical_tracking",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("olid", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False, index=True),
        sa.Column("language", sa.String(50), nullable=True, index=True),
        sa.Column("country", sa.String(50), nullable=True, index=True),
        sa.Column("first_publish_year", sa.Integer(), nullable=True),
        sa.Column("total_editions_known", sa.Integer(), nullable=True, default=0),
        sa.Column("track_all_editions", sa.Boolean(), nullable=True, default=False),
        sa.Column("track_new_only", sa.Boolean(), nullable=True, default=False),
        sa.Column("selected_editions", sa.JSON(), nullable=True),
        sa.Column("selected_years", sa.JSON(), nullable=True),
        sa.Column("delete_from_client_on_completion", sa.Boolean(), nullable=True, default=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("download_category", sa.String(100), nullable=True),
        sa.Column("organization_pattern", sa.String(255), nullable=True),
        sa.Column("search_aliases", sa.String(512), nullable=True),
        sa.Column("periodical_metadata", sa.JSON(), nullable=True),
        sa.Column("last_metadata_update", sa.DateTime(), nullable=True),
        sa.Column("last_searched", sa.DateTime(), nullable=True, index=True),
        sa.Column("search_count", sa.Integer(), nullable=True, default=0),
        sa.Column("search_interval_hours", sa.Integer(), nullable=True, default=6),
        sa.Column("last_cache_match", sa.DateTime(), nullable=True, index=True),
        sa.Column("total_issues_discovered", sa.Integer(), nullable=True, default=0),
        sa.Column("last_discovery_count", sa.Integer(), nullable=True, default=0),
        sa.Column("last_discovery_date", sa.DateTime(), nullable=True),
        sa.Column("searches_without_new_issues", sa.Integer(), nullable=True, default=0),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "periodicals",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, index=True),
        sa.Column("language", sa.String(50), nullable=True, index=True),
        sa.Column("category", sa.String(100), nullable=True, index=True),
        sa.Column("issue_date", sa.DateTime(), nullable=False, index=True),
        sa.Column("file_path", sa.String(512), nullable=False, unique=True),
        sa.Column("cover_path", sa.String(512), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True, index=True),
        sa.Column("parsed_metadata", sa.JSON(), nullable=True),
        sa.Column("derived_metadata", sa.JSON(), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("tracking_id", sa.Integer(), sa.ForeignKey("periodical_tracking.id"), nullable=True, index=True),
    )

    op.create_table(
        "search_results",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("provider", sa.String(100), nullable=False, index=True),
        sa.Column("query", sa.String(255), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False, index=True),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("publication_date", sa.DateTime(), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("fuzzy_match_group_id", sa.String(255), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("periodical_id", sa.Integer(), sa.ForeignKey("periodicals.id"), nullable=True),
        sa.UniqueConstraint("fuzzy_match_group_id", "query", name="uq_search_cache_group_query"),
    )

    op.create_table(
        "download_submissions",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "tracking_id",
            sa.Integer(),
            sa.ForeignKey("periodical_tracking.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("search_result_id", sa.Integer(), sa.ForeignKey("search_results.id"), nullable=True, index=True),
        sa.Column("job_id", sa.String(255), nullable=True, index=True),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "PENDING", "DOWNLOADING", "COMPLETED", "FAILED", "SKIPPED", name="statusenum"),
            nullable=True,
        ),
        sa.Column("source_url", sa.String(512), nullable=False),
        sa.Column("result_title", sa.String(255), nullable=False),
        sa.Column("fuzzy_match_group", sa.String(255), nullable=True, index=True),
        sa.Column("client_name", sa.String(100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=True, default=0),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("extra_status", sa.String(512), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("periodical_id", sa.Integer(), sa.ForeignKey("periodicals.id"), nullable=False, index=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="ocr_statusenum"),
            nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=True, index=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=True, default=0),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("ocr_metadata", sa.JSON(), nullable=True),
        sa.Column("processing_time_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "discovered_issues",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "tracking_id",
            sa.Integer(),
            sa.ForeignKey("periodical_tracking.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False, index=True),
        sa.Column("normalized_title", sa.String(255), nullable=False, index=True),
        sa.Column("fuzzy_match_group", sa.String(255), nullable=False, index=True),
        sa.Column("issue_date", sa.DateTime(), nullable=True, index=True),
        sa.Column("issue_number", sa.String(50), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True, index=True),
        sa.Column("month", sa.Integer(), nullable=True, index=True),
        sa.Column("language", sa.String(50), nullable=True, index=True),
        sa.Column("country", sa.String(50), nullable=True, index=True),
        sa.Column("first_seen", sa.DateTime(), nullable=True, index=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True, index=True),
        sa.Column("times_seen", sa.Integer(), nullable=True, default=1),
        sa.Column("download_status", sa.String(50), nullable=False, default="discovered", index=True),
        sa.Column("download_priority", sa.Integer(), nullable=True, default=50, index=True),
        sa.Column("latest_url", sa.String(512), nullable=True),
        sa.Column("latest_provider", sa.String(100), nullable=True),
        sa.Column("latest_pubdate", sa.DateTime(), nullable=True, index=True),
        sa.Column("search_result_ids", sa.JSON(), nullable=True),
        sa.Column(
            "current_submission_id",
            sa.Integer(),
            sa.ForeignKey("download_submissions.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("submission_ids", sa.JSON(), nullable=True),
        sa.Column("periodical_id", sa.Integer(), sa.ForeignKey("periodicals.id"), nullable=True, index=True),
        sa.Column("attempt_count", sa.Integer(), nullable=True, default=0),
        sa.Column("max_retries", sa.Integer(), nullable=True, default=1),
        sa.Column("last_attempt", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Index("ix_discovered_issues_tracking_fuzzy", "tracking_id", "fuzzy_match_group"),
    )

    op.create_table(
        "stacks",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("cover_override_path", sa.String(512), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "stack_memberships",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("stack_id", sa.Integer(), sa.ForeignKey("stacks.id"), nullable=False, index=True),
        sa.Column(
            "periodical_tracking_id",
            sa.Integer(),
            sa.ForeignKey("periodical_tracking.id"),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column(
            "periodical_id",
            sa.Integer(),
            sa.ForeignKey("periodicals.id"),
            nullable=True,
            unique=True,
            index=True,
        ),
        sa.Column("added_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "reading_progress",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column(
            "periodical_id",
            sa.Integer(),
            sa.ForeignKey("periodicals.id"),
            nullable=False,
            index=True,
            unique=True,
        ),
        sa.Column("current_page", sa.Integer(), nullable=True),
        sa.Column("current_chapter", sa.Integer(), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("last_read_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("reading_progress")
    op.drop_table("stack_memberships")
    op.drop_table("stacks")
    op.drop_table("discovered_issues")
    op.drop_table("ocr_jobs")
    op.drop_table("download_submissions")
    op.drop_table("search_results")
    op.drop_table("periodicals")
    op.drop_table("periodical_tracking")
    op.drop_table("credentials")
