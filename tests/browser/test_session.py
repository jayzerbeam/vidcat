from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from browser.metadata import Bookmark, StoredMetadata, empty_metadata
from browser.session import VideoSession
from browser.ui.state import BookmarksChanged, FileMetadataChanged, SelectionChanged, Thumbnail, ThumbnailsChanged
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
    """Duck-typed UiState signal; records emissions in a shared order log.

    Like the real Signal, emit invokes connected handlers synchronously, iterating over a
    tuple snapshot of the handler list.
    """

    def __init__(self, log: list[str], name: str) -> None:
        self.emissions: list[Any] = []
        self.handlers: list[Callable[[Any], None]] = []
        self._log = log
        self._name = name

    def connect(self, callback: Callable[[Any], None]) -> None:
        self.handlers.append(callback)

    def emit(self, value: Any) -> None:
        self.emissions.append(value)
        self._log.append(self._name)
        for handler in tuple(self.handlers):
            handler(value)


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
        self.stored_metadata_changed = FakeSignal(log, "stored_metadata_changed")
        self.staged_metadata_changed = FakeSignal(log, "staged_metadata_changed")
        self.thumbnails_changed = FakeSignal(log, "thumbnails_changed")
        self.bookmarks_changed = FakeSignal(log, "bookmarks_changed")


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


def _split_list(value: Any) -> tuple[str, ...]:
    """Split comma-separated text like Tk does, but pass structured values through.

    A restaged pane holds the payload's list values; the widget round-trip they survive in
    the real app would hand them back as structured values, not comma-separated text.
    """
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return tuple(value.split(","))


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
    return VideoSession(cast(Any, state), cast(Any, store), split_list=_split_list)


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
    assert state.selection_changed.emissions == [SelectionChanged((f,))]
    # the view refreshes before the selection signal
    assert log == ["staged_metadata_changed", "thumbnails_changed", "bookmarks_changed", "selection_changed"]


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
    assert state.selection_changed.emissions == [SelectionChanged(())]
    assert log == ["staged_metadata_changed", "thumbnails_changed", "bookmarks_changed", "selection_changed"]


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
    assert state.selection_changed.emissions == [
        SelectionChanged((f,)),
        SelectionChanged(()),
        SelectionChanged((f,)),
        SelectionChanged(()),
    ]


def test_load_emits_thumbnails_as_named_payload(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    """The stored raw (jpeg, frame_no, time_ms) tuples are converted at the UI boundary."""
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)

    session.select((f,), triggered=f)

    assert state.thumbnails_changed.emissions == [ThumbnailsChanged((Thumbnail(b"jpg", 1, 1),))]


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
    assert log == ["staged_metadata_changed", "thumbnails_changed", "bookmarks_changed", "write"]


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

    assert log == ["staged_metadata_changed", "thumbnails_changed", "bookmarks_changed"]
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


def test_stored_metadata_for_selected_file_restages(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    log: list[str],
    tmp_path: Path,
) -> None:
    """A store-side event for the selected file fully replaces the staged view."""
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)
    session.select((f,), triggered=f)
    log.clear()
    payload = empty_metadata()
    payload["title"] = "restaged"
    payload["actors"] = ["alice", "bob"]
    payload["tags"] = ["tag"]
    payload["thumbnails"] = [(b"newjpg", 2, 20)]

    state.stored_metadata_changed.emit(FileMetadataChanged(f, payload))

    assert state.meta_title.value == "restaged"
    assert state.meta_actors.value == ["alice", "bob"]
    assert state.meta_tags.value == ["tag"]
    assert state.thumbnails_changed.emissions[-1] == ThumbnailsChanged((Thumbnail(b"newjpg", 2, 20),))
    # the payload is copied, not retained: later staged edits replace top-level keys on the
    # copy, never on the emitter's snapshot
    assert session._metadata == payload
    assert session._metadata is not payload
    assert log == ["stored_metadata_changed", "staged_metadata_changed", "thumbnails_changed", "bookmarks_changed"]


def test_stored_metadata_for_other_file_is_ignored(
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
    log.clear()
    state.staged_metadata_changed.emissions.clear()
    state.thumbnails_changed.emissions.clear()
    state.bookmarks_changed.emissions.clear()
    payload = empty_metadata()
    payload["title"] = "other"
    other = tmp_path / "other.mp4"

    state.stored_metadata_changed.emit(FileMetadataChanged(other, payload))

    assert log == ["stored_metadata_changed"]
    assert state.staged_metadata_changed.emissions == []
    assert state.thumbnails_changed.emissions == []
    assert state.bookmarks_changed.emissions == []
    assert state.meta_title.value == "loaded"
    assert session._metadata == loaded_metadata


def test_bulk_edit_restage_is_persisted_by_save(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    """The reported bug: Ctrl+S must not revert a bulk edit with the stale staged values."""
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)
    session.select((f,), triggered=f)
    payload = empty_metadata()
    payload["title"] = "loaded"
    payload["actors"] = ["alice", "bob"]
    payload["tags"] = ["tag"]

    state.stored_metadata_changed.emit(FileMetadataChanged(f, payload))
    session.save()

    assert len(store.writes) == 1
    path, metadata = store.writes[0]
    assert path == f
    assert metadata["actors"] == ("alice", "bob")
    assert metadata["tags"] == ("tag",)


def test_thumbnail_generation_restage_is_persisted_by_save(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Bulk thumbnail generation writes the store; a later save must keep the new thumbnails."""
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)
    session.select((f,), triggered=f)
    payload = empty_metadata()
    payload["title"] = "loaded"
    payload["thumbnails"] = [(b"newjpg", 2, 20)]

    state.stored_metadata_changed.emit(FileMetadataChanged(f, payload))
    session.save()

    assert state.thumbnails_changed.emissions[-1] == ThumbnailsChanged((Thumbnail(b"newjpg", 2, 20),))
    _, metadata = store.writes[0]
    assert metadata["thumbnails"] == [(b"newjpg", 2, 20)]


def test_clean_restage_does_not_resurrect_deleted_metadata(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    """Clean emits empty metadata; a later save must not write the old values back."""
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)
    session.select((f,), triggered=f)

    state.stored_metadata_changed.emit(FileMetadataChanged(f, empty_metadata()))
    session.save()

    _, metadata = store.writes[0]
    assert metadata["title"] == ""
    assert metadata["actors"] == ()
    assert metadata["tags"] == ()
    assert metadata["thumbnails"] == []


def test_restage_does_not_reemit_the_store_signal(
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
    log.clear()
    payload = empty_metadata()
    payload["title"] = "restaged"

    state.stored_metadata_changed.emit(FileMetadataChanged(f, payload))

    # exactly one render: the handler must never re-emit the store-side signal it consumes
    assert log == ["stored_metadata_changed", "staged_metadata_changed", "thumbnails_changed", "bookmarks_changed"]
    assert log.count("stored_metadata_changed") == 1


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
    assert state.selection_changed.emissions == [SelectionChanged((f,)), SelectionChanged(())]
    assert log == ["staged_metadata_changed", "thumbnails_changed", "bookmarks_changed", "selection_changed"]


def test_load_keeps_none_size_label_when_store_has_no_metadata(
    session: VideoSession, state: FakeState, tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")

    session.select((f,), triggered=f)

    assert session.selected_path == f
    assert state.meta_size.value == "metadata size: none"


def test_load_emits_bookmarks_parsed_from_sidecar(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    """The stored plain dicts are converted to typed bookmarks, in time order, at the UI boundary."""
    f = _write_file(tmp_path / "video.mp4")
    loaded_metadata["bookmarks"] = [
        {"time_ms": 7000, "frame_no": 175, "name": "outro"},
        {"time_ms": 5000, "frame_no": 125, "name": "intro"},
    ]
    store.results[f] = StoredMetadata(loaded_metadata, 1234)

    session.select((f,), triggered=f)

    assert state.bookmarks_changed.emissions == [
        BookmarksChanged(f, (Bookmark(5000, 125, "intro"), Bookmark(7000, 175, "outro")))
    ]


def test_load_emits_empty_bookmarks_for_legacy_metadata(
    session: VideoSession,
    state: FakeState,
    store: FakeStore,
    loaded_metadata: dict[str, Any],
    tmp_path: Path,
) -> None:
    del loaded_metadata["bookmarks"]
    f = _write_file(tmp_path / "video.mp4")
    store.results[f] = StoredMetadata(loaded_metadata, 1234)

    session.select((f,), triggered=f)

    assert state.bookmarks_changed.emissions == [BookmarksChanged(f, ())]


def test_clear_emits_empty_bookmarks_for_no_path(session: VideoSession, state: FakeState, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    state.bookmarks_changed.emissions.clear()

    session.clear()

    assert state.bookmarks_changed.emissions == [BookmarksChanged(Path(), ())]


def test_add_bookmark_stages_and_emits_without_writing(
    session: VideoSession, state: FakeState, store: FakeStore, log: list[str], tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    log.clear()
    state.bookmarks_changed.emissions.clear()

    added = session.add_bookmark(5000, 125, "intro")

    assert added is True
    assert state.bookmarks_changed.emissions == [BookmarksChanged(f, (Bookmark(5000, 125, "intro"),))]
    assert log == ["bookmarks_changed"]
    # staged only: the sidecar is untouched until save()
    assert store.writes == []


def test_add_bookmark_duplicate_time_returns_false_without_emission(
    session: VideoSession, state: FakeState, tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    session.add_bookmark(5000, 125, "intro")
    state.bookmarks_changed.emissions.clear()

    added = session.add_bookmark(5000, 150, "other")

    assert added is False
    assert state.bookmarks_changed.emissions == []


def test_add_bookmark_keeps_unsaved_entry_edits(
    session: VideoSession, state: FakeState, log: list[str], tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    state.meta_title.value = "edited but unsaved"
    log.clear()

    session.add_bookmark(5000, 125, "intro")

    # pins the no-_show() decision: a refresh would re-seed the entry widgets from _metadata
    assert state.meta_title.value == "edited but unsaved"
    assert log == ["bookmarks_changed"]


def test_remove_bookmark_stages_and_emits_reduced_list(
    session: VideoSession, state: FakeState, store: FakeStore, log: list[str], tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    session.add_bookmark(5000, 125, "intro")
    session.add_bookmark(7000, 175, "outro")
    state.meta_title.value = "edited but unsaved"
    log.clear()
    state.bookmarks_changed.emissions.clear()

    session.remove_bookmark(5000)

    assert state.bookmarks_changed.emissions == [BookmarksChanged(f, (Bookmark(7000, 175, "outro"),))]
    assert state.meta_title.value == "edited but unsaved"
    assert log == ["bookmarks_changed"]
    assert store.writes == []


def test_remove_bookmark_missing_time_emits_nothing(session: VideoSession, state: FakeState, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    session.add_bookmark(5000, 125, "intro")
    state.bookmarks_changed.emissions.clear()

    session.remove_bookmark(7000)

    assert state.bookmarks_changed.emissions == []


def test_mutators_without_selection_do_nothing(session: VideoSession, state: FakeState, log: list[str]) -> None:
    assert session.add_bookmark(5000, 125, "intro") is False

    session.remove_bookmark(5000)

    assert state.bookmarks_changed.emissions == []
    assert log == []


def test_save_writes_staged_bookmarks_as_plain_dicts(
    session: VideoSession, state: FakeState, store: FakeStore, tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    session.select((f,), triggered=f)
    session.add_bookmark(7000, 175, "outro")
    session.add_bookmark(5000, 125, "intro")
    # save() re-reads the entry widgets as comma-separated text through split_list
    state.meta_actors.value = ""
    state.meta_tags.value = ""

    session.save()

    assert len(store.writes) == 1
    _, metadata = store.writes[0]
    assert metadata["bookmarks"] == [
        {"time_ms": 5000, "frame_no": 125, "name": "intro"},
        {"time_ms": 7000, "frame_no": 175, "name": "outro"},
    ]
