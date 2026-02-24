"""
OCR Performance Benchmarks — DPI vs Speed vs Accuracy

Renders the sample PDF at 200 DPI and 300 DPI, runs Tesseract on each,
then compares timing and the metadata extracted (year, month, volume, issue).

Run all benchmarks:
    .venv/bin/python -m pytest tests/performance/test_ocr_benchmarks.py -v --benchmark-only -s --benchmark-min-rounds=3

Run accuracy tests only (with output):
    .venv/bin/python -m pytest tests/performance/test_ocr_benchmarks.py -k accuracy -v -s

Save a baseline to compare against later:
    .venv/bin/python -m pytest tests/performance/test_ocr_benchmarks.py -v --benchmark-only --benchmark-save=baseline --benchmark-min-rounds=3

Compare against a saved baseline:
    .venv/bin/python -m pytest tests/performance/test_ocr_benchmarks.py -v --benchmark-only --benchmark-compare=baseline --benchmark-min-rounds=3
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
PDF_PATH = str(FIXTURES_DIR / "pdf" / "NationalGeographic 2000-01.pdf")

# Known ground-truth values for the NatGeo fixture — all optimizations must
# keep both accuracy tests green.
_EXPECTED_YEAR = 2000
_EXPECTED_MONTH = "January"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_page(pdf_path: str, dpi: int, page_num: int = 0):
    """Render a single PDF page to a PIL Image at the given DPI."""
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz
    from PIL import Image

    doc = fitz.open(pdf_path)
    pix = doc[page_num].get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def _render_all_pages(pdf_path: str, dpi: int, max_pages: int = 2):
    """Render up to max_pages of a PDF to PIL Images at the given DPI."""
    try:
        import fitz
    except ImportError:
        import pymupdf as fitz
    from PIL import Image

    doc = fitz.open(pdf_path)
    images = []
    for i in range(min(max_pages, doc.page_count)):
        pix = doc[i].get_pixmap(dpi=dpi)
        images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    doc.close()
    return images


def _run_tesseract(img, lang: str = "eng") -> dict:
    """Run Tesseract image_to_data on a PIL Image, return the raw result dict."""
    import pytesseract
    from core.constants.ocr import (
        OCR_TESSERACT_PSM,
        OCR_TESSERACT_OEM,
        OCR_TIMEOUT_SECONDS,
    )

    config = f"--psm {OCR_TESSERACT_PSM} --oem {OCR_TESSERACT_OEM}"
    return pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        lang=lang,
        config=config,
        timeout=OCR_TIMEOUT_SECONDS,
    )


def _extract_metadata(data: dict, confidence_threshold: int = 30) -> dict:
    """Convert raw Tesseract output dict into production-equivalent metadata."""
    from services.ocr.service import OCRService

    text_parts = []
    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
        if text and conf > confidence_threshold:
            text_parts.append(text)
            words.append({"text": text, "confidence": conf})

    return OCRService.extract_metadata_from_text(" ".join(text_parts), words)


def _accuracy_report(label: str, meta: dict, img_size: tuple) -> None:
    """Print a human-readable accuracy summary (-s to see it)."""
    print(f"\n  [{label}]")
    print(f"    Image size : {img_size[0]}x{img_size[1]} px")
    print(f"    Year       : {meta.get('year')}")
    print(f"    Month      : {meta.get('month')}")
    print(f"    Volume     : {meta.get('volume')}")
    print(f"    Issue      : {meta.get('issue_number')}")
    print(f"    Text snip  : {meta.get('detected_text', '')[:120]!r}")


def _assert_accuracy(label: str, meta: dict) -> None:
    """Assert known ground-truth values — fails with a clear message if an optimization regresses."""
    assert meta.get("year") == _EXPECTED_YEAR, (
        f"{label}: expected year={_EXPECTED_YEAR}, got {meta.get('year')!r}\n"
        f"detected_text={meta.get('detected_text', '')[:200]!r}"
    )
    assert meta.get("month") == _EXPECTED_MONTH, (
        f"{label}: expected month={_EXPECTED_MONTH!r}, got {meta.get('month')!r}"
    )


# ---------------------------------------------------------------------------
# Module-scoped fixtures — render once, reused across all benchmark rounds
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ocr_available():
    from services.ocr.service import OCR_AVAILABLE

    if not OCR_AVAILABLE:
        pytest.skip("Tesseract not available — install with: brew install tesseract")


@pytest.fixture(scope="module")
def image_300dpi():
    """Pre-rendered 300 DPI image (original production DPI)."""
    return _render_page(PDF_PATH, dpi=300)


@pytest.fixture(scope="module")
def image_200dpi():
    """Pre-rendered 200 DPI image (current production DPI after DPI change)."""
    return _render_page(PDF_PATH, dpi=200)


@pytest.fixture(scope="module")
def image_200dpi_resized(image_200dpi):
    """200 DPI image resized to OCR_IMAGE_MAX_DIMENSION on the longest axis."""
    from PIL import Image as PILImage
    from core.constants.ocr import OCR_IMAGE_MAX_DIMENSION

    w, h = image_200dpi.size
    scale = OCR_IMAGE_MAX_DIMENSION / max(w, h)
    if scale < 1.0:
        return image_200dpi.resize(
            (int(w * scale), int(h * scale)), PILImage.Resampling.LANCZOS
        )
    return image_200dpi


@pytest.fixture(scope="module")
def image_200dpi_top40(image_200dpi):
    """200 DPI image cropped to the top 40%."""
    w, h = image_200dpi.size
    return image_200dpi.crop((0, 0, w, int(h * 0.4)))


# ---------------------------------------------------------------------------
# Benchmark 1 — Baseline: render + OCR at 300 and 200 DPI (full image)
# These are the reference numbers everything else is measured against.
# ---------------------------------------------------------------------------


class TestBaseline:
    """Render + OCR on the full image at 300 and 200 DPI (reference numbers)."""

    def test_pipeline_300dpi(self, benchmark, ocr_available):
        """Full pipeline at 300 DPI — original production setting."""

        def run():
            img = _render_page(PDF_PATH, dpi=300)
            return _run_tesseract(img)

        data = benchmark(run)
        assert "text" in data

    def test_pipeline_200dpi(self, benchmark, ocr_available):
        """Full pipeline at 200 DPI — current production setting."""

        def run():
            img = _render_page(PDF_PATH, dpi=200)
            return _run_tesseract(img)

        data = benchmark(run)
        assert "text" in data


# ---------------------------------------------------------------------------
# Benchmark 2 — Resize to OCR_IMAGE_MAX_DIMENSION (1200px)
# The 200 DPI render is already 3820x5556 px — well above what Tesseract needs
# for large cover text. Downscaling to 1200px on the longest axis reduces pixel
# count by ~95%, which should be the largest single speedup available.
# ---------------------------------------------------------------------------


class TestResize:
    """Does downscaling to 1200px before OCR trade speed for acceptable accuracy?"""

    def test_ocr_200dpi_full(self, benchmark, ocr_available, image_200dpi):
        """Baseline: Tesseract on full 200 DPI image (3820x5556)."""
        data = benchmark(_run_tesseract, image_200dpi)
        assert "text" in data

    def test_ocr_200dpi_resized_1200(
        self, benchmark, ocr_available, image_200dpi_resized
    ):
        """Tesseract on image resized to max 1200px on longest axis."""
        data = benchmark(_run_tesseract, image_200dpi_resized)
        assert "text" in data


# ---------------------------------------------------------------------------
# Benchmark 3 — Crop to top band
# Magazine cover dates and titles are almost always in the top third or top
# half of the cover. Cropping eliminates the bulk of the image before OCR.
# ---------------------------------------------------------------------------


class TestCrop:
    """Crop the image to just the top band before handing to Tesseract."""

    def test_ocr_200dpi_full(self, benchmark, ocr_available, image_200dpi):
        """Baseline: Tesseract on full 200 DPI image."""
        data = benchmark(_run_tesseract, image_200dpi)
        assert "text" in data

    def test_ocr_200dpi_top40pct(self, benchmark, ocr_available, image_200dpi_top40):
        """Tesseract on top 40% of 200 DPI image."""
        data = benchmark(_run_tesseract, image_200dpi_top40)
        assert "text" in data


# ---------------------------------------------------------------------------
# Benchmark 4 — Parallel page processing
# Currently the 2-page scan is sequential: page 1 OCR completes, then page 2.
# Each pytesseract call spawns its own tesseract subprocess, so they can run
# in parallel. We pre-render both pages (fitz isn't thread-safe) then submit
# both OCR calls to a ThreadPoolExecutor simultaneously.
# ---------------------------------------------------------------------------


class TestParallelPages:
    """Sequential vs parallel OCR across the 2-page scan."""

    def test_two_pages_sequential(self, benchmark, ocr_available):
        """Baseline: render + OCR 2 pages one at a time (current production)."""
        images = _render_all_pages(PDF_PATH, dpi=200, max_pages=2)

        def run():
            return [_run_tesseract(img) for img in images]

        results = benchmark(run)
        assert len(results) == len(images)

    def test_two_pages_parallel(self, benchmark, ocr_available):
        """Render 2 pages sequentially (fitz constraint), then OCR both in parallel."""
        images = _render_all_pages(PDF_PATH, dpi=200, max_pages=2)

        def run():
            with ThreadPoolExecutor(max_workers=len(images)) as pool:
                return list(pool.map(_run_tesseract, images))

        results = benchmark(run)
        assert len(results) == len(images)


# ---------------------------------------------------------------------------
# Accuracy tests — correctness gate for every candidate optimization.
# All must pass before an optimization is considered safe to ship.
# Run with -s to see the printed report.
# ---------------------------------------------------------------------------


def test_accuracy_300dpi(ocr_available, image_300dpi):
    """300 DPI full image must extract year=2000 and month=January."""
    data = _run_tesseract(image_300dpi)
    meta = _extract_metadata(data)
    _accuracy_report("300 DPI full", meta, image_300dpi.size)
    _assert_accuracy("300 DPI full", meta)


def test_accuracy_200dpi(ocr_available, image_200dpi):
    """200 DPI full image must extract year=2000 and month=January."""
    data = _run_tesseract(image_200dpi)
    meta = _extract_metadata(data)
    _accuracy_report("200 DPI full", meta, image_200dpi.size)
    _assert_accuracy("200 DPI full", meta)


def test_accuracy_200dpi_resized(ocr_available, image_200dpi_resized):
    """Resized-to-1200px 200 DPI image must extract year=2000 and month=January."""
    data = _run_tesseract(image_200dpi_resized)
    meta = _extract_metadata(data)
    _accuracy_report("200 DPI resized 1200px", meta, image_200dpi_resized.size)
    _assert_accuracy("200 DPI resized 1200px", meta)


def test_accuracy_200dpi_top40(ocr_available, image_200dpi_top40):
    """Top-40% crop of 200 DPI image must extract year=2000 and month=January."""
    data = _run_tesseract(image_200dpi_top40)
    meta = _extract_metadata(data)
    _accuracy_report("200 DPI top 40%", meta, image_200dpi_top40.size)
    _assert_accuracy("200 DPI top 40%", meta)


def test_accuracy_comparison(
    ocr_available,
    image_200dpi,
    image_200dpi_resized,
    image_200dpi_top40,
):
    """
    Print a full side-by-side accuracy report for all candidate optimizations.

    Run with -s to see output:
        pytest tests/performance/test_ocr_benchmarks.py::test_accuracy_comparison -v -s
    """
    candidates = [
        ("200 DPI full (baseline)", image_200dpi),
        ("200 DPI resized 1200px", image_200dpi_resized),
        ("200 DPI top 40%", image_200dpi_top40),
    ]

    results = []
    for label, img in candidates:
        data = _run_tesseract(img)
        meta = _extract_metadata(data)
        _accuracy_report(label, meta, img.size)
        results.append((label, meta))

    baseline_year = results[0][1].get("year")
    baseline_month = results[0][1].get("month")

    print("\n  Accuracy delta vs 200 DPI full baseline:")
    for label, meta in results[1:]:
        y_ok = "OK  " if meta.get("year") == baseline_year else "DIFF"
        m_ok = "OK  " if meta.get("month") == baseline_month else "DIFF"
        print(f"    year={y_ok}  month={m_ok}  — {label}")

    assert (
        True
    )  # reporting only — correctness enforced by individual accuracy tests above


# ---------------------------------------------------------------------------
# PNG generation benchmarks — sequential (old) vs parallel (new)
# ---------------------------------------------------------------------------

import multiprocessing
import tempfile

_mp_ctx_bench = multiprocessing.get_context("spawn")


def _gen_png_in_process_bench(pdf_path: str, png_path: str, result_queue) -> None:
    """Minimal PNG generation worker for benchmarking (mirrors production logic)."""
    try:
        from pdf2image import convert_from_path
        from PIL import Image

        images = convert_from_path(
            pdf_path, first_page=1, last_page=1, dpi=200, fmt="png"
        )
        if images:
            img = images[0]
            if max(img.size) > 1200:
                ratio = 1200 / max(img.size)
                img = img.resize(
                    tuple(int(d * ratio) for d in img.size), Image.Resampling.LANCZOS
                )
            img.save(png_path, "PNG")
            result_queue.put({"success": True})
        else:
            result_queue.put({"success": False, "error": "no images"})
    except Exception as exc:
        result_queue.put({"success": False, "error": str(exc)})


class TestPngGeneration:
    """Sequential (old) vs parallel (new) PNG generation for a batch of N PDFs.

    Uses the same fixture PDF N times to simulate a batch — the cost is real
    poppler work, not a stub.
    """

    BATCH_SIZE = 5  # simulate a full default batch

    def _make_png_paths(self, tmp_dir: str, n: int):
        return [str(Path(tmp_dir) / f"bench_{i}.png") for i in range(n)]

    def test_png_generation_sequential(self, benchmark, ocr_available):
        """Old path: start one process, join, repeat for each job in the batch."""

        def run():
            with tempfile.TemporaryDirectory() as tmp:
                png_paths = self._make_png_paths(tmp, self.BATCH_SIZE)
                for png_path in png_paths:
                    q = _mp_ctx_bench.Queue()
                    proc = _mp_ctx_bench.Process(
                        target=_gen_png_in_process_bench,
                        args=(PDF_PATH, png_path, q),
                        daemon=True,
                    )
                    proc.start()
                    proc.join(timeout=30)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=2)

        benchmark(run)

    def test_png_generation_parallel(self, benchmark, ocr_available):
        """New path: start all N processes at once, then collect results."""

        def run():
            with tempfile.TemporaryDirectory() as tmp:
                png_paths = self._make_png_paths(tmp, self.BATCH_SIZE)
                running = []
                for png_path in png_paths:
                    q = _mp_ctx_bench.Queue()
                    proc = _mp_ctx_bench.Process(
                        target=_gen_png_in_process_bench,
                        args=(PDF_PATH, png_path, q),
                        daemon=True,
                    )
                    proc.start()
                    running.append((proc, q))

                import time as _time

                deadline = _time.monotonic() + 30
                for proc, q in running:
                    remaining = max(0, deadline - _time.monotonic())
                    proc.join(timeout=remaining)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=2)

        benchmark(run)
