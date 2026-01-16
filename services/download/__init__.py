"""
Download services package - download client management
"""

# Import main class from submodule
from .manager import DownloadManager

# Re-export for backward compatibility
__all__ = [
    "DownloadManager",
]
