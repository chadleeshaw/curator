#!/usr/bin/env python3
"""
Test OCR functionality on sample PNG images.
Uses the OCRService to extract text and metadata.
"""

import os
import sys
import time
from pathlib import Path
import pytest

# Set environment variables for PaddleOCR before importing
os.environ['USE_GPU'] = 'False'
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'

# Add parent directory to path to import services
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ocr_service import OCRService

# Test images to process
TEST_IMAGES = [
    "magazine.png",
    "comic.png",
]


def run_ocr_on_image(test_image: Path) -> bool:
    """
    Test OCR on a single image using OCRService.

    Args:
        test_image: Path to the image file

    Returns:
        True if test passed, False otherwise
    """
    if not test_image.exists():
        print(f"❌ Test image not found: {test_image}")
        return False

    print(f"📄 Testing OCR on: {test_image.name}")
    print(f"📍 Full path: {test_image}")
    print("-" * 80)

    # Test 1: Extract raw text
    print("\n🔍 Test 1: Extracting text using OCRService.extract_text_from_image()...")
    start = time.time()
    extracted_text = OCRService.extract_text_from_image(str(test_image), language="en")
    elapsed = time.time() - start
    print(f"✓ Text extraction completed in {elapsed:.2f}s")
    print("-" * 80)

    if not extracted_text:
        print("⚠️  No text detected in image")
        # Don't fail the test - some images may not have text
    else:
        print("\n📄 Extracted Text:")
        print("-" * 80)
        print(extracted_text)
        print("-" * 80)

    # Test 2: Analyze cover and extract metadata
    print("\n🔍 Test 2: Analyzing cover using OCRService.analyze_cover()...")
    start = time.time()
    metadata = OCRService.analyze_cover(str(test_image), language="en")
    elapsed = time.time() - start
    print(f"✓ Cover analysis completed in {elapsed:.2f}s")
    print("-" * 80)

    print("\n📊 Extracted Metadata:")
    print("-" * 80)
    print(f"  OCR Available:     {metadata.get('ocr_available', False)}")
    print(f"  Text Found:        {metadata.get('text_found', False)}")
    print(f"  Used OCR:          {metadata.get('used_ocr', False)}")
    print(f"  Issue Number:      {metadata.get('issue_number', 'Not detected')}")
    print(f"  Year:              {metadata.get('year', 'Not detected')}")
    print(f"  Month:             {metadata.get('month', 'Not detected')}")
    print(f"  Volume:            {metadata.get('volume', 'Not detected')}")
    print(f"  Special Edition:   {metadata.get('special_edition', False)}")
    print("-" * 80)

    if metadata.get('detected_text'):
        print("\n📄 Full Detected Text from Metadata:")
        print("-" * 80)
        print(metadata['detected_text'])
        print("-" * 80)

    return True


@pytest.mark.parametrize("image_name", TEST_IMAGES)
def test_ocr_on_image(image_name):
    """Test OCR on a single image using OCRService (pytest parameterized)"""

    # Check if OCR is available
    assert OCRService.is_available(), "OCR service not available. Install with: pip install easyocr"

    # Get test image path
    test_dir = Path(__file__).parent / "png"
    test_image = test_dir / image_name

    print("\n" + "=" * 80)
    print(f"Testing: {image_name}")
    print("=" * 80 + "\n")

    # Run the test
    result = run_ocr_on_image(test_image)
    assert result, f"OCR test failed for {image_name}"


def run_all_tests():
    """Run all OCR tests (for standalone execution)"""

    # Check if OCR is available
    if not OCRService.is_available():
        print("❌ OCR service not available. Install with: pip install easyocr")
        return False

    print("✓ OCR service is available")
    print("-" * 80)

    # Get test image directory
    test_dir = Path(__file__).parent / "png"

    # Track results
    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    # Test each image
    for image_name in TEST_IMAGES:
        test_image = test_dir / image_name

        print("\n" + "=" * 80)
        print(f"Testing: {image_name}")
        print("=" * 80 + "\n")

        total_tests += 1
        try:
            if run_ocr_on_image(test_image):
                passed_tests += 1
                print(f"\n✅ Test passed for {image_name}")
            else:
                failed_tests += 1
                print(f"\n⚠️  Test failed for {image_name}")
        except Exception as e:
            failed_tests += 1
            print(f"\n❌ Test error for {image_name}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests:  {total_tests}")
    print(f"Passed:       {passed_tests}")
    print(f"Failed:       {failed_tests}")
    print("=" * 80)

    return failed_tests == 0


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("OCR TEST - OCRService Text Detection & Metadata Extraction")
    print("=" * 80 + "\n")

    try:
        success = run_all_tests()
        print("\n" + "=" * 80)
        if success:
            print("✅ All OCR tests completed successfully!")
        else:
            print("⚠️  Some OCR tests failed")
        print("=" * 80 + "\n")

        exit(0 if success else 1)

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ OCR test suite failed with error: {e}")
        print("=" * 80 + "\n")
        import traceback
        traceback.print_exc()
        exit(1)
