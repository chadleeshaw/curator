"""
Unified parser entry point for all parsing operations.
Delegates to specialized parsers and returns standardized dataclasses.
"""
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from core.parsers.models import (
    ParsedMetadata,
    ParsedFilename,
    ParsedFilepath,
    ParsedSearchResult,
    ParsedDownloadFile,
)
from core.parsers.title import TitleMatcher
from core.parsers.metadata import MetadataExtractor
from core.parsers.language import detect_language
from core.parsers.country import detect_country


class UnifiedParser:
    """
    Central parser that handles all parsing use cases.
    Returns consistent dataclass types for type safety.
    """

    def __init__(self, fuzzy_threshold: int = 80):
        """
        Initialize unified parser.

        Args:
            fuzzy_threshold: Threshold for title matching (0-100)
        """
        self.title_matcher = TitleMatcher(threshold=fuzzy_threshold)
        self.metadata_extractor = MetadataExtractor()

    def parse_file(self, file_path: Path) -> ParsedMetadata:
        """
        Parse a local file (PDF/EPUB) combining filename and filepath data.

        Use Case 1 & 2: Filename + Filepath parsing

        Args:
            file_path: Path to the file

        Returns:
            ParsedMetadata with all extracted information
        """
        # Parse filename
        filename_data = self._parse_filename_only(file_path)

        # Parse filepath
        filepath_data = self._parse_filepath_only(file_path)

        # Combine both sources - filename takes priority
        title = filename_data.title or filepath_data.title_from_path or file_path.stem

        # Clean and normalize title
        cleaned_title = self.title_matcher.clean_release_title(title)
        base_title, is_special, special_name = self.title_matcher.extract_base_title(cleaned_title)

        # Detect language and country from full path
        full_path_str = str(file_path)
        language = filepath_data.language_from_path or detect_language(full_path_str)
        country = detect_country(full_path_str)

        # Determine confidence
        confidence = "high" if filename_data.confidence == "high" else "medium"
        if not filename_data.issue_date and not filepath_data.year_from_path:
            confidence = "low"

        # Build comprehensive metadata
        return ParsedMetadata(
            title=cleaned_title,
            base_title=base_title,
            normalized_title=cleaned_title.lower(),
            language=language,
            country=country,
            issue_date=filename_data.issue_date,
            year=filename_data.year or filepath_data.year_from_path,
            month=filename_data.issue_date.month if filename_data.issue_date else None,
            month_name=filename_data.month_name,
            issue_number=filename_data.issue_number,
            volume=filename_data.volume,
            is_special_edition=is_special or filename_data.is_special_edition,
            special_edition_name=special_name if is_special else None,
            file_path=file_path,
            original_filename=file_path.name,
            confidence=confidence,
            parse_source="file",
            matched_pattern=filename_data.matched_pattern,
            raw_metadata=filename_data.raw_metadata,
        )

    def parse_filename_string(self, filename: str) -> ParsedFilename:
        """
        Parse just a filename string (without path context).

        Args:
            filename: Filename to parse

        Returns:
            ParsedFilename with extracted data
        """
        return self._parse_filename_only(Path(filename))

    # pylint: disable=too-many-positional-arguments
    def parse_search_result(
        self,
        title: str,
        url: str,
        provider: str,
        publication_date: Optional[datetime] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedSearchResult:
        """
        Parse a search result from download providers.

        Use Case 4: Search results parsing

        Args:
            title: Raw title from search result
            url: Download URL
            provider: Provider name
            publication_date: Publication date if available
            raw_metadata: Raw provider data

        Returns:
            ParsedSearchResult with cleaned and parsed data
        """
        # Validate
        if not self.title_matcher.validate_before_parsing(title):
            # Return minimal result for invalid titles
            return ParsedSearchResult(
                title=title,
                original_title=title,
                cleaned_title=title,
                base_title=title,
                language="English",
                country=None,
                is_special_edition=False,
                special_edition_name=None,
                publication_date=publication_date,
                provider=provider,
                url=url,
                raw_metadata=raw_metadata or {},
            )

        # Clean title
        cleaned_title = self.title_matcher.clean_release_title(title)

        # Extract base title and special edition info
        base_title, is_special, special_name = self.title_matcher.extract_base_title(cleaned_title)

        # Detect language and country
        language = detect_language(title)
        country = detect_country(title)

        return ParsedSearchResult(
            title=cleaned_title,
            original_title=title,
            cleaned_title=cleaned_title,
            base_title=base_title,
            language=language,
            country=country,
            is_special_edition=is_special,
            special_edition_name=special_name if is_special else None,
            publication_date=publication_date,
            provider=provider,
            url=url,
            raw_metadata=raw_metadata or {},
        )

    def parse_download_file(
        self,
        file_path: Path,
        title_hint: Optional[str] = None,
    ) -> ParsedDownloadFile:
        """
        Parse a file from download client.

        Use Case 3: Download client file data parsing

        Args:
            file_path: Path to downloaded file
            title_hint: Optional title hint from download client

        Returns:
            ParsedDownloadFile with parsed data
        """
        # Use hint if provided, otherwise parse from file
        if title_hint:
            cleaned_title = self.title_matcher.clean_release_title(title_hint)
        else:
            metadata = self.parse_file(file_path)
            cleaned_title = metadata.title

        # Detect language and country from full path
        full_path_str = str(file_path)
        language = detect_language(full_path_str)
        country = detect_country(full_path_str)

        # Try to extract date from filename
        filename_data = self._parse_filename_only(file_path)

        return ParsedDownloadFile(
            file_path=file_path,
            title=cleaned_title,
            cleaned_title=cleaned_title,
            language=language,
            country=country,
            issue_date=filename_data.issue_date,
            source="download_client",
        )

    def _parse_filename_only(self, file_path: Path) -> ParsedFilename:
        """Internal: Parse filename using MetadataExtractor"""
        result = self.metadata_extractor.extract_from_filename(file_path)

        return ParsedFilename(
            title=result.get("title", file_path.stem),
            issue_date=result.get("issue_date"),
            issue_number=result.get("edition_number"),
            volume=result.get("volume"),
            year=result.get("year"),
            month_name=result.get("month_name"),
            is_special_edition=result.get("is_special_edition", False),
            confidence="high" if result.get("issue_date") else "low",
            matched_pattern=result.get("pattern", "unknown"),
            raw_metadata=result,
        )

    def _parse_filepath_only(self, file_path: Path) -> ParsedFilepath:
        """Internal: Parse directory structure"""
        title_from_path = self.metadata_extractor.get_title_from_path(file_path)

        # Extract language from path components
        path_str = str(file_path)
        language = detect_language(path_str)

        # Try to find year in path
        year = None
        for part in file_path.parts:
            if part.isdigit() and len(part) == 4:
                try:
                    year_val = int(part)
                    if 1900 <= year_val <= 2100:
                        year = year_val
                        break
                except ValueError:
                    pass

        return ParsedFilepath(
            title_from_path=title_from_path,
            language_from_path=language if language != "English" else None,
            year_from_path=year,
            confidence="medium" if title_from_path else "low",
        )
