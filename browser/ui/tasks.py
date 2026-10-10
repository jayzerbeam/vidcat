import gc
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from functools import partial
from queue import Queue
from typing import Any

from .status_window import StatusWindow


class UiDispatcher:
    """FIFO marshaling of callbacks onto the Tk main thread."""

    _root: tk.Misc
    _interval_ms: int
    _queue: Queue[Callable[[], None]]

    def __init__(self, root: tk.Misc, interval_ms: int = 30) -> None:
        self._root = root
        self._interval_ms = interval_ms
        self._queue = Queue()
        self._root.after(interval_ms, self._drain)

    def post(self, callback: Callable[..., None], *args: Any) -> None:
        """Queue callback(*args) to run on the Tk main thread."""
        self._queue.put(partial(callback, *args))

    def _drain(self) -> None:
        try:
            while not self._queue.empty():
                callback = self._queue.get()
                try:
                    callback()
                except Exception as ex:
                    print(f"error: UI callback failed: {ex}")
                    traceback.print_exc()
        finally:
            # reschedule even if draining failed partway, so one bad callback cannot stall the queue
            self._root.after(self._interval_ms, self._drain)


class JobContext:
    """Worker-thread-safe bridge handed to background work."""

    _dispatcher: UiDispatcher
    _status: StatusWindow

    def __init__(self, dispatcher: UiDispatcher, status: StatusWindow) -> None:
        self._dispatcher = dispatcher
        self._status = status

    def post(self, callback: Callable[..., None], *args: Any) -> None:
        """Marshal callback(*args) to the UI thread."""
        self._dispatcher.post(callback, *args)

    def progress(self, info: str, fraction: float) -> None:
        """Set the status text and the progress bar, on the UI thread."""
        self._dispatcher.post(self._set_progress, info, fraction)

    def fraction(self, value: float) -> None:
        """Set the progress bar only, on the UI thread."""
        self._dispatcher.post(self._set_fraction, value)

    def progress_func(self, prefix: str) -> Callable[[float], None]:
        """Return a progress callback rendering ``f"{prefix} {fraction * 100:.1f}%"``."""
        return lambda fraction: self.progress(f"{prefix} {fraction * 100:.1f}%", fraction)

    def _set_progress(self, info: str, fraction: float) -> None:
        self._status.info = info
        self._status.progress = fraction

    def _set_fraction(self, value: float) -> None:
        self._status.progress = value


class BackgroundJobs:
    """Runs background work with the shared status/busy lifecycle."""

    _dispatcher: UiDispatcher
    _status: StatusWindow
    _on_busy: Callable[[bool], None]

    def __init__(self, dispatcher: UiDispatcher, status: StatusWindow, on_busy: Callable[[bool], None]) -> None:
        self._dispatcher = dispatcher
        self._status = status
        self._on_busy = on_busy

    def run(self, work: Callable[[JobContext], None], *, busy: bool = False, collect_garbage: bool = False) -> None:
        """Show the status window and run work(ctx) on a daemon thread, then hide it."""
        self._status.show()
        if busy:
            self._on_busy(True)

        ctx = JobContext(self._dispatcher, self._status)

        def _thread() -> None:
            try:
                work(ctx)
            except Exception as ex:
                print(f"error: background job failed: {ex}")
                traceback.print_exc()
            finally:
                if busy:
                    self._dispatcher.post(self._on_busy, False)
                self._dispatcher.post(self._status.hide)
                if collect_garbage:
                    # jobs create many buffers; collecting afterward keeps memory from ballooning
                    gc.collect()

        threading.Thread(target=_thread, daemon=True).start()
