#!/usr/bin/env python3
"""Test ConfigLoader functionality"""
import sys
sys.path.insert(0, '.')

from core.config import ConfigLoader  # noqa: E402
import logging

logging.basicConfig(level=logging.WARNING)

print("\n🧪 ConfigLoader Tests\n")
print("=" * 50)

results = {}

# Test initialization
print("Testing ConfigLoader.__init__()...", end=" ")
try:
    config_loader = ConfigLoader()
    assert config_loader.config is not None
    assert isinstance(config_loader.config, dict)
    print("✓ PASS")
    results["__init__()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["__init__()"] = False

# Test get_search_providers
print("Testing get_search_providers()...", end=" ")
try:
    providers = config_loader.get_search_providers()
    assert isinstance(providers, list)
    assert len(providers) > 0
    assert all(isinstance(p, dict) for p in providers)
    assert all("type" in p for p in providers)
    print(f"✓ PASS ({len(providers)} providers)")
    results["get_search_providers()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_search_providers()"] = False

# Test get_metadata_providers
print("Testing get_metadata_providers()...", end=" ")
try:
    providers = config_loader.get_metadata_providers()
    assert isinstance(providers, list)
    assert len(providers) > 0
    assert all(isinstance(p, dict) for p in providers)
    assert all("type" in p for p in providers)
    print(f"✓ PASS ({len(providers)} providers)")
    results["get_metadata_providers()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_metadata_providers()"] = False

# Test get_download_client
print("Testing get_download_client()...", end=" ")
try:
    client = config_loader.get_download_client()
    assert isinstance(client, dict)
    assert "type" in client
    assert client["type"] == "sabnzbd"
    print("✓ PASS")
    results["get_download_client()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_download_client()"] = False

# Test get_storage
print("Testing get_storage()...", end=" ")
try:
    storage = config_loader.get_storage()
    assert isinstance(storage, dict)
    assert "db_path" in storage
    assert "download_dir" in storage
    assert "organize_dir" in storage
    print("✓ PASS")
    results["get_storage()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_storage()"] = False

# Test get_matching
print("Testing get_matching()...", end=" ")
try:
    matching = config_loader.get_matching()
    assert isinstance(matching, dict)
    assert "fuzzy_threshold" in matching
    print("✓ PASS")
    results["get_matching()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_matching()"] = False

# Test get_logging
print("Testing get_logging()...", end=" ")
try:
    logging_config = config_loader.get_logging()
    assert isinstance(logging_config, dict)
    assert "level" in logging_config
    print("✓ PASS")
    results["get_logging()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_logging()"] = False

# Test get_all_config
print("Testing get_all_config()...", end=" ")
try:
    all_config = config_loader.get_all_config()
    assert isinstance(all_config, dict)
    assert "search_providers" in all_config
    assert "metadata_providers" in all_config
    assert "download_client" in all_config
    print("✓ PASS")
    results["get_all_config()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["get_all_config()"] = False

# Test reload_config
print("Testing reload_config()...", end=" ")
try:
    config_loader.reload_config()
    assert config_loader.config is not None
    print("✓ PASS")
    results["reload_config()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["reload_config()"] = False

print("\n" + "=" * 50)
print("Test Summary")
print("=" * 50)
for test_name, passed in results.items():
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

all_passed = all(results.values())
print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))
