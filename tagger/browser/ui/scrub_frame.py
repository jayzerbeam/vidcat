import queue
import threading
import tkinter as tk
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from typing import Any, NamedTuple

from PIL import Image, ImageTk

from ui.tk_decorator import tk_debounce
from util.format import clock_format
from util.video import VideoReader

from .constants import VirtualEventSequence


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

    _widgets: __Widgets
    _path: Path | None
    _duration_ms: float
    _frame_rate: float
    _current_frame: Image.Image | None
    _frame_image: ImageTk.PhotoImage | None
    _load_seq: int
    _seek_seq: int
    _requests: queue.Queue[tuple[_ScrubRequest, int, Any]]
    _results: queue.Queue[tuple[Any, ...]]
    _poll_after: str | None
    _worker: threading.Thread

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._path = None
        self._duration_ms = 0.0
        self._frame_rate = 0.0
        self._current_frame = None
        self._frame_image = None
        self._load_seq = 0
        self._seek_seq = 0
        self._requests = queue.Queue()
        self._results = queue.Queue()
        self._poll_after = None

        ctrlfrm = ttk.Frame(self)
        self._widgets = __class__.__Widgets(
            video=tk.Canvas(self),
            seek=ttk.Scale(self, orient=tk.HORIZONTAL, to=1.0, command=self._handle_seek),
            controls=ctrlfrm,
            open=ttk.Button(ctrlfrm, text="Open", command=self._handle_open),
            position=ttk.Label(ctrlfrm, anchor=tk.E, width=24),
        )
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._widgets.video.grid(column=0, row=0, columnspan=2, padx=4, pady=(4, 0), sticky="NSEW")
        self._widgets.seek.grid(column=0, row=1, padx=(4, 4), sticky="EW")
        self._widgets.controls.grid(column=0, row=2, padx=(4, 4), pady=(0, 4), sticky="EW")
        self._widgets.controls.columnconfigure(0, weight=1)
        self._widgets.open.grid(column=0, row=0, sticky="W")
        self._widgets.position.grid(column=1, row=0, sticky="E")
        self._widgets.video.bind("<Configure>", self._handle_video_configure, add=True)

        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._poll_results()

    def load(self, path: Path) -> None:
        """Load a video file for scrubbing. Replaces any previously loaded file."""
        if path == self._path and self._duration_ms > 0:
            return

        self._path = path
        self._duration_ms = 0.0
        self._frame_rate = 0.0
        self._current_frame = None
        self._widgets.video.delete("frame")
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])
        self._update_time_label(None)

        self._load_seq += 1
        self._requests.put((_ScrubRequest.LOAD, self._load_seq, path))

    def clear(self) -> None:
        self._path = None
        self._duration_ms = 0.0
        self._frame_rate = 0.0
        self._current_frame = None
        self._widgets.video.delete("frame")
        self._widgets.seek.state(["disabled"])
        self._widgets.open.state(["disabled"])
        self._update_time_label(None)

        # invalidate any pending load result and release the file handle
        self._load_seq += 1
        self._requests.put((_ScrubRequest.CLOSE, 0, None))

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
                except Exception as ex:
                    print(f"error: failed to load {payload} for scrubbing: {ex}")
                    continue
                self._results.put((_ScrubRequest.LOAD, seq, reader.duration, reader.frame_rate, frame))
            elif kind is _ScrubRequest.SEEK:
                if reader is None:
                    continue
                # coalesce: skip if a newer request is already queued
                if not self._requests.empty():
                    continue
                frame = reader.frame_at(payload)
                self._results.put((_ScrubRequest.SEEK, seq, payload, frame))
            elif kind is _ScrubRequest.CLOSE:
                if reader is not None:
                    reader.close()
                    reader = None

        if reader is not None:
            reader.close()

    def _poll_results(self) -> None:
        while not self._results.empty():
            kind, seq, *rest = self._results.get()
            if kind is _ScrubRequest.LOAD:
                self._apply_loaded(seq, *rest)
            elif kind is _ScrubRequest.SEEK:
                self._apply_frame(seq, *rest)
        self._poll_after = self.after(30, self._poll_results)

    def _apply_loaded(self, seq: int, duration: float | None, frame_rate: float, frame: Image.Image | None) -> None:
        if seq != self._load_seq:
            return

        self._duration_ms = (duration or 0.0) * 1000
        self._frame_rate = frame_rate
        if self._duration_ms > 0:
            self._widgets.seek.state(["!disabled"])
            self._widgets.open.state(["!disabled"])
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
        frameno = round(time_s * self._frame_rate)
        self._widgets.position.config(text=f"{clock_format(time_s, decimals=3)}  frame {frameno}")

    def _handle_open(self) -> None:
        if self._path is None or self._duration_ms <= 0:
            return
        ms = round(float(self._widgets.seek.get()) * self._duration_ms)
        self.event_generate(VirtualEventSequence.PLAY_FROM_MS, data=ms)

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
