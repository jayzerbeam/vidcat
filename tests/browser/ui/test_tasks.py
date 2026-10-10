import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from browser.ui import tasks as tasks_module
from browser.ui.tasks import BackgroundJobs, JobContext, UiDispatcher


class FakeRoot:
    """Records after() schedules and runs the oldest pending callback on demand."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[int, Callable[[], None]]] = []

    def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
        self.scheduled.append((delay_ms, callback))

    def run_next(self) -> None:
        _, callback = self.scheduled.pop(0)
        callback()


class FakeDispatcher:
    """Records posted callbacks and can execute them FIFO on demand."""

    def __init__(self) -> None:
        self.posted: list[tuple[Any, tuple[Any, ...]]] = []

    def post(self, callback: Any, *args: Any) -> None:
        self.posted.append((callback, args))

    def run_all(self) -> None:
        while self.posted:
            callback, args = self.posted.pop(0)
            callback(*args)


class FakeStatus:
    """Records show/hide in a shared log and holds the current info/progress values."""

    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.info = ""
        self.progress = 0.0

    def show(self) -> None:
        self.log.append("show")

    def hide(self) -> None:
        self.log.append("hide")


class SyncThread:
    """Thread stand-in that runs its target synchronously when started."""

    def __init__(self, target: Callable[[], None], daemon: bool | None = None) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


def _wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


@pytest.fixture
def log() -> list[str]:
    return []


@pytest.fixture
def dispatcher() -> FakeDispatcher:
    return FakeDispatcher()


@pytest.fixture
def status(log: list[str]) -> FakeStatus:
    return FakeStatus(log)


@pytest.fixture
def sync_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make BackgroundJobs run work synchronously so terminal state is deterministic."""
    monkeypatch.setattr(tasks_module.threading, "Thread", SyncThread)


def test_dispatcher_schedules_drain_on_construction() -> None:
    root = FakeRoot()

    UiDispatcher(root)

    assert len(root.scheduled) == 1
    assert root.scheduled[0][0] == 30


def test_dispatcher_runs_callbacks_fifo_and_reschedules() -> None:
    root = FakeRoot()
    dispatcher = UiDispatcher(root)
    calls: list[int] = []

    dispatcher.post(calls.append, 1)
    dispatcher.post(calls.append, 2)
    assert calls == []

    root.run_next()

    assert calls == [1, 2]
    assert len(root.scheduled) == 1


def test_dispatcher_isolates_callback_failures(capsys: pytest.CaptureFixture[str]) -> None:
    root = FakeRoot()
    dispatcher = UiDispatcher(root)
    calls: list[str] = []

    def _fail() -> None:
        raise RuntimeError("boom")

    dispatcher.post(_fail)
    dispatcher.post(calls.append, "after")

    root.run_next()

    assert calls == ["after"]
    assert len(root.scheduled) == 1
    captured = capsys.readouterr()
    assert "error: UI callback failed: boom" in captured.out
    assert "Traceback" in captured.err


def test_job_context_post_forwards_to_ui_thread(dispatcher: FakeDispatcher, status: FakeStatus) -> None:
    ctx = JobContext(dispatcher, status)
    seen: list[str] = []

    ctx.post(seen.append, "value")

    assert seen == []  # only queued, not run on the worker side
    dispatcher.run_all()
    assert seen == ["value"]


def test_job_context_progress_sets_info_and_bar(dispatcher: FakeDispatcher, status: FakeStatus) -> None:
    ctx = JobContext(dispatcher, status)

    ctx.progress("loading", 0.25)

    assert (status.info, status.progress) == ("", 0.0)  # applied when the UI thread drains
    dispatcher.run_all()
    assert (status.info, status.progress) == ("loading", 0.25)


def test_job_context_fraction_sets_bar_only(dispatcher: FakeDispatcher, status: FakeStatus) -> None:
    status.info = "keep"
    ctx = JobContext(dispatcher, status)

    ctx.fraction(0.75)

    dispatcher.run_all()
    assert (status.info, status.progress) == ("keep", 0.75)


@pytest.mark.parametrize(
    ("prefix", "fraction", "info"),
    [
        ("Extracting frames...", 0.123, "Extracting frames... 12.3%"),
        ("Resizing frames...", 0.05, "Resizing frames... 5.0%"),
    ],
)
def test_job_context_progress_func_renders_percent(
    dispatcher: FakeDispatcher, status: FakeStatus, prefix: str, fraction: float, info: str
) -> None:
    ctx = JobContext(dispatcher, status)

    ctx.progress_func(prefix)(fraction)

    dispatcher.run_all()
    assert (status.info, status.progress) == (info, fraction)


def test_background_jobs_lifecycle(
    monkeypatch: pytest.MonkeyPatch, log: list[str], dispatcher: FakeDispatcher, status: FakeStatus
) -> None:
    collected: list[int] = []
    monkeypatch.setattr(tasks_module.gc, "collect", lambda: collected.append(1))
    jobs = BackgroundJobs(dispatcher, status, lambda busy: log.append(f"busy:{busy}"))
    finished = threading.Event()
    daemons: list[bool] = []

    def work(ctx: JobContext) -> None:
        daemons.append(threading.current_thread().daemon)
        log.append("work")
        finished.set()

    jobs.run(work, busy=True, collect_garbage=True)

    assert finished.wait(timeout=5)
    assert daemons == [True]
    # show/busy-on run before the work; the terminal signals are queued, not run by the worker
    assert log == ["show", "busy:True", "work"]

    _wait_for(lambda: collected == [1])
    assert log == ["show", "busy:True", "work"]

    dispatcher.run_all()

    # busy-off is posted before hide (spec delta 6)
    assert log == ["show", "busy:True", "work", "busy:False", "hide"]


def test_background_jobs_without_busy_or_gc(
    sync_threads: None, monkeypatch: pytest.MonkeyPatch, log: list[str], dispatcher: FakeDispatcher, status: FakeStatus
) -> None:
    collected: list[int] = []
    monkeypatch.setattr(tasks_module.gc, "collect", lambda: collected.append(1))
    jobs = BackgroundJobs(dispatcher, status, lambda busy: log.append(f"busy:{busy}"))

    jobs.run(lambda ctx: None)

    assert collected == []
    assert log == ["show"]
    assert [callback for callback, _ in dispatcher.posted] == [status.hide]

    dispatcher.run_all()

    assert log == ["show", "hide"]
    assert collected == []


def test_background_jobs_logs_work_failure_and_still_closes(
    sync_threads: None, capsys: pytest.CaptureFixture[str], log: list[str], dispatcher: FakeDispatcher, status: FakeStatus
) -> None:
    jobs = BackgroundJobs(dispatcher, status, lambda busy: None)

    def work(ctx: JobContext) -> None:
        raise RuntimeError("boom")

    jobs.run(work, busy=True)

    captured = capsys.readouterr()
    assert "error: background job failed: boom" in captured.out
    assert "Traceback" in captured.err
    assert log == ["show"]

    dispatcher.run_all()

    assert log == ["show", "hide"]
