"""
Download client constants — shared across SABnzbd and NZBGet clients.

Encryption detection indicators are shared between both clients.
NZBGet-specific status sets and history messages are also defined here.
"""

# ---------------------------------------------------------------------------
# Shared: Encryption/password indicators (used by SABnzbd and NZBGet)
# ---------------------------------------------------------------------------

ENCRYPTION_INDICATORS = [
    "encrypted rar",
    "encrypted archive",
    "archive requires a password",
    "password protected",
    "all passwords were tried",
]
"""Substrings (lowercase) indicating a download is encrypted or password-protected."""

ENCRYPTION_INDICATORS_HISTORY = [
    "encrypted rar",
    "encrypted archive",
    "archive requires a password",
    "password protected",
    "unpacking failed",
    "all passwords were tried",
]
"""Extended encryption indicators used when checking SABnzbd history failure messages."""


# ---------------------------------------------------------------------------
# NZBGet: listgroups Status values (active queue items only)
# These NEVER appear in history — history uses composite statuses like "SUCCESS/ALL".
# Reference: https://nzbget.com/documentation/api/listgroups
# ---------------------------------------------------------------------------

NZBGET_DOWNLOADING_STATUSES = {"DOWNLOADING", "FETCHING"}
"""Queue statuses indicating an active download or NZB fetch."""

NZBGET_POST_PROCESSING_STATUSES = {
    "PP_QUEUED",
    "LOADING_PARS",
    "VERIFYING_SOURCES",
    "REPAIRING",
    "VERIFYING_REPAIRED",
    "RENAMING",
    "UNPACKING",
    "MOVING",
    "POST_UNPACK_RENAMING",
    "EXECUTING_SCRIPT",
    "PP_FINISHED",
}
"""Queue statuses indicating post-processing stages (download complete, processing in progress)."""

NZBGET_PENDING_STATUSES = {"QUEUED", "PAUSED"}
"""Queue statuses indicating a pending/paused download."""


# ---------------------------------------------------------------------------
# NZBGet: History composite Status values and human-readable messages
# Reference: https://nzbget.com/documentation/api/history
# ---------------------------------------------------------------------------

NZBGET_HISTORY_STATUS_MESSAGES = {
    "FAILURE/PAR": "Par-check failed — file is corrupted beyond repair",
    "FAILURE/UNPACK": "Unpack failed — archive may be damaged",
    "FAILURE/MOVE": "Failed to move files to destination directory",
    "FAILURE/SCAN": "Malformed NZB file could not be parsed",
    "FAILURE/HEALTH": "Download health too low — too many failed articles",
    "FAILURE/BAD": "Download marked as bad",
    "WARNING/SPACE": "Unpack failed — not enough disk space",
    "WARNING/PASSWORD": "Archive requires a password",
    "WARNING/DAMAGED": "Par-check required but disabled in NZBGet settings",
    "WARNING/REPAIRABLE": "Par-repair needed but disabled in NZBGet settings",
    "WARNING/HEALTH": "Download health below 100% — no par-files available",
    "WARNING/SCRIPT": "Post-processing script failed",
    "DELETED/MANUAL": "Download was manually deleted",
    "DELETED/DUPE": "Download was deleted by duplicate check",
    "DELETED/HEALTH": "Download was deleted by health check",
    "DELETED/COPY": "Duplicate NZB already in queue or history",
    "DELETED/GOOD": "Deleted — good duplicate already exists",
}
"""Map of NZBGet history composite Status to human-readable error messages."""
