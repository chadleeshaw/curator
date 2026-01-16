"""
File importer - backward compatibility wrapper.
The actual implementation has moved to services/importer/importer.py
"""

from services.importer.importer import FileImporter

__all__ = ["FileImporter"]
