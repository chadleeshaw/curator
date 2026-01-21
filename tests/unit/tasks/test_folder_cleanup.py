"""
Tests for folder cleanup task.

Tests folder cleanup logic including:
- Protection of folders with supported files
- Deletion of folders with only non-supported files
- Protection of system folders (.covers, .cache, etc.)
- Empty folder cleanup
- Exhaustive scanning
"""

import shutil
from pathlib import Path

import pytest

from tasks.folder_cleanup import FolderCleanup


class TestFolderCleanupProtection:
    """Test that folders with supported files are protected"""

    def test_protects_folder_with_pdf(self, tmp_path):
        """Folder with .pdf file should be protected"""
        folder = tmp_path / "test_magazine"
        folder.mkdir()
        (folder / "issue.pdf").touch()
        (folder / "info.nfo").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert not is_safe
        assert "importable file" in reason.lower()
        assert metadata["supported_count"] == 1
        assert folder.exists()

    def test_protects_folder_with_epub(self, tmp_path):
        """Folder with .epub file should be protected"""
        folder = tmp_path / "test_book"
        folder.mkdir()
        (folder / "book.epub").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert not is_safe
        assert metadata["supported_count"] == 1

    def test_protects_folder_with_cbz(self, tmp_path):
        """Folder with .cbz file should be protected"""
        folder = tmp_path / "test_comic"
        folder.mkdir()
        (folder / "comic.cbz").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert not is_safe
        assert metadata["supported_count"] == 1

    def test_protects_folder_with_cbr(self, tmp_path):
        """Folder with .cbr file should be protected"""
        folder = tmp_path / "test_comic"
        folder.mkdir()
        (folder / "comic.cbr").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert not is_safe
        assert metadata["supported_count"] == 1

    def test_protects_folder_with_supported_file_in_subdirectory(self, tmp_path):
        """Folder with supported file in subdirectory should be protected"""
        folder = tmp_path / "parent"
        subfolder = folder / "subfolder"
        subfolder.mkdir(parents=True)
        (subfolder / "issue.pdf").touch()
        (folder / "readme.txt").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert not is_safe
        assert metadata["supported_count"] == 1


class TestFolderCleanupDeletion:
    """Test that folders with only non-supported files are deleted"""

    def test_deletes_folder_with_only_nfo(self, tmp_path):
        """Folder with only .nfo should be deleted"""
        folder = tmp_path / "bad_download"
        folder.mkdir()
        (folder / "info.nfo").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert is_safe
        assert "non-importable" in reason.lower()
        assert metadata["supported_count"] == 0
        assert metadata["other_count"] == 1

    def test_deletes_folder_with_only_txt_and_jpg(self, tmp_path):
        """Folder with only .txt and .jpg should be deleted"""
        folder = tmp_path / "bad_download"
        folder.mkdir()
        (folder / "readme.txt").touch()
        (folder / "cover.jpg").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert is_safe
        assert metadata["supported_count"] == 0
        assert metadata["other_count"] == 2

    def test_deletes_folder_with_video_files(self, tmp_path):
        """Folder with only video files should be deleted"""
        folder = tmp_path / "video_download"
        folder.mkdir()
        (folder / "sample.mp4").touch()
        (folder / "movie.avi").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert is_safe
        assert metadata["supported_count"] == 0
        assert metadata["other_count"] == 2

    def test_deletes_empty_folder(self, tmp_path):
        """Completely empty folder should be deleted"""
        folder = tmp_path / "empty"
        folder.mkdir()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        assert is_safe
        assert "empty" in reason.lower()
        assert metadata["supported_count"] == 0
        assert metadata["other_count"] == 0


class TestProtectedSystemFolders:
    """Test that system folders are always protected"""

    def test_protects_covers_folder(self, tmp_path):
        """/.covers folder should be protected"""
        covers = tmp_path / ".covers"
        covers.mkdir()
        (covers / "image.jpg").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(covers)

        assert not is_safe
        assert "protected" in reason.lower()
        assert ".covers" in reason

    def test_protects_cache_folder(self, tmp_path):
        """/.cache folder should be protected"""
        cache = tmp_path / ".cache"
        cache.mkdir()
        (cache / "temp.dat").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(cache)

        assert not is_safe
        assert "protected" in reason.lower()

    def test_protects_git_folder(self, tmp_path):
        """/.git folder should be protected"""
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(git)

        assert not is_safe
        assert "protected" in reason.lower()

    def test_protects_subfolder_inside_covers(self, tmp_path):
        """Folders inside /.covers should be protected"""
        covers = tmp_path / ".covers"
        subfolder = covers / "thumbnails"
        subfolder.mkdir(parents=True)
        (subfolder / "thumb.jpg").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(subfolder)

        assert not is_safe
        assert "protected" in reason.lower()


class TestDryRunMode:
    """Test that dry run mode doesn't actually delete anything"""

    def test_dry_run_reports_but_doesnt_delete(self, tmp_path):
        """Dry run should report what would be deleted without deleting"""
        folder = tmp_path / "bad_download"
        folder.mkdir()
        (folder / "info.nfo").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=True)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        # Should report as deleted but folder still exists
        assert stats["deleted"] == 1
        assert folder.exists()

    def test_live_mode_actually_deletes(self, tmp_path):
        """Live mode should actually delete folders"""
        folder = tmp_path / "bad_download"
        folder.mkdir()
        (folder / "info.nfo").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        # Should delete and folder should not exist
        assert stats["deleted"] == 1
        assert not folder.exists()


class TestExhaustiveScanning:
    """Test that scanning finds all files recursively"""

    def test_finds_files_in_deep_subdirectories(self, tmp_path):
        """Should find files multiple levels deep"""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "file.pdf").touch()

        root = tmp_path / "a"
        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(root)

        assert not is_safe
        assert metadata["supported_count"] == 1

    def test_scans_all_subdirectories_for_supported_files(self, tmp_path):
        """Should check all subdirectories, not just top level"""
        folder = tmp_path / "parent"
        sub1 = folder / "sub1"
        sub2 = folder / "sub2"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)

        # Top level has junk
        (folder / "readme.txt").touch()
        # But deep subdirectory has supported file
        (sub2 / "issue.pdf").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        is_safe, reason, metadata = cleanup._is_safe_to_delete(folder)

        # Should be protected because of the PDF in sub2
        assert not is_safe
        assert metadata["supported_count"] == 1


class TestCleanupStatistics:
    """Test that cleanup statistics are accurate"""

    def test_counts_deleted_folders(self, tmp_path):
        """Should accurately count deleted folders"""
        (tmp_path / "bad1").mkdir()
        (tmp_path / "bad1" / "info.nfo").touch()
        (tmp_path / "bad2").mkdir()
        (tmp_path / "bad2" / "readme.txt").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        assert stats["deleted"] == 2
        assert stats["errors"] == 0

    def test_counts_protected_folders(self, tmp_path):
        """Should accurately count protected folders"""
        good1 = tmp_path / "good1"
        good1.mkdir()
        (good1 / "issue.pdf").touch()

        good2 = tmp_path / "good2"
        good2.mkdir()
        (good2 / "book.epub").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        assert stats["protected"] == 2
        assert stats["deleted"] == 0

    def test_tracks_size_freed(self, tmp_path):
        """Should track total size of deleted files"""
        folder = tmp_path / "bad"
        folder.mkdir()
        file = folder / "large.txt"
        file.write_bytes(b"x" * 1000)  # 1000 bytes

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        assert stats["total_size_freed"] >= 1000


class TestComplexScenarios:
    """Test complex real-world scenarios"""

    def test_mixed_good_and_bad_folders(self, tmp_path):
        """Should handle mix of folders to keep and delete"""
        # Good folder with PDF
        good = tmp_path / "magazine"
        good.mkdir()
        (good / "issue.pdf").touch()
        (good / "info.nfo").touch()

        # Bad folder with only junk
        bad = tmp_path / "junk"
        bad.mkdir()
        (bad / "sample.mp4").touch()

        # Empty folder
        empty = tmp_path / "empty"
        empty.mkdir()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        assert stats["protected"] == 1  # magazine folder
        assert stats["deleted"] == 2  # junk and empty
        assert good.exists()
        assert not bad.exists()
        assert not empty.exists()

    def test_nested_downloads_structure(self, tmp_path):
        """Should handle nested download folder structures"""
        # Typical SABnzbd structure
        download = tmp_path / "Magazine.Name.2024"
        incomplete = download / "_UNPACK_Magazine.Name.2024"
        incomplete.mkdir(parents=True)

        # Create the actual file
        (download / "Magazine Name 2024.pdf").touch()
        # Temp unpacking folder with junk
        (incomplete / "temp.001").touch()
        (incomplete / "temp.002").touch()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        # Main folder should be protected (has PDF)
        # UNPACK subfolder should be deleted (only temp files)
        assert download.exists()
        assert (download / "Magazine Name 2024.pdf").exists()
        assert not incomplete.exists()

    def test_preserves_covers_cache_during_library_cleanup(self, tmp_path):
        """Should never touch .covers folder in library"""
        # Library structure
        covers = tmp_path / ".covers"
        covers.mkdir()
        (covers / "thumb1.jpg").touch()
        (covers / "thumb2.jpg").touch()

        # Bad folder that should be deleted
        bad = tmp_path / "empty_category"
        bad.mkdir()

        cleanup = FolderCleanup(str(tmp_path), str(tmp_path), dry_run=False)
        stats = cleanup.cleanup_directory(tmp_path, "test")

        # .covers should be completely untouched
        assert covers.exists()
        assert (covers / "thumb1.jpg").exists()
        assert (covers / "thumb2.jpg").exists()
        # Bad folder should be deleted
        assert not bad.exists()


class TestFullCleanupRun:
    """Test the complete cleanup run across both directories"""

    def test_cleans_both_downloads_and_library_dirs(self, tmp_path):
        """Should clean both downloads and organized directories"""
        downloads_dir = tmp_path / "downloads"
        library_dir = tmp_path / "organized"
        downloads_dir.mkdir()
        library_dir.mkdir()

        # Bad folder in downloads
        (downloads_dir / "bad1").mkdir()
        (downloads_dir / "bad1" / "junk.txt").touch()

        # Bad folder in organized
        (library_dir / "bad2").mkdir()
        (library_dir / "bad2" / "trash.nfo").touch()

        cleanup = FolderCleanup(str(downloads_dir), str(library_dir), dry_run=False)
        stats = cleanup.run()

        assert stats["total_deleted"] == 2
        assert stats["downloads"]["deleted"] == 1
        assert stats["organized"]["deleted"] == 1
