"""Behavior tests for OCR text extraction and the background OCR queue.

pytesseract, pdf2image, and PaddleOCR are mocked so the tests never need the
Tesseract or Poppler binaries. Queue tests use a file-backed SQLite database.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Queue
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# The OCR modules mention PaddleOCR but do not import it. A stub keeps an
# accidental import from failing when the package is not installed.
sys.modules.setdefault("paddleocr", ModuleType("paddleocr"))

from models.database import Base, OCRJob, Periodical
from services.ocr.queue import (
    OCRQueueService,
    _apply_scan_metadata_to_periodical,
    _generate_png_in_process,
    _generate_pngs_parallel,
    _ocr_worker,
)
from services.ocr.service import OCRService, _parse_paddle_ocr_results

SAMPLE_TEXT = "National Geographic ISSUE 42 MARCH 2019 VOL. 7"
SAMPLE_WORDS = ["ISSUE", "42", "MARCH", "2019", "VOL.", "7"]


@pytest.fixture
def test_db(tmp_path):
    """File-backed SQLite database, same pattern as the services conftest."""
    db_path = tmp_path / "ocr-service.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield engine, factory
    finally:
        engine.dispose()


@pytest.fixture
def session(test_db):
    _engine, factory = test_db
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def ocr_queue(monkeypatch):
    """Queue service that cannot spawn Poppler or read the app config."""
    monkeypatch.setattr("services.ocr.queue.ConfigLoader", MagicMock())
    monkeypatch.setattr(
        "services.ocr.queue._generate_pngs_parallel",
        lambda jobs, timeout=120: {job["periodical_id"]: "failed" for job in jobs},
    )
    return OCRQueueService()


def _add_periodical(session, file_path, **overrides) -> Periodical:
    values = {
        "user_id": 1,
        "title": "National Geographic",
        "issue_date": datetime(2020, 1, 15, tzinfo=UTC),
        "file_path": str(file_path),
    }
    values.update(overrides)
    row = Periodical(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _add_job(session, periodical, **overrides) -> OCRJob:
    values = {
        "periodical_id": periodical.id,
        "status": OCRJob.StatusEnum.PENDING,
        "attempt_count": 0,
    }
    values.update(overrides)
    job = OCRJob(**values)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _library(tmp_path, filename):
    root = tmp_path / "library"
    document = root / "issues" / filename
    cover = root / "covers" / "cover.jpg"
    document.parent.mkdir(parents=True, exist_ok=True)
    cover.parent.mkdir(parents=True, exist_ok=True)
    cover.write_bytes(b"cover")
    return document, cover


def _write_ocr_png(periodical) -> Path:
    png = Path(periodical.cover_path).parent.parent / ".ocr_covers" / f"{periodical.id}_ocr.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"png")
    return png


def _pending_issue(session, tmp_path, filename="issue.pdf", create_file=True, create_png=False, **overrides):
    document, cover = _library(tmp_path, filename)
    if create_file:
        document.write_bytes(b"%PDF-1.4\n")
    periodical = _add_periodical(session, document, cover_path=str(cover), **overrides)
    png = _write_ocr_png(periodical) if create_png else None
    job = _add_job(session, periodical)
    return periodical, job, png


def _sample_metadata():
    return {
        "ocr_available": True,
        "text_found": True,
        "used_ocr": True,
        "detected_text": SAMPLE_TEXT,
        "issue_number": 42,
        "year": 2019,
        "month": "March",
        "volume": 7,
        "special_edition": False,
        "overall_confidence": 92,
        "extraction_method": "ocr_image",
    }


def _tesseract_payload(words):
    count = len(words)
    return {
        "text": words + [""],
        "conf": ["90"] * count + ["-1"],
        "left": list(range(count + 1)),
        "top": [1] * (count + 1),
        "width": [8] * (count + 1),
        "height": [8] * (count + 1),
    }


def _install_tesseract(monkeypatch, words):
    monkeypatch.setattr("services.ocr.service.OCR_AVAILABLE", True)
    seen = []

    def image_to_data(img, output_type=None, lang=None, config=None, timeout=None):
        seen.append({"size": img.size, "lang": lang, "config": config, "timeout": timeout})
        return _tesseract_payload(words)

    monkeypatch.setattr("services.ocr.service.pytesseract.image_to_data", image_to_data)
    return seen


class _FakePixmap:
    def __init__(self):
        self.width = 30
        self.height = 20
        self.samples = b"\xff" * (self.width * self.height * 3)


class _FakePage:
    def get_pixmap(self, dpi=300):
        return _FakePixmap()


class _FakeDoc:
    page_count = 2

    def __getitem__(self, _index):
        return _FakePage()

    def close(self):
        return None


def _assert_no_fields(result):
    assert result["year"] is None
    assert result["month"] is None
    assert result["issue_number"] is None
    assert result["volume"] is None
    assert result["special_edition"] is False


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


def test_queue_ocr_job_inserts_a_row_and_a_second_queue_is_a_no_op(session, tmp_path):
    periodical = _add_periodical(session, tmp_path / "queued.pdf")

    job = OCRQueueService.queue_ocr_job(
        session,
        periodical.id,
        priority=OCRJob.PriorityEnum.HIGH.value,
        language="French",
    )

    assert job is not None
    assert job.id is not None
    assert job.periodical_id == periodical.id
    assert job.status == OCRJob.StatusEnum.PENDING
    assert job.priority == OCRJob.PriorityEnum.HIGH.value
    assert job.language == "French"
    assert session.query(OCRJob).count() == 1

    assert OCRQueueService.queue_ocr_job(session, periodical.id, language="French") is None
    job.status = OCRJob.StatusEnum.PROCESSING
    session.commit()
    assert OCRQueueService.queue_ocr_job(session, periodical.id) is None
    assert session.query(OCRJob).count() == 1


def test_process_queue_completes_when_the_worker_returns_text(session, tmp_path, ocr_queue, monkeypatch):
    periodical, job, png = _pending_issue(session, tmp_path, create_png=True, language="English")
    seen = {}

    def analyze(cover_path, language=None):
        seen["cover_path"] = cover_path
        seen["language"] = language
        return _sample_metadata()

    monkeypatch.setattr("services.ocr.queue.OCRService.analyze_cover", analyze)
    job.language = "German"
    session.commit()

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    session.refresh(periodical)
    assert stats["processed"] == 1
    assert stats["succeeded"] == 1
    assert stats["failed"] == 0
    assert job.status == OCRJob.StatusEnum.COMPLETED
    assert job.attempt_count == 1
    assert job.ocr_metadata["detected_text"] == SAMPLE_TEXT
    assert job.ocr_metadata["year"] == 2019
    assert job.ocr_metadata["month"] == "March"
    assert job.ocr_metadata["issue_number"] == 42
    assert job.processing_time_seconds >= 0
    assert seen["cover_path"] == str(png)
    assert seen["language"] == "German"
    assert periodical.parsed_metadata["ocr_scan"]["detected_text"] == SAMPLE_TEXT
    assert periodical.derived_metadata["year"]["value"] == 2019
    assert periodical.derived_metadata["month"]["value"] == 3
    assert periodical.derived_metadata["issue_number"]["value"] == 42
    assert periodical.issue_date.year == 2019
    assert periodical.issue_date.month == 3
    assert periodical.extra_metadata["needs_reorganization"] is True
    assert png.exists() is False


def test_process_queue_fails_when_the_worker_raises(session, tmp_path, ocr_queue, monkeypatch):
    _periodical, job, png = _pending_issue(session, tmp_path, create_png=True)

    def explode(_cover_path, language=None):
        raise RuntimeError("worker blew up")

    monkeypatch.setattr("services.ocr.queue._ocr_worker", explode)

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["processed"] == 1
    assert stats["failed"] == 1
    assert stats["succeeded"] == 0
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.attempt_count == 1
    assert job.last_error == "RuntimeError: worker blew up"
    assert png.exists() is True


def test_process_queue_fails_when_the_worker_returns_an_error(session, tmp_path, ocr_queue, monkeypatch):
    _periodical, job, png = _pending_issue(session, tmp_path, create_png=True)

    def analyze(_cover_path, language=None):
        raise ValueError("tesseract failed")

    monkeypatch.setattr("services.ocr.queue.OCRService.analyze_cover", analyze)

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["processed"] == 1
    assert stats["failed"] == 1
    assert stats["succeeded"] == 0
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "tesseract failed"
    assert job.attempt_count == 1
    assert png.exists() is False


def test_process_queue_fails_when_the_pdf_is_missing(session, tmp_path, ocr_queue, monkeypatch):
    _periodical, job, _png = _pending_issue(session, tmp_path, filename="missing.pdf", create_file=False)
    calls = []
    monkeypatch.setattr(
        "services.ocr.queue._generate_pngs_parallel",
        lambda jobs, timeout=120: calls.extend(jobs) or {},
    )

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert calls == []
    assert stats["failed"] == 1
    assert stats["processed"] == 0
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "Could not generate OCR PNG"
    assert job.attempt_count == 0


def test_process_queue_fails_for_a_non_pdf(session, tmp_path, ocr_queue, monkeypatch):
    _periodical, job, _png = _pending_issue(session, tmp_path, filename="issue.cbz")
    calls = []
    monkeypatch.setattr(
        "services.ocr.queue._generate_pngs_parallel",
        lambda jobs, timeout=120: calls.extend(jobs) or {},
    )

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert calls == []
    assert stats["failed"] == 1
    assert stats["processed"] == 0
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "Could not generate OCR PNG"


def test_process_queue_fails_when_png_generation_fails(session, tmp_path, ocr_queue, monkeypatch):
    periodical, job, _png = _pending_issue(session, tmp_path, create_png=False)
    calls = []

    def generate(jobs, timeout=120):
        calls.extend(jobs)
        return {item["periodical_id"]: "failed" for item in jobs}

    monkeypatch.setattr("services.ocr.queue._generate_pngs_parallel", generate)

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["failed"] == 1
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "Could not generate OCR PNG"
    assert calls[0]["periodical_id"] == periodical.id
    assert calls[0]["pdf_path"] == periodical.file_path


def test_process_queue_skips_a_periodical_that_already_has_an_ocr_scan(session, tmp_path, ocr_queue):
    periodical, job, _png = _pending_issue(session, tmp_path, create_file=False)
    periodical.parsed_metadata = {"ocr_scan": {"year": 2018, "detected_text": "already scanned"}}
    session.commit()

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["skipped"] == 1
    assert stats["processed"] == 0
    assert job.status == OCRJob.StatusEnum.COMPLETED
    assert job.last_error == "Skipped - already has ocr_scan"
    assert job.completed_at is not None


def test_process_queue_skips_when_text_scan_has_sufficient_metadata(session, tmp_path, ocr_queue):
    periodical, job, _png = _pending_issue(session, tmp_path, create_file=False)
    periodical.parsed_metadata = {"text_scan": {"has_sufficient_metadata": True, "year": 2018}}
    session.commit()

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["skipped"] == 1
    assert job.status == OCRJob.StatusEnum.COMPLETED
    assert job.last_error == "Skipped - text_scan has sufficient metadata"


def test_process_queue_still_tries_when_a_date_scan_has_no_year(session, tmp_path, ocr_queue):
    periodical, job, _png = _pending_issue(session, tmp_path, filename="missing.pdf", create_file=False)
    periodical.parsed_metadata = {"text_scan": {"has_sufficient_metadata": True}}
    periodical.extra_metadata = {"needs_date_scan": True}
    session.commit()

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["skipped"] == 0
    assert stats["failed"] == 1
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "Could not generate OCR PNG"


def test_process_queue_fails_when_the_periodical_is_gone(session, ocr_queue):
    job = OCRJob(periodical_id=424242, status=OCRJob.StatusEnum.PENDING, attempt_count=0)
    session.add(job)
    session.commit()

    stats = ocr_queue.process_queue(session, batch_size=1)

    session.refresh(job)
    assert stats["failed"] == 1
    assert stats["processed"] == 0
    assert job.status == OCRJob.StatusEnum.FAILED
    assert job.last_error == "Periodical not found"


def test_process_queue_resets_a_stuck_job_that_has_no_retries_left(session, tmp_path, ocr_queue):
    periodical = _add_periodical(session, tmp_path / "stuck.pdf")
    job = _add_job(
        session,
        periodical,
        status=OCRJob.StatusEnum.PROCESSING,
        attempt_count=3,
        started_at=datetime.now(UTC) - timedelta(minutes=45),
    )

    stats = ocr_queue.process_queue(session, batch_size=1, max_retries=3)

    session.refresh(job)
    assert stats == {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    assert job.status == OCRJob.StatusEnum.PENDING
    assert job.started_at is None
    assert job.attempt_count == 3


def test_cleanup_old_jobs_removes_finished_jobs_past_the_cutoff(session, tmp_path):
    periodical = _add_periodical(session, tmp_path / "old.pdf")
    old = datetime.now(UTC) - timedelta(days=30)
    recent = datetime.now(UTC) - timedelta(days=1)
    old_completed = _add_job(session, periodical, status=OCRJob.StatusEnum.COMPLETED, completed_at=old)
    old_failed = _add_job(session, periodical, status=OCRJob.StatusEnum.FAILED, completed_at=old)
    recent_completed = _add_job(session, periodical, status=OCRJob.StatusEnum.COMPLETED, completed_at=recent)
    recent_failed = _add_job(session, periodical, status=OCRJob.StatusEnum.FAILED, completed_at=recent)
    pending = _add_job(session, periodical)
    processing = _add_job(
        session,
        periodical,
        status=OCRJob.StatusEnum.PROCESSING,
        started_at=old,
        completed_at=old,
    )
    removed_ids = {old_completed.id, old_failed.id}
    kept_ids = {recent_completed.id, recent_failed.id, pending.id, processing.id}

    deleted = OCRQueueService.cleanup_old_jobs(session, days=7)

    remaining = {row.id for row in session.query(OCRJob).all()}
    assert deleted == 2
    assert removed_ids.isdisjoint(remaining)
    assert remaining == kept_ids


def test_get_queue_status_counts_each_state_and_resets_stuck_jobs(session, tmp_path):
    periodical = _add_periodical(session, tmp_path / "status.pdf")
    pending = _add_job(session, periodical)
    stuck = _add_job(
        session,
        periodical,
        status=OCRJob.StatusEnum.PROCESSING,
        started_at=datetime.now(UTC) - timedelta(minutes=45),
    )
    _add_job(
        session,
        periodical,
        status=OCRJob.StatusEnum.PROCESSING,
        started_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    _add_job(session, periodical, status=OCRJob.StatusEnum.COMPLETED, completed_at=datetime.now(UTC))
    _add_job(session, periodical, status=OCRJob.StatusEnum.FAILED, completed_at=datetime.now(UTC))

    empty = OCRQueueService()
    status = empty.get_queue_status(session)

    session.refresh(stuck)
    session.refresh(pending)
    assert status["pending"] == 2
    assert status["processing"] == 1
    assert status["completed"] == 1
    assert status["failed"] == 1
    assert status["total"] == 5
    assert status["oldest_pending_age_seconds"] >= 0
    assert stuck.status == OCRJob.StatusEnum.PENDING
    assert stuck.started_at is None
    empty.shutdown()


def test_empty_queue_reports_no_work(session, ocr_queue):
    assert ocr_queue.process_queue(session) == {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    status = OCRQueueService.get_queue_status(session)
    assert status["total"] == 0
    assert status["oldest_pending_age_seconds"] is None
    ocr_queue.shutdown()


def test_generate_png_in_process_writes_a_page_without_pdf2image(monkeypatch, tmp_path):
    assert _generate_pngs_parallel([]) == {}
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    large_png = tmp_path / "large.png"
    small_png = tmp_path / "small.png"
    images = {
        "large": Image.new("RGB", (2400, 1000), "white"),
        "small": Image.new("RGB", (400, 300), "white"),
    }

    def convert_from_path(pdf_path, first_page, last_page, dpi, fmt):
        assert Path(pdf_path) == pdf
        assert (first_page, last_page, fmt) == (1, 1, "png")
        assert dpi in (72, 96)
        return [images["large" if dpi == 72 else "small"]]

    fake_pdf2image = ModuleType("pdf2image")
    fake_pdf2image.convert_from_path = convert_from_path
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

    large_result = Queue()
    _generate_png_in_process(str(pdf), str(large_png), 72, 1200, large_result)
    saved = large_result.get_nowait()
    assert saved["success"] is True
    assert saved["original_size"] == (2400, 1000)
    assert Image.open(large_png).size == (1200, 500)

    small_result = Queue()
    _generate_png_in_process(str(pdf), str(small_png), 96, 1200, small_result)
    assert small_result.get_nowait()["success"] is True
    assert Image.open(small_png).size == (400, 300)


def test_generate_png_in_process_reports_empty_and_failed_conversions(monkeypatch, tmp_path):
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    fake_pdf2image = ModuleType("pdf2image")

    def no_images(*_args, **_kwargs):
        return []

    fake_pdf2image.convert_from_path = no_images
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)
    empty = Queue()
    _generate_png_in_process(str(pdf), str(tmp_path / "empty.png"), 72, 1200, empty)
    assert empty.get_nowait() == {"success": False, "error": "No images extracted"}

    def broken(*_args, **_kwargs):
        raise RuntimeError("poppler missing")

    fake_pdf2image.convert_from_path = broken
    failed = Queue()
    _generate_png_in_process(str(pdf), str(tmp_path / "failed.png"), 72, 1200, failed)
    assert failed.get_nowait() == {"success": False, "error": "poppler missing"}


def test_ocr_worker_returns_text_and_turns_exceptions_into_errors(monkeypatch):
    monkeypatch.setattr(
        "services.ocr.queue.OCRService.analyze_cover",
        lambda _path, language=None: {"detected_text": SAMPLE_TEXT, "year": 2019, "month": "March"},
    )
    success = _ocr_worker("/tmp/cover.png", language="English")
    assert success["success"] is True
    assert success["metadata"]["detected_text"] == SAMPLE_TEXT
    assert success["metadata"]["year"] == 2019
    assert success["metadata"]["month"] == "March"

    def timed_out(_path, language=None):
        raise TimeoutError("tesseract timed out")

    monkeypatch.setattr("services.ocr.queue.OCRService.analyze_cover", timed_out)
    timeout = _ocr_worker("cover.png")
    assert timeout["success"] is False
    assert timeout["error"] == "OCR timeout: Operation took too long"

    def illegal(_path, language=None):
        raise RuntimeError("illegal instruction")

    monkeypatch.setattr("services.ocr.queue.OCRService.analyze_cover", illegal)
    runtime = _ocr_worker("cover.png")
    assert runtime["success"] is False
    assert "Runtime error" in runtime["error"]

    def unexpected(_path, language=None):
        raise ValueError("bad image")

    monkeypatch.setattr("services.ocr.queue.OCRService.analyze_cover", unexpected)
    other = _ocr_worker("cover.png")
    assert other == {"success": False, "error": "bad image"}


def test_apply_scan_metadata_writes_year_month_and_issue():
    blank = Periodical(
        user_id=1,
        title="Wired",
        issue_date=datetime(1890, 1, 1, tzinfo=UTC),
        file_path="blank.pdf",
    )
    assert _apply_scan_metadata_to_periodical(blank, {}) is False
    assert _apply_scan_metadata_to_periodical(blank, None) is False

    low = Periodical(
        user_id=1,
        title="Wired",
        issue_date=datetime(1890, 1, 1, tzinfo=UTC),
        file_path="low.pdf",
    )
    assert _apply_scan_metadata_to_periodical(low, {"year": 2019, "year_confidence": 10}) is False
    assert low.derived_metadata is None

    row = Periodical(
        user_id=1,
        title="Wired",
        issue_date=datetime(1890, 1, 1, tzinfo=UTC),
        file_path="wired.pdf",
    )
    updated = _apply_scan_metadata_to_periodical(
        row,
        {"year": 2019, "month": "March", "issue_number": 42, "volume": 7},
    )
    assert updated is True
    assert row.derived_metadata["year"] == {"value": 2019, "source": "ocr", "confidence": 1.0}
    assert row.derived_metadata["month"]["value"] == 3
    assert row.derived_metadata["issue_number"]["value"] == 42
    assert row.derived_metadata["volume"]["value"] == 7
    assert row.issue_date.year == 2019
    assert row.issue_date.month == 3


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def test_extract_metadata_reads_year_month_and_issue():
    words = [
        {"text": "ISSUE", "confidence": 90},
        {"text": "42", "confidence": 88},
        {"text": "MARCH", "confidence": 91},
        {"text": "2019", "confidence": 96},
        {"text": "VOL.", "confidence": 80},
        {"text": "7", "confidence": 85},
    ]

    result = OCRService.extract_metadata_from_text(SAMPLE_TEXT, words_data=words)

    assert result["year"] == 2019
    assert result["month"] == "March"
    assert result["issue_number"] == 42
    assert result["volume"] == 7
    assert result["special_edition"] is False
    assert result["detected_text"] == SAMPLE_TEXT
    assert result["year_confidence"] == 96
    assert result["month_confidence"] == 91
    assert result["issue_number_confidence"] == 88
    assert result["volume_confidence"] == 85
    assert result["overall_confidence"] is not None


def test_extract_metadata_on_empty_text_returns_no_fields():
    for text in ("", "   \n\t"):
        _assert_no_fields(OCRService.extract_metadata_from_text(text))
        _assert_no_fields(OCRService.extract_metadata_from_text(text, words_data=[]))


def test_image_ocr_returns_year_month_and_issue(monkeypatch, tmp_path):
    seen = _install_tesseract(monkeypatch, SAMPLE_WORDS)
    image_path = tmp_path / "cover.png"
    Image.new("RGB", (1400, 700), "white").save(image_path)

    assert OCRService.is_available() is True
    text = OCRService.extract_text_from_image(str(image_path), language="French")
    words = OCRService.extract_text_and_words_from_image(str(image_path), language="French")
    cover = OCRService.analyze_cover(str(image_path), language="French")

    assert text == "ISSUE 42 MARCH 2019 VOL. 7"
    assert words["text"] == text
    assert words["word_count"] == 6
    assert words["words"][0]["text"] == "ISSUE"
    assert cover["year"] == 2019
    assert cover["month"] == "March"
    assert cover["issue_number"] == 42
    assert cover["volume"] == 7
    assert cover["text_found"] is True
    assert cover["extraction_method"] == "ocr_image"
    assert cover["year_confidence"] == 90
    assert all(call["lang"] == "fra" for call in seen)
    assert all(max(call["size"]) <= 1200 for call in seen)
    assert seen[0]["timeout"] == 300


def test_analyze_cover_on_empty_ocr_text_returns_no_fields(monkeypatch, tmp_path):
    _install_tesseract(monkeypatch, [])
    image_path = tmp_path / "blank.png"
    Image.new("RGB", (40, 20), "white").save(image_path)

    result = OCRService.analyze_cover(str(image_path))

    assert result == {"ocr_available": True, "text_found": False, "used_ocr": True}
    assert result.get("year") is None
    assert result.get("month") is None
    assert result.get("issue_number") is None


def test_extract_text_from_pdf_pages_feeds_metadata_extraction(monkeypatch, tmp_path):
    seen = _install_tesseract(monkeypatch, SAMPLE_WORDS)
    monkeypatch.setattr("services.ocr.service.pymupdf.open", lambda _path: _FakeDoc())
    pdf = tmp_path / "issue.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    pages = OCRService.extract_text_from_pdf_pages(str(pdf), language="en")
    cover = OCRService.analyze_cover(str(pdf), language="en")
    metadata = OCRService.extract_metadata_from_text(pages["full_text"])

    assert pages["total_pages"] == 2
    assert pages["scanned_pages"] == 2
    assert pages["pages"][0]["word_count"] == 6
    assert "ISSUE 42 MARCH 2019 VOL. 7" in pages["full_text"]
    assert metadata["year"] == 2019
    assert metadata["month"] == "March"
    assert metadata["issue_number"] == 42
    assert cover["year"] == 2019
    assert cover["month"] == "March"
    assert cover["issue_number"] == 42
    assert cover["extraction_method"] == "ocr_pdf_pages"
    assert cover["pages_scanned"] == 2
    assert all(call["lang"] == "eng" for call in seen)


def test_ocr_methods_stop_when_unavailable_and_swallow_read_errors(monkeypatch, tmp_path):
    monkeypatch.setattr("services.ocr.service.OCR_AVAILABLE", False)
    monkeypatch.setattr("services.ocr.service._ocr_config.warning_logged", False)
    image_path = tmp_path / "cover.png"
    Image.new("RGB", (10, 10), "white").save(image_path)

    assert OCRService.is_available() is False
    assert OCRService.extract_text_from_image(str(image_path)) == ""
    assert OCRService.extract_text_and_words_from_image(str(image_path)) == {
        "text": "",
        "words": [],
        "word_count": 0,
    }
    assert OCRService.extract_text_from_pdf_pages(str(tmp_path / "issue.pdf")) == {
        "pages": [],
        "error": "OCR not available",
    }
    assert OCRService.analyze_cover(str(image_path)) == {"ocr_available": False}

    monkeypatch.setattr("services.ocr.service.OCR_AVAILABLE", True)

    def unreadable(_path):
        raise OSError("unreadable pdf")

    monkeypatch.setattr("services.ocr.service.pymupdf.open", unreadable)
    missing = tmp_path / "missing.png"
    assert OCRService.extract_text_from_image(str(missing)) == ""
    word_result = OCRService.extract_text_and_words_from_image(str(missing))
    assert word_result["text"] == ""
    assert word_result["words"] == []
    assert missing.name in word_result["error"]
    pdf_result = OCRService.extract_text_from_pdf_pages(str(tmp_path / "bad.pdf"))
    assert pdf_result["pages"] == []
    assert "unreadable pdf" in pdf_result["error"]
    cover = OCRService.analyze_cover(str(tmp_path / "bad.pdf"))
    assert cover["text_found"] is False
    assert "unreadable pdf" in cover["error"]


def test_analyze_cover_skips_epub_files(monkeypatch, tmp_path):
    monkeypatch.setattr("services.ocr.service.OCR_AVAILABLE", True)
    epub = tmp_path / "book.epub"
    epub.write_bytes(b"epub")

    result = OCRService.analyze_cover(str(epub))

    assert result["ocr_available"] is True
    assert result["skipped"] is True
    assert result["used_ocr"] is False
    assert result["text_found"] is False


def test_legacy_paddle_results_are_read_without_importing_paddleocr():
    assert "paddleocr" in sys.modules

    class _Item:
        rec_texts = ["Issue", "42"]

    assert _parse_paddle_ocr_results([]) == []
    assert _parse_paddle_ocr_results(None) == []
    assert _parse_paddle_ocr_results([{"rec_texts": ["March", "2019"]}]) == ["March", "2019"]
    assert _parse_paddle_ocr_results([_Item(), {"nope": 1}, "x"]) == ["Issue", "42"]
