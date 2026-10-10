import pickle
import time
import traceback
from collections.abc import Callable, Iterator, Sequence
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, NamedTuple, Protocol

from util.file.sidecar import MagicSidecar
from util.video import ProgressFunc, VideoThumbnailer

EMPTY_METADATA: Final[dict[str, Any]] = {
    "title": "",
    "video_properties": {"dimensions": (0, 0), "duration": 0},
    "actors": [],
    "tags": [],
    "thumbnails": [],
}


def empty_metadata() -> dict[str, Any]:
    """Return a deep copy of the empty metadata schema, safe for mutation."""
    return deepcopy(EMPTY_METADATA)


class BulkAction(StrEnum):
    ADD_ACTOR = "ADD_ACTOR"
    DEL_ACTOR = "DEL_ACTOR"
    ADD_TAG = "ADD_TAG"
    DEL_TAG = "DEL_TAG"


class StoredMetadata(NamedTuple):
    metadata: dict[str, Any]
    byte_size: int  # 0 when missing/unreadable fallback


class Sidecar(Protocol):
    """Structural type of a metadata sidecar, injectable so tests avoid platform storage."""

    @property
    def exists(self) -> bool: ...
    def read(self) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def delete(self) -> None: ...


class MetadataStore:
    """Persists pickled metadata in per-file sidecars under a single namespace."""

    _namespace: str
    _factory: Callable[[Path, str], Sidecar]

    def __init__(self, namespace: str, open_sidecar: Callable[[Path, str], Sidecar] = MagicSidecar) -> None:
        self._namespace = namespace
        self._factory = open_sidecar

    def _open(self, path: Path) -> Sidecar:
        return self._factory(path, self._namespace)

    def exists(self, path: Path) -> bool:
        return self._open(path).exists

    def read(self, path: Path) -> StoredMetadata:
        raw = self._open(path).read()
        return StoredMetadata(pickle.loads(raw), len(raw))

    def read_or_empty(self, path: Path) -> StoredMetadata:
        """Read metadata, falling back to an empty schema with byte_size 0 and logging the reason."""
        try:
            return self.read(path)
        except FileNotFoundError:
            print(f"{path} does not have a magic sidecar")
        except pickle.UnpicklingError:
            print(f"{path} does not have valid pickle data, using default")
        except Exception as ex:
            print(f"{path} failed to load metadata: {ex}")
        return StoredMetadata(empty_metadata(), 0)

    def write(self, path: Path, metadata: dict[str, Any]) -> int:
        """Write metadata to the sidecar and return the pickled payload size in bytes."""
        buf = pickle.dumps(metadata)
        self._open(path).write(buf)
        return len(buf)

    def delete(self, path: Path) -> None:
        self._open(path).delete()

    def delete_files(self, paths: Sequence[Path]) -> Iterator[Path]:
        """Delete sidecars, yielding each file whose sidecar was deleted."""
        for p in paths:
            if not p.is_file():
                continue

            try:
                self.delete(p)
            except Exception as ex:
                print(f"error: failed to delete metadata for {p}: {ex}")
                traceback.print_exc()
            else:
                yield p

    def edit(self, path: Path, action: BulkAction, value: str) -> dict[str, Any] | None:
        """Apply a bulk edit and write the sidecar unconditionally; None when the file is skipped."""
        metadata = empty_metadata()
        try:
            metadata = pickle.loads(self._open(path).read())
        except FileNotFoundError:
            pass
        except Exception as ex:
            print(f"error: failed to load metadata for {path}: {ex}")
            traceback.print_exc()
            return None

        apply_bulk_edit(metadata, action, value)

        try:
            print(f"updating metadata for {path}")
            self.write(path, metadata)
        except Exception as ex:
            print(f"error: failed to write metadata for {path}: {ex}")
            traceback.print_exc()
            return None
        else:
            return metadata

    def edit_files(self, paths: Sequence[Path], action: BulkAction, value: str) -> Iterator[tuple[Path, dict[str, Any]]]:
        for p in paths:
            if not p.is_file():
                continue

            metadata = self.edit(p, action, value)
            if metadata is not None:
                yield p, metadata


def apply_bulk_edit(metadata: dict[str, Any], action: BulkAction, value: str) -> bool:
    """Apply one bulk actor/tag action to metadata in place; returns whether anything changed."""
    actors = list(metadata.get("actors", []))
    tags = list(metadata.get("tags", []))

    match action:
        case BulkAction.ADD_ACTOR:
            if value in actors:
                return False
            actors.append(value)
            metadata["actors"] = sorted(actors)
        case BulkAction.DEL_ACTOR:
            if value not in actors:
                return False
            actors.remove(value)
            metadata["actors"] = actors
        case BulkAction.ADD_TAG:
            tag = value.lower()
            if tag in tags:
                return False
            tags.append(tag)
            metadata["tags"] = sorted(tags)
        case BulkAction.DEL_TAG:
            tag = value.lower()
            if tag not in tags:
                return False
            tags.remove(tag)
            metadata["tags"] = tags

    return True


def generate_video_metadata(
    path: Path,
    thumb_interval: str,
    thumb_height: str,
    extract_progress_func: ProgressFunc = lambda f: None,
    resize_progress_func: ProgressFunc = lambda f: None,
) -> dict[str, Any]:
    """Probe the video and build its metadata: dimensions, duration, thumbnails."""
    m = {}
    vt = VideoThumbnailer(path)
    m["video_properties"] = {}
    m["video_properties"]["dimensions"] = vt.dimensions
    m["video_properties"]["duration"] = round(vt.duration, 2) if vt.duration is not None else 0
    vt.extract_frames(interval=float(thumb_interval), progress_func=extract_progress_func)
    vt.resize_frames(resize_height=int(thumb_height), progress_func=resize_progress_func)
    jpgs = vt.gen_jpgs()
    if jpgs is not None:
        m["thumbnails"] = jpgs

    return m


def refresh_files(
    files: Sequence[Path],
    store: MetadataStore,
    *,
    on_file: Callable[[Path, dict[str, Any]], None],
    on_progress: Callable[[str, float], None],
) -> None:
    """Read each file's sidecar (skipping absent ones) and report metadata and progress."""
    total = len(files)
    for i, f in enumerate(files, start=1):
        on_progress(f"[{i} / {total}] {f.name}", i / total)
        try:
            stored = store.read(f)
        except FileNotFoundError:
            continue
        except Exception as ex:
            print(f"error: failed to load metadata for {f}: {ex}")
            traceback.print_exc()
        else:
            on_file(f, stored.metadata)


def aggregate_files(
    files: Sequence[Path],
    store: MetadataStore,
    *,
    on_file: Callable[[Path, dict[str, Any]], None],
    on_progress: Callable[[str, float], None],
    interval_s: float = 0.05,
) -> tuple[dict[str, int], dict[str, int]]:
    """Read sidecars and count lowercased actor/tag occurrences, with throttled progress."""
    actors: dict[str, int] = {}
    tags: dict[str, int] = {}
    total = len(files)
    last_time = time.time()

    def _incr(totals: dict[str, int], keys: Sequence[str]) -> None:
        for k in keys:
            k = k.lower()
            if k not in totals:
                totals[k] = 1
            else:
                totals[k] += 1

    for c, path in enumerate(files):
        if time.time() > last_time + interval_s:
            on_progress(f"[{c}/{total}] {path}", (c + 1) / total)
            last_time = time.time()

        if not path.is_file():
            continue

        if not store.exists(path):
            continue

        try:
            stored = store.read(path)
        except pickle.UnpicklingError:
            print(f"failed to unpickle metadata for {path}")
        except Exception:
            print(f"failed to read metadata for {path}")
        else:
            on_file(path, stored.metadata)
            _incr(actors, stored.metadata.get("actors", []))
            _incr(tags, stored.metadata.get("tags", []))

    return actors, tags


def generate_files(
    files: Sequence[Path],
    store: MetadataStore,
    *,
    interval: str,
    height: str,
    on_file: Callable[[Path, dict[str, Any]], None],
    on_progress: Callable[[str, float], None],
    on_fraction: Callable[[float], None],
) -> None:
    """Generate video metadata for files, writing sidecars only on success.

    Per-file metadata and terminal progress are reported even when generation fails.
    """
    total = len(files)
    for c, f in enumerate(files):  # c is the number of files fully processed before this one
        metadata = store.read_or_empty(f).metadata

        on_progress(f"[{c + 1} / {total}] {f}", c / total)

        # the callbacks are invoked synchronously by generate_video_metadata within this iteration;
        # c is bound through the default argument to keep the per-file progress math
        def _extract_progress(fraction: float, c: int = c) -> None:
            on_fraction(c / total + (0.5 / total) * fraction)

        def _resize_progress(fraction: float, c: int = c) -> None:
            on_fraction(c / total + (0.5 * fraction + 0.5) / total)

        try:
            metadata |= generate_video_metadata(
                f, interval, height, extract_progress_func=_extract_progress, resize_progress_func=_resize_progress
            )
            store.write(f, metadata)
        except Exception as ex:
            print(f"error: failed to generate metadata for {f}: {ex}")
            traceback.print_exc()
        finally:
            on_file(f, metadata)
            on_fraction((c + 1) / total)
