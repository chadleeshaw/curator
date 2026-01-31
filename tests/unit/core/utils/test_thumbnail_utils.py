#!/usr/bin/env python3
"""
Test suite for core.thumbnail_utils module
"""

from pathlib import Path
from PIL import Image

# Path setup handled by conftest.py

from core.utils.thumbnail import generate_thumbnail, get_or_create_thumbnail


def test_generate_thumbnail_from_path():
    """Test generating thumbnail from image path"""
    import tempfile

    # Create a test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (1000, 1000), color="red")
        img.save(f.name, "PNG")
        test_path = Path(f.name)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        thumbnail_path = generate_thumbnail(test_path, output_dir)

        assert thumbnail_path is not None
        assert thumbnail_path.exists()

        # Check thumbnail dimensions
        thumb_img = Image.open(thumbnail_path)
        assert thumb_img.width <= 400
        assert thumb_img.height <= 600

    # Cleanup
    test_path.unlink()


def test_generate_thumbnail_maintains_aspect_ratio():
    """Test that thumbnail maintains aspect ratio"""
    import tempfile

    # Create a rectangular image (2:1 aspect ratio)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img = Image.new("RGB", (1000, 500), color="blue")
        img.save(f.name, "PNG")
        test_path = Path(f.name)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        thumbnail_path = generate_thumbnail(test_path, output_dir, max_width=200, max_height=200)

        if thumbnail_path:
            thumb_img = Image.open(thumbnail_path)
            # Aspect ratio should be maintained (2:1)
            aspect_ratio = thumb_img.width / thumb_img.height
            assert 1.9 < aspect_ratio < 2.1  # Allow small rounding differences

    # Cleanup
    test_path.unlink()


def test_get_or_create_thumbnail():
    """Test get_or_create_thumbnail function"""
    import tempfile

    # Create a test image in organized structure
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        covers_dir = base_dir / "covers"
        covers_dir.mkdir()

        test_image = covers_dir / "test.jpg"
        img = Image.new("RGB", (800, 600), color="yellow")
        img.save(test_image, "JPEG")

        # Should create thumbnail
        thumbnail_path = get_or_create_thumbnail(test_image)

        assert thumbnail_path is not None
        assert thumbnail_path.exists()
