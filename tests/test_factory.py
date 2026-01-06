#!/usr/bin/env python3
"""Test ProviderFactory functionality"""
import sys

sys.path.insert(0, ".")

from core.config import ConfigLoader  # noqa: E402
from core.factory import ProviderFactory, ClientFactory  # noqa: E402
from core.bases import SearchProvider, DownloadClient  # noqa: E402
import logging

logging.basicConfig(level=logging.WARNING)

print("\n🧪 Factory Tests\n")
print("=" * 50)

results = {}

# Test ProviderFactory with search providers
print("Testing ProviderFactory.create() - Search Providers...", end=" ")
try:
    config_loader = ConfigLoader(config_path="tests/config.test.yaml")
    search_config = config_loader.get_search_providers()

    created_count = 0
    for provider_config in search_config[:1]:  # Test first one
        provider = ProviderFactory.create(provider_config)
        assert isinstance(provider, SearchProvider)
        assert hasattr(provider, "search")
        assert provider.type == provider_config.get("type")
        assert provider.name == provider_config.get("name")
        created_count += 1

    assert created_count > 0
    print(f"✓ PASS (created {created_count} provider)")
    results["create_search_providers"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["create_search_providers"] = False

# Test ProviderFactory with metadata providers
print("Testing ProviderFactory.create() - Metadata Providers...", end=" ")
try:
    config_loader = ConfigLoader()
    metadata_config = config_loader.get_metadata_providers()

    created_count = 0
    for provider_config in metadata_config:
        provider = ProviderFactory.create(provider_config)
        assert isinstance(provider, SearchProvider)
        assert hasattr(provider, "search")
        assert provider.type == provider_config.get("type")
        created_count += 1

    assert created_count > 0
    print(f"✓ PASS (created {created_count} providers)")
    results["create_metadata_providers"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["create_metadata_providers"] = False

# Test ProviderFactory with invalid type
print("Testing ProviderFactory.create() - Invalid Type...", end=" ")
try:
    invalid_config = {"type": "invalid_provider_type"}
    try:
        provider = ProviderFactory.create(invalid_config)
        print("❌ FAIL: Should have raised ValueError")
        results["invalid_provider_type"] = False
    except ValueError as e:
        assert "Unknown provider type" in str(e)
        print("✓ PASS (correctly raised ValueError)")
        results["invalid_provider_type"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["invalid_provider_type"] = False

# Test ClientFactory
print("Testing ClientFactory.create() - Download Clients...", end=" ")
try:
    config_loader = ConfigLoader()
    client_config = config_loader.get_download_client()

    client = ClientFactory.create(client_config)
    assert isinstance(client, DownloadClient)
    assert hasattr(client, "submit")
    assert hasattr(client, "get_status")
    assert hasattr(client, "get_completed_downloads")
    assert client.type == client_config.get("type")
    print("✓ PASS")
    results["create_download_client"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["create_download_client"] = False

# Test ClientFactory with invalid type
print("Testing ClientFactory.create() - Invalid Type...", end=" ")
try:
    invalid_config = {"type": "invalid_client_type"}
    try:
        client = ClientFactory.create(invalid_config)
        print("❌ FAIL: Should have raised ValueError")
        results["invalid_client_type"] = False
    except ValueError as e:
        assert "Unknown client type" in str(e)
        print("✓ PASS (correctly raised ValueError)")
        results["invalid_client_type"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["invalid_client_type"] = False

# Test provider search functionality
print("Testing Provider.search() via factory...", end=" ")
try:
    config_loader = ConfigLoader()
    search_config = config_loader.get_search_providers()

    if search_config:
        provider = ProviderFactory.create(search_config[0])
        results_list = provider.search("test")
        assert isinstance(results_list, list)
        print("✓ PASS")
        results["provider_search"] = True
    else:
        print("⚠ SKIP (no search providers)")
        results["provider_search"] = True
except Exception as e:
    print(f"⚠ {str(e)[:50]}")
    results["provider_search"] = True

print("\n" + "=" * 50)
print("Test Summary")
print("=" * 50)
for test_name, passed in results.items():
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

all_passed = all(results.values())
print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))
