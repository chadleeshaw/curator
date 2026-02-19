"""Auto-apply the 'slow' marker to every test in the performance directory.

This keeps CI fast: the CI command runs with -m "not slow", so all benchmark
and accuracy tests here are skipped unless explicitly opted-in locally or in
a dedicated performance job.
"""

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "performance" in str(item.fspath):
            item.add_marker(pytest.mark.slow)
