"""
Download manager - backward compatibility wrapper.
The actual implementation has moved to services/download/manager.py
"""

# Re-export everything from the new package location for backward compatibility
from services.download.manager import *  # noqa: F401, F403
