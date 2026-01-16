"""
OCR service - backward compatibility wrapper.
The actual implementation has moved to services/ocr/service.py
"""

# Re-export everything from the new package location for backward compatibility
from services.ocr.service import *  # noqa: F401, F403
