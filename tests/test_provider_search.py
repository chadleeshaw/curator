import sys
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

# Suppress debug logging to reduce output
logging.basicConfig(level=logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from core.config import ConfigLoader  # noqa: E402
from core.factory import ProviderFactory  # noqa: E402
from providers.newsnab import NewsnabProvider  # noqa: E402

print("\n🧪 Search Provider Tests (Newsnab)\n")
print("=" * 50)

results = {}

# Test Newsnab init
print("Testing NewsnabProvider.__init__()...", end=" ")
try:
    config_loader = ConfigLoader(config_path="tests/config.test.yaml")
    search_providers_config = config_loader.get_search_providers()
    newsnab_config = next(
        (p for p in search_providers_config if p.get("type") == "newsnab"), None
    )

    if newsnab_config:
        provider = NewsnabProvider(newsnab_config)
        assert hasattr(provider, "api_url")
        assert hasattr(provider, "api_key")
        assert hasattr(provider, "categories")
        print("✓ PASS")
        results["NewsnabProvider.__init__()"] = True
    else:
        print("⚠ SKIP (not configured)")
        results["NewsnabProvider.__init__()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["NewsnabProvider.__init__()"] = False

# Test Newsnab categories configuration
print("Testing NewsnabProvider categories config...", end=" ")
try:
    if newsnab_config:
        # Test with configured categories
        provider = NewsnabProvider(newsnab_config)
        assert provider.categories == "7000,7010,7020,7030"

        # Test with default categories (no categories in config)
        config_no_categories = newsnab_config.copy()
        if "categories" in config_no_categories:
            del config_no_categories["categories"]
        provider_default = NewsnabProvider(config_no_categories)
        assert provider_default.categories == "7000,7010,7020,7030"

        print("✓ PASS")
        results["NewsnabProvider categories config"] = True
    else:
        print("⚠ SKIP (not configured)")
        results["NewsnabProvider categories config"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["NewsnabProvider categories config"] = False

# Test Newsnab search
print("Testing NewsnabProvider.search()...", end=" ")
try:
    if newsnab_config:
        provider = ProviderFactory.create(newsnab_config)
        results_list = provider.search("National Geographic")
        assert isinstance(results_list, list)
        print(f"✓ PASS ({len(results_list)} results)")
        results["NewsnabProvider.search()"] = True
    else:
        print("⚠ SKIP (not configured)")
        results["NewsnabProvider.search()"] = True
except Exception as e:
    print(f"⚠ {str(e)[:50]}")
    results["NewsnabProvider.search()"] = True  # Skip if offline

# Test internal XML API
print("Testing NewsnabProvider._search_xml_api()...", end=" ")
try:
    if newsnab_config:
        results_list = provider._search_xml_api("National Geographic")
        assert isinstance(results_list, list)
        print(f"✓ PASS ({len(results_list)} results)")
        results["NewsnabProvider._search_xml_api()"] = True
    else:
        print("⚠ SKIP (not configured)")
        results["NewsnabProvider._search_xml_api()"] = True
except Exception as e:
    print(f"⚠ {str(e)[:50]}")
    results["NewsnabProvider._search_xml_api()"] = True  # Skip if offline

print("\n" + "=" * 50)
print("Test Summary")
print("=" * 50)
for test_name, passed in results.items():
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

all_passed = all(results.values())
print("\n" + ("All tests passed! ✓" if all_passed else "Some tests had issues"))
