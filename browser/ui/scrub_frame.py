import queue
import threading
import tkinter as tk
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from PIL import Image, ImageTk

from browser.metadata import Bookmark
from ui.tk_decorator import tk_debounce
from util.format import clock_format
from util.video import VideoReader

from .actions import UiContext
from .bookmark_frame import BookmarkFrame
from .state import BookmarksChanged, SelectionChanged


class _ScrubRequest(StrEnum):
    LOAD = "load"
    SEEK = "seek"
    CLOSE = "close"
    STOP = "stop"


class ScrubFrame(ttk.Frame):
    class __Widgets(NamedTuple):
        video: tk.Canvas
        seek: ttk.Scale
        controls: ttk.Frame
        open: ttk.Button
        position: ttk.Label
        bookmarks: BookmarkFrame

    _ctx: UiContext
    _widgets: __Widgets
    _path: Path | None
    _bookmarks_path: Path | None
    _bookmarks: tuple[Bookmark, ...]
    _duration_ms: float
    _frame_rate: float | None
    _current_frame: Image.Image | None
    _frame_image: ImageTk.PhotoImage | None
    _load_seq: int
    _seek_seq: int
    _requests: queue.Queue[tuple[_ScrubRequest, int, Any]]
    _results: queue.Queue[tuple[Any, ...]]
    _poll_after: str | None
    _worker: threading.Thread

    def __init__(self, parent: tk.Misc, ctx: UiContext, *args: Any, **kwargs: Any):
        super().__init__(parent, *args, **kwargs)
        self._ctx = ctx
        self._path = None
        self._bookmarks_path = None
        self._bookmarks = ()
        self._duration_ms = 0.0
        self._frame_rate = None
        self._current_frame = None
        self._frame_image = None
        self._load_seq = 0
        self._seek_seq = 0
        self._requests = queue.Queue()
        self._results = queue.Queue()
        self._poll_after = None

        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        ctrlfrm = ttk.Frame(self)
        self._widgets = __class__.__Widgets(
            video=tk.Canvas(self),
            seek=ttk.Scale(self, orient=tk.HORIZONTAL, to=1.0, command=self._handle_seek),
            controls=ctrlfrm,
            open=ttk.Button(ctrlfrm, text="Open", command=self._handle_open),
            position=ttk.Label(ctrlfrm, anchor=tk.E, width=24),
            bookmarks=BookmarkFrame(pane),
        )
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])
        self._widgets.bookmarks.set_enabled(False)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        pane.add(self._widgets.video, weight=1)
        pane.add(self._widgets.bookmarks, weight=0)
        pane.grid(column=0, row=0, columnspan=2, padx=(4, 4), pady=(4, 0), sticky="NSEW")
        self._widgets.seek.grid(column=0, row=1, padx=(4, 4), sticky="EW")
        self._widgets.controls.grid(column=0, row=2, padx=(4, 4), pady=(0, 4), sticky="EW")
        self._widgets.controls.columnconfigure(0, weight=1)
        self._widgets.open.grid(column=0, row=0, sticky="W")
        self._widgets.position.grid(column=1, row=0, sticky="E")
        self._widgets.video.bind("<Configure>", self._handle_video_configure, add=True)
        self._widgets.bookmarks.set_add_handler(self._handle_bookmark_add)
        self._widgets.bookmarks.set_seek_handler(self._handle_bookmark_seek)
        self._widgets.bookmarks.set_remove_handler(self._handle_bookmark_remove)

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._poll_results()

        ctx.state.selection_changed.connect(self._handle_selection)
        ctx.state.bookmarks_changed.connect(self._handle_bookmarks_changed)

    def _handle_selection(self, change: SelectionChanged) -> None:
        paths = change.paths
        if len(paths) == 1 and paths[0].is_file():
            self.load(paths[0])
        else:
            # synchronous clear: App relies on the file handle being released before trashing
            self.clear(wait=True)

    def load(self, path: Path) -> None:
        """Load a video file for scrubbing. Replaces any previously loaded file."""
        if path == self._path and self._duration_ms > 0:
            return

        self._path = path
        self._duration_ms = 0.0
        self._frame_rate = None
        self._current_frame = None
        self._widgets.video.delete("frame")
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])
        self._widgets.bookmarks.set_enabled(False)
        self._render_bookmarks()
        self._update_time_label(None)

        self._load_seq += 1
        self._requests.put((_ScrubRequest.LOAD, self._load_seq, path))

    def clear(self, wait: bool = False, timeout: float = 2.0) -> bool:
        self._path = None
        self._duration_ms = 0.0
        self._frame_rate = None
        self._current_frame = None
        self._widgets.video.delete("frame")
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])
        self._widgets.bookmarks.set_enabled(False)
        self._render_bookmarks()
        self._update_time_label(None)

        # invalidate any pending load result and release the file handle
        self._load_seq += 1
        done = threading.Event() if wait else None
        self._requests.put((_ScrubRequest.CLOSE, 0, done))
        if done is not None:
            return done.wait(timeout)
        return True

    def _handle_bookmarks_changed(self, change: BookmarksChanged) -> None:
        self._bookmarks_path = change.path
        self._bookmarks = change.bookmarks
        if change.path == self._path:
            self._render_bookmarks()

    def _render_bookmarks(self) -> None:
        """Render the cached bookmarks, or an empty list when they belong to another file."""
        if self._bookmarks_path is not None and self._bookmarks_path == self._path:
            self._widgets.bookmarks.set_bookmarks(self._bookmarks)
        else:
            self._widgets.bookmarks.set_bookmarks(())

    def _worker_loop(self) -> None:
        reader: VideoReader | None = None

        while True:
            kind, seq, payload = self._requests.get()
            if kind is _ScrubRequest.STOP:
                break

            if kind is _ScrubRequest.LOAD:
                if reader is not None:
                    reader.close()
                    reader = None
                try:
                    reader = VideoReader(payload)
                    frame = reader.frame_at(0.0)
                    duration = reader.duration
                    frame_rate = reader.frame_rate
                except Exception as ex:
                    # a file that can't be read (or has no frame rate) simply isn't loaded
                    print(f"error: failed to load {payload} for scrubbing: {ex}")
                    if reader is not None:
                        reader.close()
                        reader = None
                    continue
                self._results.put((_ScrubRequest.LOAD, seq, duration, frame_rate, frame))
            elif kind is _ScrubRequest.SEEK:
                if reader is None:
                    continue
                # coalesce: skip if a newer request is already queued
                if not self._requests.empty():
                    continue
                try:
                    frame = reader.frame_at(payload)
                except Exception as ex:
                    print(f"error: failed to seek {payload}s for scrubbing: {ex}")
                    continue
                self._results.put((_ScrubRequest.SEEK, seq, payload, frame))
            elif kind is _ScrubRequest.CLOSE:
                try:
                    if reader is not None:
                        reader.close()
                        reader = None
                finally:
                    if payload is not None:
                        payload.set()

        if reader is not None:
            reader.close()

    def _poll_results(self) -> None:
        try:
            while not self._results.empty():
                kind, seq, *rest = self._results.get()
                try:
                    if kind is _ScrubRequest.LOAD:
                        self._apply_loaded(seq, *rest)
                    elif kind is _ScrubRequest.SEEK:
                        self._apply_frame(seq, *rest)
                except Exception as ex:
                    print(f"error: failed to apply scrubber result: {ex}")
        finally:
            # always keep polling so one bad result can't permanently stall the scrubber
            self._poll_after = self.after(30, self._poll_results)

    def _apply_loaded(
        self, seq: int, duration: float | None, frame_rate: float | None, frame: Image.Image | None
    ) -> None:
        if seq != self._load_seq:
            return

        self._duration_ms = (duration or 0.0) * 1000
        self._frame_rate = frame_rate
        if self._duration_ms > 0:
            self._widgets.seek.state(["!disabled"])
            self._widgets.open.state(["!disabled"])
            self._widgets.bookmarks.set_enabled(True)
        self._update_time_label(0.0)
        self._draw_frame(frame)

    def _apply_frame(self, seq: int, time_s: float, frame: Image.Image | None) -> None:
        if seq != self._seek_seq:
            return
        self._update_time_label(time_s)
        self._draw_frame(frame)

    def _update_time_label(self, time_s: float | None) -> None:
        if time_s is None:
            self._widgets.position.config(text="")
            return
        text = clock_format(time_s, decimals=3)
        if text is None:
            self._widgets.position.config(text="")
            return
        if self._frame_rate is not None:
            text += f"  frame {round(time_s * self._frame_rate)}"
        self._widgets.position.config(text=text)

    def _current_ms(self) -> int | None:
        """Milliseconds at the seek bar's current position, or None when nothing is loaded."""
        if self._path is None or self._duration_ms <= 0:
            return None
        return round(float(self._widgets.seek.get()) * self._duration_ms)

    def _handle_open(self) -> None:
        ms = self._current_ms()
        if ms is None:
            return
        self._ctx.actions.play_from_ms(ms)

    def _seek_to_ms(self, ms: int) -> None:
        """Move the seek bar to ms; the Scale command then updates the label and renders the frame."""
        if self._path is None or self._duration_ms <= 0:
            return
        fraction = min(1.0, max(0.0, ms / self._duration_ms))
        self._widgets.seek.set(fraction)

    def _handle_bookmark_seek(self, bookmark: Bookmark) -> None:
        current_ms = self._current_ms()
        if current_ms is not None and current_ms == bookmark.time_ms:
            # already at this bookmark: re-seeking would only re-render the same frame
            return
        self._seek_to_ms(bookmark.time_ms)

    def _handle_bookmark_remove(self, bookmark: Bookmark) -> None:
        self._ctx.actions.remove_bookmark(bookmark.time_ms)

    def _handle_bookmark_add(self, name: str) -> bool:
        ms = self._current_ms()
        if ms is None:
            return False
        frame_no = round(ms / 1000 * self._frame_rate) if self._frame_rate is not None else None
        return self._ctx.actions.add_bookmark(ms, frame_no, name)

    @tk_debounce(50, leading=True)
    def _handle_seek(self, pos: str) -> None:
        if self._path is None or self._duration_ms <= 0:
            return
        try:
            fraction = float(pos)
        except ValueError:
            return

        time_s = fraction * (self._duration_ms / 1000)
        self._update_time_label(time_s)
        self._seek_seq += 1
        self._requests.put((_ScrubRequest.SEEK, self._seek_seq, time_s))

    @tk_debounce(100, leading=False)
    def _handle_video_configure(self, ev: tk.Event) -> None:
        self._render_current_frame()

    def _draw_frame(self, frame: Image.Image | None) -> None:
        if frame is None:
            return
        self._current_frame = frame
        self._render_current_frame()

    def _render_current_frame(self) -> None:
        if self._current_frame is None:
            return

        width = self._widgets.video.winfo_width()
        height = self._widgets.video.winfo_height()
        if width <= 1 or height <= 1:
            return

        imgw, imgh = self._current_frame.size
        scale = min(width / imgw, height / imgh)
        size = (max(1, int(imgw * scale)), max(1, int(imgh * scale)))
        image = self._current_frame.resize(size, Image.Resampling.LANCZOS)

        self._frame_image = ImageTk.PhotoImage(image)
        self._widgets.video.delete("frame")
        self._widgets.video.create_image(width // 2, height // 2, image=self._frame_image, tags="frame")

    def destroy(self) -> None:
        if self._poll_after is not None:
            self.after_cancel(self._poll_after)
            self._poll_after = None
        if self._worker.is_alive():
            self._requests.put((_ScrubRequest.STOP, 0, None))
            self._worker.join(timeout=1.0)
        super().destroy()
