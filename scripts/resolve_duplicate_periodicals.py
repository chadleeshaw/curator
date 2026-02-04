#!/usr/bin/env python3
"""
Script to resolve duplicate filenames in downloads/library by scanning for unique metadata.

This script scans files on disk that have similar names (potential duplicates) and uses
text scan and OCR to discover unique metadata (dates, volumes, issue numbers). It can
then rename the files with the discovered metadata so they can be successfully imported.

The files are NOT in the database - that's the problem. They failed to import because
they would create duplicates. This script fixes them so they CAN be imported.

Usage:
    # Dry run - show what would be done
    .venv/bin/python scripts/resolve_duplicate_periodicals.py /path/to/folder

    # Actually rename files
    .venv/bin/python scripts/resolve_duplicate_periodicals.py /path/to/folder --apply

    # Scan downloads folder
    .venv/bin/python scripts/resolve_duplicate_periodicals.py ./local/downloads

    # Skip OCR (only do text scan, faster)
    .venv/bin/python scripts/resolve_duplicate_periodicals.py /path/to/folder --no-ocr

    # Verbose output
    .venv/bin/python scripts/resolve_duplicate_periodicals.py /path/to/folder -v
"""

import argparse
import logging
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.constants.date import NUMBER_TO_MONTH
from core.parsers import Parser
from services.ocr import OCRService
from services.text_scan_service import TextScanService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".cbz", ".cbr"}


def find_potential_duplicates(folder: Path) -> Dict[str, List[Path]]:
    """
    Find files that might be duplicates based on similar names.

    Groups files by a normalized key (title without date/issue info).

    Args:
        folder: Folder to scan

    Returns:
        Dict mapping normalized title to list of file paths
    """
    parser = Parser()
    groups = defaultdict(list)

    # Find all supported files
    all_files = []
    for ext in SUPPORTED_EXTENSIONS:
        all_files.extend(folder.rglob(f"*{ext}"))
        all_files.extend(folder.rglob(f"*{ext.upper()}"))

    logger.info(f"Found {len(all_files)} files to analyze")

    for file_path in all_files:
        try:
            # Parse the filename to extract title
            parsed = parser.parse_file(file_path)
            title = parsed.base_title or file_path.stem

            # Normalize the title for grouping
            # Remove common variations that don't affect identity
            normalized = title.lower().strip()
            normalized = re.sub(r"[_\-\.\s]+", " ", normalized)
            normalized = re.sub(r"\s+", " ", normalized).strip()

            groups[normalized].append(file_path)
        except Exception as e:
            logger.debug(f"Error parsing {file_path.name}: {e}")
            # Fall back to simple normalization
            normalized = file_path.stem.lower()
            normalized = re.sub(r"[_\-\.\s]+", " ", normalized)
            groups[normalized].append(file_path)

    # Filter to only groups with potential duplicates (2+ files)
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    return duplicates


def scan_file_for_metadata(file_path: Path, use_ocr: bool = True) -> Dict:
    """
    Scan a file for metadata using text scan and optionally OCR.

    Args:
        file_path: Path to the file
        use_ocr: Whether to try OCR if text scan doesn't find enough

    Returns:
        Dict with discovered metadata
    """
    result = {
        "text_scan": None,
        "ocr_scan": None,
        "issue_date": None,
        "year": None,
        "month": None,
        "volume": None,
        "issue_number": None,
        "source": None,
    }

    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return result

    # Try text scan first (faster)
    if file_path.suffix.lower() in [".pdf", ".epub"]:
        try:
            logger.debug(f"Running text scan for {file_path.name}")
            text_result = TextScanService.scan_document(str(file_path))
            result["text_scan"] = text_result

            if text_result.get("year"):
                result["year"] = text_result["year"]
                result["month"] = text_result.get("month")
                result["source"] = "text_scan"

                if result["month"]:
                    result["issue_date"] = datetime(result["year"], result["month"], 1)
                else:
                    result["issue_date"] = datetime(result["year"], 1, 1)

            if text_result.get("volume"):
                result["volume"] = text_result["volume"]
            if text_result.get("issue_number"):
                result["issue_number"] = text_result["issue_number"]

        except Exception as e:
            logger.debug(f"Text scan failed for {file_path.name}: {e}")

    # Try OCR if text scan didn't find a date and file is PDF
    if use_ocr and not result["issue_date"] and file_path.suffix.lower() == ".pdf":
        if OCRService.is_available():
            try:
                logger.debug(f"Running OCR scan for {file_path.name}")
                ocr_result = OCRService.analyze_cover(str(file_path))
                result["ocr_scan"] = ocr_result

                if ocr_result and ocr_result.get("year"):
                    result["year"] = ocr_result["year"]
                    result["month"] = ocr_result.get("month")
                    result["source"] = "ocr_scan"

                    if result["month"]:
                        result["issue_date"] = datetime(result["year"], result["month"], 1)
                    else:
                        result["issue_date"] = datetime(result["year"], 1, 1)

                if ocr_result:
                    if ocr_result.get("volume") and not result["volume"]:
                        result["volume"] = ocr_result["volume"]
                    if ocr_result.get("issue_number") and not result["issue_number"]:
                        result["issue_number"] = ocr_result["issue_number"]

            except Exception as e:
                logger.debug(f"OCR scan failed for {file_path.name}: {e}")
        else:
            logger.debug("OCR service not available")

    return result


def generate_new_filename(
    file_path: Path,
    base_title: str,
    scan_result: Dict,
) -> Optional[str]:
    """
    Generate a new filename based on discovered metadata.

    Args:
        file_path: Original file path
        base_title: Base title from parser
        scan_result: Result from scan_file_for_metadata

    Returns:
        New filename (without path), or None if no unique metadata found
    """
    parts = [base_title]

    # Add date if found
    if scan_result["year"]:
        if scan_result["month"]:
            month_name = NUMBER_TO_MONTH.get(scan_result["month"], str(scan_result["month"]))
            parts.append(f"{month_name} {scan_result['year']}")
        else:
            parts.append(str(scan_result["year"]))

    # Add volume if found
    if scan_result["volume"]:
        parts.append(f"Vol.{scan_result['volume']}")

    # Add issue number if found
    if scan_result["issue_number"]:
        parts.append(f"No.{scan_result['issue_number']}")

    # If we only have the title and no new metadata, return None
    if len(parts) == 1:
        return None

    # Build new filename
    new_stem = " - ".join(parts)
    # Sanitize for filesystem
    new_stem = re.sub(r'[<>:"/\\|?*]', "", new_stem)
    new_stem = re.sub(r"\s+", " ", new_stem).strip()

    return f"{new_stem}{file_path.suffix}"


def rename_file(file_path: Path, new_name: str, dry_run: bool = True) -> Optional[Path]:
    """
    Rename a file.

    Args:
        file_path: Current file path
        new_name: New filename (just the name, not full path)
        dry_run: If True, don't actually rename

    Returns:
        New path if renamed, None otherwise
    """
    new_path = file_path.parent / new_name

    # Handle collision
    if new_path.exists() and new_path != file_path:
        # Add a numeric suffix
        stem = new_path.stem
        suffix = new_path.suffix
        counter = 1
        while new_path.exists():
            new_path = file_path.parent / f"{stem} ({counter}){suffix}"
            counter += 1

    if new_path == file_path:
        return None

    logger.info(f"  Rename: {file_path.name}")
    logger.info(f"      ->  {new_path.name}")

    if not dry_run:
        try:
            shutil.move(str(file_path), str(new_path))
            return new_path
        except Exception as e:
            logger.error(f"  Failed to rename: {e}")
            return None

    return new_path


def resolve_duplicates(
    folder: Path,
    dry_run: bool = True,
    use_ocr: bool = True,
    verbose: bool = False,
):
    """
    Find potential duplicate files and resolve them using metadata scanning.

    Args:
        folder: Folder to scan
        dry_run: If True, only log what would be done
        use_ocr: Whether to use OCR for scanning
        verbose: Enable verbose output
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not folder.exists():
        logger.error(f"Folder not found: {folder}")
        return

    logger.info(f"Scanning folder: {folder}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
    logger.info(f"OCR: {'enabled' if use_ocr else 'disabled'}")

    # Find potential duplicates
    duplicates = find_potential_duplicates(folder)

    if not duplicates:
        logger.info("No potential duplicates found!")
        return

    total_groups = len(duplicates)
    total_files = sum(len(f) for f in duplicates.values())
    logger.info(f"Found {total_groups} groups with {total_files} potential duplicate files")

    parser = Parser()
    scanned_count = 0
    renamed_count = 0
    resolvable_count = 0

    separator = "=" * 60
    for normalized_title, files in duplicates.items():
        logger.info("\n%s", separator)
        logger.info("Group: '%s' (%d files)", normalized_title, len(files))

        # Track unique metadata found
        file_metadata = []

        for file_path in files:
            logger.info(f"  File: {file_path.name}")

            # Parse existing filename
            try:
                parsed = parser.parse_file(file_path)
                base_title = parsed.base_title or file_path.stem

                # Check if filename already has good metadata
                if parsed.issue_date and parsed.confidence != "low":
                    logger.info(f"    Already has date: {parsed.issue_date.strftime('%Y-%m')}")
                    file_metadata.append({
                        "path": file_path,
                        "base_title": base_title,
                        "scan_result": {
                            "year": parsed.year,
                            "month": parsed.issue_date.month if parsed.issue_date else None,
                            "volume": parsed.volume,
                            "issue_number": parsed.edition_number,
                            "issue_date": parsed.issue_date,
                            "source": "filename",
                        },
                        "needs_rename": False,
                    })
                    continue
            except Exception:
                base_title = file_path.stem

            # Scan for metadata
            scanned_count += 1
            scan_result = scan_file_for_metadata(file_path, use_ocr=use_ocr)

            # Report what was found
            if scan_result["source"]:
                findings = []
                if scan_result["year"]:
                    findings.append(f"year={scan_result['year']}")
                if scan_result["month"]:
                    findings.append(f"month={scan_result['month']}")
                if scan_result["volume"]:
                    findings.append(f"vol={scan_result['volume']}")
                if scan_result["issue_number"]:
                    findings.append(f"issue={scan_result['issue_number']}")
                logger.info(f"    Scanned ({scan_result['source']}): {', '.join(findings)}")
            else:
                logger.info("    No metadata found from scanning")

            file_metadata.append({
                "path": file_path,
                "base_title": base_title,
                "scan_result": scan_result,
                "needs_rename": scan_result["source"] is not None,
            })

        # Check if we can resolve this group
        unique_dates = set()
        unique_volumes = set()
        unique_issues = set()

        for fm in file_metadata:
            sr = fm["scan_result"]
            if sr.get("issue_date"):
                unique_dates.add(sr["issue_date"])
            if sr.get("volume"):
                unique_volumes.add(sr["volume"])
            if sr.get("issue_number"):
                unique_issues.add(sr["issue_number"])

        can_resolve = (
            len(unique_dates) >= len(files)
            or len(unique_volumes) >= len(files)
            or len(unique_issues) >= len(files)
        )

        if can_resolve:
            resolvable_count += 1
            logger.info(
                f"  -> RESOLVABLE: {len(unique_dates)} dates, "
                f"{len(unique_volumes)} volumes, {len(unique_issues)} issues"
            )
        elif len(unique_dates) > 1 or len(unique_volumes) > 1 or len(unique_issues) > 1:
            logger.info(
                f"  -> PARTIALLY resolvable: {len(unique_dates)} dates, "
                f"{len(unique_volumes)} volumes, {len(unique_issues)} issues"
            )
        else:
            logger.info("  -> NOT resolvable: no unique metadata found")
            continue

        # Rename files that need it
        for fm in file_metadata:
            if not fm["needs_rename"]:
                continue

            new_name = generate_new_filename(
                fm["path"],
                fm["base_title"],
                fm["scan_result"],
            )

            if new_name and new_name != fm["path"].name:
                if rename_file(fm["path"], new_name, dry_run=dry_run):
                    renamed_count += 1

    logger.info("\n%s", separator)
    logger.info("Summary:")
    logger.info(f"  Total duplicate groups: {total_groups}")
    logger.info(f"  Total files in groups: {total_files}")
    logger.info(f"  Files scanned: {scanned_count}")
    logger.info(f"  Groups resolvable: {resolvable_count}")
    logger.info(f"  Files renamed: {renamed_count}")

    if dry_run:
        logger.info("\nDry run - no changes made. Run with --apply to rename files.")
    else:
        logger.info(f"\nRenamed {renamed_count} files. You can now re-import the folder.")


def main():
    parser = argparse.ArgumentParser(
        description="Resolve duplicate files by scanning for unique metadata and renaming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder to scan for duplicates",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files (default is dry run)",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Skip OCR scanning (only do text scan, faster)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    resolve_duplicates(
        folder=args.folder,
        dry_run=not args.apply,
        use_ocr=not args.no_ocr,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
