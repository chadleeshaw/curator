"""
Internet Archive download client implementation.
Handles direct downloads from archive.org without external download managers.
"""

import hashlib
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from internetarchive import get_item

from core.constants.internet_archive import (
    IA_PREFERRED_FORMATS,
    IA_DOWNLOAD_TIMEOUT,
    IA_DOWNLOAD_CHUNK_SIZE,
    IA_DOWNLOAD_RETRY_ATTEMPTS,
    IA_DOWNLOAD_RETRY_DELAY,
    IA_DEFAULT_MAX_CONCURRENT_DOWNLOADS,
    IA_STATUS_PENDING,
    IA_STATUS_DOWNLOADING,
    IA_STATUS_COMPLETED,
    IA_STATUS_FAILED,
    IA_DOWNLOAD_BASE_URL,
)
from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


class DownloadJob:
    """Represents a single download job"""

    def __init__(self, job_id: str, identifier: str, title: str, dest_path: str):
        self.job_id = job_id
        self.identifier = identifier
        self.title = title
        self.dest_path = dest_path
        self.status = IA_STATUS_PENDING
        self.progress = 0
        self.file_path: Optional[str] = None
        self.error: Optional[str] = None
        self.expected_size = 0
        self.downloaded_size = 0
        self.download_url: Optional[str] = None
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None


class InternetArchiveClient(DownloadClient):
    """Download client for Internet Archive direct downloads"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = "internet_archive"

        # Download directory
        self.downloads_dir = Path(config.get("downloads_dir", "/tmp/ia_downloads"))
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        # Concurrency settings
        self.max_concurrent = config.get("max_concurrent", IA_DEFAULT_MAX_CONCURRENT_DOWNLOADS)

        # Preferred file formats
        self.preferred_formats = config.get("file_formats", IA_PREFERRED_FORMATS)

        # Job tracking
        self._jobs: Dict[str, DownloadJob] = {}
        self._jobs_lock = threading.Lock()

        # Thread pool for background downloads
        self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent, thread_name_prefix="ia_download")

        logger.info(
            f"[{self.name}] Initialized with downloads_dir={self.downloads_dir}, "
            f"max_concurrent={self.max_concurrent}"
        )

    def _generate_job_id(self, identifier: str) -> str:
        """Generate a unique job ID"""
        unique_str = f"{identifier}-{time.time()}-{uuid.uuid4().hex[:8]}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    def _get_best_file(self, item_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the best downloadable file from item metadata.

        Args:
            item_metadata: Item metadata from IA API

        Returns:
            Dict with file info or None
        """
        files = item_metadata.get("files", [])
        if not files:
            return None

        # Build list of available files by format
        format_files = {}
        for f in files:
            fmt = f.get("format", "")
            name = f.get("name", "")
            if fmt and name:
                size_str = f.get("size", "0")
                try:
                    size = int(size_str) if size_str else 0
                except (ValueError, TypeError):
                    size = 0
                format_files.setdefault(fmt, []).append({
                    "name": name,
                    "format": fmt,
                    "size": size,
                })

        # Find best format in order of preference
        for preferred_fmt in self.preferred_formats:
            if preferred_fmt in format_files:
                return format_files[preferred_fmt][0]

        # Fallback: return any PDF-like format
        for fmt, files_list in format_files.items():
            if "pdf" in fmt.lower():
                return files_list[0]

        return None

    def _download_file(self, job: DownloadJob):
        """
        Execute the actual file download in a background thread.

        Args:
            job: DownloadJob instance to process
        """
        try:
            job.status = IA_STATUS_DOWNLOADING
            job.started_at = time.time()

            logger.info(f"[{self.name}] Starting download for {job.identifier}")

            # Get item metadata to find best file
            item = get_item(job.identifier)
            metadata = item.item_metadata

            best_file = self._get_best_file(metadata)
            if not best_file:
                job.status = IA_STATUS_FAILED
                job.error = f"No suitable file format found for {job.identifier}"
                logger.error(f"[{self.name}] {job.error}")
                return

            file_name = best_file["name"]
            job.expected_size = best_file.get("size", 0)
            job.download_url = f"{IA_DOWNLOAD_BASE_URL}/{job.identifier}/{file_name}"

            # Determine destination path
            safe_title = "".join(c if c.isalnum() or c in " .-_" else "_" for c in job.title)[:100]
            ext = Path(file_name).suffix or ".pdf"
            dest_file = self.downloads_dir / f"{safe_title}{ext}"

            # Handle duplicate filenames
            counter = 1
            while dest_file.exists():
                dest_file = self.downloads_dir / f"{safe_title}_{counter}{ext}"
                counter += 1

            logger.info(f"[{self.name}] Downloading {job.download_url} -> {dest_file}")

            # Download with retry logic
            for attempt in range(IA_DOWNLOAD_RETRY_ATTEMPTS):
                try:
                    response = requests.get(
                        job.download_url,
                        stream=True,
                        timeout=IA_DOWNLOAD_TIMEOUT,
                    )
                    response.raise_for_status()

                    # Get content length if available
                    content_length = response.headers.get("content-length")
                    if content_length:
                        job.expected_size = int(content_length)

                    # Stream download
                    job.downloaded_size = 0
                    with open(dest_file, "wb") as f:
                        for chunk in response.iter_content(chunk_size=IA_DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                job.downloaded_size += len(chunk)

                                # Update progress
                                if job.expected_size > 0:
                                    job.progress = int((job.downloaded_size / job.expected_size) * 100)

                    # Verify download
                    if dest_file.exists() and dest_file.stat().st_size > 0:
                        job.status = IA_STATUS_COMPLETED
                        job.file_path = str(dest_file)
                        job.progress = 100
                        job.completed_at = time.time()
                        logger.info(
                            f"[{self.name}] Download completed: {job.identifier} -> {dest_file} "
                            f"({job.downloaded_size / 1024 / 1024:.1f} MB)"
                        )
                        return
                    else:
                        raise Exception("Downloaded file is empty or missing")

                except requests.exceptions.RequestException as e:
                    logger.warning(
                        f"[{self.name}] Download attempt {attempt + 1}/{IA_DOWNLOAD_RETRY_ATTEMPTS} "
                        f"failed for {job.identifier}: {e}"
                    )
                    if attempt < IA_DOWNLOAD_RETRY_ATTEMPTS - 1:
                        time.sleep(IA_DOWNLOAD_RETRY_DELAY)
                    else:
                        raise

            # All retries exhausted
            job.status = IA_STATUS_FAILED
            job.error = f"Download failed after {IA_DOWNLOAD_RETRY_ATTEMPTS} attempts"

        except Exception as e:
            job.status = IA_STATUS_FAILED
            job.error = str(e)
            logger.error(f"[{self.name}] Download failed for {job.identifier}: {e}", exc_info=True)

    def submit(self, nzb_url: str, title: str = None, category: str = None) -> Optional[str]:
        """
        Submit an Internet Archive item for download.

        Args:
            nzb_url: For IA, this is the item identifier (not a URL)
            title: Optional title for the download
            category: Optional category (not used for IA)

        Returns:
            Job ID for tracking the download
        """
        identifier = nzb_url  # The "URL" from search results is actually the IA identifier

        try:
            job_id = self._generate_job_id(identifier)

            job = DownloadJob(
                job_id=job_id,
                identifier=identifier,
                title=title or identifier,
                dest_path=str(self.downloads_dir),
            )

            with self._jobs_lock:
                self._jobs[job_id] = job

            # Submit download to thread pool
            self._executor.submit(self._download_file, job)

            logger.info(f"[{self.name}] Submitted download: {identifier} -> job_id={job_id}")
            return job_id

        except Exception as e:
            logger.error(f"[{self.name}] Error submitting download for {identifier}: {e}")
            return None

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get download status for a job.

        Args:
            job_id: Job ID from submit()

        Returns:
            Dict with status info
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)

        if not job:
            logger.debug(f"[{self.name}] Job not found: {job_id}")
            return {"status": "unknown", "progress": 0}

        result = {
            "status": job.status,
            "progress": job.progress,
        }

        if job.file_path:
            result["file_path"] = job.file_path

        if job.error:
            result["error"] = job.error

        if job.expected_size > 0:
            result["size"] = job.expected_size
            result["downloaded"] = job.downloaded_size

        return result

    def get_completed_downloads(self) -> List[Dict[str, Any]]:
        """
        Get list of completed downloads not yet processed.

        Returns:
            List of completed download info
        """
        completed = []

        with self._jobs_lock:
            for job_id, job in self._jobs.items():
                if job.status == IA_STATUS_COMPLETED and job.file_path:
                    completed.append({
                        "job_id": job_id,
                        "file_path": job.file_path,
                        "title": job.title,
                    })

        return completed

    def delete(self, job_id: str) -> bool:
        """
        Delete a job from tracking (and optionally the downloaded file).

        Args:
            job_id: Job ID to delete

        Returns:
            True if successfully deleted
        """
        with self._jobs_lock:
            job = self._jobs.pop(job_id, None)

        if job:
            logger.info(f"[{self.name}] Deleted job {job_id}: {job.title}")
            return True

        logger.warning(f"[{self.name}] Job not found for deletion: {job_id}")
        return False

    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Internet Archive.

        Returns:
            Dict with success status and message
        """
        try:
            # Verify downloads directory is writable
            test_file = self.downloads_dir / ".ia_test"
            test_file.touch()
            test_file.unlink()

            # Test IA API connectivity
            item = get_item("principia_mathematica")  # Well-known item that should always exist
            if item and item.identifier:
                return {
                    "success": True,
                    "message": f"Connection successful. Downloads dir: {self.downloads_dir}",
                }

            return {
                "success": False,
                "message": "Could not verify Internet Archive connectivity",
            }

        except PermissionError:
            return {
                "success": False,
                "message": f"Downloads directory not writable: {self.downloads_dir}",
            }
        except Exception as e:
            logger.error(f"[{self.name}] Connection test failed: {e}")
            return {
                "success": False,
                "message": f"Connection test failed: {str(e)}",
            }

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Clean up old completed/failed jobs from memory.

        Args:
            max_age_hours: Remove jobs older than this many hours
        """
        cutoff = time.time() - (max_age_hours * 3600)

        with self._jobs_lock:
            to_remove = [
                job_id for job_id, job in self._jobs.items()
                if job.status in (IA_STATUS_COMPLETED, IA_STATUS_FAILED) and job.created_at < cutoff
            ]

            for job_id in to_remove:
                del self._jobs[job_id]

        if to_remove:
            logger.info(f"[{self.name}] Cleaned up {len(to_remove)} old jobs")

    def shutdown(self):
        """Shutdown the thread pool executor"""
        self._executor.shutdown(wait=False)
        logger.info(f"[{self.name}] Shutdown complete")
