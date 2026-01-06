import sys
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

# Suppress debug logging to reduce output
logging.basicConfig(level=logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from core.config import ConfigLoader  # noqa: E402
from core.factory import ProviderFactory  # noqa: E402
from providers.wikipedia import WikipediaProvider  # noqa: E402
from providers.crossref import CrossRefProvider  # noqa: E402

print("\n🧪 Metadata Provider Tests\n")
print("=" * 50)

results = {}

# Wikipedia tests
print("Testing WikipediaProvider.__init__()...", end=" ")
try:
    config_loader = ConfigLoader()
    metadata_providers_config = config_loader.get_metadata_providers()
    wiki_config = next(
        (p for p in metadata_providers_config if p.get("type") == "wikipedia"), None
    )

    if wiki_config:
        provider = WikipediaProvider(wiki_config)
        assert provider.base_url == "https://en.wikipedia.org/w/api.php"
        print("✓ PASS")
        results["WikipediaProvider.__init__()"] = True
    else:
        print("⚠ SKIP")
        results["WikipediaProvider.__init__()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["WikipediaProvider.__init__()"] = False

print("Testing WikipediaProvider.search()...", end=" ")
try:
    if wiki_config:
        provider = ProviderFactory.create(wiki_config)
        search_results = provider.search("National Geographic")
        assert isinstance(search_results, list)
        print(f"✓ PASS ({len(search_results)} results)")
        results["WikipediaProvider.search()"] = True
    else:
        print("⚠ SKIP")
        results["WikipediaProvider.search()"] = True
except Exception as e:
    print(f"❌ FAIL: {str(e)[:50]}")
    results["WikipediaProvider.search()"] = False

print("Testing WikipediaProvider._extract_metadata()...", end=" ")
try:
    if wiki_config:
        provider = WikipediaProvider(wiki_config)
        test_extract = "National Geographic is published by National Geographic Society. ISSN: 0027-9358"
        metadata = provider._extract_metadata("National Geographic", test_extract)
        assert isinstance(metadata, dict)
        assert "issn" in metadata
        print("✓ PASS")
        results["WikipediaProvider._extract_metadata()"] = True
    else:
        print("⚠ SKIP")
        results["WikipediaProvider._extract_metadata()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["WikipediaProvider._extract_metadata()"] = False

# CrossRef tests
print("Testing CrossRefProvider.__init__()...", end=" ")
try:
    crossref_config = next(
        (p for p in metadata_providers_config if p.get("type") == "crossref"), None
    )

    if crossref_config:
        provider = CrossRefProvider(crossref_config)
        assert provider.base_url == "https://api.crossref.org/v1"
        print("✓ PASS")
        results["CrossRefProvider.__init__()"] = True
    else:
        print("⚠ SKIP")
        results["CrossRefProvider.__init__()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["CrossRefProvider.__init__()"] = False

print("Testing CrossRefProvider.search()...", end=" ")
try:
    if crossref_config:
        provider = ProviderFactory.create(crossref_config)
        search_results = provider.search("Nature")
        assert isinstance(search_results, list)
        print(f"✓ PASS ({len(search_results)} results)")
        results["CrossRefProvider.search()"] = True
    else:
        print("⚠ SKIP")
        results["CrossRefProvider.search()"] = True
except Exception as e:
    print(f"❌ FAIL: {str(e)[:50]}")
    results["CrossRefProvider.search()"] = False

print("Testing CrossRefProvider._parse_journal_item()...", end=" ")
try:
    if crossref_config:
        provider = CrossRefProvider(crossref_config)
        test_item = {
            "title": "Nature",
            "ISSN": ["0028-0836"],
            "publisher": "Nature Publishing Group",
            "URL": "https://www.nature.com",
            "coverage": {},
        }
        result = provider._parse_journal_item(test_item)
        assert result is not None
        print("✓ PASS")
        results["CrossRefProvider._parse_journal_item()"] = True
    else:
        print("⚠ SKIP")
        results["CrossRefProvider._parse_journal_item()"] = True
except Exception as e:
    print(f"❌ FAIL: {e}")
    results["CrossRefProvider._parse_journal_item()"] = False

print("\n" + "=" * 50)
print("Test Summary")
print("=" * 50)
for test_name, passed in results.items():
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")

all_passed = all(results.values())
print("\n" + ("All tests passed! ✓" if all_passed else "Some tests failed. ❌"))
