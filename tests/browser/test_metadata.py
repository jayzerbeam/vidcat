from pathlib import Path
from typing import Any

import pytest

from browser import metadata as metadata_module
from browser.metadata import (
    EMPTY_METADATA,
    Bookmark,
    BulkAction,
    MetadataStore,
    aggregate_files,
    apply_bulk_edit,
    delete_bookmark,
    empty_metadata,
    generate_files,
    generate_video_metadata,
    insert_bookmark,
    parse_bookmarks,
    refresh_files,
)

type SidecarStorage = dict[tuple[Path, str], bytes]


class FakeSidecar:
    """In-memory sidecar storage shared through a dict keyed by (path, namespace)."""

    def __init__(self, storage: SidecarStorage, path: Path, namespace: str) -> None:
        self._storage = storage
        self._key = (path, namespace)

    @property
    def exists(self) -> bool:
        return self._key in self._storage

    def read(self) -> bytes:
        if self._key not in self._storage:
            raise FileNotFoundError(f"no sidecar for {self._key[0]}")
        return self._storage[self._key]

    def write(self, data: bytes) -> int:
        self._storage[self._key] = data
        return len(data)

    def delete(self) -> None:
        if self._key not in self._storage:
            raise FileNotFoundError(f"no sidecar for {self._key[0]}")
        del self._storage[self._key]


def _write_file(path: Path) -> Path:
    path.write_text("x")
    return path


@pytest.fixture
def storage() -> SidecarStorage:
    return {}


@pytest.fixture
def store(storage: SidecarStorage) -> MetadataStore:
    return MetadataStore("meta", lambda path, namespace: FakeSidecar(storage, path, namespace))


def test_empty_metadata_returns_independent_copies() -> None:
    one = empty_metadata()
    two = empty_metadata()

    one["actors"].append("actor")
    one["video_properties"]["dimensions"] = (1, 1)
    one["bookmarks"].append({"time_ms": 0, "frame_no": None, "name": ""})

    assert two == EMPTY_METADATA
    assert EMPTY_METADATA["actors"] == []
    assert EMPTY_METADATA["video_properties"]["dimensions"] == (0, 0)
    assert EMPTY_METADATA["bookmarks"] == []


def test_apply_bulk_edit_add_actor_sorts_and_reports_change() -> None:
    metadata = empty_metadata()
    metadata["actors"] = ["b"]

    assert apply_bulk_edit(metadata, BulkAction.ADD_ACTOR, "a") is True
    assert metadata["actors"] == ["a", "b"]

    assert apply_bulk_edit(metadata, BulkAction.ADD_ACTOR, "a") is False
    assert metadata["actors"] == ["a", "b"]


def test_apply_bulk_edit_del_actor_removes_and_preserves_order() -> None:
    metadata = empty_metadata()
    metadata["actors"] = ["b", "a", "c"]

    assert apply_bulk_edit(metadata, BulkAction.DEL_ACTOR, "a") is True
    assert metadata["actors"] == ["b", "c"]

    assert apply_bulk_edit(metadata, BulkAction.DEL_ACTOR, "a") is False


def test_apply_bulk_edit_tag_actions_use_lowercase() -> None:
    metadata = empty_metadata()

    assert apply_bulk_edit(metadata, BulkAction.ADD_TAG, "MiXeD") is True
    assert metadata["tags"] == ["mixed"]

    assert apply_bulk_edit(metadata, BulkAction.DEL_TAG, "MIXED") is True
    assert metadata["tags"] == []


def test_apply_bulk_edit_coerces_tuples_and_tolerates_missing_keys() -> None:
    metadata: dict[str, Any] = {"actors": ("b",)}

    assert apply_bulk_edit(metadata, BulkAction.ADD_ACTOR, "a") is True
    assert metadata["actors"] == ["a", "b"]

    assert apply_bulk_edit({}, BulkAction.DEL_ACTOR, "missing") is False
    assert apply_bulk_edit({}, BulkAction.ADD_TAG, "New") is True
    assert apply_bulk_edit({}, BulkAction.DEL_TAG, "new") is False


def test_parse_bookmarks_tolerates_missing_key_and_non_list() -> None:
    assert parse_bookmarks({}) == ()
    assert parse_bookmarks({"bookmarks": None}) == ()
    assert parse_bookmarks({"bookmarks": "nope"}) == ()


def test_parse_bookmarks_skips_non_dict_entries_and_invalid_times() -> None:
    metadata = {
        "bookmarks": [
            "not a dict",
            None,
            {"frame_no": 1, "name": "no time"},
            {"time_ms": True, "frame_no": 2, "name": "bool time"},
            {"time_ms": 1.5, "frame_no": 3, "name": "float time"},
            {"time_ms": "4", "frame_no": 4, "name": "string time"},
            {"time_ms": 5, "frame_no": 5, "name": "ok"},
        ]
    }

    assert parse_bookmarks(metadata) == (Bookmark(5, 5, "ok"),)


def test_parse_bookmarks_sorts_by_time_and_neutralizes_malformed_fields() -> None:
    metadata = {
        "bookmarks": [
            {"time_ms": 3000, "frame_no": 30, "name": "c"},
            {"time_ms": 10, "frame_no": None, "name": "a"},
            {"time_ms": 2000, "frame_no": "30f", "name": 7},
            {"time_ms": 1000, "frame_no": 3.0, "name": "float frame"},
            {"time_ms": 1500, "frame_no": "3", "name": "string frame"},
        ]
    }

    # frame_no takes only a plain int: 3.0 and "3" would convert by value, but must still neutralize
    assert parse_bookmarks(metadata) == (
        Bookmark(10, None, "a"),
        Bookmark(1000, None, "float frame"),
        Bookmark(1500, None, "string frame"),
        Bookmark(2000, None, ""),
        Bookmark(3000, 30, "c"),
    )


def test_insert_bookmark_keeps_time_order_and_stores_plain_dicts() -> None:
    metadata = empty_metadata()
    metadata["bookmarks"] = [{"time_ms": 3000, "frame_no": 30, "name": "c"}]

    assert insert_bookmark(metadata, Bookmark(1000, 10, "a")) is True
    assert insert_bookmark(metadata, Bookmark(2000, None, "")) is True

    assert metadata["bookmarks"] == [
        {"time_ms": 1000, "frame_no": 10, "name": "a"},
        {"time_ms": 2000, "frame_no": None, "name": ""},
        {"time_ms": 3000, "frame_no": 30, "name": "c"},
    ]
    assert all(type(entry) is dict for entry in metadata["bookmarks"])


def test_insert_bookmark_rejects_duplicate_time_and_leaves_list_unchanged() -> None:
    metadata = empty_metadata()
    metadata["bookmarks"] = [{"time_ms": 1000, "frame_no": 10, "name": "a"}]
    existing = metadata["bookmarks"]

    assert insert_bookmark(metadata, Bookmark(1000, 99, "other")) is False
    assert metadata["bookmarks"] is existing


def test_insert_bookmark_creates_missing_key_and_round_trips_through_parse() -> None:
    metadata: dict[str, Any] = {}

    assert insert_bookmark(metadata, Bookmark(1500, None, "named")) is True
    assert metadata["bookmarks"] == [{"time_ms": 1500, "frame_no": None, "name": "named"}]
    assert parse_bookmarks(metadata) == (Bookmark(1500, None, "named"),)


def test_delete_bookmark_removes_exactly_the_matching_time() -> None:
    metadata = empty_metadata()
    metadata["bookmarks"] = [
        {"time_ms": 1000, "frame_no": 10, "name": "a"},
        {"time_ms": 2000, "frame_no": 20, "name": "b"},
    ]

    assert delete_bookmark(metadata, 1000) is True
    assert metadata["bookmarks"] == [{"time_ms": 2000, "frame_no": 20, "name": "b"}]


def test_delete_bookmark_missing_time_or_key_returns_false_unmodified() -> None:
    metadata = empty_metadata()
    metadata["bookmarks"] = [{"time_ms": 1000, "frame_no": 10, "name": "a"}]
    existing = metadata["bookmarks"]

    assert delete_bookmark(metadata, 999) is False
    assert metadata["bookmarks"] is existing

    absent: dict[str, Any] = {}
    assert delete_bookmark(absent, 1000) is False
    assert absent == {}


def test_store_read_round_trip(store: MetadataStore, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")
    metadata = empty_metadata()
    metadata["title"] = "hello"

    size = store.write(f, metadata)
    stored = store.read(f)

    assert size > 0
    assert stored.byte_size == size
    assert stored.metadata == metadata


def test_store_read_allows_legacy_numpy_thumbnails_and_rejects_unsafe_globals(
    store: MetadataStore, tmp_path: Path
) -> None:
    import numpy as np

    f = _write_file(tmp_path / "video.mp4")
    metadata = empty_metadata()
    metadata["thumbnails"] = [(np.frombuffer(b"\xff\xd8\xff\xd9", dtype=np.uint8), 1, 100)]
    store.write(f, metadata)

    loaded = store.read(f).metadata
    assert bytes(loaded["thumbnails"][0][0]) == b"\xff\xd8\xff\xd9"

    class _Exploit:
        def __reduce__(self) -> tuple[Any, tuple[str]]:
            return (eval, ("1 + 1",))

    bad = _write_file(tmp_path / "bad.mp4")
    store.write(bad, {"title": _Exploit()})
    with pytest.raises(metadata_module.pickle.UnpicklingError, match="forbidden"):
        store.read(bad)


def test_store_read_absent_raises(store: MetadataStore, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")

    with pytest.raises(FileNotFoundError):
        store.read(f)


def test_store_read_or_empty_fallbacks(
    store: MetadataStore, storage: SidecarStorage, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write_file(tmp_path / "video.mp4")

    missing = store.read_or_empty(f)
    assert (missing.metadata, missing.byte_size) == (EMPTY_METADATA, 0)

    storage[(f, "meta")] = b"not a pickle"
    corrupt = store.read_or_empty(f)
    assert (corrupt.metadata, corrupt.byte_size) == (EMPTY_METADATA, 0)

    out = capsys.readouterr().out
    assert f"{f} does not have a magic sidecar" in out
    assert f"{f} does not have valid pickle data, using default" in out


def test_store_delete_files_skips_non_files_and_continues_on_error(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ok = _write_file(tmp_path / "ok.mp4")
    bad = _write_file(tmp_path / "bad.mp4")
    store.write(ok, {"title": "ok"})
    store.write(bad, {"title": "bad"})
    real_delete = store.delete

    def _delete(path: Path) -> None:
        if path == bad:
            raise OSError("boom")
        real_delete(path)

    monkeypatch.setattr(store, "delete", _delete)

    deleted = list(store.delete_files([ok, tmp_path / "missing.mp4", bad]))

    assert deleted == [ok]
    assert store.exists(ok) is False
    assert store.exists(bad) is True
    assert f"error: failed to delete metadata for {bad}: boom" in capsys.readouterr().out


def test_store_edit_skips_write_when_nothing_changed(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    bare = _write_file(tmp_path / "bare.mp4")
    store.write(f, {"actors": ["a"]})
    writes: list[Path] = []
    real_write = store.write

    def _write(path: Path, metadata: dict[str, Any]) -> int:
        writes.append(path)
        return real_write(path, metadata)

    monkeypatch.setattr(store, "write", _write)

    assert store.edit(f, BulkAction.ADD_ACTOR, "a") is None
    assert store.edit(bare, BulkAction.DEL_ACTOR, "a") is None
    assert writes == []
    assert store.exists(bare) is False


def test_store_edit_returns_none_when_load_fails(
    store: MetadataStore, storage: SidecarStorage, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    storage[(f, "meta")] = b""  # pickle.loads raises EOFError

    assert store.edit(f, BulkAction.ADD_ACTOR, "actor") is None
    # the failed load must not touch the existing (corrupt) payload
    assert storage[(f, "meta")] == b""
    assert f"error: failed to load metadata for {f}" in capsys.readouterr().out


def test_store_edit_returns_none_when_write_fails(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write_file(tmp_path / "video.mp4")

    def _fail(path: Path, metadata: dict[str, Any]) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(store, "write", _fail)

    assert store.edit(f, BulkAction.ADD_TAG, "x") is None
    assert f"error: failed to write metadata for {f}: disk full" in capsys.readouterr().out


def test_store_edit_returns_and_persists_updated_metadata(store: MetadataStore, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")

    result = store.edit(f, BulkAction.ADD_ACTOR, "actor")

    assert result is not None
    assert result["actors"] == ["actor"]
    assert store.read(f).metadata == result


def test_store_edit_files_skips_non_files(store: MetadataStore, tmp_path: Path) -> None:
    f = _write_file(tmp_path / "video.mp4")

    results = list(store.edit_files([f, tmp_path / "missing.mp4"], BulkAction.ADD_TAG, "Tag"))

    assert [p for p, _ in results] == [f]
    assert results[0][1]["tags"] == ["tag"]


def test_refresh_files_reports_metadata_and_progress(
    store: MetadataStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = _write_file(tmp_path / "one.mp4")
    two = _write_file(tmp_path / "two.mp4")
    store.write(one, {"title": "one"})

    seen: list[tuple[Path, dict[str, Any]]] = []
    progress: list[tuple[str, float]] = []

    refresh_files(
        (one, two),
        store,
        on_file=lambda path, metadata: seen.append((path, metadata)),
        on_progress=lambda info, value: progress.append((info, value)),
    )

    assert seen == [(one, {"title": "one"})]
    assert progress == [("[1 / 2] one.mp4", 0.5), ("[2 / 2] two.mp4", 1.0)]
    # an absent sidecar is skipped silently by refresh
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_refresh_files_logs_corrupt_sidecar_with_traceback(
    store: MetadataStore, storage: SidecarStorage, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _write_file(tmp_path / "video.mp4")
    storage[(f, "meta")] = b"not a pickle"

    seen: list[tuple[Path, dict[str, Any]]] = []
    progress: list[tuple[str, float]] = []

    refresh_files(
        (f,),
        store,
        on_file=lambda path, metadata: seen.append((path, metadata)),
        on_progress=lambda info, value: progress.append((info, value)),
    )

    assert seen == []
    assert progress == [("[1 / 1] video.mp4", 1.0)]
    captured = capsys.readouterr()
    assert f"error: failed to load metadata for {f}:" in captured.out
    assert "Traceback" in captured.err


def test_aggregate_files_counts_lowercased_and_skips(
    store: MetadataStore, storage: SidecarStorage, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = _write_file(tmp_path / "one.mp4")
    two = _write_file(tmp_path / "two.mp4")
    corrupt = _write_file(tmp_path / "corrupt.mp4")
    unreadable = _write_file(tmp_path / "unreadable.mp4")
    bare = _write_file(tmp_path / "bare.mp4")  # no sidecar
    directory = tmp_path / "dir.mp4"
    directory.mkdir()

    store.write(one, {"actors": ["Alice", "bob"], "tags": ["TAG"]})
    store.write(two, {"actors": ["alice"]})  # missing tags key
    storage[(corrupt, "meta")] = b"not a pickle"
    storage[(unreadable, "meta")] = b""  # pickle.loads raises EOFError

    seen: list[tuple[Path, dict[str, Any]]] = []

    actors, tags = aggregate_files(
        (one, directory, two, bare, corrupt, unreadable),
        store,
        on_file=lambda path, metadata: seen.append((path, metadata)),
        on_progress=lambda info, value: None,
    )

    assert actors == {"alice": 2, "bob": 1}
    assert tags == {"tag": 1}
    assert [p for p, _ in seen] == [one, two]

    out = capsys.readouterr().out
    assert f"failed to unpickle metadata for {corrupt}" in out
    assert f"failed to read metadata for {unreadable}" in out


def test_aggregate_files_emits_progress_per_file_at_zero_interval(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = [_write_file(tmp_path / f"{n}.mp4") for n in range(3)]
    ticks = iter(range(100))
    monkeypatch.setattr(metadata_module.time, "time", lambda: next(ticks))
    progress: list[tuple[str, float]] = []

    aggregate_files(
        files,
        store,
        on_file=lambda path, metadata: None,
        on_progress=lambda info, value: progress.append((info, value)),
        interval_s=0,
    )

    assert progress == [(f"[0/3] {files[0]}", 1 / 3), (f"[1/3] {files[1]}", 2 / 3), (f"[2/3] {files[2]}", 1.0)]


def test_generate_files_writes_on_success_and_reports_fractions(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    one = _write_file(tmp_path / "one.mp4")
    two = _write_file(tmp_path / "two.mp4")
    store.write(one, {"title": "keep"})

    def _fake_generate(path: Path, interval: str, height: str, extract_progress_func=None, resize_progress_func=None):
        if extract_progress_func is not None:
            extract_progress_func(0.5)
        if resize_progress_func is not None:
            resize_progress_func(0.5)
        return {"video_properties": {"dimensions": (1, 1), "duration": 2.0}}

    monkeypatch.setattr(metadata_module, "generate_video_metadata", _fake_generate)

    seen: list[tuple[Path, dict[str, Any]]] = []
    progress: list[tuple[str, float]] = []
    fractions: list[float] = []

    generate_files(
        (one, two),
        store,
        interval="-30",
        height="200",
        on_file=lambda path, metadata: seen.append((path, metadata)),
        on_progress=lambda info, value: progress.append((info, value)),
        on_fraction=fractions.append,
    )

    assert [p for p, _ in seen] == [one, two]
    assert seen[0][1]["title"] == "keep"
    assert seen[0][1]["video_properties"] == {"dimensions": (1, 1), "duration": 2.0}
    assert progress == [(f"[1 / 2] {one}", 0.0), (f"[2 / 2] {two}", 0.5)]
    assert fractions == [0.125, 0.375, 0.5, 0.625, 0.875, 1.0]
    assert store.read(one).metadata == seen[0][1]
    assert store.read(two).metadata == seen[1][1]


def test_generate_files_reports_failure_without_writing(
    store: MetadataStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = _write_file(tmp_path / "one.mp4")

    def _fail(path: Path, interval: str, height: str, extract_progress_func=None, resize_progress_func=None):
        raise RuntimeError("nope")

    monkeypatch.setattr(metadata_module, "generate_video_metadata", _fail)

    seen: list[tuple[Path, dict[str, Any]]] = []
    fractions: list[float] = []

    generate_files(
        (one,),
        store,
        interval="-30",
        height="200",
        on_file=lambda path, metadata: seen.append((path, metadata)),
        on_progress=lambda info, value: None,
        on_fraction=fractions.append,
    )

    assert [p for p, _ in seen] == [one]
    assert fractions == [1.0]
    assert store.exists(one) is False
    assert f"error: failed to generate metadata for {one}: nope" in capsys.readouterr().out


def test_generate_video_metadata_builds_schema_and_converts_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created: list[Any] = []

    class FakeThumbnailer:
        dimensions = (640, 480)
        duration = 3.14159

        def __init__(self, path: Path) -> None:
            self.path = path
            self.interval: float | None = None
            self.height: int | None = None
            created.append(self)

        def extract_frames(self, interval: float, progress_func: Any) -> None:
            self.interval = interval

        def resize_frames(self, resize_height: int, progress_func: Any) -> None:
            self.height = resize_height

        def gen_jpgs(self) -> list[str]:
            return ["a.jpg"]

    monkeypatch.setattr(metadata_module, "VideoThumbnailer", FakeThumbnailer)

    result = generate_video_metadata(tmp_path / "video.mp4", "-30", "200")

    assert result == {"video_properties": {"dimensions": (640, 480), "duration": 3.14}, "thumbnails": ["a.jpg"]}
    assert (created[0].path, created[0].interval, created[0].height) == (tmp_path / "video.mp4", -30.0, 200)
