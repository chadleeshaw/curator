"""
Integration test demonstrating country-to-language inference in action.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.unified_parser import UnifiedParser


def demonstrate_country_language_inference():
    """Demonstrate the automatic language inference from country detection."""
    parser = UnifiedParser()

    test_cases = [
        ("Wired [DE] January 2024", "DE", "German"),
        ("National Geographic [FR] December 2024", "FR", "French"),
        ("Time [ES] 2024", "ES", "Spanish"),
        ("PC Gamer [PT] No.405 2024", "PT", "Portuguese"),
        ("Magazine [BR] 2024", "BR", "Portuguese"),
        ("Tech Weekly [JP] 2024", "JP", "Japanese"),
        ("Gaming [CN] December 2024", "CN", "Chinese"),
        ("Computer World [PL] 2024", "PL", "Polish"),
        ("Science Monthly [UK] 2024", "UK", "English"),
        ("Wired [US] January 2024", "US", "English"),
    ]

    print("\n" + "="*80)
    print("COUNTRY-TO-LANGUAGE INFERENCE DEMONSTRATION")
    print("="*80 + "\n")

    for title, expected_country, expected_language in test_cases:
        result = parser.parse_search_result(
            title=title,
            url="http://example.com",
            provider="test"
        )

        status = "✓" if result.language == expected_language else "✗"
        print(f"{status} {title}")
        print(f"  Country: {result.country} (expected: {expected_country})")
        print(f"  Language: {result.language} (expected: {expected_language})")
        print()

    print("="*80)
    print("\nBENEFITS:")
    print("- No need to explicitly mark language in filenames when country is present")
    print("- Works for 100+ countries with their primary languages")
    print("- Explicit language keywords still take priority when present")
    print("="*80 + "\n")


if __name__ == "__main__":
    demonstrate_country_language_inference()
