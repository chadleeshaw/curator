"""
OCR queue service - backward compatibility wrapper.
The actual implementation has moved to services/ocr/queue.py
"""

# Re-export everything from the new package location for backward compatibility
from services.ocr.queue import *  # noqa: F401, F403
