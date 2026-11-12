"""Behavior tests for EPUB, comic, and PDF readers plus EPUB/CBZ helpers.

Files are built in ``tmp_path``. OCR and tesseract are not used.

``core.utils.cbz._get_sorted_image_files`` documents numeric page order and then
sorts names with ``list.sort``. ``page10.png`` is therefore the cover when the
archive also contains ``page2.png``. ``core.utils.readers.comic`` lists
``page2.png`` first.
"""

import zipfile
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from PIL import Image
from ebooklib import epub

from core.utils.cbz import (
    _get_sorted_image_files,
    extract_cover_from_cbr,
    extract_cover_from_cbz,
    validate_cbr,
    validate_cbz,
)
from core.utils.epub import extract_cover_from_epub, extract_text_from_epub
from core.utils.readers.comic import (
    get_comic_metadata,
    get_comic_page,
    get_comic_page_thumbnail,
    get_sorted_image_files,
)
from core.utils.readers.epub import get_epub_chapter, get_epub_image, get_epub_metadata
from core.utils.readers.pdf import get_pdf_metadata, get_pdf_page, get_pdf_page_thumbnail


def _jpeg_bytes(color, size=(8, 8)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _png_bytes(color, size=(12, 20), mode="RGB") -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _write_cbz(path: Path, files: dict) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def _write_epub(path: Path, title: str, author: str, documents: list, images: list) -> None:
    book = epub.EpubBook()
    book.set_identifier("reader-test")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    items = []
    for file_name, html in documents:
        document = epub.EpubHtml(title=file_name, file_name=file_name, lang="en")
        document.content = html
        book.add_item(document)
        items.append(document)
    for file_name, data, media_type in images:
        image = epub.EpubImage()
        image.file_name = file_name
        image.media_type = media_type
        image.content = data
        book.add_item(image)
    if documents:
        book.toc = (epub.Link(documents[0][0], "Start", "start"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(path), book)


def _html(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def _open_image(data: bytes) -> Image.Image:
    assert data[:2] == b"\xff\xd8"
    image = Image.open(BytesIO(data))
    image.load()
    return image


def _channel_dominates(pixel, index: int) -> bool:
    return pixel[index] >= 200 and all(pixel[other] < 40 for other in range(3) if other != index)


def test_epub_reader_reports_metadata_and_filtered_chapters(tmp_path):
    photo = _jpeg_bytes((200, 10, 10))
    path = tmp_path / "weekly.epub"
    _write_epub(
        path,
        title="Test Weekly",
        author="Ada Editor",
        documents=[
            ("cover.xhtml", _html("<h1>Cover</h1>")),
            ("boilerplate.xhtml", _html("<p>This file is Project Gutenberg boilerplate.</p>")),
            ("front.xhtml", _html("<h1>Test Weekly</h1><p>Issue intro</p>")),
            (
                "chapters/opening.xhtml",
                _html('<h1>Opening Essay</h1><p>Hello readers</p><img src="../images/photo.jpg"/>'),
            ),
            ("notes/raw_file.xhtml", _html("<p>No heading here</p>")),
            ("legal_page.xhtml", _html("<h1>The Copyright Page</h1><p>rights</p>")),
            ("later.xhtml", _html("<h1>Test Weekly</h1><p>Later duplicate</p>")),
        ],
        images=[("images/photo.jpg", photo, "image/jpeg")],
    )

    metadata = get_epub_metadata(path)

    assert metadata["title"] == "Test Weekly"
    assert metadata["author"] == "Ada Editor"
    assert metadata["chapters"] == ["Contents", "Opening Essay", "Raw_File", "Test Weekly"]
    assert metadata["total_chapters"] == 4
    assert "error" not in metadata
    assert get_epub_image(path, "photo.jpg") == photo
    assert get_epub_image(path, "missing.jpg") is None


def test_epub_reader_chapter_html_rewrites_images_and_rejects_missing_indexes(tmp_path):
    path = tmp_path / "weekly.epub"
    _write_epub(
        path,
        title="Test Weekly",
        author="Ada Editor",
        documents=[
            ("front.xhtml", _html("<h1>Test Weekly</h1><p>Issue intro</p>")),
            (
                "chapters/opening.xhtml",
                _html('<h1>Opening Essay</h1><p>Hello readers</p><img src="../images/photo.jpg"/>'),
            ),
        ],
        images=[("images/photo.jpg", _jpeg_bytes((200, 10, 10)), "image/jpeg")],
    )

    first = get_epub_chapter(path, 0)
    rewritten = get_epub_chapter(path, 1, magazine_id=7)
    original = get_epub_chapter(path, 1)

    assert first is not None
    assert "Issue intro" in first
    assert "/api/periodicals/" not in first
    assert rewritten is not None
    assert "Opening Essay" in rewritten
    assert "Hello readers" in rewritten
    assert 'src="/api/periodicals/7/epub/image/photo.jpg"' in rewritten
    assert "../images/photo.jpg" not in rewritten
    assert original is not None
    assert "photo.jpg" in original
    assert "/api/periodicals/" not in original
    assert get_epub_chapter(path, 2) is None
    assert get_epub_chapter(path, -1) is None


def test_epub_reader_returns_error_metadata_and_none_for_unreadable_file(tmp_path):
    path = tmp_path / "broken.epub"
    path.write_text("this is not an epub")

    metadata = get_epub_metadata(path)

    assert metadata["error"] is True
    assert metadata["title"] == "broken"
    assert metadata["author"] == "Unknown"
    assert metadata["chapters"] == []
    assert metadata["total_chapters"] == 0
    assert get_epub_chapter(path, 0) is None
    assert get_epub_image(path, "photo.jpg") is None


def test_epub_text_extraction_stops_after_max_items(tmp_path):
    path = tmp_path / "stories.epub"
    _write_epub(
        path,
        title="Stories",
        author="Ada Editor",
        documents=[
            ("alpha.xhtml", _html("<p>Alpha paragraph unique</p>")),
            ("beta.xhtml", _html("<p>Beta paragraph unique</p>")),
        ],
        images=[],
    )

    first_only = extract_text_from_epub(path, max_items=1)
    both = extract_text_from_epub(path, max_items=2)
    missing = extract_text_from_epub(tmp_path / "missing.epub")

    assert "Alpha paragraph unique" in first_only
    assert "Beta paragraph unique" not in first_only
    assert "Alpha paragraph unique" in both
    assert "Beta paragraph unique" in both
    assert missing == ""


def test_epub_cover_extraction_prefers_a_named_cover_then_the_first_image(tmp_path):
    named = tmp_path / "named.epub"
    cover_png = _png_bytes((10, 20, 200), size=(8, 8))
    other_png = _png_bytes((200, 10, 10), size=(8, 8))
    _write_epub(
        named,
        title="Named",
        author="Ada Editor",
        documents=[("chapter.xhtml", _html("<p>Body</p>"))],
        images=[
            ("images/other.png", other_png, "image/png"),
            ("images/cover.png", cover_png, "image/png"),
        ],
    )
    fallback = tmp_path / "fallback.epub"
    _write_epub(
        fallback,
        title="Fallback",
        author="Ada Editor",
        documents=[("chapter.xhtml", _html("<p>Body</p>"))],
        images=[
            ("images/first.png", other_png, "image/png"),
            ("images/second.png", cover_png, "image/png"),
        ],
    )
    empty = tmp_path / "empty.epub"
    _write_epub(
        empty,
        title="Empty",
        author="Ada Editor",
        documents=[("chapter.xhtml", _html("<p>Body</p>"))],
        images=[],
    )

    named_cover = extract_cover_from_epub(named, tmp_path / "named-out")
    fallback_cover = extract_cover_from_epub(fallback, tmp_path / "fallback-out")
    empty_cover = extract_cover_from_epub(empty, tmp_path / "empty-out")
    missing_cover = extract_cover_from_epub(tmp_path / "missing.epub", tmp_path / "missing-out")

    assert named_cover == tmp_path / "named-out" / "named.jpg"
    assert fallback_cover == tmp_path / "fallback-out" / "fallback.jpg"
    with Image.open(named_cover) as image:
        assert image.format == "JPEG"
        assert _channel_dominates(image.getpixel((0, 0)), 2)
    with Image.open(fallback_cover) as image:
        assert _channel_dominates(image.getpixel((0, 0)), 0)
    assert empty_cover is None
    assert not (tmp_path / "empty-out" / "empty.jpg").exists()
    assert missing_cover is None


def test_comic_reader_returns_naturally_sorted_page_bytes(tmp_path):
    page1 = _png_bytes((0, 255, 0))
    page2 = _png_bytes((255, 0, 0))
    page3 = _png_bytes((0, 0, 255))
    page10 = _png_bytes((255, 255, 0))
    hidden = _png_bytes((1, 2, 3))
    path = tmp_path / "Issue One.cbz"
    _write_cbz(
        path,
        {
            "page10.png": page10,
            "page2.png": page2,
            "folder/page1.png": page1,
            "page3.JPG": page3,
            "notes.txt": b"ignore me",
            ".hidden.png": hidden,
        },
    )

    metadata = get_comic_metadata(path)

    assert metadata == {
        "title": "Issue One",
        "format": "CBZ",
        "page_count": 4,
        "pages": ["folder/page1.png", "page2.png", "page3.JPG", "page10.png"],
    }
    assert get_comic_page(path, 0) == page1
    assert get_comic_page(path, 1) == page2
    assert get_comic_page(path, 2) == page3
    assert get_comic_page(path, 3) == page10
    assert get_comic_page(path, 4) is None
    assert get_comic_page(path, -1) is None

    with zipfile.ZipFile(path) as archive:
        assert get_sorted_image_files(archive, ".cbr") == [
            "folder/page1.png",
            "page2.png",
            "page3.JPG",
            "page10.png",
        ]


def test_comic_reader_thumbnails_missing_pages_and_bad_archives(tmp_path):
    page = _png_bytes((0, 255, 0), size=(12, 20))
    transparent = _png_bytes((255, 0, 0, 0), size=(4, 4), mode="RGBA")
    comic = tmp_path / "thumb.cbz"
    _write_cbz(comic, {"page2.png": page, "page10.png": transparent})
    empty = tmp_path / "empty.cbz"
    _write_cbz(empty, {"readme.txt": b"no images"})
    corrupt = tmp_path / "corrupt.cbz"
    corrupt.write_text("not a zip")
    unsupported = tmp_path / "issue.txt"
    unsupported.write_text("nope")

    thumbnail = get_comic_page_thumbnail(comic, 0, max_size=8)
    transparent_thumb = get_comic_page_thumbnail(comic, 1, max_size=4)

    with _open_image(thumbnail) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (5, 8)
        assert _channel_dominates(image.getpixel((0, 0)), 1)
    with _open_image(transparent_thumb) as image:
        assert image.mode == "RGB"
        pixel = image.getpixel((0, 0))
        assert pixel[0] >= 250 and pixel[1] >= 250 and pixel[2] >= 250
    assert get_comic_page_thumbnail(comic, 5) is None
    assert get_comic_metadata(empty) == {
        "title": "empty",
        "format": "CBZ",
        "page_count": 0,
        "pages": [],
    }
    assert get_comic_page(empty, 0) is None
    with pytest.raises(FileNotFoundError):
        get_comic_metadata(tmp_path / "missing.cbz")
    with pytest.raises(zipfile.BadZipFile):
        get_comic_page(corrupt, 0)
    with pytest.raises(ValueError, match="Unsupported format: .txt"):
        get_comic_metadata(unsupported)


def test_pdf_reader_metadata_pages_and_thumbnails(tmp_path):
    path = tmp_path / "Nat Geo.pdf"
    document = pymupdf.open()
    document.new_page(width=200, height=400)
    document[0].insert_text((36, 72), "Hello page one")
    document.new_page(width=200, height=400)
    document[1].insert_text((36, 72), "Hello page two")
    document.save(path)
    document.close()

    metadata = get_pdf_metadata(path)
    first = get_pdf_page(path, 0, dpi=72)
    second = get_pdf_page(path, 1, dpi=144)
    thumbnail = get_pdf_page_thumbnail(path, 1, max_height=50)

    assert metadata == {
        "title": "Nat Geo",
        "format": "PDF",
        "page_count": 2,
        "pages": ["Page 1", "Page 2"],
    }
    with _open_image(first) as image:
        assert image.format == "JPEG"
        assert image.size == (200, 400)
    with _open_image(second) as image:
        assert image.size == (400, 800)
    assert first != second
    with _open_image(thumbnail) as image:
        assert image.format == "JPEG"
        assert image.size == (25, 50)
    with pytest.raises(ValueError, match=r"Invalid page index: 5 \(PDF has 2 pages\)"):
        get_pdf_page(path, 5)
    with pytest.raises(ValueError, match=r"Invalid page index: -1 \(PDF has 2 pages\)"):
        get_pdf_page_thumbnail(path, -1)


def test_pdf_reader_rejects_unreadable_files(tmp_path):
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not a pdf")
    missing = tmp_path / "missing.pdf"

    with pytest.raises(pymupdf.FileDataError, match="corrupt.pdf"):
        get_pdf_metadata(corrupt)
    with pytest.raises(pymupdf.FileNotFoundError, match="missing.pdf"):
        get_pdf_page(missing, 0)
    with pytest.raises(pymupdf.FileDataError, match="corrupt.pdf"):
        get_pdf_page_thumbnail(corrupt, 0)


def test_cbz_validation_and_cover_extraction(tmp_path):
    red = _png_bytes((255, 0, 0), size=(8, 8))
    transparent = _png_bytes((255, 0, 0, 0), size=(6, 6), mode="RGBA")
    comic = tmp_path / "Opaque.cbz"
    _write_cbz(comic, {"page.png": red, "notes.txt": b"skip"})
    clear = tmp_path / "Clear.cbz"
    _write_cbz(clear, {"a.png": transparent})
    empty = tmp_path / "Empty.cbz"
    _write_cbz(empty, {"readme.txt": b"none"})
    invalid = tmp_path / "invalid.cbz"
    invalid.write_text("not a zip")

    cover = extract_cover_from_cbz(comic, tmp_path / "covers")
    clear_cover = extract_cover_from_cbz(clear, tmp_path / "clear-covers")

    assert validate_cbz(comic) is True
    assert validate_cbz(tmp_path / "missing.cbz") is False
    assert validate_cbz(invalid) is False
    assert cover == tmp_path / "covers" / "Opaque.jpg"
    with Image.open(cover) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert _channel_dominates(image.getpixel((0, 0)), 0)
    with Image.open(clear_cover) as image:
        pixel = image.getpixel((0, 0))
        assert image.mode == "RGB"
        assert pixel == (255, 255, 255)
    assert extract_cover_from_cbz(empty, tmp_path / "empty-out") is None
    assert extract_cover_from_cbz(invalid, tmp_path / "invalid-out") is None
    assert extract_cover_from_cbz(tmp_path / "missing.cbz", tmp_path / "missing-out") is None


def test_cbz_cover_uses_lexicographic_name_order(tmp_path):
    """Cover selection follows ``list.sort`` on the archive names.

    ``_get_sorted_image_files`` describes numeric page order, and the comic
    reader lists ``page2.png`` before ``page10.png``. Cover extraction sorts the
    names as strings, so ``page10.png`` is the image written to the JPEG.
    """
    page2 = _png_bytes((255, 0, 0), size=(8, 8))
    page10 = _png_bytes((0, 0, 255), size=(8, 8))
    path = tmp_path / "Order.cbz"
    _write_cbz(path, {"page10.png": page10, "page2.png": page2})

    cover = extract_cover_from_cbz(path, tmp_path / "out")
    reader_pages = get_comic_metadata(path)["pages"]

    assert reader_pages == ["page2.png", "page10.png"]
    assert cover is not None
    with Image.open(cover) as image:
        assert _channel_dominates(image.getpixel((0, 0)), 2)


def test_cbr_helpers_reject_non_archives_and_sort_names_lexicographically(tmp_path):
    missing = tmp_path / "missing.cbr"
    invalid = tmp_path / "invalid.cbr"
    invalid.write_bytes(b"not a rar")

    class Info:
        def __init__(self, filename):
            self.filename = filename

    class Archive:
        def infolist(self):
            return [
                Info("page10.png"),
                Info("page2.png"),
                Info(".hidden.png"),
                Info("readme.txt"),
            ]

    assert validate_cbr(missing) is False
    assert validate_cbr(invalid) is False
    assert extract_cover_from_cbr(invalid, tmp_path / "out") is None
    assert extract_cover_from_cbr(missing, tmp_path / "missing-out") is None
    assert _get_sorted_image_files(Archive(), ".cbr") == ["page10.png", "page2.png"]
