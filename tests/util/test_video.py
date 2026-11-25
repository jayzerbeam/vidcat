from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

import util.video as video_module
from util.video import VideoReader, VideoThumbnailer


class FakeStream:
    width = 640
    height = 480
    time_base = Fraction(1, 100)
    average_rate = Fraction(25, 1)
    guessed_rate = None
    base_rate = None
    duration = 100


class FakePacket:
    pts = 100


class NoPtsPacket(FakePacket):
    pts = None


class FakeFrame:
    pts = 50

    def to_image(self) -> object:
        return object()


class FrameAt04s(FakeFrame):
    pts = 40  # the 0.4 s mark at FakeStream.time_base (1/100)


class FakeContainer:
    """Minimal av container double: hands out packets/frames, records close()."""

    def __init__(
        self,
        video_streams: list[FakeStream] | None = None,
        *,
        seek_error: Exception | None = None,
        demux_packets: list[FakePacket] | None = None,
        decode_frames: list[FakeFrame] | None = None,
    ) -> None:
        self.streams = SimpleNamespace(video=video_streams if video_streams is not None else [FakeStream()])
        self.seek_error = seek_error
        self._demux_packets = demux_packets if demux_packets is not None else [FakePacket()]
        self._decode_frames = decode_frames if decode_frames is not None else [FakeFrame()]
        self.closed = False
        self.seek_targets: list[int] = []

    def seek(self, *args, **kwargs) -> None:
        self.seek_targets.append(int(args[0]))
        if self.seek_error is not None:
            raise self.seek_error

    def demux(self, *args, **kwargs):
        return iter(list(self._demux_packets))

    def decode(self, *args, **kwargs):
        return iter(list(self._decode_frames))

    def close(self) -> None:
        self.closed = True


def _patch_av(monkeypatch: pytest.MonkeyPatch, *containers: FakeContainer) -> None:
    """Hand out one FakeContainer per av.open() call, in order."""
    remaining = list(containers)

    def _open(_path: Path) -> FakeContainer:
        return remaining.pop(0)

    monkeypatch.setattr(video_module, "av", SimpleNamespace(open=_open))


def test_thumbnailer_init_closes_container_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer()
    _patch_av(monkeypatch, container)

    vt = VideoThumbnailer(Path("clip.mp4"))

    assert container.closed is True
    assert vt.duration == 1.0


def test_thumbnailer_init_closes_container_when_no_video_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(video_streams=[])
    _patch_av(monkeypatch, container)

    with pytest.raises(ValueError, match="no video streams"):
        VideoThumbnailer(Path("clip.mp4"))

    assert container.closed is True


def test_thumbnailer_init_closes_container_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(seek_error=OSError("corrupt index"))
    _patch_av(monkeypatch, container)

    with pytest.raises(OSError, match="corrupt index"):
        VideoThumbnailer(Path("clip.mp4"))

    assert container.closed is True


def test_thumbnailer_probe_falls_back_to_stream_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(demux_packets=[NoPtsPacket()])
    _patch_av(monkeypatch, container)

    vt = VideoThumbnailer(Path("clip.mp4"))

    # the last packet carries no PTS: FakeStream.duration (100 ticks) stands in
    assert vt._last_pts == 100
    assert vt.duration == 1.0


def test_thumbnailer_probe_survives_packetless_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(demux_packets=[])
    _patch_av(monkeypatch, container)

    # an empty demux used to raise StopIteration out of __init__
    vt = VideoThumbnailer(Path("clip.mp4"))

    assert vt._last_pts == 100
    assert container.closed is True


def test_extract_frames_closes_container_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    init, extract = FakeContainer(), FakeContainer()
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))
    vt.extract_frames(interval=-1)

    assert extract.closed is True
    assert len(vt._frames) == 1


def test_extract_frames_closes_container_when_no_video_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    init, extract = FakeContainer(), FakeContainer(video_streams=[])
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))

    with pytest.raises(ValueError, match="no video streams"):
        vt.extract_frames(interval=-1)

    assert extract.closed is True


def test_extract_frames_closes_container_when_probe_yields_no_packets(monkeypatch: pytest.MonkeyPatch) -> None:
    init = FakeContainer()
    extract = FakeContainer(demux_packets=[])
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))

    with pytest.raises(StopIteration):
        vt.extract_frames(interval=-1)

    assert extract.closed is True


def test_extract_frames_closes_container_when_decode_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    init = FakeContainer()
    extract = FakeContainer(decode_frames=[])
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))

    with pytest.raises(StopIteration):
        vt.extract_frames(interval=-1)

    assert extract.closed is True


def test_extract_frames_frame_number_at_interval_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    init = FakeContainer()
    extract = FakeContainer(decode_frames=[FrameAt04s()])
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))
    vt.extract_frames(interval=30.0)

    # 0.4 s into a 25 fps video is frame 10; the old code returned thumbnail index * fps (0)
    _, frameno, framems = vt._frames[0]
    assert frameno == 10
    assert framems == 400


def test_extract_frames_frame_number_at_fixed_sample_count(monkeypatch: pytest.MonkeyPatch) -> None:
    init = FakeContainer()
    extract = FakeContainer(decode_frames=[FrameAt04s()])
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))
    vt.extract_frames(interval=-4)

    # 4 samples over 1 s: the old code returned thumbnail index * fps (40) here
    _, frameno, _ = vt._frames[0]
    assert frameno == 10


def test_extract_frames_logs_real_frame_count_and_duration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    init, extract = FakeContainer(), FakeContainer()
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))
    vt.extract_frames(interval=-1)

    # 1 s at 25 fps; the old code double-applied time_base and divided by the rate ("0 frames, 0s")
    assert "25 frames, 1s" in capsys.readouterr().out


def test_extract_frames_seeks_in_demux_tick_units(monkeypatch: pytest.MonkeyPatch) -> None:
    init, extract = FakeContainer(), FakeContainer()
    _patch_av(monkeypatch, init, extract)

    vt = VideoThumbnailer(Path("clip.mp4"))
    vt.extract_frames(interval=-1)

    # the probe seeks to the far end first; extraction starts at tick 1 instead of 1 * time_base (which truncated to 0)
    assert extract.seek_targets == [1 << 48, 1]


def test_video_reader_closes_container_when_no_video_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(video_streams=[])
    _patch_av(monkeypatch, container)

    with pytest.raises(ValueError, match="no video streams"):
        VideoReader(Path("clip.mp4"))

    assert container.closed is True


def test_video_reader_closes_container_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(seek_error=OSError("truncated file"))
    _patch_av(monkeypatch, container)

    with pytest.raises(OSError, match="truncated file"):
        VideoReader(Path("clip.mp4"))

    assert container.closed is True


def test_video_reader_probe_falls_back_to_stream_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(demux_packets=[NoPtsPacket()])
    _patch_av(monkeypatch, container)

    reader = VideoReader(Path("clip.mp4"))

    assert reader._last_pts == 100
    assert reader.duration == 1.0


def test_video_reader_probe_survives_packetless_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer(demux_packets=[])
    _patch_av(monkeypatch, container)

    # an empty demux used to raise StopIteration out of __init__
    reader = VideoReader(Path("clip.mp4"))

    assert reader._last_pts == 100
    assert container.closed is False


def test_video_reader_keeps_container_open_until_close(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer()
    _patch_av(monkeypatch, container)

    reader = VideoReader(Path("clip.mp4"))

    # the reader stays usable for scrubbing after setup; close() owns teardown
    assert container.closed is False
    assert reader.duration == 1.0
    reader.close()
    assert container.closed is True


def test_video_reader_fps_is_frames_per_second(monkeypatch: pytest.MonkeyPatch) -> None:
    container = FakeContainer()
    _patch_av(monkeypatch, container)

    reader = VideoReader(Path("clip.mp4"))

    # FakeStream.average_rate is 25/1: the property reports the rate itself, not its period
    assert reader.fps == 25.0
