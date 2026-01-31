"""
PDF reader utilities for page-by-page reading.

DEPRECATED: This module has been moved to core.utils.readers.pdf
Import from the new location instead:
    from core.utils.readers.pdf import get_pdf_metadata, get_pdf_page, get_pdf_page_thumbnail
"""

# Re-export from new location for backward compatibility
from core.utils.readers.pdf import get_pdf_metadata, get_pdf_page, get_pdf_page_thumbnail

__all__ = ["get_pdf_metadata", "get_pdf_page", "get_pdf_page_thumbnail"]
