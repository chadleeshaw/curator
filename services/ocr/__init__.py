"""
OCR services package - text extraction and queue management
"""


def __getattr__(name):
    if name == "OCRService":
        from .service import OCRService

        return OCRService
    elif name == "OCRQueueService":
        from .queue import OCRQueueService

        return OCRQueueService
    elif name == "_apply_scan_metadata_to_periodical":
        from .queue import _apply_scan_metadata_to_periodical

        return _apply_scan_metadata_to_periodical
    raise AttributeError(f"module 'services.ocr' has no attribute '{name}'")
