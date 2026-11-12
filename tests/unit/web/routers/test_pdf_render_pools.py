"""PDF page renders use process pools that must recover and shut down."""

import asyncio
import inspect
from concurrent.futures.process import BrokenProcessPool
from unittest.mock import Mock

import pytest

import web.routers.periodicals.files as files
from core.constants.files import PDF_RENDER_PAGE_WORKERS, PDF_RENDER_THUMBNAIL_WORKERS


@pytest.fixture(autouse=True)
def _clear_render_pools():
    files._render_pools.clear()
    yield
    for pool in list(files._render_pools.values()):
        pool.shutdown(wait=False, cancel_futures=True)
    files._render_pools.clear()


def test_pool_size_prefers_the_environment(monkeypatch):
    monkeypatch.setenv("CURATOR_PDF_RENDER_PAGE_WORKERS", "3")
    monkeypatch.setenv("CURATOR_PDF_RENDER_THUMBNAIL_WORKERS", "1")

    assert files._render_pool_size("page") == 3
    assert files._render_pool_size("thumbnail") == 1


def test_pool_size_reads_config_when_the_environment_is_unset(monkeypatch):
    monkeypatch.delenv("CURATOR_PDF_RENDER_PAGE_WORKERS", raising=False)

    class _Loader:
        def get_pdf(self):
            return {"render_page_workers": 6}

    monkeypatch.setattr("core.config.ConfigLoader", lambda: _Loader())

    assert files._render_pool_size("page") == 6


def test_an_unusable_pool_size_keeps_the_default(monkeypatch):
    monkeypatch.setenv("CURATOR_PDF_RENDER_PAGE_WORKERS", "0")
    monkeypatch.setenv("CURATOR_PDF_RENDER_THUMBNAIL_WORKERS", "nope")

    assert files._render_pool_size("page") == PDF_RENDER_PAGE_WORKERS
    assert files._render_pool_size("thumbnail") == PDF_RENDER_THUMBNAIL_WORKERS


def test_shutdown_render_pools_stops_workers():
    page = Mock()
    thumbnail = Mock()
    files._render_pools["page"] = page
    files._render_pools["thumbnail"] = thumbnail

    files.shutdown_render_pools()

    page.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    thumbnail.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    assert files._render_pools == {}


def test_application_shutdown_stops_the_render_pools():
    from web.app import lifespan

    assert "shutdown_render_pools" in inspect.getsource(lifespan)


@pytest.mark.asyncio
async def test_a_broken_process_pool_is_replaced(monkeypatch):
    monkeypatch.setenv("CURATOR_PDF_RENDER_PAGE_WORKERS", "2")
    created = []

    class _Pool:
        def __init__(self, max_workers, mp_context):
            self.max_workers = max_workers
            created.append(self)

        def shutdown(self, wait=True, cancel_futures=False):
            return None

    monkeypatch.setattr(files, "ProcessPoolExecutor", _Pool)
    loop = asyncio.get_running_loop()
    calls = {"n": 0}

    def run_in_executor(pool, func, *args):
        calls["n"] += 1
        future = loop.create_future()
        if calls["n"] == 1:
            future.set_exception(BrokenProcessPool("worker died"))
        else:
            future.set_result(b"jpeg")
        return future

    monkeypatch.setattr(loop, "run_in_executor", run_in_executor)

    with pytest.raises(BrokenProcessPool):
        await files._render_in_process("page", lambda *_args: b"", "file.pdf", 0)

    assert "page" not in files._render_pools
    assert await files._render_in_process("page", lambda *_args: b"", "file.pdf", 0) == b"jpeg"
    assert len(created) == 2
    assert created[0].max_workers == 2
    assert "page" in files._render_pools
