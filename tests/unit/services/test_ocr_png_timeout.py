"""One slow OCR image must not cancel the other PDFs in the batch."""

from queue import Queue

from services.ocr.queue import _generate_pngs_parallel


class _Finished:
    def __init__(self, target, args, daemon):
        self.queue = args[4]
        self.killed = False
        self.pid = 1

    def start(self):
        self.queue.put({"success": True})

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False

    def kill(self):
        self.killed = True


class _Slow:
    def __init__(self, target, args, daemon):
        self.killed = False
        self.pid = 2

    def start(self):
        return None

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return True

    def kill(self):
        self.killed = True


def test_a_slow_pdf_does_not_cancel_a_finished_one(monkeypatch):
    finished = {}
    slow = {}

    def process_factory(target, args, daemon):
        if args[0] == "slow.pdf":
            proc = _Slow(target, args, daemon)
            slow["proc"] = proc
            return proc
        proc = _Finished(target, args, daemon)
        finished["proc"] = proc
        return proc

    monkeypatch.setattr("services.ocr.queue._mp_ctx.Process", process_factory)
    monkeypatch.setattr("services.ocr.queue._mp_ctx.Queue", Queue)

    jobs = [
        {"periodical_id": 1, "pdf_path": "slow.pdf", "png_path": "slow.png", "dpi": 72, "max_dimension": 100},
        {"periodical_id": 2, "pdf_path": "done.pdf", "png_path": "done.png", "dpi": 72, "max_dimension": 100},
    ]

    results = _generate_pngs_parallel(jobs, timeout=0)

    assert results[1] == "timeout"
    assert results[2] == "ok"
    assert slow["proc"].killed is True
    assert finished["proc"].killed is False
