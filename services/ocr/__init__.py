"""
OCR services package - text extraction and queue management
"""

# Import main classes from submodules
from .service import OCRService
from .queue import OCRQueueService, _apply_scan_metadata_to_magazine

# Re-export for backward compatibility
__all__ = [
    "OCRService",
    "OCRQueueService",
    "_apply_scan_metadata_to_magazine",
]
