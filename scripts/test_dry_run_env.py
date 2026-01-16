#!/usr/bin/env python3
"""
Test script to verify dry_run environment variable logic.

This demonstrates the behavior of the reorganization endpoint when
checking the CURATOR_DRY_RUN environment variable.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def get_dry_run_value(explicit_value=None):
    """
    Simulate the dry_run logic from reorganize_library endpoint.

    Args:
        explicit_value: Explicitly provided dry_run value (or None)

    Returns:
        Final dry_run value to use
    """
    # Determine dry_run value: parameter > env var > default False
    if explicit_value is None:
        dry_run_env = os.environ.get("CURATOR_DRY_RUN", "false").lower()
        dry_run = dry_run_env in ("true", "1", "yes")
    else:
        dry_run = explicit_value

    return dry_run


# Test cases
test_cases = [
    # (explicit_param, env_var_value, expected_result, description)
    (None, None, False, "No param, no env var -> False (default)"),
    (None, "true", True, "No param, env=true -> True"),
    (None, "false", False, "No param, env=false -> False"),
    (None, "1", True, "No param, env=1 -> True"),
    (None, "yes", True, "No param, env=yes -> True"),
    (None, "TRUE", True, "No param, env=TRUE (case insensitive) -> True"),
    (True, None, True, "Explicit True, no env -> True (param wins)"),
    (False, "true", False, "Explicit False, env=true -> False (param wins)"),
    (True, "false", True, "Explicit True, env=false -> True (param wins)"),
]

print("=" * 80)
print("  DRY_RUN ENVIRONMENT VARIABLE TEST")
print("=" * 80)
print()

passed = 0
failed = 0

for explicit_param, env_value, expected, description in test_cases:
    # Set or clear environment variable
    if env_value is not None:
        os.environ["CURATOR_DRY_RUN"] = env_value
    else:
        os.environ.pop("CURATOR_DRY_RUN", None)

    result = get_dry_run_value(explicit_param)
    status = "✓" if result == expected else "✗"

    if result == expected:
        passed += 1
    else:
        failed += 1

    print(f"{status} {description}")
    print(f"  Param: {explicit_param}, Env: {env_value}")
    print(f"  Expected: {expected}, Got: {result}")

    if result != expected:
        print("  ❌ FAILED")

    print()

# Clean up
os.environ.pop("CURATOR_DRY_RUN", None)

print("=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 80)

print("\nBehavior Summary:")
print("  1. If dry_run parameter is explicitly provided (True/False), use it")
print("  2. Otherwise, check CURATOR_DRY_RUN environment variable:")
print("     - 'true', '1', 'yes' (case insensitive) -> dry_run=True")
print("     - Any other value or not set -> dry_run=False (default)")
print()

sys.exit(0 if failed == 0 else 1)
