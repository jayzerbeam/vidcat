from pathlib import Path
from typing import Any, cast

import pytest

from browser.metadata import StoredMetadata, empty_metadata
from browser.session import VideoSession
from util.format import nice_bytesize, nice_duration


class FakeVar:
    """Duck-typed Tk variable: plain get/set storage."""

    def __init__(self) -> None:
        self.value: Any = ""

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class FakeSignal:
    """Duck-typed UiState signal; records emissions in a shared order log."""

    def __init__(self, log: list[str], name: str) -> None:
        self.emissions: list[Any] = []
        self._log = log
        self._name = name

    def emit(self, value: Any) -> None:
        self.emissions.append(value)
        self._log.append(self._name)


class FakeState:
    """Duck-typed UiState exposing exactly the vars/signals VideoSession uses."""

    def __init__(self, log: list[str]) -> None:
        self.file_path = FakeVar()
        self.file_size = FakeVar()
        self.meta_size = FakeVar()
        self.meta_title = FakeVar()
        self.meta_actors = FakeVar()
        self.meta_tags = FakeVar()
        self.video_len = FakeVar()
        self.video_res = FakeVar()
        self.selection_changed = FakeSignal(log, "selection_changed")
        self.file_metadata_changed = FakeSignal(log, "file_metadata_changed")
        self.thumbnails_changed = FakeSignal(log, "thumbnails_changed")


class FakeStore:
    """Duck-typed MetadataStore with configurable reads and recorded writes."""

    def __init__(self, log: list[str], write_size: int = 2000) -> None:
        self.results: dict[Path, StoredMetadata] = {}
        self.writes: list[tuple[Path, dict[str, Any]]] = []
        self.write_size = write_size
        self._log = log

    def read_or_empty(self, path: Path) -> StoredMetadata:
        return self.results.get(path, StoredMetadata(empty_metadata(), 0))

    def write(self, path: Path, metadata: dict[str, Any]) -> int:
        self.writes.append((path, metadata))
        self._log.append("write")
        return self.write_size


def _write_file(path: Path) -> Path:
    path.write_text("x")
    return path


@pytest.fixture
def log() -> list[str]:
    return []


@pytest.fixture
def state(log: list[str]) -> FakeState:
    return FakeState(log)


@pytest.fixture
def store(log: list[str]) -> FakeStore:
    return FakeStore(log)


@pytest.fixture
def session(state: FakeState, store: FakeStore) -> VideoSession:
    return VideoSession(cast(Any, state), cast(Any, store), split_list=lambda value: tuple(value.split(",")))


@pytest.fixture
def loaded_metadata() -> dict[str, Any]:
    metadata = empty_metadata()
    metadata["title"] = "loaded"
    metadata["actors"] = ["actor"]
    metadata["tags"] = ["tag"]
    metadata["video_properties"] = {"dimensions": (640, 480), "duration": 90.0}
    metadata["thumbnails"] = [(b"jpg", 1, 1)]
    return metadata


def test_select_triggered_file_loads_and_emits_selection_last(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)

    session.select((f,), triggered=f)

    assert session.selected_path == f
    assert state.file_path.value == str(f)
    assert state.file_size.value == f"size: {nice_bytesize(f.stat().st_size, largest_unit='M')}"
    assert state.meta_size.value == f"metadata size: {nice_bytesize(1234)}"
    assert state.meta_title.value == "loaded"
    assert state.video_len.value == f"length: {nice_duration(90)}"
    assert state.video_res.value == "resolution: 640x480"
    assert state.selection_changed.emissions == [(f,)]
    # the view refreshes before the selection signal
    assert log == ["file_metadata_changed", "thumbnails_changed", "selection_changed"]


def test_select_triggered_directory_clears(
    session: VideoSession, state: FakeState, log: list[str], tmp_path: Path
) -> None:
    directory = tmp_path / "folder.mp4"
    directory.mkdir()

    session.select((directory,), triggered=directory)

    assert session.selected_path is None
    assert state.file_path.value == ""
    assert state.file_size.value == "size: none"
    assert state.meta_size.value == "metadata size: none"
    assert state.selection_changed.emissions == [()]
    assert log == ["file_metadata_changed", "thumbnails_changed", "selection_changed"]


def test_select_without_trigger_picks_first_file(session: VideoSession, tmp_path: Path) -> None:
    directory = tmp_path / "sub"
    directory.mkdir()
    first = _write_file(tmp_path / "first.mp4")
    second = _write_file(tmp_path / "second.mp4")

    session.select((directory, first, second))

    assert session.selected_path == first


def test_select_without_files_clears(session: VideoSession, state: FakeState, tmp_path: Path) -> None:
    directory = tmp_path / "sub"
    directory.mkdir()
    f = _write_file(tmp_path / "video.mp4")

    session.select((f,), triggered=f)
    assert session.selected_path == f

    session.select((directory,))
    assert session.selected_path is None

    session.select((f,), triggered=f)
    assert session.selected_path == f

    session.select(())
    assert session.selected_path is None
    assert state.selection_changed.emissions == [(f,), (), (f,), ()]


def test_save_writes_title_actors_tags_and_size_label(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)
    log.clear()
    state.meta_title.value = "new title"
    state.meta_actors.value = "alice,bob"
    state.meta_tags.value = "Tag"

    session.save()

    assert len(store.writes) == 1
    path, metadata = store.writes[0]
    assert path == f
    assert metadata["title"] == "new title"
    assert metadata["actors"] == ("alice", "bob")
    assert metadata["tags"] == ("Tag",)
    # the loaded metadata is mutated in place, not rebuilt
    assert metadata["video_properties"] == {"dimensions": (640, 480), "duration": 90.0}
    assert metadata["thumbnails"] == [(b"jpg", 1, 1)]
    assert state.meta_size.value == f"metadata size: {round(store.write_size / 1000)}KB"
    # the view refreshes before the sidecar is written
    assert log == ["file_metadata_changed", "thumbnails_changed", "write"]


def test_apply_for_none_matching_path_only_refreshes(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)
    log.clear()

    session.apply_for(f, None)

    assert log == ["file_metadata_changed", "thumbnails_changed"]
    assert state.meta_title.value == "loaded"


def test_apply_for_matching_path_merges_generated_metadata(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)

    session.apply_for(f, {"title": "generated"})

    assert state.meta_title.value == "generated"
    # loaded fields survive the merge
    assert state.meta_actors.value == ["actor"]


def test_apply_for_wrong_path_is_a_no_op(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    other = _write_file(tmp_path / "other.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)
    log.clear()

    session.apply_for(other, {"title": "generated"})

    assert state.meta_title.value == "loaded"
    assert log == []


def test_apply_for_cleared_selection_is_a_no_op(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)
    session.clear()
    log.clear()

    session.apply_for(f, {"title": "generated"})

    assert state.meta_title.value == ""
    assert log == []


def test_clear_resets_state_and_emits(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 10)
    session.select((f,), triggered=f)
    log.clear()

    session.clear()

    assert session.selected_path is None
    assert (state.file_path.value, state.file_size.value) == ("", "size: none")
    assert state.meta_size.value == "metadata size: none"
    assert state.meta_title.value == ""
    assert state.selection_changed.emissions == [(f,), ()]
    assert log == ["file_metadata_changed", "thumbnails_changed", "selection_changed"]


def test_load_keeps_none_size_label_when_store_has_no_metadata(
    session: VideoSession, state: FakeState, tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")

    session.select((f,), triggered=f)

    assert session.selected_path == f
    assert state.meta_size.value == "metadata size: none"
