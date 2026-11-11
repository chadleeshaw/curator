"""Scanned pages are served as their embedded JPEG; everything else is rendered."""

from io import BytesIO

import pymupdf
from PIL import Image

from core.utils.readers.pdf import MAX_PAGE_WIDTH_PX, get_pdf_page


def _jpeg(width=600, height=800) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _pdf(tmp_path, build, width=600, height=800):
    doc = pymupdf.open()
    build(doc.new_page(width=width, height=height))
    path = tmp_path / "test.pdf"
    doc.save(path)
    doc.close()
    return path


def test_full_page_scan_is_returned_untouched(tmp_path):
    scan = _jpeg()
    path = _pdf(tmp_path, lambda page: page.insert_image(page.rect, stream=scan))
    assert get_pdf_page(path, 0) == scan


def test_scan_with_visible_text_is_rendered(tmp_path):
    scan = _jpeg()

    def build(page):
        page.insert_image(page.rect, stream=scan)
        page.insert_text((72, 72), "Headline over the photo")

    assert get_pdf_page(_pdf(tmp_path, build), 0) != scan


def test_scan_with_invisible_ocr_layer_is_returned_untouched(tmp_path):
    scan = _jpeg()

    def build(page):
        page.insert_image(page.rect, stream=scan)
        page.insert_text((72, 72), "ocr text", render_mode=3)

    assert get_pdf_page(_pdf(tmp_path, build), 0) == scan


def test_partial_image_is_rendered(tmp_path):
    scan = _jpeg()
    path = _pdf(tmp_path, lambda page: page.insert_image(pymupdf.Rect(0, 0, 300, 400), stream=scan))
    assert get_pdf_page(path, 0) != scan


def test_oversized_page_render_is_capped(tmp_path):
    path = _pdf(tmp_path, lambda page: page.insert_text((72, 72), "poster"), width=4000, height=5000)
    assert Image.open(BytesIO(get_pdf_page(path, 0))).width <= MAX_PAGE_WIDTH_PX
