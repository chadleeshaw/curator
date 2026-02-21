from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Union


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
    def search(self, query: str, category: str = None, aliases: Optional[Sequence[str]] = None) -> List[SearchResult]:
        """
        Search for periodicals matching query.

        Args:
            query: Periodical title or search term
            category: Optional category filter (e.g., "Magazines", "Comics")
            aliases: Optional alternative search terms (e.g., search aliases from tracking)

        Returns:
            List of SearchResult objects
        """

    @property
    def is_rate_limited(self) -> bool:
        """
        Check if this provider is currently rate limited.

        Returns:
            True if rate limited (searches will return empty), False otherwise
        """
        return False

    def get_provider_info(self) -> Dict[str, Any]:
        """Get metadata about this provider"""
        return {
            "type": self.type,
            "name": self.name,
            "enabled": self.config.get("enabled", True),
        }


class DownloadClient(ABC):
    """Abstract base class for download clients"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", self.__class__.__name__)
        self.type = config.get("type", "unknown")

    @abstractmethod
    def submit(self, url: str, title: str = None, category: str = None) -> str:
        """
        Submit a download URL to the client.

        Args:
            url: URL to the download file (NZB, magnet link, .torrent URL, etc.)
            title: Optional title for the job
            category: Optional category for download client (determines download folder)

        Returns:
            Job ID returned by the client
        """

    def submit_content(self, content: Union[str, bytes], title: str = None, category: str = None) -> Optional[str]:
        """
        Submit raw download content directly to the client (avoids provider URL fetch).

        Override in subclasses to support direct content upload.
        Default implementation returns None (caller should use submit() with URL instead).

        NZB clients (SABnzbd, NZBGet) accept NZB XML as a string and encode internally.
        Torrent clients (qBittorrent) accept .torrent file bytes.

        Returns:
            Job ID returned by the client, or None if not supported or hash unavailable
        """
        return None

    @staticmethod
    def _sanitize_title(title: str, max_length: int = 100) -> str:
        """Normalize a job title: replace path separators and truncate."""
        sanitized = title.replace("/", "-").replace("\\", "-").strip()
        return sanitized[:max_length].strip() if len(sanitized) > max_length else sanitized

    @staticmethod
    def _to_bytes(content: Union[str, bytes]) -> bytes:
        """Encode content to bytes if it is a string, otherwise pass through."""
        return content.encode("utf-8") if isinstance(content, str) else content

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

    @abstractmethod
    def delete(self, job_id: str) -> bool:
        """
        Delete a job from the download client (queue or history).

        Args:
            job_id: Job ID to delete

        Returns:
            True if successfully deleted, False otherwise
        """

    def get_client_info(self) -> Dict[str, Any]:
        """Get metadata about this client"""
        return {"type": self.type, "name": self.name}
