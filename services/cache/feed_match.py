"""
RSS Feed Match Service — Phase 2 of cache-first auto-download.

Matches locally cached RSS feed entries (from FeedSyncService) against
all tracked periodicals. This is entirely local — no API calls needed.
Matched entries are forwarded to the existing IssueDiscoveryService for
evaluation and download queue processing.

Architecture:
    1. Feed Sync (FeedSyncService): Polls RSS → upserts RssFeedEntry rows
    2. Local Match (this service): Matches cached entries against tracking rules
    3. Download Queue: Standard issue discovery flow handles downloads
"""

import logging
import re
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from core.interfaces import SearchResult
from models.cache import RssFeedEntry
from models.database import PeriodicalTracking

logger = logging.getLogger(__name__)


class FeedMatchService:
    """
    Match cached RSS feed entries against tracked periodicals.

    Takes batches of new RssFeedEntry rows and checks each against all
    tracked periodical titles and aliases. Matched entries are converted
    to SearchResult format for the IssueDiscoveryService pipeline.

    This is the critical optimization: instead of N API calls (one per
    tracked periodical), we do N local string comparisons against M
    cached entries — O(N*M) in-memory operations with zero HTTP requests.
    """

    def match_entries_against_tracking(
        self,
        entries: List[RssFeedEntry],
        session: Session,
    ) -> Dict[str, Any]:
        """
        Match a batch of RSS feed entries against all tracked periodicals.

        For each entry, checks if the title matches any tracked periodical's
        title or search aliases using word boundary matching to avoid
        substring false positives (e.g., "Maxim" won't match "Maximo").

        Args:
            entries: Batch of RssFeedEntry objects to match
            session: Database session for querying tracking records

        Returns:
            Dict with:
                - matches: Dict[tracking_id, List[SearchResult]] grouped by periodical
                - matched_entry_ids: List[int] of matched RssFeedEntry IDs
                - skipped_entry_ids: List[int] of non-matching entry IDs
                - stats: {matched, skipped, total}
        """
        result = {
            "matches": {},
            "matched_entry_ids": [],
            "skipped_entry_ids": [],
            "stats": {"matched": 0, "skipped": 0, "total": len(entries)},
        }

        if not entries:
            return result

        # Load all active tracking records with their search terms
        tracking_records = session.query(PeriodicalTracking).all()
        if not tracking_records:
            # No tracked periodicals — mark all as skipped
            result["skipped_entry_ids"] = [e.id for e in entries]
            result["stats"]["skipped"] = len(entries)
            logger.debug("[FeedMatch] No tracked periodicals, skipping all entries")
            return result

        # Build lookup: list of (tracking_id, search_terms) tuples
        tracking_search_terms = self._build_search_terms(tracking_records)

        for entry in entries:
            # Normalize title: replace delimiters with spaces for word boundary matching
            normalized_title = re.sub(r"[_.\-]", " ", entry.title.lower()) if entry.title else ""
            matched = False

            for tracking_id, search_terms, tracking_record in tracking_search_terms:
                # Use word boundary matching to avoid false positives
                # "Maxim" should NOT match "Maximo Garcia"
                if self._title_matches_any_term(normalized_title, search_terms):
                    # Match found — convert to SearchResult format
                    search_result = self._entry_to_search_result(entry)

                    if tracking_id not in result["matches"]:
                        result["matches"][tracking_id] = []
                    result["matches"][tracking_id].append(search_result)

                    result["matched_entry_ids"].append(entry.id)
                    result["stats"]["matched"] += 1
                    matched = True
                    break  # One match per entry is sufficient

            if not matched:
                result["skipped_entry_ids"].append(entry.id)
                result["stats"]["skipped"] += 1

        if result["stats"]["matched"] > 0:
            logger.info(
                f"[FeedMatch] Matched {result['stats']['matched']} entries "
                f"to {len(result['matches'])} periodicals, "
                f"skipped {result['stats']['skipped']}"
            )

        return result

    @staticmethod
    def _title_matches_any_term(normalized_title: str, search_terms: List[str]) -> bool:
        """
        Check if normalized title matches any search term using word boundaries.

        Uses word boundary matching to prevent substring false positives:
        - "Maxim" matches "Maxim Magazine" ✓
        - "Maxim" does NOT match "Maximo Garcia" ✗

        Args:
            normalized_title: Title normalized with delimiters replaced by spaces
            search_terms: List of lowercase search terms to match

        Returns:
            True if any term matches as a whole word in the title
        """
        for term in search_terms:
            # Ensure term is lowercase for case-insensitive matching
            term_lower = term.lower()

            # Build word boundary pattern
            # Handle special chars correctly (e.g., "C++", "40+")
            escaped = re.escape(term_lower)

            # Check if term starts/ends with word character
            starts_with_word = bool(re.match(r"^\w", term_lower))
            ends_with_word = bool(re.search(r"\w$", term_lower))

            if starts_with_word and ends_with_word:
                # Normal word like "maxim" - use boundaries on both sides
                pattern = rf"\b{escaped}\b"
            elif starts_with_word and not ends_with_word:
                # Word ending with special char like "c++"
                pattern = rf"\b{escaped}(?=\s|[^\w]|$)"
            elif not starts_with_word and ends_with_word:
                # Word starting with special char (rare)
                pattern = rf"{escaped}\b"
            else:
                # All special chars (very rare)
                pattern = escaped

            if re.search(pattern, normalized_title):
                return True

        return False

    @staticmethod
    def _build_search_terms(
        tracking_records: List[PeriodicalTracking],
    ) -> List[Tuple[int, List[str], PeriodicalTracking]]:
        """
        Build search term lookup from tracking records.

        For each tracked periodical, builds a list of lowercase search terms
        including the title and any configured aliases.

        Skips "Watch Only" periodicals (no download criteria set) to avoid
        creating unnecessary DiscoveredIssue records that would be immediately
        marked as "ignored" by the evaluation step.

        Args:
            tracking_records: List of PeriodicalTracking objects

        Returns:
            List of (tracking_id, search_terms, tracking_record) tuples
        """
        search_terms = []

        for tracking in tracking_records:
            # Skip periodicals with no download criteria (Watch Only mode)
            if not tracking.track_all_editions and not tracking.track_new_only:
                if not tracking.selected_years or len(tracking.selected_years) == 0:
                    continue

            terms = [tracking.title.lower()]

            # Add search aliases
            if tracking.search_aliases:
                for alias in tracking.search_aliases.split(","):
                    alias = alias.strip().lower()
                    if alias:
                        terms.append(alias)

            search_terms.append((tracking.id, terms, tracking))

        return search_terms

    @staticmethod
    def _entry_to_search_result(entry: RssFeedEntry) -> Dict[str, Any]:
        """
        Convert an RssFeedEntry to a SearchResult dict for IssueDiscoveryService.

        Follows the same format expected by IssueDiscoveryService.record_search_results().

        Args:
            entry: RssFeedEntry cache object

        Returns:
            Dict compatible with IssueDiscoveryService.record_search_results()
        """
        raw_metadata = {"source": "feed_cache", "guid": entry.guid}
        if entry.category:
            raw_metadata["category"] = entry.category

        # Use provider_type for routing (e.g., "internet_archive"), fall back to provider_name for legacy entries
        provider = entry.provider_type if entry.provider_type else entry.provider_name

        return {
            "title": entry.title,
            "url": entry.url,
            "provider": provider,
            "pubdate": entry.published_date.isoformat() if entry.published_date else None,
            "guid": entry.guid,
            "raw_metadata": raw_metadata,
        }
