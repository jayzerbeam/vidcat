import io
from collections.abc import Callable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import av
from PIL import Image

ProgressFunc = Callable[[float], None]


def _stream_rate(stream: Any) -> Fraction | None:
    """Best-effort frames-per-second for a video stream, or None if the container doesn't report one."""
    return stream.average_rate or stream.guessed_rate or stream.base_rate


class VideoThumbnailer:
    _DEFAULT_FPS = 30  # incase it's unknown
    _path: Path
    _frames: list[tuple[Image.Image, int, int]]
    _dimensions: tuple[int, int]

    _time_base: Fraction | None
    _average_rate: Fraction | None
    _last_pts: int | None

    def __init__(self, path: Path):
        self._frames = []
        self._path = path

        avcontainer = av.open(self._path)
        if len(avcontainer.streams.video) == 0:
            raise ValueError(f"{self._path} has no video streams")
        vs = avcontainer.streams.video[0]

        self._dimensions = (vs.width, vs.height)
        self._time_base = vs.time_base
        self._average_rate = _stream_rate(vs)
        avcontainer.seek(1 << 48, stream=vs, any_frame=True)
        pkt = next(avcontainer.demux(vs))
        self._last_pts = pkt.pts
        avcontainer.close()

    @property
    def dimensions(self) -> tuple[int, int]:
        return self._dimensions

    @property
    def duration(self) -> float | None:
        if self._last_pts is None or self._time_base is None:
            return None
        return float(self._last_pts * self._time_base)

    @property
    def frame_rate(self) -> float | None:
        if self._average_rate is None:
            return None
        return float(1 / self._average_rate)

    @property
    def frame_count(self) -> int | None:
        if self._last_pts is None or self._time_base is None or self._average_rate is None:
            return None
        return int(self._last_pts * self._time_base / self._average_rate)

    def extract_frames(self, interval: float = 30.0, progress_func: ProgressFunc = lambda p: None) -> None:
        """Extract frames at a given interval

        Parameters:
        interval (float): interval in seconds if positive, fixed number of frames if negative
        progress_func (Callable[[float], None): progress callback, receives a float param [0,1]
        """
        if interval == 0:
            raise ValueError(f"invalid interval ({interval})")

        avcontainer = av.open(self._path)
        if len(avcontainer.streams.video) == 0:
            raise ValueError(f"{self._path} has no video streams")
        vs = avcontainer.streams.video[0]
        rate = _stream_rate(vs)

        avcontainer.seek(1 << 48, stream=vs, backward=True, any_frame=False)
        pkt = next(avcontainer.demux(vs))
        last_pts = pkt.pts
        if last_pts is None:
            last_pts = vs.duration
        time_base = vs.time_base
        if last_pts is None or time_base is None:
            avcontainer.close()
            raise ValueError(f"{self._path} has no usable timestamps")
        duration = last_pts * time_base

        if interval < 0:
            interval = last_pts / -interval
        else:
            interval = interval / time_base

        if rate is not None:
            print(
                f"{int(last_pts * time_base / rate)} frames, {round(duration * time_base)}s, {float(rate):.2f}fps, interval {interval:.0f} "
            )
        else:
            print(f"unknown fps, interval {interval:.0f} ")

        frames = []
        seek = 1 * time_base
        progress_func(0.0)
        while seek <= last_pts:
            avcontainer.seek(int(seek), stream=vs, backward=True, any_frame=False)
            frame = next(avcontainer.decode(vs))
            frameno = framems = 0
            if frame.pts is not None:
                if rate is not None:
                    frameno = round(frame.pts / interval * rate)
                framems = round(frame.pts * time_base * 1000)
            frames.append((frame.to_image(), frameno, framems))
            progress_func(float(seek / last_pts))
            print(".", end="")
            seek += interval

        avcontainer.close()
        print(f" {len(frames)}")
        progress_func(1.0)
        self._frames = frames

    def resize_frames(self, resize_height: int = 240, progress_func: ProgressFunc = lambda p: None) -> None:
        """Resizes all the held extracted frames
        This is a destructive operation
        """
        if not self._frames:
            return

        resized_frames = []

        # all frames should have the same dimentions so only calc off the first
        oldw, oldh = self._frames[0][0].size
        (neww, newh) = (int(resize_height / oldh * oldw), resize_height)
        s = 0
        print(f"resizing {oldw}x{oldh} -> {neww}x{newh} ", end="")
        progress_func(0.0)

        for i, fdata in enumerate(self._frames):
            try:
                rimg = fdata[0].resize((neww, newh), Image.Resampling.LANCZOS)
                resized_frames.append((rimg,) + fdata[1:])
                print(".", end="", flush=True)
                s += 1
            except Exception:
                print("x", end="", flush=True)

            progress_func(i / len(self._frames))

        print(f" {s}/{len(self._frames)}")
        progress_func(1.0)

        self._frames = resized_frames

    def gen_jpgs(self, jpgq: int = 70) -> Sequence[tuple[bytes, int, int]] | None:
        if not self._frames:
            return

        print("generating jpgs ", end="")
        jpgs = []
        s = 0  # success
        for img, fno, time in self._frames:
            if img.mode != "RGB":
                img = img.convert("RGB")

            try:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=jpgq, optimize=True)
                data = buf.getvalue()
                buf.close()
                jpgs.append((data, fno, time))
                s += 1
                print(".", end="", flush=True)
            except Exception:
                print("x", end="", flush=True)

        print(f" {s}/{len(self._frames)}")
        return jpgs


class VideoReader:
    """Random access frame reader for scrubbing.

    A video container and its decoder are not safe for concurrent use, so an instance
    must be used from a single thread and closed on that same thread.
    """

    _path: Path
    _container: Any
    _stream: Any
    _last_pts: int

    def __init__(self, path: Path):
        self._path = path
        self._container = av.open(path)
        if len(self._container.streams.video) == 0:
            raise ValueError(f"{self._path} has no video streams")
        self._stream = self._container.streams.video[0]

        self._container.seek(1 << 48, stream=self._stream)
        pkt = next(self._container.demux(self._stream))
        self._last_pts = pkt.pts

    @property
    def dimensions(self) -> tuple[int, int]:
        return (self._stream.width, self._stream.height)

    @property
    def duration(self) -> float | None:
        return float(self._last_pts * self._stream.time_base)

    @property
    def frame_rate(self) -> float | None:
        """Frames per second, or None if the container does not report a rate."""
        rate = _stream_rate(self._stream)
        return float(rate) if rate is not None else None

    def frame_at(self, time_s: float) -> Image.Image | None:
        """Decode and return the frame at (or just before) the given time in seconds"""
        duration = self.duration
        if duration is not None:
            time_s = min(max(time_s, 0.0), duration)

        try:
            self._container.seek(
                int(time_s / self._stream.time_base), stream=self._stream, backward=True, any_frame=False
            )
            frame = next(self._container.decode(self._stream))
        except Exception as ex:
            print(f"error: failed to decode frame at {time_s}s from {self._path}: {ex}")
            return None

        return frame.to_image()

    def close(self) -> None:
        self._container.close()
