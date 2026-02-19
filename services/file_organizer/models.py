"""
Data models for file organization.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FilenameComponents:
    """Components for building an organized filename."""

    title: str
    volume: Optional[int] = None
    issue_number: Optional[int] = None
    month: Optional[str] = None
    year: Optional[str] = None
    extension: str = ".pdf"
