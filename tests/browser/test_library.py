import sys
from pathlib import Path

import pytest

from browser.library import Trash, VideoLibrary

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing semantics")


@pytest.fixture
def library(tmp_path: Path) -> VideoLibrary:
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "sub" / "deep" / "deep.mp4").write_text("x")
    (tmp_path / "sub" / "a.mp4").write_text("x")
    (tmp_path / "b.mp4").write_text("x")
    (tmp_path / "c.txt").write_text("x")
    lib = VideoLibrary(tmp_path, (".mp4",))
    lib.scan()
    return lib


def test_scan_filters_extensions(library: VideoLibrary, tmp_path: Path) -> None:
    assert library.tree.root == tmp_path
    assert (library.tree.dir_count, library.tree.file_count) == (1, 1)

    sub = library.tree.dir("sub")
    assert sub is not None
    assert (sub.dir_count, sub.file_count) == (1, 1)
    assert [f.name for f in sub.files()] == ["a.mp4"]

    deep = sub.dir("deep")
    assert deep is not None
    assert [f.name for f in deep.files()] == ["deep.mp4"]


def test_rescan_picks_up_changes(library: VideoLibrary, tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    (sub / "a.mp4").unlink()
    (sub / "c.mp4").write_text("x")

    pt = library.rescan(sub)

    assert pt is library.tree.dir("sub")
    assert pt is not None
    assert [f.name for f in pt.files()] == ["c.mp4"]
    assert pt.dir("deep") is not None
    # the parent's own file list is not refreshed by a subtree rescan
    assert [f.name for f in library.tree.files()] == ["b.mp4"]


def test_rescan_returns_none_for_files_and_unknown_paths(library: VideoLibrary, tmp_path: Path) -> None:
    assert library.rescan(tmp_path / "b.mp4") is None
    assert library.rescan(tmp_path / "missing") is None

    (tmp_path / "unscanned").mkdir()
    assert library.rescan(tmp_path / "unscanned") is None


def test_remove(library: VideoLibrary, tmp_path: Path) -> None:
    assert library.remove(tmp_path / "b.mp4") is True
    assert library.tree.file_count == 0
    # remove only drops the tree entry, it does not delete the file
    assert (tmp_path / "b.mp4").exists()

    assert library.remove(tmp_path / "sub") is True
    assert library.tree.dir("sub") is None

    assert library.remove(tmp_path / "unknown.mp4") is False
    assert library.remove(tmp_path.parent / "outside.mp4") is False


def test_iter_files_depth_first(library: VideoLibrary, tmp_path: Path) -> None:
    assert list(library.iter_files()) == [
        tmp_path / "sub" / "deep" / "deep.mp4",
        tmp_path / "sub" / "a.mp4",
        tmp_path / "b.mp4",
    ]


def test_iter_files_scoped_to_subtree(library: VideoLibrary, tmp_path: Path) -> None:
    assert list(library.iter_files(tmp_path / "sub")) == [
        tmp_path / "sub" / "deep" / "deep.mp4",
        tmp_path / "sub" / "a.mp4",
    ]
    assert list(library.iter_files(tmp_path / "unknown")) == []


def test_trash_creates_missing_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "trash"

    trash = Trash(path)

    assert path.is_dir()
    assert trash.available is True


def test_trash_unavailable_when_mkdir_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "trash"

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("drive unavailable")

    monkeypatch.setattr(Path, "mkdir", _fail)

    trash = Trash(path)

    assert trash.available is False
    assert f"error: failed to create trash directory {path}: drive unavailable" in capsys.readouterr().out


def test_trash_send_moves_files_and_skips_missing(tmp_path: Path) -> None:
    trash = Trash(tmp_path / "trash")
    one = tmp_path / "one.mp4"
    two = tmp_path / "two.mp4"
    one.write_text("x")
    two.write_text("x")

    moved = trash.send([one, tmp_path / "missing.mp4", two])

    assert moved == [one, two]
    assert not one.exists()
    assert not two.exists()
    assert (tmp_path / "trash" / "one.mp4").exists()
    assert (tmp_path / "trash" / "two.mp4").exists()


def test_trash_send_avoids_overwriting_same_named_entry(tmp_path: Path) -> None:
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    (trash_dir / "video.mp4").write_text("original")
    trash = Trash(trash_dir)
    source = tmp_path / "video.mp4"
    source.write_text("new")

    moved = trash.send([source])

    assert moved == [source]
    assert not source.exists()
    # the pre-existing entry is intact; the new file lands beside it under a numbered name
    assert (trash_dir / "video.mp4").read_text() == "original"
    assert (trash_dir / "video (1).mp4").read_text() == "new"

    # a further collision number keeps increasing instead of reusing a taken name
    another = tmp_path / "again.mp4"
    another.write_text("again")
    (trash_dir / "again.mp4").write_text("taken")

    assert trash.send([another]) == [another]
    assert (trash_dir / "again.mp4").read_text() == "taken"
    assert (trash_dir / "again (1).mp4").read_text() == "again"


def test_trash_unavailable_when_path_is_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "trash"
    path.write_text("not a directory")
    f = tmp_path / "video.mp4"
    f.write_text("x")

    trash = Trash(path)

    assert trash.available is False
    assert trash.send([f]) == []
    assert f.exists()
    assert "error:trash directory is not a directory, could not initialize" in capsys.readouterr().out


@windows_only
def test_trash_send_reports_move_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trash_path = tmp_path / "trash"
    trash = Trash(trash_path)
    f = tmp_path / "video.mp4"
    f.write_text("x")

    # an open CRT handle blocks the rename on Windows
    with open(f, "rb"):
        moved = trash.send([f])

    assert moved == []
    assert f.exists()
    assert not (trash_path / f.name).exists()
    assert f"error: failed to move {f} to trash:" in capsys.readouterr().out
