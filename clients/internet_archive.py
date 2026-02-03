"""
Internet Archive download client implementation.
Handles direct downloads from archive.org without external download managers.
Supports both individual files (PDF, EPUB) and collection archives (ZIP, TAR.GZ).
"""

import gzip
import hashlib
import logging
import os
import shutil
import tarfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from internetarchive import get_item

from core.constants.internet_archive import (
    IA_PREFERRED_FORMATS,
    IA_TEXT_PDF_FORMATS,
    IA_COLLECTION_FORMATS,
    IA_EXTRACTABLE_EXTENSIONS,
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
    IA_COMPRESS_BASE_URL,
)
from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


class DownloadJob:  # pylint: disable=too-many-instance-attributes
    """Represents a single download job"""

    def __init__(self, job_id: str, identifier: str, title: str, dest_path: str, prefer_collection: bool = False):
        self.job_id = job_id
        self.identifier = identifier
        self.title = title
        self.dest_path = dest_path
        self.prefer_collection = prefer_collection  # Prefer ZIP/TAR collection formats
        self.status = IA_STATUS_PENDING
        self.progress = 0
        self.file_path: Optional[str] = None  # Single file or comma-separated list for collections
        self.error: Optional[str] = None
        self.expected_size = 0
        self.downloaded_size = 0
        self.download_url: Optional[str] = None
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.extracted_count: int = 0  # Number of files extracted from collection


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

        # Threshold for using compress URL (for multi-file items)
        self.compress_threshold = 3  # Use compress URL if 3+ files of desired format

        logger.info(
            f"[{self.name}] Initialized with downloads_dir={self.downloads_dir}, "
            f"max_concurrent={self.max_concurrent}"
        )

    def _generate_job_id(self, identifier: str) -> str:
        """Generate a unique job ID"""
        unique_str = f"{identifier}-{time.time()}-{uuid.uuid4().hex[:8]}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    def _get_download_strategy(self, item_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Determine the best download strategy for an item.

        For items with multiple files of the desired format, use the /compress/
        endpoint to download them all in a single ZIP. For single files, download directly.

        Args:
            item_metadata: Item metadata from IA API

        Returns:
            Dict with:
                - strategy: "direct" or "compress"
                - format: The format to download (e.g., "Text PDF")
                - files: List of matching files
                - url: Download URL
                - is_collection: Whether result will be a collection archive
        """
        files = item_metadata.get("files", [])
        identifier = item_metadata.get("metadata", {}).get("identifier", "")

        # Count files by format, prioritizing Text PDF
        format_counts: Dict[str, List[Dict]] = {}
        for f in files:
            fmt = f.get("format", "")
            if fmt:
                format_counts.setdefault(fmt, []).append(f)

        # Check for Text PDF first (best for text scanning)
        for text_pdf_fmt in IA_TEXT_PDF_FORMATS:
            if text_pdf_fmt in format_counts:
                matching_files = format_counts[text_pdf_fmt]
                if len(matching_files) >= self.compress_threshold:
                    # Use compress URL for multiple files
                    # URL encode the format name
                    encoded_format = text_pdf_fmt.upper().replace(" ", "%20")
                    return {
                        "strategy": "compress",
                        "format": text_pdf_fmt,
                        "files": matching_files,
                        "url": f"{IA_COMPRESS_BASE_URL}/{identifier}/formats={encoded_format}",
                        "is_collection": True,
                        "file_count": len(matching_files),
                    }
                elif len(matching_files) == 1:
                    # Direct download for single file
                    file_info = matching_files[0]
                    return {
                        "strategy": "direct",
                        "format": text_pdf_fmt,
                        "files": matching_files,
                        "url": f"{IA_DOWNLOAD_BASE_URL}/{identifier}/{file_info['name']}",
                        "is_collection": False,
                        "file_count": 1,
                        "file_info": file_info,
                    }

        # Check other preferred formats
        for preferred_fmt in self.preferred_formats:
            # Look for exact match or substring match
            for fmt, fmt_files in format_counts.items():
                if preferred_fmt.lower() in fmt.lower():
                    if len(fmt_files) >= self.compress_threshold:
                        encoded_format = fmt.upper().replace(" ", "%20")
                        return {
                            "strategy": "compress",
                            "format": fmt,
                            "files": fmt_files,
                            "url": f"{IA_COMPRESS_BASE_URL}/{identifier}/formats={encoded_format}",
                            "is_collection": True,
                            "file_count": len(fmt_files),
                        }
                    elif len(fmt_files) >= 1:
                        file_info = fmt_files[0]
                        return {
                            "strategy": "direct",
                            "format": fmt,
                            "files": fmt_files,
                            "url": f"{IA_DOWNLOAD_BASE_URL}/{identifier}/{file_info['name']}",
                            "is_collection": False,
                            "file_count": len(fmt_files),
                            "file_info": file_info,
                        }

        return {"strategy": "none", "format": None, "files": [], "url": None, "is_collection": False}

    def _get_best_file(
        self, item_metadata: Dict[str, Any], prefer_collection: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best downloadable file from item metadata.

        Args:
            item_metadata: Item metadata from IA API
            prefer_collection: If True, prefer collection archive formats (ZIP, etc.)

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
                format_files.setdefault(fmt, []).append(
                    {
                        "name": name,
                        "format": fmt,
                        "size": size,
                        "is_collection": fmt in IA_COLLECTION_FORMATS,
                    }
                )

        # If preferring collection, try collection formats first
        if prefer_collection:
            for collection_fmt in IA_COLLECTION_FORMATS:
                if collection_fmt in format_files:
                    return format_files[collection_fmt][0]

        # PRIORITY 1: Text PDF formats (have embedded OCR text - best for text scanning)
        for text_pdf_fmt in IA_TEXT_PDF_FORMATS:
            if text_pdf_fmt in format_files:
                logger.debug(f"Found preferred text format: {text_pdf_fmt}")
                return format_files[text_pdf_fmt][0]

        # PRIORITY 2: Find best format in order of preference
        # Use case-insensitive matching to handle variants like "Text PDF"
        for preferred_fmt in self.preferred_formats:
            preferred_lower = preferred_fmt.lower()
            # First try exact match
            if preferred_fmt in format_files:
                return format_files[preferred_fmt][0]
            # Then try case-insensitive substring match (e.g., "PDF" matches "Text PDF")
            for fmt, files_list in format_files.items():
                if preferred_lower in fmt.lower():
                    return files_list[0]

        # Fallback: return any PDF-like format
        for fmt, files_list in format_files.items():
            if "pdf" in fmt.lower():
                return files_list[0]

        # Last resort: try collection formats
        for collection_fmt in IA_COLLECTION_FORMATS:
            if collection_fmt in format_files:
                return format_files[collection_fmt][0]

        return None

    def _is_extractable(self, file_path: Path) -> bool:
        """
        Check if a file is an extractable archive.

        Args:
            file_path: Path to the downloaded file

        Returns:
            True if the file can be extracted
        """
        suffix = file_path.suffix.lower()
        # Handle double extensions like .tar.gz
        if file_path.stem.lower().endswith(".tar"):
            suffix = ".tar.gz"
        return suffix in IA_EXTRACTABLE_EXTENSIONS

    def _extract_archive(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        """
        Extract an archive file to the destination directory.

        Args:
            archive_path: Path to the archive file
            dest_dir: Directory to extract files to

        Returns:
            List of extracted file paths
        """
        extracted_files = []
        suffix = archive_path.suffix.lower()

        # Handle double extensions like .tar.gz
        if archive_path.stem.lower().endswith(".tar"):
            suffix = ".tar.gz"

        try:
            if suffix == ".zip":
                extracted_files = self._extract_zip(archive_path, dest_dir)
            elif suffix in (".tar.gz", ".tgz"):
                extracted_files = self._extract_tar_gz(archive_path, dest_dir)
            elif suffix == ".tar":
                extracted_files = self._extract_tar(archive_path, dest_dir)
            elif suffix == ".gz":
                extracted_files = self._extract_gzip(archive_path, dest_dir)
            else:
                logger.warning(f"[{self.name}] Unknown archive format: {suffix}")
                return [archive_path]  # Return original if can't extract

            logger.info(f"[{self.name}] Extracted {len(extracted_files)} files from {archive_path.name}")

            # Remove the archive file after successful extraction
            if extracted_files:
                archive_path.unlink()
                logger.debug(f"[{self.name}] Removed archive file: {archive_path}")

            return extracted_files

        except Exception as e:
            logger.error(f"[{self.name}] Failed to extract {archive_path}: {e}")
            return [archive_path]  # Return original on failure

    def _extract_zip(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        """Extract a ZIP archive."""
        extracted = []
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.namelist():
                # Skip directories and hidden files
                if member.endswith("/") or member.startswith("__") or member.startswith("."):
                    continue
                # Extract only supported file types
                member_ext = Path(member).suffix.lower()
                if member_ext in (".pdf", ".epub", ".mobi", ".djvu", ".cbz", ".cbr"):
                    # Extract to flat directory (no subdirs)
                    member_name = Path(member).name
                    dest_path = dest_dir / member_name
                    # Handle duplicates
                    counter = 1
                    while dest_path.exists():
                        stem = Path(member).stem
                        dest_path = dest_dir / f"{stem}_{counter}{member_ext}"
                        counter += 1
                    with zf.open(member) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(dest_path)
        return extracted

    def _extract_tar_gz(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        """Extract a TAR.GZ archive."""
        extracted = []
        with tarfile.open(archive_path, "r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                member_name = Path(member.name).name
                if member_name.startswith(".") or member_name.startswith("__"):
                    continue
                member_ext = Path(member_name).suffix.lower()
                if member_ext in (".pdf", ".epub", ".mobi", ".djvu", ".cbz", ".cbr"):
                    dest_path = dest_dir / member_name
                    counter = 1
                    while dest_path.exists():
                        stem = Path(member_name).stem
                        dest_path = dest_dir / f"{stem}_{counter}{member_ext}"
                        counter += 1
                    with tf.extractfile(member) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(dest_path)
        return extracted

    def _extract_tar(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        """Extract a TAR archive."""
        extracted = []
        with tarfile.open(archive_path, "r") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                member_name = Path(member.name).name
                if member_name.startswith(".") or member_name.startswith("__"):
                    continue
                member_ext = Path(member_name).suffix.lower()
                if member_ext in (".pdf", ".epub", ".mobi", ".djvu", ".cbz", ".cbr"):
                    dest_path = dest_dir / member_name
                    counter = 1
                    while dest_path.exists():
                        stem = Path(member_name).stem
                        dest_path = dest_dir / f"{stem}_{counter}{member_ext}"
                        counter += 1
                    with tf.extractfile(member) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted.append(dest_path)
        return extracted

    def _extract_gzip(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        """Extract a GZIP file (single file compression)."""
        # GZIP typically wraps a single file, remove .gz extension
        out_name = archive_path.stem
        if not Path(out_name).suffix:
            out_name = out_name + ".pdf"  # Default to PDF if no extension
        dest_path = dest_dir / out_name
        with gzip.open(archive_path, "rb") as src, open(dest_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return [dest_path]

    def _download_file(self, job: DownloadJob):
        """
        Execute the actual file download in a background thread.
        Handles both single files and collection archives (ZIP, TAR.GZ).
        Uses /compress/ endpoint for items with multiple files of desired format.

        Args:
            job: DownloadJob instance to process
        """
        try:
            job.status = IA_STATUS_DOWNLOADING
            job.started_at = time.time()

            logger.info(f"[{self.name}] Starting download for {job.identifier}")

            # Get item metadata to determine download strategy
            item = get_item(job.identifier)
            metadata = item.item_metadata

            # Determine best download strategy (direct file vs compress URL)
            strategy = self._get_download_strategy(metadata)

            if strategy["strategy"] == "none":
                job.status = IA_STATUS_FAILED
                job.error = f"No suitable file format found for {job.identifier}"
                logger.error(f"[{self.name}] {job.error}")
                return

            download_url = strategy["url"]
            is_collection = strategy["is_collection"]
            file_count = strategy.get("file_count", 1)
            format_name = strategy["format"]

            # For direct downloads, get file size from metadata
            if strategy["strategy"] == "direct" and "file_info" in strategy:
                job.expected_size = int(strategy["file_info"].get("size", 0))

            job.download_url = download_url

            # Determine destination path and extension
            safe_title = "".join(c if c.isalnum() or c in " .-_" else "_" for c in job.title)[:100]

            if strategy["strategy"] == "compress":
                # Compress endpoint returns a ZIP
                ext = ".zip"
                logger.info(f"[{self.name}] Using compress URL for {file_count} {format_name} files")
            else:
                # Direct download - use original file extension
                file_info = strategy.get("file_info", {})
                ext = Path(file_info.get("name", ".pdf")).suffix or ".pdf"

            dest_file = self.downloads_dir / f"{safe_title}{ext}"

            # Handle duplicate filenames
            counter = 1
            while dest_file.exists():
                dest_file = self.downloads_dir / f"{safe_title}_{counter}{ext}"
                counter += 1

            logger.info(
                f"[{self.name}] Downloading {download_url} -> {dest_file}"
                f"{f' ({file_count} files via compress)' if is_collection else ''}"
            )

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

                    # Stream download with progress logging
                    job.downloaded_size = 0
                    last_logged_progress = -1
                    last_logged_mb = -1

                    with open(dest_file, "wb") as f:
                        for chunk in response.iter_content(chunk_size=IA_DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                job.downloaded_size += len(chunk)

                                # Update progress
                                if job.expected_size > 0:
                                    job.progress = int((job.downloaded_size / job.expected_size) * 100)

                                    # Log progress every 10% or every 10MB
                                    current_mb = job.downloaded_size // (10 * 1024 * 1024)  # Every 10MB
                                    if (job.progress >= last_logged_progress + 10) or (current_mb > last_logged_mb):
                                        logger.info(
                                            f"[{self.name}] Download progress for {job.identifier}: "
                                            f"{job.progress}% ({job.downloaded_size / 1024 / 1024:.1f} MB / "
                                            f"{job.expected_size / 1024 / 1024:.1f} MB)"
                                        )
                                        last_logged_progress = job.progress
                                        last_logged_mb = current_mb

                    # Verify download
                    if dest_file.exists() and dest_file.stat().st_size > 0:
                        logger.info(
                            f"[{self.name}] Download completed: {job.identifier} -> {dest_file} "
                            f"({job.downloaded_size / 1024 / 1024:.1f} MB)"
                        )

                        # Check if this is an archive that needs extraction
                        if self._is_extractable(dest_file):
                            logger.info(f"[{self.name}] Extracting archive: {dest_file}")
                            extracted_files = self._extract_archive(dest_file, self.downloads_dir)

                            if extracted_files:
                                # Store list of extracted files (comma-separated for compatibility)
                                job.file_path = ",".join(str(f) for f in extracted_files)
                                job.extracted_count = len(extracted_files)
                                logger.info(f"[{self.name}] Extracted {len(extracted_files)} files from collection")
                            else:
                                # Extraction failed, keep original archive
                                job.file_path = str(dest_file)
                        else:
                            job.file_path = str(dest_file)

                        job.status = IA_STATUS_COMPLETED
                        job.progress = 100
                        job.completed_at = time.time()
                        return
                    else:
                        raise IOError("Downloaded file is empty or missing")

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
        For collection archives, returns individual entries for each extracted file.

        Returns:
            List of completed download info
        """
        completed = []

        with self._jobs_lock:
            for job_id, job in self._jobs.items():
                if job.status == IA_STATUS_COMPLETED and job.file_path:
                    # Check if this was a collection with multiple extracted files
                    if job.extracted_count > 0 and "," in job.file_path:
                        # Return each extracted file as a separate completed download
                        file_paths = job.file_path.split(",")
                        for i, file_path in enumerate(file_paths):
                            completed.append(
                                {
                                    "job_id": f"{job_id}_{i}",
                                    "file_path": file_path.strip(),
                                    "title": job.title,
                                    "is_collection_item": True,
                                    "collection_job_id": job_id,
                                }
                            )
                    else:
                        # Single file download
                        completed.append(
                            {
                                "job_id": job_id,
                                "file_path": job.file_path,
                                "title": job.title,
                                "is_collection_item": False,
                            }
                        )

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
                job_id
                for job_id, job in self._jobs.items()
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
