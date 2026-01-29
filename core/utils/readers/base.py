"""
Base classes and shared utilities for reader implementations.

This module provides common functionality used across different reader types.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseReader(ABC):
    """
    Abstract base class for periodical readers.

    Provides common interface for reading different file formats.
    """

    @abstractmethod
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from the file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file metadata
        """
        pass

    @abstractmethod
    def get_page_count(self, file_path: Path) -> int:
        """
        Get the number of pages/chapters in the file.

        Args:
            file_path: Path to the file

        Returns:
            Number of pages or chapters
        """
        pass

    @abstractmethod
    def extract_page(self, file_path: Path, page_index: int) -> bytes:
        """
        Extract a specific page from the file.

        Args:
            file_path: Path to the file
            page_index: Zero-based page index

        Returns:
            Page content as bytes
        """
        pass
