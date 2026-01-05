from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SearchResult:
    """Standardized search result from any provider"""

    title: str
    url: str
    provider: str
    publication_date: Optional[datetime] = None
    raw_metadata: Dict[str, Any] = None  # Provider-specific fields

    def __post_init__(self):
        if self.raw_metadata is None:
            self.raw_metadata = {}


class SearchProvider(ABC):
    """Abstract base class for search providers"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.type = config.get("type", "unknown")

    @abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        """
        Search for periodicals matching query.

        Args:
            query: Periodical title or search term

        Returns:
            List of SearchResult objects
        """

    def get_provider_info(self) -> Dict[str, Any]:
        """Get metadata about this provider"""
        return {"type": self.type, "name": self.name, "enabled": self.config.get("enabled", True)}


class DownloadClient(ABC):
    """Abstract base class for download clients"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.type = config.get("type", "unknown")

    @abstractmethod
    def submit(self, nzb_url: str, title: str = None) -> str:
        """
        Submit an NZB URL to download.

        Args:
            nzb_url: URL to NZB file
            title: Optional title for the job

        Returns:
            Job ID returned by the client
        """

    @abstractmethod
    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get download status for a job.

        Args:
            job_id: ID returned by submit()

        Returns:
            Dict with keys: status (str), progress (0-100), file_path (str if completed)
        """

    @abstractmethod
    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of completed downloads not yet processed.

        Returns:
            List of dicts with keys: job_id, file_path, title
        """

    def get_client_info(self) -> Dict[str, Any]:
        """Get metadata about this client"""
        return {"type": self.type, "name": self.name}
