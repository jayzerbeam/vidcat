import sys
from pathlib import Path

import pytest

from util.file.sidecar import MagicSidecar

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="NTFS alternate data streams")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        MagicSidecar(tmp_path / "missing.mp4", "meta")


@windows_only
def test_round_trip(tmp_path: Path) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    sidecar = MagicSidecar(f, "meta")
    assert sidecar.exists is False
    assert sidecar.write(b"payload") == 7
    assert sidecar.exists is True
    assert sidecar.read() == b"payload"
    sidecar.delete()
    assert sidecar.exists is False


@windows_only
def test_read_missing_stream(tmp_path: Path) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    with pytest.raises(FileNotFoundError):
        MagicSidecar(f, "meta").read()


@windows_only
def test_delete_missing_stream(tmp_path: Path) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    with pytest.raises(FileNotFoundError):
        MagicSidecar(f, "meta").delete()


@windows_only
def test_namespace_isolation(tmp_path: Path) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    one = MagicSidecar(f, "one")
    two = MagicSidecar(f, "two")
    one.write(b"1")
    two.write(b"2")
    assert one.read() == b"1"
    assert two.read() == b"2"
    one.delete()
    assert one.exists is False
    assert two.read() == b"2"


def test_linux_not_implemented(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    monkeypatch.setattr("util.file.sidecar.platform.system", lambda: "Linux")
    with pytest.raises(NotImplementedError):
        MagicSidecar(f, "meta")


def test_darwin_not_implemented(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    monkeypatch.setattr("util.file.sidecar.platform.system", lambda: "Darwin")
    with pytest.raises(NotImplementedError):
        MagicSidecar(f, "meta")


def test_unknown_platform(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "video.mp4"
    f.write_bytes(b"data")
    monkeypatch.setattr("util.file.sidecar.platform.system", lambda: "Plan9")
    with pytest.raises(OSError):
        MagicSidecar(f, "meta")
