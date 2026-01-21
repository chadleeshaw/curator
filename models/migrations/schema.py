"""
Schema migrations - column additions and renames.

This module defines the expected database schema for automatic migrations.
The DatabaseManager will automatically add missing columns and rename columns
based on these definitions.
"""

# Expected schema for column additions
# Format: {table_name: [(column_name, column_definition)]}
COLUMN_ADDITIONS = {
    "credentials": [
        ("api_token", "VARCHAR(255)"),
    ],
    "periodical_tracking": [
        ("delete_from_client_on_completion", "BOOLEAN DEFAULT 1"),
        ("language", "VARCHAR(50) DEFAULT 'English'"),
        ("category", "VARCHAR(100)"),
        ("download_category", "VARCHAR(100)"),
        ("country", "VARCHAR(50)"),
        ("organization_pattern", "VARCHAR(255)"),
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
        # New metadata structure columns
        ("parsed_metadata", "JSON"),
        ("derived_metadata", "JSON"),
    ],
    "download_submissions": [
        ("extra_status", "VARCHAR(512)"),
    ],
}

# Column renames
# Format: {table_name: [(old_name, new_name)]}
COLUMN_RENAMES = {
    "ocr_jobs": [("magazine_id", "periodical_id")],
    "search_results": [("magazine_id", "periodical_id")],
    "discovered_issues": [("magazine_id", "periodical_id")],
    "download_submissions": [("magazine_id", "periodical_id")],
    "downloads": [("magazine_id", "periodical_id")],
    "reading_progress": [("magazine_id", "periodical_id")],
}
