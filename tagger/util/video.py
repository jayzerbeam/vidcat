import io
from collections.abc import Callable, Sequence
from contextlib import suppress
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image

ProgressFunc = Callable[[float], None]


class VideoThumbnailer:
    _DEFAULT_FPS = 30  # incase it's unknown
    _path: Path
    _frames: list[tuple[Image.Image, int, int]]
    _dimensions: tuple[int, int]

    _time_base: Fraction
    _average_rate: Fraction
    _last_pts: int

    def __init__(self, path: Path):
        self._frames = []
        self._path = path

        avcontainer = av.open(self._path)
        if len(avcontainer.streams.video) == 0:
            raise ValueError(f"{self._path} has no video streams")
        vs = avcontainer.streams.video[0]

        self._dimensions = (vs.width, vs.height)
        self._time_base = vs.time_base
        self._average_rate = vs.average_rate
        avcontainer.seek(1 << 48, stream=vs)
        pkt = next(avcontainer.demux(vs))
        self._last_pts = pkt.pts
        avcontainer.close()

    @property
    def dimensions(self) -> tuple[int, int]:
        return self._dimensions

    @property
    def duration(self) -> float | None:
        return float(self._last_pts * self._time_base)

    @property
    def frame_rate(self) -> float:
        return float(1 / self._average_rate)

    @property
    def frame_count(self) -> int:
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

        avcontainer.seek(1 << 48, stream=vs, backward=True, any_frame=False)
        pkt = next(avcontainer.demux(vs))
        last_pts = pkt.pts
        duration = last_pts * vs.time_base

        if interval < 0:
            interval = last_pts / -interval  # type: ignore
        else:
            interval = interval / vs.time_base  # type: ignore

        print(
            f"{int(pkt.pts * vs.time_base / vs.average_rate)} frames, {round(duration * vs.time_base)}s, {float(vs.average_rate):.2f}fps, interval {interval:.0f} "
        )

        frames = []
        seek = 1 * vs.time_base
        progress_func(0.0)
        while seek <= last_pts:
            avcontainer.seek(int(seek), stream=vs, backward=True, any_frame=False)
            frame = next(avcontainer.decode(vs))
            frameno = framems = 0
            with suppress(TypeError):
                frameno = round(frame.pts / interval * vs.average_rate)
            with suppress(TypeError):
                framems = round(frame.pts * vs.time_base * 1000)
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
            except:
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
                img.convert("RGB")

            try:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=jpgq, optimize=True)
                bytes = buf.getvalue()
                buf.close()
                jpgs.append((bytes, fno, time))
                s += 1
                print(".", end="", flush=True)
            except:
                print("x", end="", flush=True)

        print(f" {s}/{len(self._frames)}")
        return jpgs
