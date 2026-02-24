"""
Text processing utilities for titles, filenames, and metadata.
"""

import re


def clean_title(title: str, remove_descriptors: bool = False) -> str:
    """
    Clean a title string by removing common artifacts.

    Args:
        title: Raw title string
        remove_descriptors: If True, also remove words like "magazine", "quarterly"

    Returns:
        Cleaned title string
    """
    # Replace dots and underscores with spaces
    cleaned = title.replace(".", " ").replace("_", " ")

    # Remove release group tags [xxx] and (xxx)
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned)

    # Remove language codes (but not country codes like UK)
    cleaned = re.sub(
        r"[\s]+(?:de|en|fr|es|it|pt|ru|nl|pl|sv|no|fi|da|ja|ko|zh|ar)(?:[\s]|$)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    if remove_descriptors:
        cleaned = re.sub(
            r"\b(?:quarterly|monthly|weekly|magazine|the|hacker|hybrid|digital|print)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    # NOTE: Do NOT remove "Special Edition" here - it needs to be preserved
    # for title_matcher.extract_base_title() to detect special editions properly

    # Clean trailing dashes and normalize whitespace
    cleaned = re.sub(r"\s*-\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned
